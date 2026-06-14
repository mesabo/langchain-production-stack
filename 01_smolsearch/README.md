# SmolSearch — Semantic Search API

A production-grade semantic document search service built on FAISS, LCEL, and FastAPI. Supports similarity search, MMR diversity search, and streaming RAG-augmented answers — deployable locally or on GCP Cloud Run.

## Architecture

```
User Query
    │
    ▼
FastAPI /search or /stream
    │
    ▼
SmolSearchPipeline
    ├── HuggingFaceEmbeddings (all-MiniLM-L6-v2) ──► embed query
    ├── FAISS index ──────────────────────────────► retrieve k docs
    │       └── MMR variant for diversity
    └── LCEL chain (ChatHuggingFace | StrOutputParser) ► synthesize answer
            └── stream_answer(): yields token chunks
```

**Stack:** LangChain 0.3 · FAISS · sentence-transformers · SmolLM2-135M · FastAPI · Docker · GCP Cloud Run

---

## API endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Service liveness check |
| POST | `/index` | Index a list of documents |
| POST | `/search` | Retrieve top-k similar documents |
| POST | `/answer` | RAG answer (blocking) |
| POST | `/stream` | RAG answer (streaming SSE) |

### Example: index and search

```bash
# Index documents
curl -X POST http://localhost:8080/index \
  -H "Content-Type: application/json" \
  -d '{"documents": ["FAISS enables fast similarity search.", "LangChain builds LLM pipelines."], "ids": ["d1", "d2"]}'

# Similarity search
curl -X POST http://localhost:8080/search \
  -H "Content-Type: application/json" \
  -d '{"query": "What is FAISS?", "k": 2}'

# Streaming answer
curl -X POST http://localhost:8080/stream \
  -H "Content-Type: application/json" \
  -d '{"query": "Explain FAISS.", "k": 2}'
```

---

## Local run

```bash
# Prerequisites: conda activate slm-gpu
bash run.sh             # unit tests + smoke
uvicorn app.main:app --reload --port 8080
```

## GCP Cloud Run deploy

```bash
# Requires: gcloud auth login, project configured
bash deploy/gcp_deploy.sh your-project-id asia-northeast1
```

## Tests

```bash
pytest tests/ -q
```

Expected: 5/5 tests pass in < 60 seconds.

---

## Key design decisions

- **FAISS in-memory index** — no disk I/O for single-instance deployment; for multi-instance, swap with ChromaDB + GCS backend (see `02_ragify/`).
- **Streaming via FastAPI `StreamingResponse`** — token chunks arrive as plain text; integrate with Server-Sent Events (SSE) for browser clients.
- **CPU-first design** — all models run on CPU by default; add `device_map="auto"` in `build_llm()` and switch to the CUDA Docker image for GPU deployment.
