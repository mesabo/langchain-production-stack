"""RAGify FastAPI application — multi-strategy RAG with RAGAS evaluation."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import yaml
    with open(Path(__file__).parent.parent / "configs" / "app.yaml") as f:
        _CFG = yaml.safe_load(f)
except Exception:
    _CFG = {
        "embed_backbone": "sentence-transformers/all-MiniLM-L6-v2",
        "backbone": "HuggingFaceTB/SmolLM2-135M-Instruct",
        "max_new_tokens": 128,
        "temperature": 0.1,
    }

from src.pipeline import RAGifyPipeline
from langchain_core.documents import Document

_pipeline: RAGifyPipeline | None = None


def get_pipeline() -> RAGifyPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = RAGifyPipeline(_CFG)
    return _pipeline


_TAGS = [
    {
        "name": "Query",
        "description": (
            "RAG query endpoint. Choose a retrieval strategy, then the pipeline retrieves "
            "relevant chunks and generates a grounded answer using SmolLM2."
        ),
    },
    {
        "name": "Index",
        "description": "Add documents to the in-memory FAISS store before querying.",
    },
    {
        "name": "System",
        "description": "Health check and liveness probe.",
    },
]

app = FastAPI(
    title="RAGify",
    version="1.0.0",
    description="""
## Multi-strategy RAG with RAGAS evaluation

**RAGify** demonstrates three retrieval strategies on the same document store so you can compare their
output for the same query side-by-side.

### Quick start
1. **`POST /index`** — upload your documents (plain text list).
2. **`POST /query`** — ask a question and pick a retrieval strategy.
3. Compare the `answer` and `sources` across strategies to see the difference.

### Retrieval strategies
| Strategy | Description | Best for |
|----------|-------------|----------|
| `similarity` | Cosine nearest-neighbour (FAISS `IndexFlatL2`) | General-purpose, fastest |
| `mmr` | Maximum Marginal Relevance | Avoiding duplicate context chunks |
| `multi_query` | LLM rewrites the query N times, merges results | Paraphrase-sensitive / broad questions |

### Model stack
- **Embeddings:** `sentence-transformers/all-MiniLM-L6-v2` (384-dim)
- **Generation:** `HuggingFaceTB/SmolLM2-135M-Instruct`
""",
    openapi_tags=_TAGS,
    contact={"name": "sLM Universe Learning", "email": "mesabo18@gmail.com"},
    license_info={"name": "MIT"},
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
                "GDPR Article 83 sets fines of up to 4% of global annual turnover for serious violations.",
                "A personal data breach must be reported to the supervisory authority within 72 hours.",
                "Data subjects have the right to erasure ('right to be forgotten') under GDPR Article 17.",
            ]
        }
    })

    documents: list[str] = Field(
        ...,
        description=(
            "Plain-text documents to embed and store. Each string becomes one retrievable chunk. "
            "For best results, keep each document focused on a single topic (100–500 words)."
        ),
        min_length=1,
        examples=[["GDPR Article 83 sets fines of up to 4% of global annual turnover."]],
    )


class QueryRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "query": "What are the GDPR fines for a data breach?",
            "k": 3,
            "strategy": "similarity",
        }
    })

    query: str = Field(
        ...,
        description="Natural language question. The pipeline retrieves context then generates a grounded answer.",
        min_length=1,
        max_length=512,
        examples=["What are the GDPR fines for a data breach?"],
    )
    k: int = Field(
        3,
        description="Number of context chunks to retrieve before generation.",
        ge=1,
        le=20,
        examples=[3],
    )
    strategy: Literal["similarity", "mmr", "multi_query"] = Field(
        "similarity",
        description=(
            "Retrieval strategy:\n"
            "- `similarity` — cosine nearest-neighbour (default, fastest)\n"
            "- `mmr` — Maximum Marginal Relevance (diverse results)\n"
            "- `multi_query` — LLM rewrites the query N times and merges results "
            "(slower but better recall on paraphrase-sensitive corpora)"
        ),
    )


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str = Field(..., description="Always `ok` when running.", examples=["ok"])
    service: str = Field(..., description="Service name.", examples=["ragify"])


class IndexResponse(BaseModel):
    indexed: int = Field(..., description="Number of documents added to the store.", examples=[3])


class QueryResponse(BaseModel):
    query: str = Field(..., description="Original question echoed back.", examples=["What are GDPR fines?"])
    strategy: str = Field(..., description="Retrieval strategy used.", examples=["similarity"])
    answer: str = Field(
        ...,
        description="Answer generated by the sLM, grounded in the retrieved source chunks.",
        examples=["Under GDPR Article 83, fines can reach up to 4% of global annual turnover..."],
    )
    sources: list[str] = Field(
        ...,
        description=(
            "First 80 characters of each retrieved source chunk (for quick inspection). "
            "These are the exact passages the answer is grounded in."
        ),
        examples=[["GDPR Article 83 sets fines of up to 4%...", "A personal data breach must be reported..."]],
    )


_ERR_NO_INDEX = {
    "description": "No documents indexed yet — call `POST /index` first.",
    "content": {"application/json": {"example": {"detail": "No documents indexed yet."}}},
}
_ERR_VALIDATION = {
    "description": "Request body failed validation.",
    "content": {"application/json": {"example": {"detail": [{"loc": ["body", "query"], "msg": "field required"}]}}},
}

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/health",
    summary="Health check",
    description="Returns `ok` if the service is running.",
    tags=["System"],
    response_model=HealthResponse,
)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="ragify")


@app.post(
    "/index",
    summary="Index documents",
    description="""
Upload plain-text documents to the FAISS store.

**Tips**
- Split long PDFs or articles into ~300-word chunks before indexing for better retrieval precision.
- The index is **in-memory** and resets on service restart.
- You can call `/index` multiple times to add batches incrementally.
- Document IDs are auto-assigned as `doc_0`, `doc_1`, …
""",
    tags=["Index"],
    response_model=IndexResponse,
    responses={422: _ERR_VALIDATION},
)
def index(req: IndexRequest) -> IndexResponse:
    pipeline = get_pipeline()
    docs = [Document(page_content=t, metadata={"id": f"doc_{i}"}) for i, t in enumerate(req.documents)]
    pipeline.index(docs)
    return IndexResponse(indexed=len(docs))


@app.post(
    "/query",
    summary="RAG query",
    description="""
Retrieve relevant chunks and generate a grounded answer.

**End-to-end flow**

```
query
  └─► retrieve (strategy)        ← top-k chunks from FAISS
        └─► prompt assembly      ← "Context: {chunks}\\nQuestion: {query}"
              └─► SmolLM2        ← generates the answer
                    └─► response
```

**Choosing a strategy**

| Strategy | When to use |
|----------|-------------|
| `similarity` | Default — single query, fast, accurate for most cases |
| `mmr` | Your retrieved chunks tend to be near-duplicate passages |
| `multi_query` | The question has multiple phrasings or the corpus uses varied vocabulary |

**Output:** `answer` is the generated text; `sources` lists the first 80 characters of each retrieved chunk
so you can verify the answer is grounded.
""",
    tags=["Query"],
    response_model=QueryResponse,
    responses={400: _ERR_NO_INDEX, 422: _ERR_VALIDATION},
)
def query(req: QueryRequest) -> QueryResponse:
    pipeline = get_pipeline()
    if pipeline.store is None:
        raise HTTPException(status_code=400, detail="No documents indexed yet.")
    if req.strategy == "mmr":
        docs = pipeline.mmr_retrieve(req.query, k=req.k)
    elif req.strategy == "multi_query":
        docs = pipeline.multi_query_retrieve(req.query, k=req.k)
    else:
        docs = pipeline.similarity_retrieve(req.query, k=req.k)
    answer = pipeline.rag_answer(req.query, docs)
    return QueryResponse(
        query=req.query,
        strategy=req.strategy,
        answer=answer,
        sources=[d.page_content[:80] for d in docs],
    )
