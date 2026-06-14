# LangChain Production Stack

Four production-grade LangChain applications deployable to **GCP Cloud Run** with GitHub Actions CI/CD.

Stack covers semantic search, multi-strategy RAG, LangGraph stateful agents, and LLMOps patterns (semantic caching, cost tracking, retry middleware). All services run on local sLMs (HuggingFace) with no OpenAI API dependency.

---

## Projects

| # | Project | Stack | Description |
|---|---|---|---|
| 01 | [SmolSearch](01_smolsearch/) | FAISS + LCEL + FastAPI | Streaming semantic search with MMR diversity |
| 02 | [RAGify](02_ragify/) | MultiQueryRetriever + RAGAS + FastAPI | Multi-strategy RAG with evaluation metrics |
| 03 | [AgentFlow](03_agentflow/) | LangGraph + ToolRegistry + FastAPI | Stateful agent with tool dispatch and trace logging |
| 04 | [LLMOps Baseline](04_llmops_baseline/) | SemanticCache + CostTracker + FastAPI | Production LLMOps: caching, retry, cost tracking |

---

## Architecture

```
.
├── 01_smolsearch/          # FAISS semantic search + streaming RAG
│   ├── src/pipeline.py     # SmolSearchPipeline (FAISS, MMR, stream)
│   ├── app/main.py         # FastAPI: /index /search /answer /stream
│   ├── deploy/Dockerfile
│   └── tests/
├── 02_ragify/              # Multi-strategy RAG with RAGAS eval
│   ├── src/pipeline.py     # RAGifyPipeline (similarity, MMR, multi-query, compression)
│   ├── app/main.py         # FastAPI: /index /query
│   ├── deploy/Dockerfile
│   └── tests/
├── 03_agentflow/           # LangGraph stateful agent
│   ├── src/graph.py        # StateGraph + ToolRegistry + TraceWriter
│   ├── app/main.py         # FastAPI: /run
│   ├── deploy/Dockerfile
│   └── tests/
├── 04_llmops_baseline/     # LLMOps production patterns
│   ├── src/stack.py        # SemanticCache + CostTracker + LLMOpsStack
│   ├── app/main.py         # FastAPI: /query /metrics
│   ├── deploy/Dockerfile
│   └── tests/
└── .github/workflows/      # CI (matrix test) + 4 per-project deploy workflows
```

---

## Tech stack

- **LangChain 0.3** / **LCEL** — composable chain pipelines with streaming
- **LangGraph 0.2** — stateful multi-node graphs with conditional routing
- **LangSmith** — offline JSONL trace logging (live when `LANGSMITH_API_KEY` set)
- **FAISS** — dense vector similarity search (CPU)
- **RAGAS** — RAG evaluation (context recall, semantic similarity)
- **FastAPI + uvicorn** — production-grade async HTTP API
- **HuggingFace Transformers** — local sLM inference, no vendor API required
- **GCP Cloud Run** — serverless container deployment
- **GitHub Actions** — CI matrix testing + CD per-project deploy pipelines

---

## Quickstart

```bash
# Install and run any project
pip install -r 01_smolsearch/requirements.txt
PYTHONPATH=01_smolsearch uvicorn 01_smolsearch.app.main:app --reload --port 8080

# Unit tests
PYTHONPATH=01_smolsearch pytest 01_smolsearch/tests/ -v
```

---

## Deploy to GCP Cloud Run

See [DEPLOYMENT.md](DEPLOYMENT.md) for full GCP setup: Artifact Registry, service account, IAM permissions.

Required GitHub repository secrets: `GCP_PROJECT_ID`, `GCP_SA_KEY`, `GCP_REGION`.

Each push to `main` that touches a project directory triggers its deploy workflow automatically.

---

## API endpoints

| Service | Method | Path | Description |
|---|---|---|---|
| SmolSearch | POST | `/index` | Load documents into FAISS |
| SmolSearch | POST | `/search` | Similarity or MMR retrieval |
| SmolSearch | POST | `/stream` | Streaming RAG answer |
| RAGify | POST | `/index` | Load documents |
| RAGify | POST | `/query` | RAG with strategy selection |
| AgentFlow | POST | `/run` | Submit task to LangGraph agent |
| LLMOps | POST | `/query` | Query with semantic cache + retry |
| LLMOps | GET | `/metrics` | Token counts and latency stats |
| All | GET | `/health` | Health check |
