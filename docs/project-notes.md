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

- [ ] **3. 多个 PDF 时静默只取第一个**（难度：低，优先级：中）
  位置：`main.py` 第 15-21 行 `find_pdf_in_documents()`，`documents/` 里有多个 PDF 时只取 `pdf_files[0]`，不会提示用户还有文件被忽略。
  → 加一行提示："检测到 N 个 PDF，使用第一个：xxx.pdf"。

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

---

*这份笔记由 Claude 根据 2026-10-01 的项目状态生成，代码一旦改动，部分描述可能过时，建议对照当前代码核对。*
