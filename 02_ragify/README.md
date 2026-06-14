# RAGify — Evaluated Retrieval-Augmented Generation System

Multi-strategy RAG pipeline with automated quality measurement. Supports similarity, MMR, multi-query, and compression retrieval — all evaluated with RAGAS on a held-out test set.

## Architecture

```
Document Corpus
    │
    ▼
Ingestion: split → embed (all-MiniLM-L6-v2) → FAISS index
    │
Query ──► Retriever (4 modes) ──► Context
                                      │
                              SmolLM2 (LCEL chain)
                                      │
                              Answer + RAGAS Evaluation
                              (context_recall, semantic_similarity)
```

**Stack:** LangChain 0.3 · FAISS · ChromaDB · MultiQueryRetriever · RAGAS · FastAPI · Cloud Run

## API

| Method | Path | Description |
|---|---|---|
| POST | `/index` | Ingest documents |
| POST | `/query` | RAG query (select retrieval mode) |
| GET | `/eval` | Run RAGAS on held-out eval set |

## Run

```bash
bash run.sh                           # local smoke
uvicorn app.main:app --port 8080      # dev server
bash deploy/gcp_deploy.sh             # Cloud Run
```

## Retrieval modes

| Mode | Method | When to use |
|---|---|---|
| `similarity` | FAISS cosine | Default; fast |
| `mmr` | FAISS MMR | Diverse results |
| `multi_query` | N-query expansion | Ambiguous queries |
| `compression` | EmbeddingsFilter | Reduce context noise |

## RAGAS metrics

After indexing and querying, call `GET /eval` to run RAGAS on 10 held-out QA pairs:
- **context_recall** >= 0.70 expected
- **semantic_similarity** >= 0.75 expected
