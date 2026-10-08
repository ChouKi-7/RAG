# RAG入門プロジェクト

このプロジェクトは「PDFファイルの内容についてAIに質問できる」最小限のRAG(検索拡張生成)アプリです。

## 全体の流れ(RAGの仕組み)

1. PDFを読み込んでテキストに変換する
2. テキストを小さな断片(チャンク)に分割する
3. 各チャンクを「埋め込みベクトル(embedding)」に変換し、ベクトルDBに保存する
4. ユーザーが質問すると、質問文もベクトル化し、ベクトルDBから関連する断片を検索する
5. 検索した断片＋質問文をLLM(Claude/GPTなど)に渡し、回答を生成させる

## セットアップ手順

### 1. Python仮想環境を作る

```bash
python3 -m venv venv
source venv/bin/activate    # Windowsの場合: venv\Scripts\activate
```

### 2. 必要なライブラリをインストール

```bash
pip install -r requirements.txt
```

### 3. APIキーを設定する

`.env.example` を `.env` にコピーして、自分のAPIキーを入力してください。

```bash
cp .env.example .env
```

Google Gemini(無料枠あり)のAPIキーは以下から取得できます:
https://aistudio.google.com/app/apikey

(Claude版のコードはコメントアウトで残してあります。切り替える場合は `rag_pipeline.py` / `main.py` / `requirements.txt` 内のコメントを参照してください。)

### 4. 質問したいPDFを置く

`documents/` フォルダに、質問したいPDFファイルを1つ入れてください。
(サンプルとして自分の職務経歴書などを使うのもおすすめです)

### 5. 実行する

CLI版(ターミナルで質問):
```bash
python main.py
```

Web版(ブラウザでPDFアップロード＋チャット):
```bash
streamlit run app.py
```

## ファイル構成

```
rag-starter/
├── README.md               このファイル
├── requirements.txt         ローカル実行用の依存ライブラリ一覧
├── requirements-deploy.txt  クラウドデプロイ用の依存ライブラリ一覧(軽量版)
├── .env.example             APIキー設定のテンプレート
├── main.py                  CLI版メインプログラム
├── app.py                   Web版(Streamlit)メインプログラム
├── Dockerfile                クラウドデプロイ用のコンテナ定義
├── documents/                質問対象のPDFを置く場所
├── docs/                     学習ノート・デプロイノート
└── rag_pipeline.py          RAGの処理ロジック(コアの仕組み)
```

## 学習のポイント

- `rag_pipeline.py` の中身を読むと、RAGの5ステップがそのままコードになっていることが分かります
- まずは動かしてみて、その後コードを1行ずつ読んでいくのがおすすめです
- 詳しい解説・デプロイ手順は [docs/project-notes.ja.md](docs/project-notes.ja.md)、[docs/azure-deploy-notes.ja.md](docs/azure-deploy-notes.ja.md) にまとめてあります(中国語版は同じファイル名の `.md` 版)

## Azureへのデプロイ

Web版(`app.py`)をDockerコンテナ化し、Azure Container Apps にデプロイ済みです。

- **デプロイ日**: 2026年10月8日
- **使用サービス**: Azure Container Apps(Consumptionプラン、`--min-replicas 0` でアクセスがない時は自動スケールダウン)
- **イメージ保管先**: Docker Hub

**注意**: このデプロイはAzureの無料アカウント(登録から30日間有効な無料クレジット)を使って作成したものです。登録日から30日が経過すると、サブスクリプションの状態によっては有料プランへの移行やリソースの利用制限が発生する可能性があり、**デモURLが将来的にアクセスできなくなる可能性があります**。その場合は [docs/azure-deploy-notes.ja.md](docs/azure-deploy-notes.ja.md) の手順に従って自分のAzureアカウントで再デプロイしてください。
