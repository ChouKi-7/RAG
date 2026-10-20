# rag-starter

PDFファイルの内容について自然言語で質問できる、RAG(検索拡張生成)アプリケーションです。
文書をベクトル化して検索し、関連する箇所をもとにLLMが回答を生成する仕組みを、最小構成で実装しています。

## デモ

🔗 **https://rag-starter-app.happyrock-4818498e.japaneast.azurecontainerapps.io/**

Azure Container Apps 上にデプロイ済みです。PDFをアップロードして質問できます。

> Azureの無料クレジットを利用しているため、将来的にデモURLへアクセスできなくなる可能性があります。その場合は下記の手順でローカル環境を構築してください。

## 主な機能

- PDFアップロード＋チャット形式のWeb UI(Streamlit)
- コマンドライン版(CLI)も用意
- 日本語・中国語・英語などの多言語文書に対応(多言語embeddingモデル使用)
- Dockerコンテナ化し、Azure Container Apps にデプロイ済み
- ローカル実行は無料(埋め込みは無料のローカルモデル、生成はGoogle Geminiの無料枠を利用)

## 使用技術

| カテゴリ | 技術 |
|---|---|
| LLM / Embedding | Google Gemini API(`langchain-google-genai`) |
| オーケストレーション | LangChain |
| ベクトルDB | Chroma |
| Web UI | Streamlit |
| コンテナ / デプロイ | Docker, Azure Container Apps |

## 仕組み(RAGの5ステップ)

1. PDFを読み込んでテキストに変換する
2. テキストを小さな断片(チャンク)に分割する
3. 各チャンクを埋め込みベクトル(embedding)に変換し、ベクトルDBに保存する
4. ユーザーの質問文もベクトル化し、ベクトルDBから関連する断片を検索する
5. 検索した断片と質問文をLLMに渡し、回答を生成させる

実装は `rag_pipeline.py` に、ステップがそのまま関数として分かれています。

## セットアップ

### 1. Python仮想環境を作る

```bash
python3 -m venv venv
source venv/bin/activate    # Windowsの場合: venv\Scripts\activate
```

### 2. 依存ライブラリをインストール

```bash
pip install -r requirements.txt
```

### 3. APIキーを設定する

```bash
cp .env.example .env
```

`.env` に Google Gemini のAPIキーを設定してください(無料枠あり)。取得先: https://aistudio.google.com/app/apikey

### 4. 質問対象のPDFを置く

`documents/` フォルダに、質問したいPDFファイルを1つ入れてください。

### 5. 実行する

CLI版(ターミナルで質問):
```bash
python main.py
```

Web版(ブラウザでPDFアップロード＋チャット):
```bash
streamlit run app.py
```

## デプロイ

Web版(`app.py`)をDockerコンテナ化し、Azure Container Apps(Consumptionプラン)にデプロイしています。イメージは Docker Hub でホストし、アクセスがない時はインスタンスを自動的に0台までスケールダウンするよう設定しています。

詳細な手順は [docs/azure-deploy-notes.ja.md](docs/azure-deploy-notes.ja.md) を参照してください。

## プロジェクト構成

```
rag-starter/
├── README.md                このファイル
├── requirements.txt          ローカル実行用の依存ライブラリ一覧
├── requirements-deploy.txt   クラウドデプロイ用の依存ライブラリ一覧(軽量版)
├── .env.example              APIキー設定のテンプレート
├── main.py                   CLI版メインプログラム
├── app.py                    Web版(Streamlit)メインプログラム
├── Dockerfile                 クラウドデプロイ用のコンテナ定義
├── rag_pipeline.py           RAGの処理ロジック(コア実装)
├── documents/                 質問対象のPDFを置く場所
└── docs/                      実装・デプロイの詳細ノート(日本語/中国語)
```

## ドキュメント

- [docs/project-notes.ja.md](docs/project-notes.ja.md) — 実装の詳細解説
- [docs/azure-deploy-notes.ja.md](docs/azure-deploy-notes.ja.md) — Azureデプロイ手順
- [docs/commands-cheatsheet.md](docs/commands-cheatsheet.md) — Docker/Azureコマンド一覧

(各ファイルには同名の `.md`(中国語版)も用意しています)
