"""
rag_pipeline.py

RAG(検索拡張生成)のコア処理をまとめたファイルです。
5つのステップがそのまま関数になっています。
"""

import logging
import os
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
# Claude(有料API)版。無料プランに切り替えるため一時的にコメントアウト。戻す場合はこちらを使う。
# from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)

# 関連度のしきい値(Chromaのデフォルト距離=L2、小さいほど類似)。
# embeddingモデルによって距離のスケールが大きく異なるため provider ごとに用意している。
# 実測値(documents/ のサンプルPDFで検証): huggingface は関連16〜18/無関係29〜33、google は関連0.69〜0.76/無関係0.88〜0.92。
# 別のPDF/質問だと最適値は変わるので、環境変数 RELEVANCE_SCORE_THRESHOLD で上書き可能にしてある。
_RELEVANCE_THRESHOLDS = {
    "huggingface": 22.0,
    "google": 0.8,
}


def load_pdf(pdf_path: str):
    """
    ステップ1: PDFを読み込んでテキストに変換する
    """
    loader = PyPDFLoader(pdf_path)
    documents = loader.load()
    logger.info("[ステップ1] PDFを読み込みました。ページ数: %d", len(documents))
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
    logger.info("[ステップ2] %d 個のチャンクに分割しました。", len(chunks))
    return chunks


def get_embeddings():
    """
    埋め込みモデルを返す。

    環境変数 EMBEDDING_PROVIDER で切り替え可能:
      - "huggingface"(デフォルト): ローカルで無料で動く多言語モデル。APIキー不要だが重い(PyTorchが必要)
      - "google": Gemini の埋め込みAPI。軽量なのでクラウド(Azure等)へのデプロイ向け
    """
    provider = os.getenv("EMBEDDING_PROVIDER", "huggingface").lower()
    if provider == "google":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        model = os.getenv("GOOGLE_EMBEDDING_MODEL", "models/gemini-embedding-001")
        return GoogleGenerativeAIEmbeddings(model=model)

    from langchain_huggingface import HuggingFaceEmbeddings
    return HuggingFaceEmbeddings(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")


def build_vector_store(chunks, persist_directory: str | None = "./chroma_db"):
    """
    ステップ3: 各チャンクをベクトル化し、ベクトルDB(Chroma)に保存する

    persist_directory=None の場合はメモリ上のみ(Webアプリでアップロードしたファイル用)。
    """
    embeddings = get_embeddings()

    if persist_directory is None:
        vector_store = Chroma.from_documents(documents=chunks, embedding=embeddings)
        logger.info("[ステップ3] ベクトルDBをメモリ上に作成しました。")
        return vector_store

    # 既に永続化済みのベクトルDBがあれば、再埋め込みせずそのまま読み込む
    if os.path.exists(persist_directory) and os.listdir(persist_directory):
        vector_store = Chroma(persist_directory=persist_directory, embedding_function=embeddings)
        logger.info("[ステップ3] 既存のベクトルDBを読み込みました。保存先: %s", persist_directory)
    else:
        vector_store = Chroma.from_documents(
            documents=chunks,
            embedding=embeddings,
            persist_directory=persist_directory,
        )
        logger.info("[ステップ3] ベクトルDBを作成しました。保存先: %s", persist_directory)
    return vector_store


def build_qa_chain(vector_store, model_name: str = "gemini-3.1-flash-lite"):
    """
    ステップ4+5: 質問に対して関連チャンクを検索し、
    関連度が低すぎる場合は検索結果を使わず「見つからなかった」と答える
    QAチェーン(に相当する設定一式)を組み立てる
    """
    # Claude(有料API)版。無料プランに切り替えるため一時的にコメントアウト。戻す場合はこちらを使う。
    # llm = ChatAnthropic(model=model_name, temperature=0)
    llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)

    provider = os.getenv("EMBEDDING_PROVIDER", "huggingface").lower()
    default_threshold = _RELEVANCE_THRESHOLDS.get(provider, 22.0)
    score_threshold = float(os.getenv("RELEVANCE_SCORE_THRESHOLD", default_threshold))

    logger.info("[ステップ4-5] 質問応答チェーンを構築しました。(関連度しきい値: %s)", score_threshold)
    return {"llm": llm, "vector_store": vector_store, "score_threshold": score_threshold}


NOT_FOUND_MESSAGE = "文書内に関連する内容が見つかりませんでした。"


def _retrieve_relevant_docs(qa_chain, question: str, k: int):
    """
    検索して、関連度のしきい値を満たすチャンクだけを返す共通処理。
    (ask_question / ask_question_stream の両方から呼ばれる)
    """
    vector_store = qa_chain["vector_store"]
    score_threshold = qa_chain["score_threshold"]

    results = vector_store.similarity_search_with_score(question, k=k)
    relevant_docs = [doc for doc, score in results if score <= score_threshold]

    if not relevant_docs:
        logger.warning(
            "関連するチャンクが見つかりませんでした。question=%r, しきい値=%s, 検索結果のスコア=%s",
            question, score_threshold, [score for _, score in results],
        )
    return relevant_docs


def _build_prompt(relevant_docs, question: str) -> str:
    context = "\n\n".join(doc.page_content for doc in relevant_docs)
    return (
        "以下はPDFから抽出した文書の抜粋です。この抜粋だけを根拠にして質問に答えてください。\n"
        "抜粋の中に答えがない場合は「わかりません」と答えてください。\n\n"
        f"文書の抜粋:\n{context}\n\n質問: {question}"
    )


def ask_question(qa_chain, question: str, k: int = 3):
    """
    実際に質問を投げて回答を得る(一括取得版。CLI版 main.py で使用)。

    検索結果の関連度(距離)がしきい値を超えるもの、つまり実質的に
    無関係なチャンクは除外し、1件も残らない場合はLLMを呼ばずに
    「見つからなかった」と回答する(関連性のない内容をもとにした
    でっち上げ回答を防ぐため)。
    """
    relevant_docs = _retrieve_relevant_docs(qa_chain, question, k)

    if not relevant_docs:
        return NOT_FOUND_MESSAGE, []

    prompt = _build_prompt(relevant_docs, question)
    response = qa_chain["llm"].invoke(prompt)
    return response.content, relevant_docs


def ask_question_stream(qa_chain, question: str, k: int = 3):
    """
    実際に質問を投げて回答を得る(ストリーミング版。Web版 app.py で使用)。

    戻り値は (テキストチャンクを順に返すジェネレータ, 参照ドキュメントのリスト)。
    回答の生成が始まる前に検索・関連度判定を済ませておくので、
    「見つからなかった」場合はLLMを一切呼ばない。
    """
    relevant_docs = _retrieve_relevant_docs(qa_chain, question, k)

    if not relevant_docs:
        def _not_found():
            yield NOT_FOUND_MESSAGE
        return _not_found(), []

    prompt = _build_prompt(relevant_docs, question)

    def _stream():
        for chunk in qa_chain["llm"].stream(prompt):
            if chunk.content:
                yield chunk.content

    return _stream(), relevant_docs
