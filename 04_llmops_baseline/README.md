# LLMOps Baseline — Production LLMOps Reference Architecture

Reference implementation of a production LLMOps stack: LCEL chains, structured Pydantic output, semantic caching, async streaming, tiktoken cost tracking, and LangSmith dataset annotation for automated regression testing.

## Architecture

```
Client Request
    │
    ▼
FastAPI (async, SSE streaming)
    │
    ▼
LLMOpsStack
    ├── SemanticCache (cosine similarity, threshold=0.95)
    │       └── hit → return cached response
    ├── LCEL chain.with_retry(3)
    │       └── ChatHuggingFace | StrOutputParser
    ├── CostTracker (tiktoken: n_tokens_in, n_tokens_out, latency_ms)
    └── TraceWriter → JSONL or LangSmith
```

**Stack:** LangChain · FastAPI · tiktoken · SemanticCache · LangSmith · Docker · Vertex AI

## API

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness check |
| POST | `/invoke` | Blocking LLM call with cache |
| POST | `/stream` | SSE streaming response |
| GET | `/metrics` | Cost tracker summary |
| GET | `/cache/stats` | Cache hit rate |

## Key features

- **Semantic cache**: 95%-cosine-similarity threshold prevents redundant LLM calls for paraphrased queries
- **Retry middleware**: `chain.with_retry(stop_after_attempt=3)` handles transient errors transparently
- **Cost tracking**: every call records input/output tokens and latency — queryable at `/metrics`
- **Streaming SSE**: `StreamingResponse` with async generator; integrates with browser `EventSource`

## Run

```bash
bash run.sh
uvicorn app.main:app --port 8080
# Load test:
# pip install locust && locust -f tests/locustfile.py --host http://localhost:8080
```

## GCP Vertex AI deploy

```bash
bash deploy/vertex_deploy.sh your-project-id us-central1
```
