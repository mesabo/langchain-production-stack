FROM python:3.11-slim
LABEL maintainer="mesabo <mesabo18@gmail.com>" \
      org.opencontainers.image.title="SmolSearch" \
      org.opencontainers.image.description="Semantic search + RAG over indexed documents" \
      org.opencontainers.image.authors="mesabo" \
      org.opencontainers.image.url="https://mesabo.github.io" \
      org.opencontainers.image.source="https://github.com/mesabo/langchain-production-stack"

WORKDIR /app

# System dependencies for FAISS and sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV HF_HOME=/app/.cache/huggingface
ENV PYTHONPATH=/app

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
