# rag-starter

RAG(検索拡張生成)の学習・実験用プロジェクトです。PDFファイルの内容について自然言語で質問できる単一文書質問応答(v1、完成済み)を土台に、現在は複数の履歴書から条件に合う人を探す多文書スクリーニング機能(v2、開発中)に取り組んでいます。

## バージョン

| バージョン | 機能 | 状態 |
|---|---|---|
| **v1** | 1つのPDFについて自然言語で質問できる、単一文書のRAG質問応答 | ✅ 完成・Azureに本番デプロイ済み |
| **v2** | 複数の履歴書(PDF)の中から、「Pythonを3年以上学び、プロジェクトを独立して担当できる人」のような条件に合う候補者を探す、多文書スクリーニング機能 | 🚧 開発中(ローカルのCLIで動作確認済み、Web UI・本番デプロイは未着手) |

v1は単純な「類似度検索して回答する」方式ですが、v2が扱う「定量条件+定性条件が混ざった、網羅性が必要な質問」にはこの方式がそのまま使えないため、構造化データ抽出+条件フィルタ+LLMによる個別再確認、という別のパイプラインを設計しています。設計の詳細は [docs/design-notes.ja.md](docs/design-notes.ja.md)、v2の実装詳細は [docs/resume-screening-notes.ja.md](docs/resume-screening-notes.ja.md) を参照してください。

## デモ(v1)

🔗 **https://rag-starter-app.happyrock-4818498e.japaneast.azurecontainerapps.io/**

Azure Container Apps 上にデプロイ済みです。PDFをアップロードして質問できます。

> Azureの無料クレジットを利用しているため、将来的にデモURLへアクセスできなくなる可能性があります。その場合は下記の手順でローカル環境を構築してください。

## 主な機能

- PDFアップロード＋チャット形式のWeb UI(Streamlit、ストリーミング出力対応)
- コマンドライン版(CLI)も用意
- 日本語・中国語・英語などの多言語文書に対応(多言語embeddingモデル使用)
- 関連度スコアによるフィルタリングで、文書に根拠のない回答を抑制
- Dockerコンテナ化し、Azure Container Apps にデプロイ済み
- GitHub Actionsによるテスト・ビルド・デプロイの自動化(CI/CD、テスト失敗時はデプロイをブロック)
- ローカル実行は無料(埋め込みは無料のローカルモデル、生成はGoogle Geminiの無料枠を利用)

## 使用技術

| カテゴリ | 技術 |
|---|---|
| LLM / Embedding | Google Gemini API(`langchain-google-genai`) |
| オーケストレーション | LangChain |
| ベクトルDB | Chroma |
| Web UI | Streamlit |
| コンテナ / デプロイ | Docker, Azure Container Apps |
| CI/CD | GitHub Actions |
| テスト / Lint | pytest, ruff |

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

### v2(複数履歴書スクリーニング、開発中)を試す

`documents/` フォルダに複数の履歴書PDFを入れてから:
```bash
python resume_screening.py
```
「Pythonを3年以上学び、プロジェクトを独立して担当できる人を探す」のように条件を自然言語で入力すると、該当する候補者と判断根拠(原文引用)を表示します。CLIのみで、Web UI・Azureへのデプロイはまだ対応していません。詳細は [docs/resume-screening-notes.ja.md](docs/resume-screening-notes.ja.md) を参照してください。

## デプロイ

Web版(`app.py`)をDockerコンテナ化し、Azure Container Apps(Consumptionプラン)にデプロイしています。イメージは Docker Hub でホストし、アクセスがない時はインスタンスを自動的に0台までスケールダウンするよう設定しています。

`main`ブランチへのpushをトリガーに、GitHub Actionsが lint・単体テスト → Dockerイメージのビルド・push → Azure Container Appsへの反映 を自動実行します(テスト・lintが通らない場合はデプロイされません)。

詳細な手順は [docs/azure-deploy-notes.ja.md](docs/azure-deploy-notes.ja.md)(デプロイ)、[docs/cicd-notes.ja.md](docs/cicd-notes.ja.md)(CI/CD構築)を参照してください。

## プロジェクト構成

```
rag-starter/
├── README.md                 このファイル
├── requirements.txt           ローカル実行用の依存ライブラリ一覧
├── requirements-deploy.txt    クラウドデプロイ用の依存ライブラリ一覧(軽量版)
├── requirements-dev.txt       テスト/Lint用の依存ライブラリ(pytest, ruff)
├── pytest.ini                 pytest設定
├── .env.example               APIキー設定のテンプレート
├── main.py                    CLI版メインプログラム(v1)
├── app.py                     Web版(Streamlit)メインプログラム(v1)
├── Dockerfile                  クラウドデプロイ用のコンテナ定義
├── rag_pipeline.py            RAGの処理ロジック(v1コア実装)
├── resume_screening.py        複数履歴書スクリーニング機能(v2、開発中)
├── tests/                      単体テスト
├── .github/workflows/          CI/CDパイプライン定義(GitHub Actions)
├── documents/                  質問対象のPDFを置く場所
└── docs/                       実装・設計・デプロイの詳細ノート(日本語/中国語)
```

## ドキュメント

- [docs/project-notes.ja.md](docs/project-notes.ja.md) — v1実装の詳細解説
- [docs/resume-screening-notes.ja.md](docs/resume-screening-notes.ja.md) — v2(複数履歴書スクリーニング)の実装詳細
- [docs/design-notes.ja.md](docs/design-notes.ja.md) — 設計判断の記録(何をなぜそう設計したか)
- [docs/bug-log.ja.md](docs/bug-log.ja.md) — 発見・対応したバグの記録
- [docs/parameter-tuning.ja.md](docs/parameter-tuning.ja.md) — パラメータチューニングの実験記録
- [docs/azure-deploy-notes.ja.md](docs/azure-deploy-notes.ja.md) — Azureデプロイ手順
- [docs/cicd-notes.ja.md](docs/cicd-notes.ja.md) — CI/CD構築手順
- [docs/commands-cheatsheet.md](docs/commands-cheatsheet.md) — Docker/Azureコマンド一覧

(各ファイルには同名の `.md`(中国語版)も用意しています)
