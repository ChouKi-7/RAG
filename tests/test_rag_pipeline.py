"""
test_rag_pipeline.py

rag_pipeline.py のうち、ネットワーク接続やAPIキーを必要としない
「純粋な」関数だけを対象にした単体テスト。
実行方法: pytest
"""

from langchain_core.documents import Document

from rag_pipeline import (
    NOT_FOUND_MESSAGE,
    _RELEVANCE_THRESHOLDS,
    _build_prompt,
    split_into_chunks,
)


def _make_document(text: str) -> Document:
    return Document(page_content=text, metadata={"page": 0})


class TestSplitIntoChunks:
    def test_long_text_is_split_into_multiple_chunks(self):
        long_text = "あ" * 1200
        chunks = split_into_chunks([_make_document(long_text)], chunk_size=500, chunk_overlap=50)
        assert len(chunks) > 1

    def test_short_text_stays_as_single_chunk(self):
        short_text = "これは短いテキストです。"
        chunks = split_into_chunks([_make_document(short_text)], chunk_size=500, chunk_overlap=50)
        assert len(chunks) == 1
        assert chunks[0].page_content == short_text

    def test_each_chunk_does_not_greatly_exceed_chunk_size(self):
        long_text = "あ" * 2000
        chunks = split_into_chunks([_make_document(long_text)], chunk_size=500, chunk_overlap=50)
        for chunk in chunks:
            # RecursiveCharacterTextSplitter は厳密な固定長ではないため、
            # 多少の超過は許容しつつ、極端に大きくなっていないことだけ確認する
            assert len(chunk.page_content) <= 500 * 1.5

    def test_custom_chunk_size_is_respected(self):
        long_text = "い" * 300
        chunks = split_into_chunks([_make_document(long_text)], chunk_size=100, chunk_overlap=10)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk.page_content) <= 100 * 1.5

    def test_multiple_documents_are_all_processed(self):
        docs = [_make_document("う" * 600), _make_document("え" * 600)]
        chunks = split_into_chunks(docs, chunk_size=500, chunk_overlap=50)
        # 2つの文書それぞれが複数チャンクに分かれるはず
        assert len(chunks) >= 2


class TestRelevanceThresholds:
    def test_has_default_entries_for_both_providers(self):
        assert "huggingface" in _RELEVANCE_THRESHOLDS
        assert "google" in _RELEVANCE_THRESHOLDS

    def test_threshold_values_are_positive_numbers(self):
        for value in _RELEVANCE_THRESHOLDS.values():
            assert isinstance(value, (int, float))
            assert value > 0


class TestBuildPrompt:
    def test_prompt_contains_question_and_context(self):
        docs = [_make_document("張琪は5年のバックエンド開発経験があります。")]
        prompt = _build_prompt(docs, "経験年数は何年ですか？")
        assert "経験年数は何年ですか？" in prompt
        assert "張琪は5年のバックエンド開発経験があります。" in prompt

    def test_prompt_joins_multiple_docs_with_blank_line(self):
        docs = [_make_document("第1段落"), _make_document("第2段落")]
        prompt = _build_prompt(docs, "質問")
        assert "第1段落\n\n第2段落" in prompt


def test_not_found_message_is_non_empty():
    assert isinstance(NOT_FOUND_MESSAGE, str)
    assert len(NOT_FOUND_MESSAGE) > 0
