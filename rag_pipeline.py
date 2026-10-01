"""
rag_pipeline.py

RAG(検索拡張生成)のコア処理をまとめたファイルです。
5つのステップがそのまま関数になっています。
"""

import os
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
# Claude(有料API)版。無料プランに切り替えるため一時的にコメントアウト。戻す場合はこちらを使う。
# from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.chains import RetrievalQA


def load_pdf(pdf_path: str):
    """
    ステップ1: PDFを読み込んでテキストに変換する
    """
    loader = PyPDFLoader(pdf_path)
    documents = loader.load()
    print(f"[ステップ1] PDFを読み込みました。ページ数: {len(documents)}")
    return documents


def split_into_chunks(documents, chunk_size: int = 500, chunk_overlap: int = 50):
    """
    ステップ2: テキストを小さな断片(チャンク)に分割する

    chunk_size: 1つの断片の文字数の目安
    chunk_overlap: 断片同士を少し重複させることで、文脈の切れ目で情報が失われるのを防ぐ
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    chunks = splitter.split_documents(documents)
    print(f"[ステップ2] {len(chunks)} 個のチャンクに分割しました。")
    return chunks


def build_vector_store(chunks, persist_directory: str = "./chroma_db"):
    """
    ステップ3: 各チャンクをベクトル化し、ベクトルDB(Chroma)に保存する

    HuggingFaceEmbeddings はローカルで無料で動く埋め込みモデルなので、
    埋め込み部分は追加のAPIキー不要です。
    """
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

    # 既に永続化済みのベクトルDBがあれば、再埋め込みせずそのまま読み込む
    if os.path.exists(persist_directory) and os.listdir(persist_directory):
        vector_store = Chroma(persist_directory=persist_directory, embedding_function=embeddings)
        print(f"[ステップ3] 既存のベクトルDBを読み込みました。保存先: {persist_directory}")
    else:
        vector_store = Chroma.from_documents(
            documents=chunks,
            embedding=embeddings,
            persist_directory=persist_directory,
        )
        print(f"[ステップ3] ベクトルDBを作成しました。保存先: {persist_directory}")
    return vector_store


def build_qa_chain(vector_store, model_name: str = "gemini-3.8-flash"):
    """
    ステップ4+5: 質問に対して関連チャンクを検索し(retriever)、
    LLMに渡して回答を生成する(QAチェーン)仕組みを組み立てる
    """
    # Claude(有料API)版。無料プランに切り替えるため一時的にコメントアウト。戻す場合はこちらを使う。
    # llm = ChatAnthropic(model=model_name, temperature=0)
    llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)

    # retriever: 質問に関連するチャンクをベクトルDBから検索する役割
    retriever = vector_store.as_retriever(search_kwargs={"k": 3})  # 上位3件を取得

    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,
        retriever=retriever,
        return_source_documents=True,  # 回答の根拠となった原文も一緒に返す
    )
    print("[ステップ4-5] 質問応答チェーンを構築しました。")
    return qa_chain


def ask_question(qa_chain, question: str):
    """
    実際に質問を投げて回答を得る
    """
    result = qa_chain.invoke({"query": question})
    return result["result"], result["source_documents"]
