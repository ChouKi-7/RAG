"""
app.py

RAGアプリのWeb画面(Streamlit)。
PDFをアップロードして、その内容について質問できます。

ローカル実行: streamlit run app.py
"""

import os
import tempfile

import streamlit as st
from dotenv import load_dotenv

from rag_pipeline import load_pdf, split_into_chunks, build_vector_store, build_qa_chain, ask_question

load_dotenv()

st.set_page_config(page_title="PDF質問応答 (RAG)", page_icon="📄")
st.title("📄 PDF質問応答アプリ (RAG)")
st.caption("PDFをアップロードすると、その内容についてAIに質問できます。")

# APP_PASSWORD が設定されている場合のみパスワードを要求する(未設定ならローカル開発用に素通り)
app_password = os.getenv("APP_PASSWORD")
if app_password and not st.session_state.get("authenticated"):
    entered = st.text_input("パスワードを入力してください", type="password")
    if entered != app_password:
        if entered:
            st.error("パスワードが違います。")
        st.stop()
    st.session_state.authenticated = True

if not os.getenv("GOOGLE_API_KEY"):
    st.error("環境変数 GOOGLE_API_KEY が設定されていません。")
    st.stop()

uploaded = st.file_uploader("PDFファイルを選択", type="pdf")

if uploaded is not None and st.session_state.get("file_name") != uploaded.name:
    with st.spinner("PDFを読み込み、ベクトルDBを作成しています..."):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = tmp.name
        try:
            documents = load_pdf(tmp_path)
            chunks = split_into_chunks(documents)
            vector_store = build_vector_store(chunks, persist_directory=None)
            st.session_state.qa_chain = build_qa_chain(vector_store)
            st.session_state.file_name = uploaded.name
            st.session_state.messages = []
        except Exception:
            st.error("PDFの処理中にエラーが発生しました。しばらくしてから再度お試しください。")
            st.session_state.pop("qa_chain", None)
            st.session_state.pop("file_name", None)
            chunks = None
        finally:
            os.remove(tmp_path)
    if chunks is not None:
        st.success(f"準備完了: {uploaded.name}（{len(chunks)}チャンク）")

if "qa_chain" in st.session_state:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    question = st.chat_input("PDFについて質問してください")
    if question:
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            try:
                with st.spinner("回答を生成しています..."):
                    answer, sources = ask_question(st.session_state.qa_chain, question)
            except Exception:
                answer = "回答の生成中にエラーが発生しました。しばらくしてから再度お試しください。"
                st.error(answer)
                sources = []
            else:
                st.markdown(answer)
                with st.expander(f"参照した箇所（{len(sources)}件）"):
                    for i, doc in enumerate(sources, 1):
                        page = doc.metadata.get("page")
                        st.markdown(f"**{i}.** p.{page + 1 if page is not None else '?'}")
                        st.text(doc.page_content[:300])
        st.session_state.messages.append({"role": "assistant", "content": answer})
