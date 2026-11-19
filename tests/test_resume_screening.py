"""
test_resume_screening.py

resume_screening.py のうち、LLM/ネットワークを必要としない「純粋な」ロジック
(filter_by_structured_criteria)だけを対象にした単体テスト。
実行方法: pytest
"""

from resume_screening import (
    CandidateProfile,
    ScreeningQuery,
    SkillExperience,
    _skill_matches,
    filter_by_structured_criteria,
)


def _make_record(name: str, skills: list[tuple[str, float]], has_led_project: bool = False) -> dict:
    profile = CandidateProfile(
        candidate_name=name,
        skills=[SkillExperience(skill=skill, years=years) for skill, years in skills],
        has_led_project=has_led_project,
    )
    return {"source": f"{name}.pdf", "profile": profile, "full_text": ""}


class FakeEmbeddings:
    """実際のembeddingモデルを読み込まずにテストするための偽物。
    文字列→ベクトルの対応表を手で用意し、コサイン類似度を自分で制御できるようにする。
    embed_documents()が呼ばれた回数も数える(境界マッチングで既に一致したときは
    embeddingを計算しない、という仕様を検証するため)。
    """

    def __init__(self, vectors: dict[str, list[float]]):
        self.vectors = vectors
        self.call_count = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        return [self.vectors[t] for t in texts]


class TestFilterByStructuredCriteria:
    def test_no_criteria_returns_all_records(self):
        records = [_make_record("A", [("Java", 3)]), _make_record("B", [("Python", 1)])]
        query = ScreeningQuery()
        assert filter_by_structured_criteria(records, query) == records

    def test_filters_by_skill_name(self):
        records = [_make_record("A", [("Java", 3)]), _make_record("B", [("Python", 1)])]
        query = ScreeningQuery(skill="Java")
        result = filter_by_structured_criteria(records, query)
        assert [r["profile"].candidate_name for r in result] == ["A"]

    def test_skill_match_is_case_insensitive(self):
        records = [_make_record("A", [("Java", 2)])]
        query = ScreeningQuery(skill="java")
        result = filter_by_structured_criteria(records, query)
        assert len(result) == 1

    def test_java_does_not_falsely_match_javascript(self):
        # bug-log #14: 単純な部分文字列一致だと "java" が "JavaScript" にも
        # 一致してしまっていた。単語境界を見て区別する。
        records = [_make_record("A", [("JavaScript", 5)])]
        query = ScreeningQuery(skill="Java")
        assert filter_by_structured_criteria(records, query) == []

    def test_skill_matches_whole_word_within_compound_skill_name(self):
        assert _skill_matches("Spring", "Spring Boot") is True
        assert _skill_matches("Java", "Java（Spring Boot）") is True

    def test_skill_matches_handles_symbol_only_boundaries(self):
        # "C#"/".NET" のような記号で始まる/終わるスキル名は \b が機能しないため、
        # 境界条件を付けない特別扱いが必要(付けると自分自身にすら一致しなくなる)。
        assert _skill_matches("C#", "C#") is True
        assert _skill_matches(".NET", ".NET Framework") is True

    def test_excludes_candidate_without_the_skill(self):
        records = [_make_record("A", [("C#", 5)])]
        query = ScreeningQuery(skill="Java")
        assert filter_by_structured_criteria(records, query) == []

    def test_filters_by_min_years_on_matching_skill(self):
        records = [
            _make_record("A", [("Java", 5)]),
            _make_record("B", [("Java", 2)]),
        ]
        query = ScreeningQuery(skill="Java", min_years=3)
        result = filter_by_structured_criteria(records, query)
        assert [r["profile"].candidate_name for r in result] == ["A"]

    def test_min_years_without_skill_uses_max_across_skills(self):
        records = [
            _make_record("A", [("Java", 1), ("Python", 6)]),
            _make_record("B", [("Java", 1), ("Python", 1)]),
        ]
        query = ScreeningQuery(min_years=5)
        result = filter_by_structured_criteria(records, query)
        assert [r["profile"].candidate_name for r in result] == ["A"]

    def test_candidate_with_no_skills_is_excluded_by_min_years(self):
        records = [_make_record("A", [])]
        query = ScreeningQuery(min_years=1)
        assert filter_by_structured_criteria(records, query) == []


class TestSkillMatchesEmbeddingFallback:
    """D17: 単語境界マッチングで一致しない場合、embeddingの類似度で同義語を拾う。"""

    def test_falls_back_to_embedding_when_word_boundary_fails(self):
        embeddings = FakeEmbeddings({"ML": [1.0, 0.0], "機械学習": [1.0, 0.0]})  # 同じ方向=類似度1.0
        assert _skill_matches("ML", "機械学習", embeddings) is True

    def test_embedding_below_threshold_does_not_match(self):
        embeddings = FakeEmbeddings({"Ruby": [1.0, 0.0], "機械学習": [0.0, 1.0]})  # 直交=類似度0.0
        assert _skill_matches("Ruby", "機械学習", embeddings) is False

    def test_embedding_not_computed_when_word_boundary_already_matches(self):
        # "Java"は単語境界マッチングだけで一致するはずなので、embeddingの計算(API/モデル呼び出し)
        # までは行わない。無駄なコストを避けるための仕様。
        embeddings = FakeEmbeddings({})
        assert _skill_matches("Java", "Java", embeddings) is True
        assert embeddings.call_count == 0

    def test_no_embeddings_means_no_fallback(self):
        # embeddings=None(デフォルト)のときは、従来通り単語境界マッチングのみ。
        assert _skill_matches("ML", "機械学習", embeddings=None) is False

    def test_filter_by_structured_criteria_uses_embeddings_when_provided(self):
        records = [_make_record("A", [("機械学習", 3)])]
        query = ScreeningQuery(skill="ML")
        embeddings = FakeEmbeddings({"ML": [1.0, 0.0], "機械学習": [1.0, 0.0]})
        assert filter_by_structured_criteria(records, query, embeddings) == records
        assert filter_by_structured_criteria(records, query) == []  # embeddings省略時は従来通り
