# 複数履歴書スクリーニング機能（v2）ノート

> 対応コード：[resume_screening.py](../resume_screening.py)
> このドキュメントは「この機能がどう動くか」を説明する。設計上の「なぜこうしたか」の要約は [design-notes.ja.md D12、D13](design-notes.ja.md) を、
> 単一文書問答(v1)のコード解説は [project-notes.ja.md](project-notes.ja.md) を参照。

---

## 一、この機能が解決する課題

v1でできるのは「1つの文書に対する持ち込み可の質問応答」。しかし「5件の履歴書の中で、Pythonを3年以上学び、かつプロジェクトを独立して担当できる人は誰か」という質問は、本質的に**複数文書にまたがる条件スクリーニング**であり、「最も関連する断片を検索する」のとは違う問題——v1のベクトル検索の発想でそのままやろうとすると、2つの問題にぶつかる：

1. **網羅できない**：検索は「最も類似した上位k件」しか返さず、条件に合う人を全員見つける保証がなく、見逃しが起きやすい
2. **経験年数のような情報はチャンク分割で壊れる**：「この人がJavaを何年使ったか」は複数のプロジェクトに分散した日付区間を合算して算出する必要があり、どこか一箇所に直接答えが書いてあるわけではない。履歴書をチャンクに分割してしまうと、こういう「全文を見て初めて算出できる」情報は確実に抽出できなくなる

そのためv2ではv1のChromaベクトルDBを再利用せず、別のパイプラインを新設した：まず各履歴書を構造化データに「読み替え」、スクリーニングは構造化フィールドの厳密な一致で行い、判断が難しい部分だけLLMに1人ずつ再確認させる。

## 二、3段階の処理フロー

### 第1段階：インデックス作成——履歴書を構造化データに読み替える（`build_candidate_profiles()`）

各PDFに対して：

```python
full_text = load_resume_text(path)              # チャンク分割せず全文をテキスト化
profile = extract_candidate_profile(full_text, llm)  # LLMで構造化フィールドに抽出
```

抽出には `pydantic.BaseModel` で定義したスキーマを使い、`llm.with_structured_output()` で出力形式を強制する。プロンプトで「できるだけJSONで出して」と頼る方式ではない：

```python
class SkillExperience(BaseModel):
    skill: str
    years: float   # LLMがプロジェクトの日付から逆算した値。履歴書に直接書かれた数字ではない

class CandidateProfile(BaseModel):
    candidate_name: str
    skills: list[SkillExperience]
    has_led_project: bool
    leadership_evidence: str | None   # 上記判断の根拠となる原文の抜粋
```

抽出結果は**ファイル内容のハッシュをキーにキャッシュ**する（`resume_profiles_cache.json`）。履歴書の内容が変わらなければ再度LLMを呼ばない——v1の「既存のベクトルDBがあればそのまま読み込む」という考え方と同じ（API無料枠の節約）。

### 第2段階：クエリ理解——自然言語の質問を構造化条件に解析する（`parse_query()`）

ユーザーが「Pythonを3年以上学び、プロジェクトを独立して担当できる人を探す」と入力すると、同じ仕組みで次のように解析される：

```python
ScreeningQuery(skill="Python", min_years=3.0, qualitative_criteria="プロジェクトを独立して担当できる")
```

### 第3段階：二段階の絞り込み

**まず構造化フィルタ**（`filter_by_structured_criteria()`。純粋なPythonロジックで、LLMを呼ばない）：

```python
candidate_years = matching_skill.years  # そのスキルにヒットした
if candidate_years < query.min_years:
    continue  # 年数が足りないので除外
```

この段階はLLMに頼らないため結果が決定論的で、単体テストで検証できる（[tests/test_resume_screening.py](../tests/test_resume_screening.py) 参照）。「気分次第で見逃す」ということが起きない。

**残った候補者に対して定性的な再確認**（`judge_qualitative()`）：ひとりひとりについて、履歴書全文と「プロジェクトを独立して担当できる」という定性条件を一緒にLLMに渡し、判断理由と**原文の引用**を出力させる。「はい／いいえ」だけを出させない：

```python
class QualitativeJudgement(BaseModel):
    matches: bool
    reason: str
    evidence_quote: str | None
```

この2段階をまとめたのが `screen_candidates()`：構造化条件でまず範囲を絞り（候補者が多いときのLLM呼び出し数を節約）、定性条件で精密に絞り込む。結果には「なぜその人が選ばれたか」の根拠が付いており、ブラックボックスの結論ではない。

## 三、実測で踏んだ落とし穴

情報量の多い履歴書（4件のテスト履歴書のうち、情報が最も密な本物の履歴書だけで発生）に対して、`with_structured_output()` が**エラーも出さず黙って`None`を返す**ことがあった——根本原因は、長いコンテキストの場合にモデルが「関数呼び出し」を使わず、JSONを通常のテキスト回答に包んで返すことがあるため。`_invoke_structured()` というラッパーでフォールバック解析を実装した（まず通常のパースを試み、失敗したらテキストから正規表現でJSONを抜き出す）。詳しい経緯は [bug-log.ja.md #12](bug-log.ja.md) に記載。

## 四、使い方

```bash
python resume_screening.py
```

`documents/` 配下のすべてのPDFをスキャンする（v1の`main.py`が最初の1件しか使わないのとは違う）。各ファイルに構造化インデックスを作成した後、質問応答ループに入り、連続して複数のスクリーニング条件を質問できる。`exit`で終了。

## 五、現時点の限界（正直に書く）

- **スキル名のマッチングが粗い**：現在は大文字小文字を区別しない部分一致で、「Java」で検索すると「JavaScript」にもマッチしてしまう。同義語・別名（「機械学習」と「ML」など）は一切扱っていない
- **体系的な精度評価がまだない**：現時点では「流れが動き、結果が妥当に見える」ことしか確認しておらず、[parameter-tuning.ja.md](parameter-tuning.ja.md) のような定量評価（経験年数推定の精度、定性的な再確認の誤判定率）は行っていない
- **候補者数が増えたときのコストが未検証**：現状4件の履歴書でしかテストしておらず、10件規模でのLLM呼び出し回数・遅延・コストが許容範囲かどうかの実測データはまだない

---

*このドキュメントは2026-11-02にこの機能を実装した過程をもとにClaudeが整理したもの。*
