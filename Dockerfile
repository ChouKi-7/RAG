FROM python:3.11-slim

WORKDIR /app

# 依存ライブラリのインストール(キャッシュを効かせるため先にコピー)
COPY requirements-deploy.txt .
RUN pip install --no-cache-dir -r requirements-deploy.txt

# アプリ本体
COPY rag_pipeline.py app.py ./

# クラウドでは軽量な Gemini の埋め込みAPIを使う
ENV EMBEDDING_PROVIDER=google

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
