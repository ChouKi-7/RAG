# rag-starter プロジェクトノート

> 対象：RAGを学び始めたばかりで、まだコードの細部が分からない自分へ。
> 使い方：このプロジェクトが何だったか忘れたら、これを読めば思い出せる。

---

## 一、このプロジェクトは何をするものか

**一言でいうと**：PDFファイルに対して自然言語で質問すると、AIがPDFの中から関連する内容を探し出し、それをもとに回答してくれる——つまり適当に答えをでっち上げるのではない、ということ。

この「まず検索してから回答する」方式を **RAG（Retrieval-Augmented Generation、検索拡張生成）** と呼ぶ。

**たとえ話**：試験で「持ち込み可」を許されているようなもの。AIは自分の記憶だけで答えるのではなく、まず本（PDF）をめくって質問に最も関連する箇所を見つけ、その内容をもとに言葉を組み立てて回答する。こうすることで、AIが学習データに含まれていない内容（例えば自分の職務経歴書や社内文書）にも答えられるし、回答の根拠を確認できるというメリットがある。

---

## 二、コードは何をしているか（ステップごとの解説）

このプロジェクトの核となる2つのファイル：

- `main.py` —— 「外側」：ユーザーの入力を受け取り、結果を表示し、全体の流れをつなぐ
- `rag_pipeline.py` —— 「中身」：RAGの5つのステップ、1ステップ=1関数で実装されている

### rag_pipeline.py の5ステップ

**ステップ1：PDFを読み込む** —— `load_pdf()`
```python
loader = PyPDFLoader(pdf_path)
documents = loader.load()
```
PDFを開き、「ページ単位」でテキストを取り出す。この時点では単なるテキストで、コンピュータはまだ意味を理解していない。

**ステップ2：チャンク分割** —— `split_into_chunks()`
```python
splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
chunks = splitter.split_documents(documents)
```
なぜ分割するのか？この後「本をめくって」答えを探す際、ページ全体・本全体を1単位にすると粒度が粗すぎるし、AIの入力に収まらないから。そこで約500文字ごとの小さな断片（チャンク）に分ける。`chunk_overlap=50` は隣り合うチャンクを50文字重複させることで、文の途中でちょうど切れてしまい意味が失われるのを防ぐ。

**ステップ3：ベクトル化してDBに保存** —— `build_vector_store()`
```python
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
vector_store = Chroma.from_documents(documents=chunks, embedding=embeddings, persist_directory=persist_directory)
```
一番重要で、一番抽象的なステップ：
- `embeddings` モデルが**各チャンクのテキストを数値の列（ベクトル）に変換**する。意味が近い文章同士は、数学的な空間上でも近い位置になる。
- `Chroma` は「ベクトルデータベース」で、これらのベクトルを保存し、「類似度検索」（あるベクトルに対して、DB内で最も近いものを高速に探す）ができる。
- このステップはローカルの無料モデルで行われ、Claudeとは関係ない。課金もネット接続も不要。

**ステップ4+5：検索して回答を生成** —— `build_qa_chain()`
```python
llm = ChatAnthropic(model=model_name, temperature=0)
retriever = vector_store.as_retriever(search_kwargs={"k": 3})
qa_chain = RetrievalQA.from_chain_type(llm=llm, retriever=retriever, return_source_documents=True)
```
- `retriever`：質問時にまず質問文もベクトル化し、ベクトルDBから「最も似ている上位3件」（`k=3`）を検索する——これが「検索（Retrieval）」。
- `llm`：実際にClaude APIを呼び出す部分。
- `RetrievalQA`：「検索で得た3件の原文」＋「質問文」をまとめてClaudeに渡し、その原文をもとに回答させる——これが「拡張生成（Augmented Generation）」。

**実際の質問応答** —— `ask_question()`
```python
result = qa_chain.invoke({"query": question})
return result["result"], result["source_documents"]
```
2つのものを返す：AIの回答テキストと、参照した原文（根拠として確認できるようにするため）。

### main.py がこの5ステップをどうつなげているか

```python
documents = load_pdf(pdf_path)             # ステップ1
chunks = split_into_chunks(documents)      # ステップ2
vector_store = build_vector_store(chunks)  # ステップ3
qa_chain = build_qa_chain(vector_store)    # ステップ4+5、「パイプ」を組み立てるだけ

while True:
    question = input("質問: ")
    answer, sources = ask_question(qa_chain, question)  # ループのたびに実際に質問する
```
起動時にPDFを一度処理し、ベクトルDBと質問応答チェーンを構築する。その後ループに入り、質問を入力するたびに同じベクトルDBで検索・回答し、"exit" で終了する。

### 一言まとめ

> 「ドキュメントを断片に分割してベクトル化し保存しておく。ユーザーが質問したら、意味的に最も関連する断片を検索し、その断片と質問文を一緒に大規模言語モデルに渡して、実際の原文に基づいて回答させる仕組み。」

---

## 三、現在の状態（重要：コードの元々の設計と異なる）

プロジェクトはもともとClaude（有料API）で回答を生成する設計だったが、Claudeのキー取得には先に課金が必要なため、**現在はGoogle Geminiの無料プランに切り替え済み**：

- [rag_pipeline.py](../rag_pipeline.py)、[main.py](../main.py)、[requirements.txt](../requirements.txt)、[.env.example](../.env.example) 内のClaude関連コード（`ChatAnthropic`、`ANTHROPIC_API_KEY`、`langchain-anthropic`）は**すべてコメントアウトして保持しており、削除はしていない**。Claudeに戻したい場合はコメントを外し、Gemini側をコメントアウトすればよい。
- 現在実際に使われているのは `ChatGoogleGenerativeAI`、モデル名は `gemini-2.5-flash`、必要な環境変数は `.env` 内の `GOOGLE_API_KEY`（https://aistudio.google.com/app/apikey で無料取得）。
- `langchain-google-genai` は既にインストール済み（`pip install langchain-google-genai==2.0.7`）。

したがって上の「二、コード解説」で触れた `ChatAnthropic` / `llm = ChatAnthropic(...)` は、頭の中で `ChatGoogleGenerativeAI` に置き換えて読めばよい——**役割・仕組みは全く同じ**（どちらも「クラウドの大規模モデルを呼び出して理解・回答生成する」）、プロバイダーが変わっただけなので解説内容を書き直す必要はない。

## 四、現在の課題・TODOリスト

**並び順のルール**：上から下 = 優先度が高い順、同じ優先度なら簡単な方が上。解決したらチェックを入れる。

- [x] **1. モデル名が無効な可能性があり、エラーの原因になる**（難易度：非常に低、優先度：最高）
  場所：`rag_pipeline.py` 60行目、`model_name: str = "claude-sonnet-4-6"`
  これは実在するAnthropicのモデルIDではなく、呼び出し時に「model not found」エラーになる可能性が高い。
  → 実在する有効なモデルID（例：`claude-sonnet-5`）に変更し、できれば環境変数で上書きできるようにする。

- [x] **2. `.gitignore` が存在せず、漏洩・誤コミットのリスクがある**（難易度：低、優先度：高）
  現状、`.DS_Store` が既にgitにコミットされている。`venv/`、`.env`（APIキーが入っている）、今後生成される `chroma_db/` も、たまたままだコミットされていないだけ。
  → `.gitignore` を新規作成（`venv/`、`.env`、`chroma_db/`、`.DS_Store`、`__pycache__/` を除外）し、誤って追加済みの `.DS_Store` をgitから削除する。

- [ ] **3. PDFが複数ある場合、無言で最初の1つだけを使う**（難易度：低、優先度：中）
  場所：`main.py` 15〜21行目 `find_pdf_in_documents()`。`documents/` に複数のPDFがある場合、`pdf_files[0]` だけを使い、他のファイルが無視されたことをユーザーに伝えない。
  → 「PDFがN個見つかりました。最初の1つを使用します：xxx.pdf」のような表示を追加する。

- [x] **4. 非推奨のimportパスを使っている**（完了）
  もともと `rag_pipeline.py` では `langchain_community.vectorstores.Chroma` と `langchain_community.embeddings.HuggingFaceEmbeddings` を使っていたが、独立パッケージの `langchain-chroma==0.1.4` / `langchain-huggingface==0.1.2` に移行し、非推奨警告は出なくなった。
  注意点：インストール時に最初誤って最新版を入れてしまい、`langchain-core` が1.x系に上がってプロジェクトが固定している `langchain==0.3.7` 系と衝突した（`pip check` でエラー）。その後、互換性のある旧バージョンに戻して解決した——今後langchainエコシステムのパッケージを追加する際は、既存バージョンと互換性のあるバージョン番号を指定し、最新版をそのまま入れないよう注意する。

- [x] **5. 毎回実行のたびに全embeddingを再計算しており、無駄が多い**（完了）
  `build_vector_store()` は、`persist_directory`（`./chroma_db`）が既に存在しかつ空でなければ `Chroma(persist_directory=..., embedding_function=...)` で既存DBを読み込み、存在しなければ `Chroma.from_documents()` で新規作成するように変更した。検証済み：`python main.py` を連続2回実行すると、2回目は「既存のベクトルDBを読み込みました」と表示され、レコード数は16件のまま増えない。
  補足：この修正により、テスト中に見つかった「データ重複」の問題（下記の新発見の問題を参照）も同時に解決した——以前は実行のたびに16個のチャンクが同じDBに再書き込みされ、レコード数が32、48…と増えていっていた。

- [x] **6. 回答生成モデルを無料プランに変更する**（完了：Google Geminiに切り替え済み。上の「三、現在の状態」参照）
  理由：ステップ4+5の「質問を理解して回答を生成する」モデルは元々Claude（`ChatAnthropic`）で、これは有料APIでありキー取得には先に課金が必要だった。Geminiに切り替えたことで課金不要、無料枠でテストできるようになった。Claude関連コードは削除せずコメントアウトのみなので、いつでも戻せる。

  その他の無料・低コストの代替案は参考として残す（現時点では切り替えの必要なし）：

  | 方式 | 説明 | 必要な変更 |
  |---|---|---|
  | **Google Gemini** | 無料枠あり。Google AI Studioでキーを取得 | `langchain-google-genai` に変更、`ChatAnthropic` → `ChatGoogleGenerativeAI` |
  | **Groq** | Llama / Mixtral などのオープンソースモデルを無料で高速呼び出し可能 | `langchain-groq` に変更、`ChatAnthropic` → `ChatGroq` |
  | **Ollama（完全ローカル）** | オープンソースモデル（Llama 3など）を完全にローカルで実行。APIキー不要・ネット接続不要・無料だが、PCの性能が必要でモデル（数GB）の事前ダウンロードが必要 | `langchain-ollama` に変更、`ChatAnthropic` → `ChatOllama`、別途Ollama本体のインストールが必要 |
  | **Hugging Face Inference API** | 無料枠でホスティングされたオープンソースモデルを呼び出せる | `langchain-huggingface` のLLM用インターフェースに変更 |

  共通の変更手順（どの方式を選んでも流れは同じ）：
  1. 対応する新しいライブラリを `pip install`
  2. `rag_pipeline.py` の `from langchain_anthropic import ChatAnthropic` を新ライブラリのimportに変更
  3. `build_qa_chain()` 内の `ChatAnthropic(...)` を新しいモデルのクラスに変更
  4. 該当プラットフォームで新しいAPIキーを取得し `.env` に記入（Ollamaはキー不要）

  → これはバグ修正ではなく独立した新しい変更なので優先度は最低。節約したい時・別のモデルを試したい時にやればよい。

- [x] **7.（テスト中に新たに発見）embeddingモデルが日本語に対応しておらず、検索が機能していなかった**（完了）
  現象：日本語の職務経歴書でテストしたところ、「他叫什么」「氏名は何ですか」と聞いてもAIが「わからない」と回答——しかし氏名はPDFの最初の一文「氏名 張 琪」にそのまま書かれていた。調査の結果、原因が判明：元々使っていた `sentence-transformers/all-MiniLM-L6-v2` は主に英語で学習されたモデルで、日本語の意味理解が弱く、ベクトル検索の時点で最も基本的な情報すら見つけられていなかった（検索結果の3件が質問と全く無関係な内容になっていた）。
  → 多言語対応の `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` に変更。変更後、同じ質問で氏名を含む箇所が正しく検索されることを確認した。
  教訓：**embeddingモデルは文書の言語に合わせる必要がある**。英語モデルで日本語・中国語の文書を扱うと、検索部分が静かに機能しなくなる（エラーは出ない）。コードはエラーなく動くため、テストしないと気づきにくい落とし穴。

---

*このノートは2026-10-01時点のプロジェクト状態をもとにClaudeが作成したもの。コードが変更されると内容が古くなる可能性があるため、現在のコードと照らし合わせて確認することを推奨する。*
