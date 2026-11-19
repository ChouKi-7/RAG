"""
resume_screening_app.py

v2機能のWeb画面(Streamlit)。
複数の履歴書(PDF)をアップロードし、自然言語の条件で候補者を絞り込める。

ローカル実行: streamlit run resume_screening_app.py
"""

import logging
import os
import tempfile

import streamlit as st
from dotenv import load_dotenv

from rag_pipeline import get_embeddings, get_llm
from resume_screening import build_candidate_profiles, screen_candidates

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

st.set_page_config(page_title="複数履歴書スクリーニング (v2)", page_icon="🔍")
st.title("🔍 複数履歴書スクリーニングアプリ")
st.caption("複数の履歴書(PDF)をアップロードし、「Pythonを3年以上学び、プロジェクトを独立して担当できる人」のように条件を日本語で入力すると、該当する候補者を探します。")

# APP_PASSWORD が設定されている場合のみパスワードを要求する(v1のapp.pyと同じ仕組み)
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

llm = get_llm()
embeddings = get_embeddings()

# 構造化抽出のキャッシュは、このブラウザセッション専用の一時ファイルに分離する。
# resume_screening.py のデフォルトキャッシュ(resume_profiles_cache.json)を
# そのまま全セッションで共有すると、v1のbug-log #8(Chromaのcollection_name未指定で
# 別ユーザーの文書内容が混ざった実害)と同じ構図のリスクになる。1セッション=1
# キャッシュファイルにして、アップロードした履歴書の内容が他の訪問者に漏れないようにする。
if "cache_path" not in st.session_state:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
    tmp.write(b"{}")
    tmp.close()
    st.session_state.cache_path = tmp.name

uploaded_files = st.file_uploader(
    "履歴書PDFを選択(複数可)", type="pdf", accept_multiple_files=True,
)

uploaded_names = tuple(sorted(f.name for f in uploaded_files)) if uploaded_files else ()

if uploaded_files and st.session_state.get("uploaded_names") != uploaded_names:
    with st.spinner(f"{len(uploaded_files)}件の履歴書を解析しています(初回はLLM呼び出しのため時間がかかります)..."):
        tmp_paths = []
        try:
            for f in uploaded_files:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(f.getvalue())
                    tmp_paths.append(tmp.name)

            records = build_candidate_profiles(tmp_paths, llm, cache_path=st.session_state.cache_path)
            st.session_state.records = records
            st.session_state.uploaded_names = uploaded_names
            st.session_state.messages = []
        except Exception:
            logger.exception("履歴書の処理中にエラーが発生しました。files=%r", uploaded_names)
            st.error("履歴書の処理中にエラーが発生しました。しばらくしてから再度お試しください。")
            st.session_state.pop("records", None)
            st.session_state.pop("uploaded_names", None)
        finally:
            for path in tmp_paths:
                os.remove(path)

if "records" in st.session_state:
    records = st.session_state.records
    st.success(f"準備完了: {len(records)}件の履歴書を読み込みました。")
    with st.expander("読み込んだ候補者一覧"):
        for r in records:
            profile = r["profile"]
            skills_str = "、".join(f"{s.skill}({s.years}年)" for s in profile.skills)
            st.markdown(f"**{profile.candidate_name}** — {skills_str}")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    question = st.chat_input("探したい人材の条件を入力してください")
    if question:
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            try:
                with st.spinner("条件を解析し、候補者を絞り込んでいます..."):
                    query, results = screen_candidates(records, question, llm, embeddings)
            except Exception:
                logger.exception("スクリーニング中にエラーが発生しました。question=%r", question)
                st.error("スクリーニング中にエラーが発生しました。しばらくしてから再度お試しください。")
                results = None
            else:
                st.caption(
                    f"解析した条件: スキル={query.skill or 'なし'} / "
                    f"最低年数={query.min_years if query.min_years is not None else 'なし'} / "
                    f"定性条件={query.qualitative_criteria or 'なし'}"
                )
                if not results:
                    st.markdown("条件に合致する候補者は見つかりませんでした。")
                else:
                    st.markdown(f"**{len(results)}名**が条件に合致しました:")
                    for r in results:
                        profile = r["profile"]
                        judgement = r["judgement"]
                        skills_str = "、".join(f"{s.skill}({s.years}年)" for s in profile.skills)
                        with st.container(border=True):
                            st.markdown(f"**● {profile.candidate_name}**")
                            st.caption(f"スキル: {skills_str}")
                            if judgement is not None:
                                st.markdown(f"判定理由: {judgement.reason}")
                                if judgement.evidence_quote:
                                    st.caption(f"根拠: 「{judgement.evidence_quote}」")

        if results is not None:
            summary = f"{len(results)}名が条件に合致しました。" if results else "条件に合致する候補者は見つかりませんでした。"
            st.session_state.messages.append({"role": "assistant", "content": summary})
