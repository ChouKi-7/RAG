"""
test_resume_screening.py

resume_screening.py のうち、LLM/ネットワークを必要としない「純粋な」ロジック
(filter_by_structured_criteria)だけを対象にした単体テスト。
実行方法: pytest
"""

from resume_screening import CandidateProfile, ScreeningQuery, SkillExperience, filter_by_structured_criteria


def _make_record(name: str, skills: list[tuple[str, float]], has_led_project: bool = False) -> dict:
    profile = CandidateProfile(
        candidate_name=name,
        skills=[SkillExperience(skill=skill, years=years) for skill, years in skills],
        has_led_project=has_led_project,
    )
    return {"source": f"{name}.pdf", "profile": profile, "full_text": ""}


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

    def test_skill_match_is_case_insensitive_and_substring(self):
        records = [_make_record("A", [("JavaScript", 2)])]
        query = ScreeningQuery(skill="java")
        result = filter_by_structured_criteria(records, query)
        # "java" は "JavaScript" にも部分一致するため、これは仕様上の既知の挙動
        assert len(result) == 1

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
