"""
resume_screening.py

v2機能: 複数の履歴書(PDF)の中から、ユーザーの自然言語の条件に合う人を探す。

単純な類似度検索(v1の仕組み)だけでは、「Javaを5年学び、プロジェクトを独立して
担当できる人を探す」のような「定量条件+定性条件が混ざった、網羅性が必要な質問」
には対応できない(詳細は docs/design-notes.md の D12、D13 を参照)。

そのため、このファイルは以下の3段階のパイプラインで実装している:

  1. 索引作成: 履歴書ごとにLLMで構造化プロフィール(スキル・経験年数・プロジェクト
     主導経験の有無とその根拠)を抽出する(extract_candidate_profile)
  2. クエリ理解: ユーザーの自然言語の質問を、構造化条件(スキル・最低年数)と
     定性条件(自由文)に分解する(parse_query)
  3. 絞り込み: 構造化条件でまず機械的にフィルタし(filter_by_structured_criteria、
     LLMを呼ばない純粋なロジック)、残った候補者だけを定性条件についてLLMに
     1人ずつ原文根拠つきで判定させる(judge_qualitative)

実行方法: python resume_screening.py
"""

import glob
import hashlib
import json
import logging
import os
import re
import time

from dotenv import load_dotenv
from google.api_core.exceptions import ResourceExhausted
from pydantic import BaseModel, Field

from rag_pipeline import get_llm, load_pdf

logger = logging.getLogger(__name__)

CACHE_PATH = "resume_profiles_cache.json"

# gemini-3.1-flash-lite の無料枠は「1分あたり15リクエスト」(2026-11-02実測)。
# 候補者数が多く、構造化条件での絞り込みが効かない質問(スキル・年数を指定しない
# 定性条件だけの質問)だと、judge_qualitative() が候補者全員分=十数回を
# 一気に連続で呼ぶことになり、このレート制限に実際にぶつかる(docs/bug-log.md #13)。
_RATE_LIMIT_RETRIES = 3
_RATE_LIMIT_WAIT_SECONDS = 20


def _invoke_structured(llm, schema: type[BaseModel], prompt: str) -> BaseModel:
    """llm.with_structured_output() を叩くが、結果がNoneの場合はフォールバックする。

    実測した問題: gemini-3.1-flash-lite は、プロンプトが長い(職務経歴書全文のように
    情報量が多い)場合、関数呼び出し(tool call)としてではなく、```json ``` で
    囲んだ通常のテキスト回答としてJSONを返すことがある。この場合
    with_structured_output() の戻り値はNoneになり、内容自体は正しいJSONでも
    失われてしまう。そのため include_raw=True で元の応答も取得しておき、
    parsedがNoneだった場合はテキストからJSONを抜き出して自前でパースする。

    また、1分あたりのリクエスト数制限(429 ResourceExhausted)に当たった場合は、
    一定時間待ってから数回までリトライする(候補者数が多いと実際に起きるため)。
    """
    structured_llm = llm.with_structured_output(schema, include_raw=True)

    for attempt in range(_RATE_LIMIT_RETRIES + 1):
        try:
            result = structured_llm.invoke(prompt)
            break
        except ResourceExhausted:
            if attempt == _RATE_LIMIT_RETRIES:
                raise
            logger.warning(
                "1分あたりのリクエスト数制限に達しました。%d秒待ってリトライします(%d/%d回目)。",
                _RATE_LIMIT_WAIT_SECONDS, attempt + 1, _RATE_LIMIT_RETRIES,
            )
            time.sleep(_RATE_LIMIT_WAIT_SECONDS)

    if result["parsed"] is not None:
        return result["parsed"]

    raw_content = getattr(result["raw"], "content", "") or ""
    match = re.search(r"\{.*\}", raw_content, re.DOTALL)
    if not match:
        raise ValueError(f"構造化出力の取得に失敗しました(JSONが見つかりません): {raw_content[:200]!r}")

    logger.warning("with_structured_output()がNoneを返したため、テキスト応答からJSONを抽出しました。")
    return schema.model_validate(json.loads(match.group(0)))


# ---------------------------------------------------------------------------
# 構造化スキーマ(LLMの出力をこの形に強制する)
# ---------------------------------------------------------------------------

class SkillExperience(BaseModel):
    skill: str = Field(description="スキル・技術の名前(例: Java)")
    years: float = Field(description="推定経験年数。関連するプロジェクトの期間から算出する")


class CandidateProfile(BaseModel):
    candidate_name: str = Field(description="候補者の氏名")
    skills: list[SkillExperience] = Field(description="履歴書から読み取れる技術スキルと経験年数の一覧")
    has_led_project: bool = Field(description="プロジェクトを一人で/主体的に担当・主導した経験があるか")
    leadership_evidence: str | None = Field(
        default=None,
        description="has_led_project の判断根拠となる原文の抜粋。根拠がなければnull",
    )


class ScreeningQuery(BaseModel):
    skill: str | None = Field(default=None, description="質問に含まれる技術・スキル名。なければnull")
    min_years: float | None = Field(default=None, description="質問に含まれる最低経験年数。なければnull")
    qualitative_criteria: str | None = Field(
        default=None,
        description="年数やスキル名のような定量条件に落とし込めない、定性的な条件の原文(例: 'プロジェクトを独立して担当できる')。なければnull",
    )


class QualitativeJudgement(BaseModel):
    matches: bool = Field(description="この候補者が定性条件を満たすかどうか")
    reason: str = Field(description="判断の理由")
    evidence_quote: str | None = Field(default=None, description="判断の根拠となる履歴書内の原文引用")


# ---------------------------------------------------------------------------
# 1. 索引作成: 履歴書 → 構造化プロフィール
# ---------------------------------------------------------------------------

def load_resume_text(pdf_path: str) -> str:
    """履歴書PDFをページ単位ではなく1本のテキストとして読み込む。

    v1のチャンク分割(split_into_chunks)はあえて使わない。年数の計算や
    プロジェクト主導経験の判断は履歴書全体の文脈を見る必要があり、
    チャンクに分断すると情報が欠落するため。
    """
    documents = load_pdf(pdf_path)
    return "\n".join(doc.page_content for doc in documents)


def extract_candidate_profile(full_text: str, llm) -> CandidateProfile:
    prompt = (
        "以下は職務経歴書の全文です。内容を読み取り、指定されたスキーマに従って"
        "構造化してください。経験年数は、そのスキルを使ったプロジェクトの期間を"
        "合算して算出してください(履歴書に直接「X年」と書かれていなくても推定すること)。\n\n"
        f"{full_text}"
    )
    return _invoke_structured(llm, CandidateProfile, prompt)


def _file_signature(path: str) -> str:
    """キャッシュの有効性判定用。ファイルの中身からハッシュを計算する
    (mtimeだけだと、内容が同じでもコピー/再ダウンロードで無効判定されてしまうため)。
    """
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _load_cache(cache_path: str) -> dict:
    if not os.path.exists(cache_path):
        return {}
    with open(cache_path, encoding="utf-8") as f:
        return json.load(f)


def _save_cache(cache_path: str, cache: dict) -> None:
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def build_candidate_profiles(pdf_paths: list[str], llm, cache_path: str = CACHE_PATH) -> list[dict]:
    """履歴書PDFのリストから、構造化プロフィールのリストを作る。

    抽出結果はファイル内容のハッシュをキーにキャッシュする。履歴書の内容が
    変わらない限り、2回目以降はLLMを呼ばない(無料枠を消費しない/高速化)。
    これはv1の build_vector_store() が「既存のベクトルDBがあれば再利用する」
    (docs/design-notes.md D2)のと同じ考え方を、構造化抽出に適用したもの。
    """
    cache = _load_cache(cache_path)
    records = []
    cache_dirty = False

    for path in pdf_paths:
        signature = _file_signature(path)
        cached = cache.get(path)

        if cached and cached.get("signature") == signature:
            profile = CandidateProfile.model_validate(cached["profile"])
            full_text = cached["full_text"]
            logger.info("[履歴書スクリーニング] キャッシュを再利用しました: %s", path)
        else:
            full_text = load_resume_text(path)
            profile = extract_candidate_profile(full_text, llm)
            cache[path] = {
                "signature": signature,
                "profile": profile.model_dump(),
                "full_text": full_text,
            }
            cache_dirty = True
            logger.info("[履歴書スクリーニング] プロフィールを新規抽出しました: %s", path)

        records.append({"source": path, "profile": profile, "full_text": full_text})

    if cache_dirty:
        _save_cache(cache_path, cache)

    return records


# ---------------------------------------------------------------------------
# 2. クエリ理解: 自然言語の質問 → 構造化条件
# ---------------------------------------------------------------------------

def parse_query(question: str, llm) -> ScreeningQuery:
    prompt = (
        "以下はユーザーが人材を探すために入力した質問です。質問の中から、"
        "技術スキル名・最低経験年数(数値)・それ以外の定性的な条件、を"
        "指定されたスキーマに従って抽出してください。\n\n"
        f"質問: {question}"
    )
    return _invoke_structured(llm, ScreeningQuery, prompt)


# ---------------------------------------------------------------------------
# 3. 絞り込み: 構造化フィルタ(LLM不要) → 定性判定(候補者ごとにLLM)
# ---------------------------------------------------------------------------

def _skill_matches(query_skill: str, candidate_skill: str) -> bool:
    """スキル名が一致するか判定する(大文字小文字を無視、単語境界を考慮)。

    単純な部分文字列一致(`"java" in "javascript"`)だと、"Java"で検索したときに
    "JavaScript"を誤って一致させてしまう実害が実測で確認された(docs/bug-log.md #14)。
    そのため `\\b`(単語境界)で前後を挟んで、"java"が"javascript"の中の
    部分文字列としてではなく独立した単語として現れる場合だけ一致とみなす。

    ただし `\\b` は英数字と非英数字の切り替わりでしか機能しないため、"C#"や".NET"
    のように記号から始まる/終わるスキル名にそのまま使うと、逆に一致しなくなって
    しまう(例: "C#"の末尾にある"#"は非英数字なので、"\\bC#\\b"は"C#"自身にすら
    一致しない)。そのため、クエリの先頭/末尾が英数字のときだけ境界条件を付ける。
    """
    pattern = re.escape(query_skill.lower())
    prefix = r"\b" if query_skill[0].isalnum() else ""
    suffix = r"\b" if query_skill[-1].isalnum() else ""
    return re.search(f"{prefix}{pattern}{suffix}", candidate_skill.lower()) is not None


def filter_by_structured_criteria(records: list[dict], query: ScreeningQuery) -> list[dict]:
    """スキル名・最低経験年数の条件で候補者を絞り込む。LLMを呼ばない純粋なロジック
    なので、網羅性(見逃しがないこと)が保証できる——これが単純なベクトル類似度検索
    に対するこの設計の優位点(docs/design-notes.md D12)。
    """
    if query.skill is None and query.min_years is None:
        return list(records)

    matched = []
    for record in records:
        profile: CandidateProfile = record["profile"]

        matching_skill = None
        if query.skill is not None:
            matching_skill = next(
                (s for s in profile.skills if _skill_matches(query.skill, s.skill)),
                None,
            )
            if matching_skill is None:
                continue

        if query.min_years is not None:
            if matching_skill is not None:
                candidate_years = matching_skill.years
            else:
                candidate_years = max((s.years for s in profile.skills), default=0.0)
            if candidate_years < query.min_years:
                continue

        matched.append(record)

    return matched


def judge_qualitative(full_text: str, criteria: str, llm) -> QualitativeJudgement:
    prompt = (
        "以下は候補者の職務経歴書の全文です。この人物が次の条件を満たしているか、"
        "原文の記述だけを根拠に判定してください。記述がない場合は満たしていないと"
        f"判定してください。\n\n条件: {criteria}\n\n職務経歴書全文:\n{full_text}"
    )
    return _invoke_structured(llm, QualitativeJudgement, prompt)


def screen_candidates(records: list[dict], question: str, llm) -> tuple[ScreeningQuery, list[dict]]:
    """3段階パイプライン全体を実行する。

    戻り値: (解析されたクエリ, 条件に合致した候補者のリスト)
    候補者1件は {"source", "profile", "judgement"}(judgementは定性条件が
    なければNone)。
    """
    query = parse_query(question, llm)
    filtered = filter_by_structured_criteria(records, query)

    results = []
    if query.qualitative_criteria:
        for record in filtered:
            judgement = judge_qualitative(record["full_text"], query.qualitative_criteria, llm)
            if judgement.matches:
                results.append({**record, "judgement": judgement})
    else:
        results = [{**record, "judgement": None} for record in filtered]

    return query, results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def find_all_pdfs_in_documents() -> list[str]:
    pdf_files = sorted(glob.glob("documents/*.pdf"))
    if not pdf_files:
        print("エラー: documents/ フォルダにPDFファイルが見つかりません。")
        print("スクリーニング対象の履歴書PDFを documents/ フォルダに入れてから再実行してください。")
        exit(1)
    return pdf_files


def _print_result(result: dict) -> None:
    profile: CandidateProfile = result["profile"]
    judgement: QualitativeJudgement | None = result["judgement"]
    skills_str = "、".join(f"{s.skill}({s.years}年)" for s in profile.skills)
    print(f"  ● {profile.candidate_name}  [{result['source']}]")
    print(f"    スキル: {skills_str}")
    if judgement is not None:
        print(f"    判定理由: {judgement.reason}")
        if judgement.evidence_quote:
            print(f"    根拠: 「{judgement.evidence_quote}」")


def main():
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if not os.getenv("GOOGLE_API_KEY"):
        print("エラー: .env ファイルに GOOGLE_API_KEY を設定してください。")
        exit(1)

    pdf_paths = find_all_pdfs_in_documents()
    print(f"{len(pdf_paths)}件の履歴書を読み込みます:")
    for path in pdf_paths:
        print(f"  - {path}")

    llm = get_llm()

    print("\n構造化プロフィールを準備しています(初回のみLLM呼び出し、2回目以降はキャッシュを再利用)...")
    records = build_candidate_profiles(pdf_paths, llm)

    print("\n準備完了！例: 「Javaを5年学び、プロジェクトを独立して担当できる人を探す」('exit'で終了)\n")

    while True:
        question = input("条件: ")
        if question.strip().lower() in ("exit", "quit", "終了"):
            print("終了します。")
            break

        query, results = screen_candidates(records, question, llm)
        print(f"\n解析した条件: スキル={query.skill!r}, 最低年数={query.min_years!r}, 定性条件={query.qualitative_criteria!r}")

        if not results:
            print("条件に合致する候補者は見つかりませんでした。\n")
            continue

        print(f"{len(results)}名が条件に合致しました:")
        for result in results:
            _print_result(result)
        print()


if __name__ == "__main__":
    main()
