# Bug 记录表

> 从项目最早期(2026-09-01 初回コミット)到现在，发现并处理过的所有 bug，按发现时间顺序排列。
> 不包括纯粹的功能改进/待办事项（那些在 [docs/project-notes.md](project-notes.md) 的待办清单里），这里只记录"代码/系统行为不符合预期"这类真正的 bug。

| # | 严重程度 | 发现日期 | Bug 描述 | 根因 | 解决方式 | 解决日期 |
|---|---|---|---|---|---|---|
| 1 | 高（阻塞运行） | 2026-10-01 | `model_name` 默认值写的是 `claude-sonnet-4-6`，这不是一个真实存在的 Anthropic 模型 ID，调用直接报错 | 项目模板里的占位符/笔误，没人验证过这个模型名是否真实存在 | 改成真实可用的模型 ID（后续经过多次更换，最终定为 `gemini-3.1-flash-lite`，见 #6、#7） | 2026-10-01（首次修复），后续多次更换 |
| 2 | 低 | 2026-10-01 | 使用了 `langchain_community.vectorstores.Chroma`、`langchain_community.embeddings.HuggingFaceEmbeddings` 这两个已废弃的 import 路径，运行时打印 deprecation warning | langchain 生态把这些功能拆分成了独立包（`langchain-chroma`、`langchain-huggingface`），旧路径被标记废弃但暂未删除 | 迁移到独立包；踩坑：第一次升级不小心装了最新版，把 `langchain-core` 拉到 1.x，跟项目锁定的 `langchain==0.3.7` 系列冲突，退回兼容旧版本解决 | 2026-10-01 |
| 3 | 中 | 2026-10-01 | `build_vector_store()` 每次运行都重新计算全部 embedding、重新写入向量库，哪怕 PDF 没变、上次已经处理过 | 函数没有检查 `persist_directory` 是否已存在且非空，无条件新建 | 加判断：已有持久化数据就直接加载，没有才新建 | 2026-10-01 |
| 4 | 高 | 2026-10-01 | 用日语简历测试，问"他叫什么"，AI 回答"不知道"——但姓名明明写在 PDF 第一句 | 原本用的 `sentence-transformers/all-MiniLM-L6-v2` 是英语为主训练的 embedding 模型，日语语义理解差，检索连最基础的信息都找不到 | 换成支持多语言的 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 2026-10-01 |
| 5 | 高（阻塞部署） | 2026-10-08 | 本地构建的 Docker 镜像推送到 Azure Container Apps 后无法启动，报 401/架构不匹配错误 | 本机是 Apple Silicon（arm64），`docker build` 默认按本机架构打包，但 Azure Container Apps（Consumption 方案）只支持 `linux/amd64` | 改用 `docker buildx build --platform linux/amd64` 跨架构构建 | 2026-10-08 |
| 6 | 中 | 2026-10-08 之后某次 / 2026-10-27 又复现 | `gemini-2.5-flash` 模型调用报 404，提示"对新用户不再可用" | Google 对该模型的访问策略发生变化（外部服务变更，不是代码本身的问题） | 按 Google 报错信息里的提示，换成当时可用的模型名 | 多次发生，每次换新模型名应对 |
| 7 | 高 | 2026-10-26 | 做检索准确率评测时，第6次调用起直接报 `429 ResourceExhausted`，免费额度耗尽 | `gemini-3.8-flash` 这个模型的免费层每天只给 20 次请求额度，远低于预期 | 查了模型列表，换成 `gemini-3.1-flash-lite`——免费额度明显更高，而且响应速度从 150~367 秒降到平均几秒 | 2026-10-26 |
| 8 | 🔴 严重（含隐私风险） | 2026-10-26 | 连续用不同文档调用 `build_vector_store(chunks, persist_directory=None)`，后面建的向量库会把前面文档的内容也搜出来（"串台"） | `Chroma.from_documents()` 不指定 `collection_name` 时默认值固定为 `'langchain'`，同一进程内多次调用会不断往同一个 collection 追加数据，不会清空重建。`app.py`（Web版）正是这个用法——意味着线上不同用户上传的文档内容可能互相泄露 | 每次调用传一个 `uuid.uuid4()` 生成的唯一 `collection_name`，保证真正独立 | 2026-10-26 |
| 9 | 中（阻塞 CI） | 2026-10-26 | GitHub Actions 的 `test` job 报 `ModuleNotFoundError: No module named 'rag_pipeline'`，单元测试跑不起来 | `pytest` 默认只把测试文件所在的 `tests/` 目录加入模块搜索路径，没有自动包含项目根目录（本地测试时因为手动加了 `PYTHONPATH` 环境变量掩盖了这个问题，没写进 workflow 文件） | 新增 `pytest.ini`，设置 `pythonpath = .`，不依赖环境变量，本地和 CI 都自动生效 | 2026-10-26 |
| 10 | 🔴 严重（线上代码长期未同步） | 2026-10-27 | GitHub Actions 的 `build-and-deploy` job 一直跑绿（成功），但 Azure 上的 Container App revision 记录从 2026-10-08 之后再没更新过——意味着多次 CI/CD 推送的改动可能从未真正部署到线上 | Azure Container Apps 判断"要不要创建新 revision、要不要重新拉镜像"，依据的是镜像地址字符串本身有没有变化，不检查标签背后内容。`deploy.yml` 一直用固定的 `:latest` 标签，这个字符串从未变过 | 构建镜像时额外打一个"日期+commit短哈希"格式的唯一标签（如 `2026-10-27-a3f9c21`），部署改用这个唯一标签而不是 `:latest` | 2026-10-27 |
| 11 | 🔴 严重（阻塞使用） | 2026-10-27 | #10 修复后终于部署成功，但线上网页**每问一个问题都报错**"回答の生成中にエラーが発生しました" | 流式输出功能（`st.write_stream()`）内部需要 `import pyarrow` 做类型判断；`requirements-deploy.txt` 没锁定 `pyarrow` 版本，装的最新版要求 `numpy>=2.0`，但 `langchain-community` 等包间接把 `numpy` 锁定在 `<2.0`，版本冲突导致 import 直接崩溃 | 锁定 `pyarrow==18.1.0`（本地 Mac/Python 3.13 和部署用的 Linux/Python 3.11 都验证能正常工作的版本）；顺带发现 `requirements.txt`（本地开发用）压根没有 `streamlit`，一并补上 | 2026-10-27 |

| 12 | 中（抽取静默失败） | 2026-11-02 | 多简历筛选功能(`resume_screening.py`)里，`llm.with_structured_output()` 对内容较长的简历（4份测试简历里，只有信息量最大的那份张琪的真实简历触发）返回 `None`，导致后续代码直接因为 `None.model_dump()` 崩溃 | 用 `include_raw=True` 查看原始响应后发现：Gemini 对短文档会正常走"函数调用(tool call)"返回结构化结果，但文档/上下文较长时，模型有时会放弃函数调用，直接把JSON包在 ` ```json ` 代码块里当作普通文本回答——这种情况下 `with_structured_output()` 没有调用成功的tool call可解析，直接返回 `None`，不报错也不提示 | 写了一个 `_invoke_structured()` 包装函数：先尝试正常解析，`parsed is None` 时从原始文本回答里用正则提取JSON并手动校验，而不是直接让程序崩溃 | 2026-11-02 |
| 13 | 中（候选人规模变大后暴露） | 2026-11-10 | 用新生成的10份IT行业测试简历（共14份）测试`resume_screening.py`，问一个不带技能/年限条件、只有定性条件的问题（如"プロジェクトを独立して担当できる人を探す"）时，程序因 `429 ResourceExhausted` 崩溃 | `filter_by_structured_criteria()` 在 `query.skill`、`query.min_years` 都为空时不会过滤掉任何人，于是`screen_candidates()`里的`judge_qualitative()`要对全部候选人逐个调用LLM。候选人一多（本次14人），短时间内连续调用的次数超过了`gemini-3.1-flash-lite`免费层"每分钟15次请求"的限制——这是之前只验证过"每天"额度限制（#7）后，第一次实测撞到更严格的"每分钟"限制 | 给`_invoke_structured()`加了限流重试：捕获`ResourceExhausted`，等待20秒后重试，最多重试3次。`requirements.txt`里补充显式声明`google-api-core`（之前是间接依赖，这次直接`import`了它的异常类） | 2026-11-10 |
| 14 | 中（误判，非崩溃） | 2026-11-10 | 用新生成的IT测试简历验证"Javaを5年以上学んだ人を探す"这类查询时，`filter_by_structured_criteria()`把只会JavaScript、完全不会Java的候选人（中村優子）也判定为匹配，真正的Java资深候选人之外混进了一个假阳性结果 | `resume-screening-notes.md`/`design-notes.md`里早就记录过这是"已知局限"（简单的大小写不敏感子串匹配，`"java" in "javascript"`会判定为真），这次用专门设计过的测试数据（刻意放了一个只有JavaScript没有Java的候选人）才第一次**实测复现**出来 | 写了`_skill_matches()`函数，用`\b`单词边界包住查询词再做匹配，让"java"不再能部分匹配上"javascript"内部。但`C#`、`.NET`这类以符号开头/结尾的技能名，单词边界本身不生效（会导致连自身都匹配不上这个新坑），额外做了判断：只在查询词的首/尾字符是英数字时才加边界条件 | 2026-11-10 |

---

## 统计

- 总计发现 **14** 个 bug
- 按严重程度：🔴 严重 3 个（#8、#10、#11）、高 4 个（#1、#4、#5、#7）、中 6 个（#3、#6、#9、#12、#13、#14）、低 1 个（#2）
- 其中 **#8、#10、#11 这三个"严重"级别的 bug，全部是在"调参实验"和"确认部署是否真的生效"这类主动深挖验证的过程中意外发现的**，不是常规开发流程里暴露出来的——如果没有刻意去验证"我做的改动是不是真的生效了"，这几个 bug 可能会在生产环境里潜伏很久都不会被发现
- **#12 提醒了一个新的教训**：结构化输出(`with_structured_output`)不是"调了就一定拿到结构化结果"的保证型API，输入长度/复杂度变化时模型可能悄悄换一种方式回答，必须对"解析失败"这个分支做兜底，不能假设LLM永远老实按schema回答
- **#13 跟#7是同一个"免费额度"主题下的两种不同限制**：#7是"每天"的额度上限，#13是"每分钟"的频率限制——即使每天额度够用，短时间内请求太密集照样会被拒绝。候选人规模越大、问题的结构化条件越少，越容易触发#13这种情况
- **#14 提醒了一个教训**：知道有局限、也写进文档了，不等于真的验证过——"Java误中JavaScript"这条限制在文档里躺了好几天都只是"理论上会这样"，直到专门设计了含"只有JavaScript没有Java"这种候选人的测试数据才第一次被实测复现。另外修复过程中差点因为`\b`单词边界对符号开头的技能名（`C#`）失效，引入一个新的假阴性bug——说明"修一个边界case"本身也要补边界case的测试

## 常见根因归类（复盘用）

| 根因类型 | 对应的 bug | 共同教训 |
|---|---|---|
| 没验证外部依赖/平台的真实行为，凭假设写代码 | #1（模型名没验证）、#5（架构假设）、#8（Chroma默认行为假设）、#10（Azure revision判断逻辑假设） | **凡是涉及"调用别人的系统/库"的地方，不要凭直觉假设行为，去实测验证** |
| 依赖版本没有锁定或锁定不完整 | #2、#9（间接）、#11 | **`requirements.txt` 里的每一个关键依赖都应该锁定具体版本，新增功能后要重新检查有没有引入新的隐式依赖** |
| 本地测试环境和真实部署环境不一致，导致"本地没问题"掩盖了真实缺陷 | #5（架构不同）、#9（本地手动设了环境变量掩盖问题）、#11（Python版本/操作系统不同导致可用的包版本不同） | **凡是"本地测试通过"不能直接等同于"部署环境也没问题"，有条件应该用跟真实部署完全一致的环境做最终验证** |

---

*这份记录由 Claude 根据 2026-10-27 的项目历史整理，后续每发现一个新 bug，应该在这张表里补一行，保持跟 [docs/project-notes.md](project-notes.md) 里对应条目的说法一致。*
