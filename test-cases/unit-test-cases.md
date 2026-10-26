# rag-starter 测试用例书

> 对应：待办清单第11条（流式输出）、第12条（单元测试）、第13条（CI 接入测试）。
> 测试对象代码：[rag_pipeline.py](../rag_pipeline.py)、[app.py](../app.py)
> 自动化测试代码：[tests/test_rag_pipeline.py](../tests/test_rag_pipeline.py)
> 执行方式：`pytest tests/ -v`（本地）、GitHub Actions `test` job（CI，见 [.github/workflows/deploy.yml](../.github/workflows/deploy.yml)）

---

## 一、测试范围说明

这份测试用例覆盖的是 `rag_pipeline.py` 里**不依赖网络/API 的纯函数部分**（切块逻辑、prompt 组装、阈值配置），刻意**不包括**需要真实调用 Gemini API 的部分（`ask_question`/`ask_question_stream` 完整流程、`build_qa_chain`）——原因：

1. 这类测试需要真实 `GOOGLE_API_KEY`，CI 环境里没有配置，跑不起来
2. 即使配置了 key，测试结果会受网络状况、模型输出不确定性影响，不稳定（也不想在每次 CI 运行时消耗 API 额度）
3. 检索准确率这类"结果好不好"的验证，属于另一种性质的测试（评测/evaluation），不是这里说的单元测试，已经在手动评测里做过（见 [docs/project-notes.md](../docs/project-notes.md) 第15条）

所以这份用例书分两部分：**自动化单元测试（CI 每次 push 自动跑）** + **手动验证用例（改动时手动确认一次即可，不进 CI）**。

---

## 二、自动化单元测试用例

执行命令：`PYTHONPATH=. pytest tests/ -v`

最近一次执行结果：**10 个用例全部通过**，耗时约 1 秒（本地 venv）/ 约 11 秒（模拟 CI 环境的全新虚拟环境，含依赖安装后的运行时间）。

| 用例编号 | 测试项目 | 前置条件 | 测试步骤 / 输入 | 预期结果 | 实际结果 | 判定 |
|---|---|---|---|---|---|---|
| TC-01 | 长文本切块：超过 chunk_size 的文本应被切成多段 | 无 | 构造 1200 字符的单一文档，调用 `split_into_chunks(docs, chunk_size=500, chunk_overlap=50)` | 返回的 chunk 列表长度 > 1 | 长度 > 1 | ✅ PASS |
| TC-02 | 短文本不切块：短于 chunk_size 的文本应保持单段 | 无 | 构造一段短文本（约20字符）的文档，调用 `split_into_chunks(docs, chunk_size=500, chunk_overlap=50)` | 返回恰好 1 个 chunk，内容与原文一致 | 恰好1个chunk，内容一致 | ✅ PASS |
| TC-03 | 切块后单个片段不应远超 chunk_size | 无 | 构造 2000 字符文档，调用 `split_into_chunks(docs, chunk_size=500, chunk_overlap=50)` | 每个 chunk 长度 ≤ 750（chunk_size 的1.5倍，留一定容差） | 全部满足 | ✅ PASS |
| TC-04 | 自定义 chunk_size/overlap 参数生效 | 无 | 构造 300 字符文档，调用 `split_into_chunks(docs, chunk_size=100, chunk_overlap=10)` | 返回多个 chunk，且每个 chunk 长度 ≤ 150 | 全部满足 | ✅ PASS |
| TC-05 | 多个输入文档都应被处理 | 无 | 传入 2 份各 600 字符的文档，调用 `split_into_chunks(docs, chunk_size=500, chunk_overlap=50)` | 返回的 chunk 总数 ≥ 2（两份文档都被切分，没有遗漏） | 满足 | ✅ PASS |
| TC-06 | 相关度阈值配置：两种 provider 都要有默认值 | 无 | 检查 `_RELEVANCE_THRESHOLDS` 字典的 key | 包含 `"huggingface"` 和 `"google"` 两个 key | 都包含 | ✅ PASS |
| TC-07 | 相关度阈值必须是正数 | 无 | 遍历 `_RELEVANCE_THRESHOLDS` 所有 value | 每个值都是 int/float 类型且 > 0 | 全部满足 | ✅ PASS |
| TC-08 | Prompt 组装：应同时包含问题和原文内容 | 无 | 构造1份含特定文字的文档，调用 `_build_prompt(docs, "経験年数は何年ですか？")` | 返回的 prompt 字符串里同时包含问题原文和文档原文 | 都包含 | ✅ PASS |
| TC-09 | Prompt 组装：多个片段之间应有换行分隔 | 无 | 构造2份文档（"第1段落"、"第2段落"），调用 `_build_prompt(docs, "質問")` | prompt 中出现 `"第1段落\n\n第2段落"`（用空行分隔，模型更容易区分片段边界） | 符合预期 | ✅ PASS |
| TC-10 | "未找到相关内容"提示文案不为空 | 无 | 检查 `NOT_FOUND_MESSAGE` 常量 | 是非空字符串 | 非空字符串 | ✅ PASS |

---

## 三、手动验证用例（第11条：流式输出）

流式输出涉及真实调用 LLM，不适合写进自动化单元测试（会拖慢 CI、消耗 API 额度、结果不确定），改为**代码改动后手动跑一次**确认。

| 用例编号 | 测试项目 | 前置条件 | 测试步骤 | 预期结果 | 实际结果 | 判定 |
|---|---|---|---|---|---|---|
| TC-M01 | `ask_question_stream()` 返回类型正确 | 已建好向量库和 `qa_chain` | 调用 `ask_question_stream(qa_chain, "随便一个问题")`，检查返回的第一个元素 | 返回 `(生成器, 来源列表)` 的元组，第一个元素具有 `__next__` 方法（是生成器） | 确认是生成器 | ✅ PASS |
| TC-M02 | 不相关问题走"未找到"分支，不调用 LLM | 已建好向量库和 `qa_chain` | 调用 `ask_question_stream(qa_chain, "今天东京天气怎么样")`（与文档内容完全无关的问题），消费生成器拿到完整文本 | 文本内容等于 `NOT_FOUND_MESSAGE`，来源列表为空，且不应有调用 LLM 产生的网络等待（应该几乎瞬间返回） | 文本为"文書内に関連する内容が見つかりませんでした。"，来源为空列表，瞬间返回 | ✅ PASS |
| TC-M03 | 网页端流式显示（人工目测） | `streamlit run app.py` 已启动，已上传PDF | 在网页输入一个相关问题，观察回答区域 | 回答应该逐字/逐段出现（打字机效果），而不是转圈等待后一次性整段出现 | 待下次实际跑 `streamlit run app.py` 时人工确认（已改代码并通过 py_compile 语法检查，但尚未实际人工目测网页效果，因为这步依赖真实LLM调用，当前已知调用经常需要2-4分钟，详见待办第15条） | ⏳ 待验证 |

---

## 四、怎么在 CI 里看这些测试的执行结果

每次 `git push` 后，GitHub Actions 会自动执行 `test` job（对应本文档"二、自动化单元测试用例"这部分），结果在仓库 **Actions** 页面能看到。只有 `test` job 全部通过，后面的 `build-and-deploy` job 才会执行——这就是待办第13条要求的"测试把关"，测试不过，不允许部署。

---

*这份测试用例书由 Claude 根据 2026-10-26 新增的 `tests/test_rag_pipeline.py` 整理，代码一旦改动（尤其是改了 `split_into_chunks`/`_build_prompt`/`_RELEVANCE_THRESHOLDS` 的行为），需要同步更新这份文档的"预期结果"列，并重新跑一遍确认"实际结果"列。*
