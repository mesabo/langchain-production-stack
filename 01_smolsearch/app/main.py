"""SmolSearch FastAPI application — streaming semantic search API."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langchain_core.documents import Document

CONFIG_PATH = Path(__file__).parent.parent / "configs" / "app.yaml"
try:
    import yaml
    with open(CONFIG_PATH) as f:
        _CFG = yaml.safe_load(f)
except Exception:
    _CFG = {
        "embed_backbone": "sentence-transformers/all-MiniLM-L6-v2",
        "backbone": "HuggingFaceTB/SmolLM2-135M-Instruct",
        "max_new_tokens": 128,
        "temperature": 0.1,
    }

from src.pipeline import SmolSearchPipeline

_pipeline: SmolSearchPipeline | None = None

_SEED_DOCS = [
    ("seed_01", "LangChain is a framework for building LLM-powered applications using chains, agents, and memory."),
    ("seed_02", "FAISS enables fast approximate nearest-neighbor search over dense embedding vectors at scale."),
    ("seed_03", "RAG (Retrieval-Augmented Generation) combines document retrieval with generative models to reduce hallucination."),
    ("seed_04", "Sentence transformers encode text into fixed-size semantic vectors that capture meaning, not just keywords."),
    ("seed_05", "LangGraph is a library for building stateful multi-agent applications using directed graphs with shared state."),
    ("seed_06", "LoRA (Low-Rank Adaptation) fine-tunes large models by injecting trainable low-rank matrices into attention layers."),
    ("seed_07", "QLoRA combines quantization and LoRA to fine-tune large models on a single consumer GPU with minimal quality loss."),
    ("seed_08", "Cloud Run is Google's serverless container platform that scales to zero when there is no traffic."),
    ("seed_09", "Semantic caching stores LLM responses keyed by embedding similarity to avoid redundant inference calls."),
    ("seed_10", "DPO (Direct Preference Optimization) trains models on human preference pairs without a separate reward model."),
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    pipeline = get_pipeline()
    docs = [Document(page_content=text, metadata={"id": doc_id}) for doc_id, text in _SEED_DOCS]
    pipeline.add_documents(docs)
    yield


def get_pipeline() -> SmolSearchPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = SmolSearchPipeline(_CFG)
    return _pipeline


_TAGS = [
    {
        "name": "Search",
        "description": "Semantic search over the indexed document store. "
                       "Use `similarity` mode for pure nearest-neighbour retrieval, "
                       "`mmr` for diversity-aware Maximum Marginal Relevance results.",
    },
    {
        "name": "Answer",
        "description": "RAG endpoints that retrieve context then call the sLM to generate an answer. "
                       "`/answer` blocks until complete; `/stream` streams tokens as they are produced.",
    },
    {
        "name": "Index",
        "description": "Add documents to the in-memory FAISS index. "
                       "10 seed documents are loaded automatically on startup.",
    },
    {
        "name": "System",
        "description": "Health check and readiness probe.",
    },
]

app = FastAPI(
    title="SmolSearch",
    version="1.0.0",
    description="""
## Streaming semantic search powered by SmolLM2 + FAISS

**SmolSearch** is a production-style RAG search API built on LCEL (LangChain Expression Language).

### Quick start
1. The service pre-loads **10 seed documents** about sLM/RAG concepts on startup — no indexing needed to try it.
2. Call **`POST /search`** with a natural language query to retrieve relevant chunks.
3. Call **`POST /answer`** to get a generated answer grounded in retrieved context.
4. Call **`POST /stream`** for token-by-token streaming (use `curl --no-buffer` or a streaming client).
5. Call **`POST /index`** to add your own documents.

### Models
| Field | Type | Notes |
|-------|------|-------|
| Embedding | `all-MiniLM-L6-v2` | 384-dim sentence encoder |
| Generation | `SmolLM2-135M-Instruct` | causal decoder, 135M params |

### Retrieval modes
| Mode | Description |
|------|-------------|
| `similarity` | Cosine nearest-neighbour — fastest, highest relevance |
| `mmr` | Maximum Marginal Relevance — trades some relevance for diversity |
""",
    openapi_tags=_TAGS,
    contact={"name": "sLM Universe Learning", "email": "mesabo18@gmail.com"},
    license_info={"name": "MIT"},
    lifespan=lifespan,
    swagger_ui_parameters={
        "defaultModelsExpandDepth": 3,
        "defaultModelExpandDepth": 3,
        "docExpansion": "list",
        "displayRequestDuration": True,
        "filter": True,
        "tryItOutEnabled": True,
        "syntaxHighlight.theme": "monokai",
        "persistAuthorization": True,
    },
)

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class IndexRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "documents": [
                "LoRA inserts trainable low-rank matrices into each attention layer.",
                "QLoRA combines 4-bit NF4 quantisation with LoRA for GPU-efficient fine-tuning.",
            ],
            "ids": ["lora_intro", "qlora_intro"],
        }
    })

    documents: list[str] = Field(
        ...,
        description="List of plain-text documents to add to the FAISS index. "
                    "Each element becomes one searchable chunk.",
        min_length=1,
        examples=[["LoRA inserts low-rank adapter matrices.", "QLoRA adds 4-bit quantisation."]],
    )
    ids: list[str] | None = Field(
        None,
        description="Optional list of unique IDs, same length as `documents`. "
                    "Auto-generated as `doc_0`, `doc_1`, … when omitted.",
        examples=[["lora_intro", "qlora_intro"]],
    )


class SearchRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {"query": "How does LoRA reduce trainable parameters?", "k": 3, "mode": "similarity"}
    })

    query: str = Field(
        ...,
        description="Natural language search query.",
        min_length=1,
        max_length=512,
        examples=["How does LoRA reduce trainable parameters?"],
    )
    k: int = Field(
        3,
        description="Number of documents to return (top-k by score).",
        ge=1,
        le=20,
        examples=[3],
    )
    mode: Literal["similarity", "mmr"] = Field(
        "similarity",
        description=(
            "Retrieval mode:\n"
            "- `similarity` — pure cosine nearest-neighbour (fastest, highest per-result relevance)\n"
            "- `mmr` — Maximum Marginal Relevance (trades some relevance for diversity across results)"
        ),
    )


class AnswerRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {"query": "What is semantic caching and why does it reduce cost?", "k": 3}
    })

    query: str = Field(
        ...,
        description="Question to answer. The top-k retrieved chunks are injected as context before generation.",
        min_length=1,
        max_length=512,
        examples=["What is semantic caching and why does it reduce cost?"],
    )
    k: int = Field(
        3,
        description="Number of context chunks to retrieve. More chunks → richer context but longer prompt.",
        ge=1,
        le=10,
        examples=[3],
    )


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str = Field(..., description="Always `ok` when the service is up.", examples=["ok"])
    service: str = Field(..., description="Service name identifier.", examples=["smolsearch"])


class IndexResponse(BaseModel):
    indexed: int = Field(..., description="Number of documents successfully added to the index in this call.", examples=[2])
    total: int = Field(..., description="Total number of documents submitted in this request body.", examples=[2])


class SearchDocument(BaseModel):
    content: str = Field(..., description="Full text of the retrieved document chunk.", examples=["LoRA inserts low-rank matrices..."])
    id: str = Field(..., description="Document ID assigned at index time.", examples=["lora_intro"])


class SearchResponse(BaseModel):
    query: str = Field(..., description="Original query string echoed back.", examples=["How does LoRA work?"])
    results: list[SearchDocument] = Field(
        ...,
        description="Ranked list of matching documents, most relevant first.",
    )


class AnswerResponse(BaseModel):
    query: str = Field(..., description="Original question echoed back.", examples=["What is semantic caching?"])
    answer: str = Field(
        ...,
        description="Generated answer from the sLM, grounded in the retrieved context chunks.",
        examples=["Semantic caching stores LLM responses keyed by embedding similarity..."],
    )


_ERR_NO_INDEX = {
    "description": "No documents indexed yet — call `POST /index` first.",
    "content": {"application/json": {"example": {"detail": "No documents indexed yet."}}},
}
_ERR_VALIDATION = {
    "description": "Request body failed validation (missing required field, value out of range, etc.).",
    "content": {"application/json": {"example": {"detail": [{"loc": ["body", "query"], "msg": "field required"}]}}},
}

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/health",
    summary="Health check",
    description="Lightweight liveness probe. Returns `{\"status\": \"ok\"}` if the service is running.",
    tags=["System"],
    response_model=HealthResponse,
)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="smolsearch")


@app.post(
    "/index",
    summary="Add documents to the index",
    description="""
Add one or more plain-text documents to the in-memory FAISS index.

**Notes**
- Documents are embedded with `all-MiniLM-L6-v2` (384-dim) on the fly.
- The index is in-memory; it resets on service restart.
- 10 seed documents about sLM/RAG are pre-loaded at startup — you can start searching immediately.
- If `ids` is omitted, documents are assigned IDs `doc_0`, `doc_1`, …
""",
    tags=["Index"],
    response_model=IndexResponse,
    responses={422: _ERR_VALIDATION},
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "auto_ids": {
                            "summary": "Auto-generated IDs (simplest)",
                            "description": "Let the service assign doc_0, doc_1, … IDs automatically.",
                            "value": {
                                "documents": [
                                    "LoRA (Low-Rank Adaptation) fine-tunes models by injecting small trainable matrices into attention layers.",
                                    "QLoRA combines 4-bit NF4 quantisation with LoRA, enabling fine-tuning on a single consumer GPU.",
                                    "DPO (Direct Preference Optimization) trains on human preference pairs without a separate reward model.",
                                ],
                            },
                        },
                        "custom_ids": {
                            "summary": "Custom IDs (recommended for citation)",
                            "description": "Provide explicit IDs so you can trace which document each search result came from.",
                            "value": {
                                "documents": [
                                    "FAISS IndexFlatL2 performs exact L2 nearest-neighbour search over dense vectors.",
                                    "FAISS IndexHNSWFlat uses a hierarchical graph for approximate search — 10-100× faster at large scale.",
                                ],
                                "ids": ["faiss_flat", "faiss_hnsw"],
                            },
                        },
                    }
                }
            }
        }
    },
)
def index_documents(req: IndexRequest) -> IndexResponse:
    pipeline = get_pipeline()
    docs = [
        Document(page_content=text, metadata={"id": req.ids[i] if req.ids else f"doc_{i}"})
        for i, text in enumerate(req.documents)
    ]
    pipeline.add_documents(docs)
    return IndexResponse(indexed=len(docs), total=len(req.documents))


@app.post(
    "/search",
    summary="Semantic search",
    description="""
Retrieve the top-k most relevant documents for a natural language query.

**Modes**
| Mode | How it works |
|------|--------------|
| `similarity` | Pure cosine nearest-neighbour over FAISS `IndexFlatL2`. Fastest, highest per-result relevance. |
| `mmr` | Maximum Marginal Relevance — re-ranks candidates to balance relevance vs. inter-result diversity. Use when you need varied perspectives. |

**Tip:** start with `similarity` and switch to `mmr` if results feel repetitive.
""",
    tags=["Search"],
    response_model=SearchResponse,
    responses={400: _ERR_NO_INDEX, 422: _ERR_VALIDATION},
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "similarity_basic": {
                            "summary": "Similarity search — top 3 results",
                            "description": "Standard cosine nearest-neighbour: fastest and highest per-result relevance.",
                            "value": {"query": "How does LoRA reduce trainable parameters?", "k": 3, "mode": "similarity"},
                        },
                        "mmr_diverse": {
                            "summary": "MMR search — diverse top 5",
                            "description": "Use MMR when results feel repetitive or cover the same angle multiple times.",
                            "value": {"query": "What are the main fine-tuning techniques for LLMs?", "k": 5, "mode": "mmr"},
                        },
                        "single_result": {
                            "summary": "Best-match only (k=1)",
                            "description": "Return only the single most relevant document.",
                            "value": {"query": "What is semantic caching?", "k": 1, "mode": "similarity"},
                        },
                    }
                }
            }
        }
    },
)
def search(req: SearchRequest) -> SearchResponse:
    pipeline = get_pipeline()
    if pipeline.index is None:
        raise HTTPException(status_code=400, detail="No documents indexed yet.")
    if req.mode == "mmr":
        results = pipeline.search_mmr(req.query, k=req.k)
    else:
        results = pipeline.search(req.query, k=req.k)
    return SearchResponse(
        query=req.query,
        results=[SearchDocument(content=d.page_content, id=d.metadata.get("id", "")) for d in results],
    )


@app.post(
    "/answer",
    summary="RAG answer (blocking)",
    description="""
Retrieve the top-k context chunks and generate a complete answer using the sLM.

**Flow:** `query → FAISS search (k chunks) → prompt assembly → SmolLM2 → answer`

The endpoint **blocks** until the full answer is generated. For token-by-token streaming use `POST /stream`.

**Expected latency:** 2–15 s depending on GPU availability and `max_new_tokens`.
""",
    tags=["Answer"],
    response_model=AnswerResponse,
    responses={400: _ERR_NO_INDEX, 422: _ERR_VALIDATION},
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "concept_question": {
                            "summary": "Concept question (seed docs)",
                            "description": "Works out of the box — the 10 seed docs cover sLM concepts.",
                            "value": {"query": "What is semantic caching and why does it reduce LLM cost?", "k": 3},
                        },
                        "comparison_question": {
                            "summary": "Comparison question — wider context",
                            "description": "Use k=5 to pull in more context for comparison-style questions.",
                            "value": {"query": "What is the difference between LoRA and QLoRA?", "k": 5},
                        },
                        "factual_lookup": {
                            "summary": "Factual lookup — tight context (k=1)",
                            "description": "Single chunk is enough for a simple factual lookup.",
                            "value": {"query": "What is DPO?", "k": 1},
                        },
                    }
                }
            }
        }
    },
)
def answer(req: AnswerRequest) -> AnswerResponse:
    pipeline = get_pipeline()
    if pipeline.index is None:
        raise HTTPException(status_code=400, detail="No documents indexed yet.")
    ans = pipeline.answer(req.query, k=req.k)
    return AnswerResponse(query=req.query, answer=ans)


@app.post(
    "/stream",
    summary="RAG answer (streaming — tokens arrive as produced)",
    description="""
Retrieve context and **stream** the generated answer token-by-token as plain text.

**Response:** `Content-Type: text/plain` — tokens are flushed as they are produced by the model.

**Client examples**
```bash
# curl
curl -X POST http://localhost:8000/stream \\
     -H 'Content-Type: application/json' \\
     -d '{"query": "What is LoRA?", "k": 3}' \\
     --no-buffer

# Python httpx
import httpx
with httpx.stream("POST", "http://localhost:8000/stream",
                  json={"query": "What is LoRA?", "k": 3}) as r:
    for chunk in r.iter_text():
        print(chunk, end="", flush=True)
```

> **Note:** Swagger UI's "Try it out" will wait for the full response before displaying it. Use `curl` for real-time streaming.
""",
    tags=["Answer"],
    responses={
        200: {
            "description": "Token stream. Each chunk is a partial answer string.",
            "content": {"text/plain": {"example": "Semantic caching stores LLM responses keyed by embedding sim..."}},
        },
        400: _ERR_NO_INDEX,
        422: _ERR_VALIDATION,
    },
)
def stream_answer(req: AnswerRequest) -> StreamingResponse:
    pipeline = get_pipeline()
    if pipeline.index is None:
        raise HTTPException(status_code=400, detail="No documents indexed yet.")

    def _generate():
        for chunk in pipeline.stream_answer(req.query, k=req.k):
            yield chunk

    return StreamingResponse(_generate(), media_type="text/plain")
