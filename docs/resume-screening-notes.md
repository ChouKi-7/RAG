# 多简历筛选功能（v2）笔记

> 对应代码：[resume_screening.py](../resume_screening.py)
> 这份文档讲"这个功能怎么运作"。设计上"为什么这么做"的简短版本在 [design-notes.md D12~D18](design-notes.md)；
> 单文档问答(v1)的代码讲解在 [project-notes.md](project-notes.md)；准确率评测的数据和分析在 [resume-screening-eval.md](resume-screening-eval.md)。

---

## 一、这个功能解决什么问题

v1能做的是"对一份文档做开卷问答"。但如果问的是"5份简历里，学过Python 3年以上、还能独立负责项目的人是谁"，这种问题本质上是**跨文档的条件筛选**，不是"检索最相关的几段内容"——用v1那套向量检索的思路做，天然会有两个问题：

1. **穷举不了**：检索只返回"最相似的k段"，不保证把所有符合条件的人都找出来，容易漏判
2. **年限这种信息，切块后会被打散**："这个人用了几年Java"要把分布在不同项目里的日期区间加起来算，而不是某一段文字直接写着答案；一旦简历被切成chunk，这种"需要看完整篇才能算出来"的信息就没法可靠提取

所以v2没有复用v1的Chroma向量库，而是另开一套流程：先把每份简历"读"成结构化数据，筛选时靠结构化字段做精确匹配，不确定的部分再让LLM逐份复核。

## 二、三段式流程

### 第1步：索引阶段——把简历"读"成结构化数据（`build_candidate_profiles()`）

对每份PDF：

```python
full_text = load_resume_text(path)              # 整篇转成文字，不切块
profile = extract_candidate_profile(full_text, llm)  # LLM抽取成结构化字段
```

抽取用的是 `pydantic.BaseModel` 定义的schema，交给 `llm.with_structured_output()` 强制输出格式，而不是在prompt里拜托LLM"尽量输出JSON"：

```python
class SkillExperience(BaseModel):
    skill: str
    years: float   # LLM按项目日期推算出来的，不是简历里直接写的数字

class CandidateProfile(BaseModel):
    candidate_name: str
    skills: list[SkillExperience]
    has_led_project: bool
    leadership_evidence: str | None   # 支撑上面判断的原文片段
```

抽取结果会**按文件内容哈希缓存**到 `resume_profiles_cache.json`，简历内容没变就不会重新调用LLM——跟v1里"已有向量库就直接加载"是同一个思路（省API额度）。

### 第2步：查询理解——把自然语言问题解析成结构化条件（`parse_query()`）

用户输入"Pythonを3年以上学び、プロジェクトを独立して担当できる人を探す"，同样用`with_structured_output()`解析成：

```python
ScreeningQuery(skill="Python", min_years=3.0, qualitative_criteria="プロジェクトを独立して担当できる", limit=None)
```

`limit`（2026-11-24新增）是问题里提到的数量限制，比如"2人""上位3件"，没提到就是`None`。

### 第3步：两段式筛选

**先做结构化过滤**（`filter_by_structured_criteria()`，纯Python逻辑，不调用LLM）：

```python
candidate_years = matching_skill.years  # 命中了这个技能
if candidate_years < query.min_years:
    continue  # 不够年限，排除
```

这一步因为不靠LLM，结果是确定性的、可以写单元测试验证（见 [tests/test_resume_screening.py](../tests/test_resume_screening.py)），不会"看心情漏判"。

**剩下的候选人再做定性复核**（`judge_qualitative()`）：对每个人，把Ta简历的全文和"独立负责项目"这个定性条件一起交给LLM，要求输出判断理由**和原文引用**，不是只给"是/否"：

```python
class QualitativeJudgement(BaseModel):
    matches: bool
    match_score: int   # 0-100，2026-11-24新增，用于给结果排序
    reason: str
    evidence_quote: str | None
```

两步合起来是 `screen_candidates()`：结构化条件先缩小范围（候选人多的时候省LLM调用），定性条件再精筛，筛选结果带着"为什么选中Ta"的依据，不是黑盒结论。

### 第4步（2026-11-24新增）：排序 + 数量限制（`_rank_and_limit()`）

原来筛选结果是无序的，没法回答"帮我找2个Java经验的人"这种带数量限制的问题。现在`screen_candidates()`在返回结果前多做一步：

- **有定性条件**：按`judge_qualitative()`打的`match_score`从高到低排——这一步没有额外成本，分数本来就是判定的时候顺带输出的
- **没有定性条件**：按已经抽取好的技能年限从高到低排——同样不调用额外的LLM，纯粹复用已有数字
- 排好序之后，如果`query.limit`有值就截断到对应条数

这个顺序（先排序、再截断）是故意的：保证"前2个"真的是"最匹配的2个"，不是"随便2个"。

## 三、实测踩过的坑

`with_structured_output()`对内容量大的简历（4份测试简历里，只有信息最密集的那份真实简历触发）会**悄悄返回`None`**而不报错——根因是模型在长上下文时有时不走"函数调用"而是把JSON包在普通文本回答里。写了`_invoke_structured()`做兜底解析（先尝试正常解析，失败再从文本里正则抠JSON）。完整过程记录在 [bug-log.md #12](bug-log.md)。

## 四、怎么用

**CLI版**：

```bash
python resume_screening.py
```

会扫描 `documents/` 下的所有PDF（不像v1的`main.py`只取第一个），为每份建立结构化索引，然后进入问答循环，可以连续问多个筛选条件，`exit`退出。

**Web版**（2026-11-18新增，`resume_screening_app.py`）：

```bash
streamlit run resume_screening_app.py --server.port 8502
```

跟v1的`app.py`结构一样（同一套密码门禁、同样用`st.chat_input`做聊天式交互），区别在于支持`accept_multiple_files=True`一次上传多份PDF。有一个v1没有的设计点：**每个浏览器会话用独立的临时缓存文件**，不共用`resume_screening.py`CLI默认的那个`resume_profiles_cache.json`——这是为了避免重蹈v1 [bug-log.md #8](bug-log.md) 的覆辙（当时Chroma的`collection_name`没按会话区分，导致不同用户上传的文档内容在向量库里串台）。这里虽然用的是本地JSON文件而不是向量库，但"不同访问者的数据必须互相隔离"这条原则是一样的，所以从一开始就按会话分离，不是等出了问题再修。

## 五、已知局限（老实说）

- ~~技能名匹配比较粗糙~~（**子串误判2026-11-10已修复，同义词2026-11-18部分支持**）：原来是大小写不敏感的子串匹配，"Java"会连"JavaScript"也匹配上——用专门设计的10份IT行业测试简历实测复现后，改成了单词边界匹配（`_skill_matches()`，详见 [design-notes.md D14](design-notes.md)、[bug-log.md #14](bug-log.md)）。同义词/别名（"机器学习" vs "ML"）这块后续加了embedding相似度兜底（单词边界没匹配上时，再算两个词的向量相似度，超过阈值也算匹配，详见 [design-notes.md D17](design-notes.md)）——**但这是"部分支持"不是"解决"**：实测验证过"Go/Golang""JS/JavaScript"这类同义词能拾到，但"ML/機械学習""AWS/Amazon Web Services"这类字面差异很大的缩写还是拾不到，阈值没法同时兼顾（调低会导致bug#14复发）
- ~~还没有系统性的准确率评测~~（**2026-11-17已完成一轮，并修复了发现的主要问题**）：技能识别13/13正确，定性判断（独立负责与否）10/10正确含关键负例。年限推算最初发现"只在标题简略提及/需要跨项目加总时会明显偏低"的问题（根因是LLM不知道"今天"是哪天），已通过给抽取prompt显式传入当前日期修复——但**修复过程中又发现一个新的、尚未解决的问题**：个别候选人会把跟某技能完全无关的项目时长也错误地算进该技能的年限里（张冠李戴），这个新问题目前**尚未修复**（已记录为 [bug-log.md #16](bug-log.md)，权衡后判断"保留日期修复、接受这个新问题"整体利大于弊）。完整方法论、数据表、分析见专门的评测文档 [resume-screening-eval.md](resume-screening-eval.md)
- ~~候选人多了以后的成本还没测过~~（**2026-11-10已部分验证，发现新问题**）：用14份简历（4份旧的+10份新生成的IT行业测试简历）测试后，发现候选人一多、问题又没带技能/年限这类能先做结构化过滤的条件时，会连续密集调用LLM，撞上Gemini免费层"每分钟15次请求"的限流（[bug-log.md #13](bug-log.md)），已加重试兜底。但**延迟和费用**层面的量化数据还是没有——现在是"撞到限流会自动等待重试"，不等于"响应快、成本低"
- **排序结果里的并列分数**（2026-11-24新发现，不是bug）：定性判断是逐个候选人独立打分的，不是一次性把所有人放一起比较，所以"明显都符合"的候选人经常打出并列最高分（实测9人里前3名都是100分）。并列的人之间排前排后，目前靠的是候选人列表本身的原始顺序，不代表真实优劣——这是"独立打分"这个设计天然的副作用，详见 [design-notes.md D18](design-notes.md)

---

*这份文档由 Claude 根据 2026-11-02 实现该功能时的过程整理，2026-11-10 补充了技能匹配修复和限流问题的进展，2026-11-17 补充了系统性准确率评测、年限低估修复(bug#15)及新发现的技能归属问题(bug#16)，2026-11-18 补充了Web版(`resume_screening_app.py`)和同义词匹配(embedding兜底)的说明，2026-11-24 补充了结果排序与数量限制(`limit`)的说明。*
