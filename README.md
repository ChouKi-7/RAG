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

Anthropic(Claude)のAPIキーは以下から取得できます:
https://console.anthropic.com/

### 4. 質問したいPDFを置く

`documents/` フォルダに、質問したいPDFファイルを1つ入れてください。
(サンプルとして自分の職務経歴書などを使うのもおすすめです)

### 5. 実行する

```bash
python main.py
```

## ファイル構成

```
rag-starter/
├── README.md          このファイル
├── requirements.txt    必要なライブラリ一覧
├── .env.example        APIキー設定のテンプレート
├── main.py             メインプログラム(ここから実行する)
├── documents/           質問対象のPDFを置く場所
└── rag_pipeline.py     RAGの処理ロジック(コアの仕組み)
```

## 学習のポイント

- `rag_pipeline.py` の中身を読むと、RAGの5ステップがそのままコードになっていることが分かります
- まずは動かしてみて、その後コードを1行ずつ読んでいくのがおすすめです
- 面接で説明する時は「PDFを断片に分けてベクトル化し、質問に関連する部分だけを検索してLLMに渡す仕組み」と言えれば十分です
