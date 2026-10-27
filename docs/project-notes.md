# rag-starter 项目笔记

> 写给：刚开始学习 RAG、暂时看不懂代码细节的自己。

---

## 一、这个项目到底是干什么的

**一句话**：让你对着一个 PDF 文件用自然语言提问，AI 会先去 PDF 里找相关内容，再基于这些内容回答你——而不是凭空瞎编。

这套"先检索、再回答"的方法叫 **RAG（检索增强生成，Retrieval-Augmented Generation）**。

**类比**：就像考试时允许"开卷"——AI 不是靠自己脑子里记的东西回答，而是先翻书（PDF），找到跟问题最相关的几段，再照着这几段内容组织语言回答你。这样做的好处是：AI 可以回答它训练数据里根本没有的内容（比如你自己的简历、公司内部文档），而且回答有据可查。

---

## 二、代码在干什么（逐步讲解）

项目两个核心文件分工：

- `main.py` —— "外壳"：读用户输入、显示结果、串联流程
- `rag_pipeline.py` —— "核心"：RAG 的 5 个步骤，一个步骤一个函数

### rag_pipeline.py 的 5 步

**第1步：读 PDF** —— `load_pdf()`
```python
loader = PyPDFLoader(pdf_path)
documents = loader.load()
```
把 PDF 打开，按"页"把文字抠出来。此时拿到的是纯文字，电脑还理解不了语义。

**第2步：切块** —— `split_into_chunks()`
```python
splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
chunks = splitter.split_documents(documents)
```
为什么切？因为后面要"翻书"找答案，整页/整本书当一个单位太粗，也塞不进 AI 的上下文窗口。所以切成约 500 字一段。`chunk_overlap=50` 让相邻两段重叠 50 字，防止一句话刚好被切断导致语义丢失。

**第3步：向量化 + 存库** —— `build_vector_store()`
```python
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
vector_store = Chroma.from_documents(documents=chunks, embedding=embeddings, persist_directory=persist_directory)
```
最关键也最抽象的一步：
- `embeddings` 模型把**每一段文字变成一串数字（向量）**，意思相近的句子向量在数学空间里离得近。
- `Chroma` 是"向量数据库"，专门存这些向量，支持"相似度搜索"（给一个向量，快速找出库里离它最近的几个）。
- 这一步是本地免费模型做的，跟 Claude 没关系，不花钱也不需要联网。

**第4+5步：检索 + 生成回答** —— `build_qa_chain()`
```python
llm = ChatAnthropic(model=model_name, temperature=0)
retriever = vector_store.as_retriever(search_kwargs={"k": 3})
qa_chain = RetrievalQA.from_chain_type(llm=llm, retriever=retriever, return_source_documents=True)
```
- `retriever`：提问时先把问题也向量化，去向量库里找"最相似的 3 段文字"（`k=3`）——这是"检索"。
- `llm`：真正调用 Claude API 的地方。
- `RetrievalQA`：把"检索到的 3 段原文" + "你的问题"一起打包给 Claude，让它基于这些原文回答——这是"增强生成"。

**真正问答** —— `ask_question()`
```python
result = qa_chain.invoke({"query": question})
return result["result"], result["source_documents"]
```
返回两样东西：AI 的回答文字，以及它参考了哪几段原文（方便核实有没有瞎编）。

### main.py 怎么把 5 步串起来

```python
documents = load_pdf(pdf_path)             # 第1步
chunks = split_into_chunks(documents)      # 第2步
vector_store = build_vector_store(chunks)  # 第3步
qa_chain = build_qa_chain(vector_store)    # 第4+5步，只是搭好"管道"

while True:
    question = input("质问: ")
    answer, sources = ask_question(qa_chain, question)  # 每次循环真正问一次
```
启动时把 PDF 处理一遍、建好向量库和问答链；之后进入循环，每输入一个问题就用同一套向量库检索+回答，输入 "exit" 退出。

### 一句话总结

> "把文档切片、转成向量存起来；用户提问时，先找出语义最相关的几个片段，再把这些片段和问题一起交给大模型，让它基于这些真实原文来回答。"

---

## 三、当前状态（重要：和代码原始设计不一样了）

项目最初是用 Claude（付费 API）做回答生成，但因为申请 Claude key 需要先充值，所以**目前已经切换成 Google Gemini 的免费方案**：

- [rag_pipeline.py](../rag_pipeline.py)、[main.py](../main.py)、[requirements.txt](../requirements.txt)、[.env.example](../.env.example) 里所有 Claude 相关代码（`ChatAnthropic`、`ANTHROPIC_API_KEY`、`langchain-anthropic`）都**注释保留，没有删除**，想切回 Claude 的话把注释去掉、再把 Gemini 那行注释上即可。
- 现在实际生效的是 `ChatGoogleGenerativeAI`，模型名 `gemini-2.5-flash`，需要的环境变量是 `.env` 里的 `GOOGLE_API_KEY`（去 https://aistudio.google.com/app/apikey 免费申请）。
- `langchain-google-genai` 已经装好（`pip install langchain-google-genai==2.0.7`）。

所以上面"二、代码讲解"里提到的 `ChatAnthropic` / `llm = ChatAnthropic(...)` 这些，现在要在脑内替换成 `ChatGoogleGenerativeAI`——**原理和作用完全一样**（都是"调用云端大模型做理解+生成回答"），只是换了个供应商，所以讲解内容不用重写。

## 四、目前的缺点 / 待办清单

**排序规则**：从上到下 = 优先级从高到低、同等优先级下越简单的越靠前。打勾表示已解决。

- [x] **1. 模型名可能无效，会导致直接报错**（难度：极低，优先级：最高）
  位置：`rag_pipeline.py` 第 60 行，`model_name: str = "claude-sonnet-4-6"`
  这不是一个真实存在的 Anthropic 模型 ID，调用时大概率报 "model not found"。
  → 改成真实可用的模型 ID（如 `claude-sonnet-5`），最好支持用环境变量覆盖。

- [x] **2. 缺少 `.gitignore`，有泄露/误提交风险**（难度：低，优先级：高）
  目前 `.DS_Store` 已经被提交进 git 了；`venv/`、`.env`（里面是 API key）、将来生成的 `chroma_db/` 目前只是"运气好"没被提交。
  → 新增 `.gitignore`（排除 `venv/`、`.env`、`chroma_db/`、`.DS_Store`、`__pycache__/`），并把已经误提交的 `.DS_Store` 从 git 里移除。

- [x] **3. 多个 PDF 时静默只取第一个**（已完成）
  [main.py](../main.py) 的 `find_pdf_in_documents()` 现在用 `sorted(glob.glob(...))`（保证每次运行选中的文件固定，不受 `glob` 返回顺序不确定的影响），检测到多个 PDF 时会打印提示："N個のPDFが見つかりました。最初の1つを使用します: xxx.pdf"，并列出被忽略的其他文件名。
  本地验证：`documents/` 里现在有4个PDF（原来的 userA 简历 + 3份新生成的测试用假简历），实际运行确认提示文字正常显示，选中的文件固定是排序后的第一个。

- [x] **4. 用了已废弃的 import 路径**（已完成）
  原来 `rag_pipeline.py` 用的是 `langchain_community.vectorstores.Chroma` 和 `langchain_community.embeddings.HuggingFaceEmbeddings`，已迁移到独立的 `langchain-chroma==0.1.4` / `langchain-huggingface==0.1.2` 包，不再触发 deprecation warning。
  注意：装包时第一次不小心装了最新版，把 `langchain-core` 拉到了 1.x，跟项目锁定的 `langchain==0.3.7` 系列冲突（`pip check` 报错），后来退回兼容的旧版本才解决——以后装 langchain 生态的包时要注意锁定跟现有版本兼容的版本号，不要直接装最新版。

- [x] **5. 每次运行都重新计算全部 embedding，比较浪费**（已完成）
  `build_vector_store()` 现在会先检查 `persist_directory`（`./chroma_db`）是否已存在且非空：有就直接 `Chroma(persist_directory=..., embedding_function=...)` 加载已有库，没有才用 `Chroma.from_documents()` 新建。已验证：连续跑两次 `python main.py`，第二次会打印"既存のベクトルDBを読み込みました"，记录数保持 16 条不再累积。
  注意：这个修复顺带解决了测试时发现的"数据重复"问题（见下方新发现的问题）——以前每跑一次都会把 16 个 chunk 重新写入同一个库，导致记录数变成 32、48……现在不会了。

- [x] **6. 把生成回答的模型换成免费方案**（已完成：改用 Google Gemini，见上方"三、当前状态"）
  原因：第4+5步负责"理解问题+生成回答"的模型原本是 Claude（`ChatAnthropic`），这是付费 API，申请 key 前需要先充值。改用 Gemini 后不用充值，用免费额度即可测试。Claude 相关代码没有删除，只是注释保留，想切回去随时可以。

  其余免费/低成本方案留档备查（目前没有切换需求，不用再做）：

  | 方案 | 说明 | 需要改动 |
  |---|---|---|
  | **Google Gemini** | 有免费额度，去 Google AI Studio 申请 key | 换 `langchain-google-genai` 库，`ChatAnthropic` → `ChatGoogleGenerativeAI` |
  | **Groq** | 免费调用 Llama / Mixtral 等开源模型，速度很快 | 换 `langchain-groq` 库，`ChatAnthropic` → `ChatGroq` |
  | **Ollama（纯本地）** | 完全本地运行开源模型（如 Llama 3），不要 API key、不联网、不花钱，但需要电脑性能够、要先下载模型（几 GB） | 换 `langchain-ollama` 库，`ChatAnthropic` → `ChatOllama`，另外要先装 Ollama 软件 |
  | **Hugging Face Inference API** | 免费额度调用托管的开源模型 | 换 `langchain-huggingface` 库里的 LLM 接口 |

  通用改动步骤（不管选哪个方案，套路都一样）：
  1. `pip install` 对应的新库
  2. 把 `rag_pipeline.py` 里 `from langchain_anthropic import ChatAnthropic` 换成新库的 import
  3. 把 `build_qa_chain()` 里 `ChatAnthropic(...)` 换成新模型对应的类
  4. 去对应平台申请新的 API key，填进 `.env`（Ollama 除外，它不需要 key）

  → 这是一个独立的新改动，不是"修 bug"，优先级最低，想省钱/想体验不同模型的时候再做即可。

- [x] **7. （测试中新发现）embedding 模型不支持日语，导致检索完全失效**（已完成）
  现象：用日语简历测试时，问"他叫什么"/"氏名は何ですか"，AI 回答"不知道"——但姓名其实就写在 PDF 第一句的"氏名"字段里。排查后发现根因：原来用的 `sentence-transformers/all-MiniLM-L6-v2` 是英语为主训练的模型，日语语义理解很差，导致向量检索连最基础的信息都找不到（检索出来的 3 段跟问题完全不相关）。
  → 已换成支持多语言的 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`，换完后同样的问题能正确检索到含姓名的那一段。
  教训：**embedding 模型要跟文档的语言匹配**，用英语模型处理日语/中文文档，检索环节会悄悄失效而不报错——这个坑不测试很难发现，因为代码完全不报错，只是"回答质量很差"。

- [x] **8. `app.py` 没有错误处理，报错会把原始 Python 堆栈甩给用户看**（已完成）
  [app.py](../app.py) 里两处容易出错的地方都加了 `try/except`：上传 PDF 建库阶段、提问生成回答阶段。出错时显示友好提示（"エラーが発生しました。しばらくしてから再度お試しください"），不再暴露原始 traceback；上传失败时还会清空 session 状态方便用户重新上传。

- [x] **9. 公开 Demo 没有任何访问限制**（已完成）
  [app.py](../app.py) 新增了密码门禁：如果设置了环境变量 `APP_PASSWORD`，访问时会要求输入密码，验证通过才能继续使用（存在 `st.session_state` 里，同一浏览器 session 内不用重复输入）；**如果没设置这个环境变量，完全不受影响，本地开发/测试时照常直接用**。
  `.env.example` 里加了这一项的说明（默认注释掉）。
  **还没做的后续动作**：Azure 上现在还没配这个环境变量，线上 Demo 目前依然是无密码状态——真要给外人看之前，记得执行：
  ```bash
  az containerapp update --name rag-starter-app --resource-group rag-starter-rg \
    --set-env-vars APP_PASSWORD=secretref:app-password \
    --replace-secrets app-password=<你想设的密码>
  ```
  （具体参数可能需要对照当时的 `az containerapp update --help` 核对一下，`--replace-secrets` 这个写法没有实际验证过。）

- [x] **10. 检索质量比较粗糙，没有相关性过滤**（已完成）
  原来 `build_qa_chain()` 用的是 `RetrievalQA.from_chain_type(...)`，固定取 `k=3`，不管相关度多低都原样塞给 LLM。现在改成手动调用 `vector_store.similarity_search_with_score()`，拿到的片段按 `score_threshold` 过滤：低于阈值（更相似）才会传给 LLM，一个都没达标时直接返回"文書内に関連する内容が見つかりませんでした"，不调用 LLM。
  `qa_chain` 的返回类型从 `RetrievalQA` 对象改成了普通 dict（`{"llm", "vector_store", "score_threshold"}`），`ask_question()` 内部自己组装 prompt 调用 `llm.invoke()`，不再依赖 `RetrievalQA` 这个封装类（对应的 `from langchain.chains import RetrievalQA` 这行 import 也删掉了）。`main.py`/`app.py` 只是把 `qa_chain` 当黑盒透传，没碰过它的具体类型，所以不用改。
  **踩坑记录（重要）**：实测发现 Chroma 返回的"距离分数"，量级会因 embedding 来源不同而完全不一样——本地 `huggingface` 模型：相关内容 16~18 分、不相关 29~33 分；云端 `google` embedding：相关内容 0.69~0.76 分、不相关 0.88~0.92 分（都是分数越低越相似）。如果写死一个阈值，换个 embedding provider 直接失效。所以阈值按 provider 分别设了默认值（`_RELEVANCE_THRESHOLDS` 字典），也支持用环境变量 `RELEVANCE_SCORE_THRESHOLD` 整体覆盖。
  **注意**：这两个默认阈值是用 `documents/` 里那一份测试 PDF 实测校准的，换一份内容/语言差异很大的 PDF，这两个数字不一定还准，必要时要重新实测调整。
  本地验证：问"他叫什么"能正常检索并回答；问"今天东京天气怎么样"（跟 PDF 内容完全无关）正确返回"未找到相关内容"，没有瞎编。

- [x] **11. 没有流式输出，要等全部生成完才显示**（已完成）
  `rag_pipeline.py` 新增 `ask_question_stream()`（跟原来的 `ask_question()` 共用 `_retrieve_relevant_docs()`/`_build_prompt()` 两个抽出来的公共函数，不用写两遍逻辑），返回 `(文本片段的生成器, 来源列表)`。[app.py](../app.py) 改用 `st.write_stream(stream)` 显示回答。
  验证：用"不相关问题"分支测试过生成器结构正确、能瞬间返回（不碰网络）；真正流式的网页视觉效果因为每次调用都要等 2 分钟以上（见第15条），还没来得及人工完整验证一次，已记录进 [test-cases/unit-test-cases.md](../test-cases/unit-test-cases.md) 的 TC-M03，标记为"待验证"。
  `main.py`（CLI版）没有改，还是用原来的 `ask_question()`，不影响。

- [x] **12. 完全没有测试**（已完成）
  新增 [tests/test_rag_pipeline.py](../tests/test_rag_pipeline.py)，用 `pytest` 覆盖 `split_into_chunks()`、`_build_prompt()`、`_RELEVANCE_THRESHOLDS`、`NOT_FOUND_MESSAGE` 这些不依赖网络/API 的纯逻辑，一共10个用例，本地跑全部通过（约1秒）。完整的用例列表和预期/实际结果见新建的 [test-cases/unit-test-cases.md](../test-cases/unit-test-cases.md)（单独开的文件夹，不混进 `docs/`）。
  新增 `requirements-dev.txt`（只放 `pytest`、`ruff`，运行时不需要，纯开发/CI用）。
  刻意没测的部分：`ask_question`/`ask_question_stream`/`build_qa_chain` 这些要真实调用 Gemini API 的，不适合进自动化单元测试（没 key、不稳定、费额度），原因写在 test-cases 文档里了。

- [x] **13. 没有 CI（持续集成）**（已完成）
  在已有的 [.github/workflows/deploy.yml](../.github/workflows/deploy.yml) 里加了一个 `test` job（跑 `ruff check .` + `pytest tests/ -v`），并且让原来的 `build-and-deploy` job 加上 `needs: test`——**测试/lint 不通过，不会触发后面的部署**，这是之前讨论"CI 和 CD 的区别"时提到的、真正完整的闭环（之前只有部署自动化，没有质量把关这一环，现在补上了）。
  验证：本地建了一个全新的虚拟环境，只装 `requirements-deploy.txt` + `requirements-dev.txt`（模拟 CI 的真实环境，不是直接用本地已经装了一堆包的 venv），`ruff check .` 和 `pytest` 都确认能跑通，避免"本地能跑、CI 跑不了"的坑。

- [x] **14. 日志只用 `print`，没有分级别**（已完成）
  [rag_pipeline.py](../rag_pipeline.py) 里原来 `print(f"[ステップ...] ...")` 的状态输出，全部换成 `logger.info(...)`（`logger = logging.getLogger(__name__)`）；另外在 `_retrieve_relevant_docs()` 里新增了一条 `logger.warning(...)`，检索不到相关内容时会把问题、阈值、实际检索分数一起记下来，方便以后调阈值。
  [app.py](../app.py) 的两处 `except Exception` 里加了 `logger.exception(...)`，把真实报错堆栈记进日志（之前只给用户看友好提示，真实错误信息完全没留痕迹，运维没法排查）。
  [main.py](../main.py) 里**没有改**——它那些 `print` 都是真正的 CLI 用户界面文字（问答交互、错误提示），不是内部状态日志，不属于这次改动范围；但加了一行 `logging.basicConfig(level=logging.INFO, ...)`，保证 `rag_pipeline.py` 里改成 `logger.info()` 的那些状态提示，CLI 用户依然能看到（不加这行的话，Python 默认不显示 INFO 级别日志，会变成一个无声的功能倒退）。
  `app.py` 同样加了 `logging.basicConfig(...)`，格式带时间戳（`%(asctime)s %(levelname)s %(name)s: %(message)s`），方便云端 Log stream 里按时间/级别定位问题。
  本地验证：跑 CLI 版测试"不相关问题"，确认 `INFO` 正常显示 pipeline 各步骤状态、`WARNING` 在检索不到内容时正确打印出具体分数，用户可见的交互文字完全没受影响。

- [x] **15. 生成回答经常异常缓慢，且免费额度一天只有 20 次**（已大幅缓解，换模型解决）
  **现状（根因已更新，比最初判断更严重）**：做检索准确率评测时连续测试，观察到这样的规律：
  ```
  第1题  223.6s  成功
  第2题  155.9s  成功
  第3题  229.7s  成功
  第4题  367.2s  成功（耗时持续走高）
  第5题  235.1s  成功
  第6题  直接报错 429 ResourceExhausted
  ```
  第6题的完整报错：
  ```
  google.api_core.exceptions.ResourceExhausted: 429 You exceeded your current quota...
  Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests
  limit: 20, model: gemini-3.8-flash
  description: Generate content requests per day limit exceeded on Free Tier
  Please retry in 1h36m20s
  ```
  **真正的根因：`gemini-3.8-flash` 这个模型的免费层，每天只给 20 次请求额度（`generate_content_free_tier_requests`，limit: 20/day）。**
  这彻底改写了之前的诊断——之前以为纯粹是"gRPC 库连接不稳定导致随机变慢"，现在看更可能是：**越接近这个每日20次的硬上限，Google 服务器会先"软性拖慢"响应（排队/降速），额度真正耗尽后才直接 429 硬拒绝**。耗时数据从 223s 一路涨到 367s 的趋势，跟这个解释吻合。
  **当前状态**：今天的额度已经被测试跑光了，要等官方提示的 1小时36分钟后，或者等到第二天（太平洋时间零点）配额重置，才能继续调用。
  **之前试过但失败的修复**：给 `ChatGoogleGenerativeAI`/`GoogleGenerativeAIEmbeddings` 加 `transport="rest"` 参数，想绕开 gRPC——结果认证方式直接崩了（变成找 Google Cloud 的"默认凭证"而不是 `GOOGLE_API_KEY`，报 `DefaultCredentialsError`），已回滚。这个修复思路现在看也没对症，因为真正问题是配额不是协议。
  **解决方向（按优先级）**：
  1. **最直接、最该先做的**：去 https://ai.google.dev/gemini-api/docs/rate-limits 查一下**不同模型**各自的免费层每日额度——`gemini-3.8-flash` 给20次可能是因为它是较新/预览性质的模型，换成 `gemini-2.5-flash` 或 `gemini-2.0-flash` 这类更成熟的型号，免费额度大概率高得多（常见的免费层每日额度是几百到上千次）。**这应该是下一步第一个要验证的事**，可能不需要大改代码，只改 `build_qa_chain()` 里的默认 `model_name` 参数。
  2. **治标方案**：给 `ask_question()`/`ask_question_stream()` 加明确的"额度已用完，请稍后再试"提示（捕获 `ResourceExhausted` 异常单独处理，跟第8条已有的通用错误处理区分开，给用户更准确的信息），而不是让用户对着转圈等待或者看到一堆英文报错
  3. **真正的根治方案（如果1解决不了）**：升级到 Google 官方推荐的新包 `google-genai`，但涉及多个依赖包连锁升级，可能跟项目锁定的 `langchain==0.3.7` 系列冲突，工作量不小，优先级低于方向1
  4. **换掉 Gemini**：改用 Groq 等其他免费方案——更大的改动，等方向1验证无效后再考虑
  **这是目前整个项目里影响最严重的问题**（不只是体验问题，是"免费额度一天只能问20次"这种硬性可用性限制），比其他待办都更值得优先处理，建议排在第3、11、12、13、14 这些之前先解决，而且第1步验证成本很低，应该马上试。

  **后续更新：方向1 验证完成，效果显著**
  先试了 `gemini-2.5-flash`——结果**直接 404**：`This model models/gemini-2.5-flash is no longer available to new users`，Google 官方自己报错建议换成 `gemini-3.8-flash`（也就是我们正在用的那个），说明这条路走不通，`gemini-2.5-flash` 虽然在"列出模型"接口里还能查到，但实际调用被拒绝。
  用 `GET https://generativelanguage.googleapis.com/v1beta/models?key=...` 查了这个 key 实际能访问哪些带 "flash" 的模型，列出一批候选（`gemini-3.1-flash-lite`、`gemini-3.5-flash-lite`、`gemini-2.5-flash-lite`、`gemini-flash-lite-latest` 等 "lite" 系列），换了其中的 **`gemini-3.1-flash-lite`** 测试：
  ```
  共测6次调用，全部成功：
  5.0s / 4.6s / 13.7s / 1.8s / 3.2s / 0.5s
  平均耗时 4.76s，最慢 13.7s
  ```
  对比之前 `gemini-3.8-flash` 的 150~367秒，**快了几十倍**，而且回答准确率没有下降（不相关问题依然正确识别为"未找到"）。
  **已把 `build_qa_chain()` 的默认 `model_name` 改成 `gemini-3.1-flash-lite`**。
  **还没验证的部分**：
  - 这个模型的**每日请求额度**具体是多少还不知道（没有刻意测到打满），"lite" 系列按经验通常比标准版额度更高，但没有实测确认具体数字，不排除以后用多了同样会遇到 429
  - 还没拿着这个新模型重新跑一遍完整的 13 题检索准确率评测（之前只测了关键的几题），如果想要更严谨的数据，可以找时间补一次完整评测
  - Azure 云端那边的 Dockerfile/部署配置目前**还是指向旧的默认值**（代码改的是本地文件，还没重新构建镜像、推送、更新 Azure），线上版本还没用上这个更快的模型，需要走一遍"改代码→reBuild镜像→push→az containerapp update"的流程（现在有 CI/CD 了，直接 `git push` 应该就会自动完成）

  **后续更新2：换快模型是有代价的——`gemini-3.1-flash-lite` 会"读了原文但还是答错"，而且是稳定复现的**

  做完整13题评测后（用回原来那份userA的简历），**相关问题正确率 9/10**，平均耗时 3.10秒（最快0.35秒，最慢6.94秒）。唯一答错的一题：

  > 问：「家畜保険システムのプロジェクトで使った言語は何ですか？」（期待答案：C#）
  > 答：「抜粋の中に答えがないため、「わかりません」と答えます。」

  一开始怀疑是检索漏检（`k=3` 太小，把正确片段挤出去了），深挖后发现**不是**——用 `vs.similarity_search_with_score(question, k=16)` 把全部16个chunk的排名都列出来查证，真正包含"家畜保険"+"C#による機能実装"的那个片段，排名第1（分数0.5901），`k=3` 完全覆盖到了。直接打印实际喂给LLM的3段原文+LLM原始回答验证：**那段原文白纸黑字写着项目名和用的语言，模型看完依然回答"わかりません"**。这是模型本身的阅读理解/信息提取失误，跟 `k`、`chunk_size`、相关度阈值这些检索参数完全无关，调这些解决不了。

  **验证是不是偶发——做了两组补充测试**：

  - **A. 重复性测试**：同一个问题（家畜保険系统用什么语言）连续问3次，**3次结果完全一致，都答"わかりません"**。因为代码里 `temperature=0`，这个结果符合预期：说明这不是随机运气差，是对这个特定上下文+问题组合**稳定复现的错误**。
  - **B. 跨文档测试**：换成另外生成的3份假简历（厨师/护士/广告营销三个不同行业），各问2题（共6题），**5题答对、1题答错**：

    ```
    田中健一（シェフ）：2/2 全对
    鈴木美咲（看護師）：2/2 全对
    高橋大輔（広告営業）：1/2，其中一题又答错：
      问："中央アドバタイジング株式会社で担当した案件は何ですか？"（期待：観光）
      答："わかりません。"（原文明明写着"観光プロモーション案件を担当"）
    ```

  **结论**：这类"原文有答案、模型却说不知道"的失误，**不是userA那份简历的特殊情况，换完全不同的人物/行业依然会复现**，说明是 `gemini-3.1-flash-lite` 这个模型本身真实存在、会反复出现的弱点（大概率是"lite"系列模型为了更小更快，在指令遵循/信息提取精度上做了妥协）。

  **目前掌握的整体准确率数据**（截至这次测试，样本量还不大，仅供参考）：
  - 原始userA简历13题测试：9/10 相关问题正确（90%），不相关问题3/3 正确拒绝（100%，含检索层拦截+LLM自我判断两种方式）
  - 新增跨文档验证6题：5/6 正确（约83%）
  - 合并来看，**相关问题整体正确率大致在 85% 左右**，失败模式集中在"同一段里有多个信息点，模型偶尔漏抓其中一个"这类细节提取场景，跟 `gemini-3.8-flash`（之前没来得及做完整准确率评测，只测过是否成功回答，没细测是否完全正确）相比有没有退步，还没有同口径的对比数据。

  **要不要处理，暂时的判断**：85% 左右的正确率，对一个免费、个人学习项目来说基本可以接受，而且比"等几分钟甚至打不开"（之前 `gemini-3.8-flash` 的状态）体验好得多。如果以后要提高准确率，大概率要在**换回更强的模型**（牺牲一些速度/额度）和**保持 lite 模型 + 接受偶尔读不准**之间做选择，这个权衡目前还没定论，先记录现状，不列为紧急待办。

---

- [x] **16.（🔴 严重 bug，已修复）`build_vector_store(persist_directory=None)` 在同一进程内会把不同文档的向量库"串"在一起**（难度：低，影响：高）

  **发现经过**：为了对比"同一份简历、不同 chunk_size"和"同一 chunk_size、不同简历"的准确率，写了个评测脚本，在同一个 Python 进程里连续调用多次 `build_vector_store(chunks, persist_directory=None)`（分别传入 userA 简历和另外3份测试用假简历）。广度测试那组数据准确率低得不正常（田中健一25%、鈴木美咲50%、高橋大輔25%），其中最可疑的一条：问田中健一（厨师）"持有什么资格"，**回答的是 AI-900/AZ-900/G検定——这是 userA 的资格，根本不在田中健一那份文档里**。

  **验证过程**：写了个最小复现脚本，在同一进程里先后建两个完全无关的迷你文档（"苹果"、"汽车"）的向量库，`persist_directory=None`：
  ```python
  vs1 = build_vector_store([Document("...苹果...")], persist_directory=None)
  vs2 = build_vector_store([Document("...汽车...")], persist_directory=None)
  # vs2 应该只含"汽车"这1条，实际 vs2._collection.count() 返回 2
  # 用 vs2 搜"苹果"，真的搜到了"苹果"那段内容
  ```
  确认 bug 真实存在。

  **根因**：`Chroma.from_documents()` 有个 `collection_name` 参数，**不手动指定的话默认值固定是 `'langchain'`**。`persist_directory=None` 时底层用的是进程内的临时 Chroma 客户端，只要 collection 名字没变，同一进程里多次调用会不断往同一个 collection 里追加数据，不会自动清空重建。

  **影响范围（重要）**：`app.py`（Web版）的 `build_vector_store(chunks, persist_directory=None)` 分支正是这个用法——**只要 Azure 上那个 Streamlit 进程不重启，不同用户/不同次上传的 PDF，内容会在向量库里持续累积、互相"串台"**，后面的人提问有可能检索到之前别人上传文档的内容。这不只是正确性 bug，上传的如果是简历、合同这类敏感文档，还是一个**真实的隐私泄露风险**。

  **修复**：给每次调用传一个唯一的 `collection_name`（用 `uuid.uuid4()` 生成），保证每次"内存向量库"都是真正独立、互不干扰的：
  ```python
  vector_store = Chroma.from_documents(
      documents=chunks,
      embedding=embeddings,
      collection_name=f"session-{uuid.uuid4()}",
  )
  ```
  修复后用同样的"苹果/汽车"脚本重新验证，`vs2` 记录数正确变回1条，搜"苹果"搜不到了。单元测试、ruff 都重新跑过，没有破坏其他功能。

  **连带影响：这次做的"调参对比"评测数据全部作废**，需要在修复后重新跑一遍才能得出可信结论（深度测试三组 chunk_size 之所以"准确率完全一样"，很可能是因为后面几组的向量库里混进了前面组的数据，掩盖了真实差异，不是"chunk_size真的没影响"这个结论本身可信）。重新评测的结果见下一条。

---

*这份笔记由 Claude 根据 2026-10-01 的项目状态生成，代码一旦改动，部分描述可能过时，建议对照当前代码核对。*
