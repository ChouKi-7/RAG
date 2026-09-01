"""
main.py

このファイルを実行すると、documents/フォルダ内のPDFに対して
対話形式で質問できるようになります。

実行方法:
    python main.py
"""

import os
import glob
from dotenv import load_dotenv
from rag_pipeline import (
    load_pdf,
    split_into_chunks,
    build_vector_store,
    build_qa_chain,
    ask_question,
)

load_dotenv()


def find_pdf_in_documents():
    pdf_files = glob.glob("documents/*.pdf")
    if not pdf_files:
        print("エラー: documents/ フォルダにPDFファイルが見つかりません。")
        print("質問したいPDFを documents/ フォルダに入れてから再実行してください。")
        exit(1)
    return pdf_files[0]


def main():
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("エラー: .env ファイルに ANTHROPIC_API_KEY を設定してください。")
        exit(1)

    pdf_path = find_pdf_in_documents()
    print(f"読み込むPDF: {pdf_path}\n")

    # RAGの5ステップを順番に実行
    documents = load_pdf(pdf_path)
    chunks = split_into_chunks(documents)
    vector_store = build_vector_store(chunks)
    qa_chain = build_qa_chain(vector_store)

    print("\n準備完了！このPDFについて質問できます。('exit'で終了)\n")

    while True:
        question = input("質問: ")
        if question.strip().lower() in ("exit", "quit", "終了"):
            print("終了します。")
            break

        answer, sources = ask_question(qa_chain, question)
        print(f"\n回答: {answer}\n")
        print(f"(参照した箇所: {len(sources)}件のチャンクを使用)\n")


if __name__ == "__main__":
    main()
