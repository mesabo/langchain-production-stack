"""RAGify FastAPI application — multi-strategy RAG with RAGAS evaluation."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[4]
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

app = FastAPI(title="RAGify", version="1.0.0", description="Multi-strategy RAG with RAGAS evaluation.")
_pipeline: RAGifyPipeline | None = None


def get_pipeline() -> RAGifyPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = RAGifyPipeline(_CFG)
    return _pipeline


class IndexRequest(BaseModel):
    documents: list[str]


class QueryRequest(BaseModel):
    query: str
    k: int = 3
    strategy: str = "similarity"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ragify"}


@app.post("/index")
def index(req: IndexRequest) -> dict[str, Any]:
    pipeline = get_pipeline()
    docs = [Document(page_content=t, metadata={"id": f"doc_{i}"}) for i, t in enumerate(req.documents)]
    pipeline.index(docs)
    return {"indexed": len(docs)}


@app.post("/query")
def query(req: QueryRequest) -> dict[str, Any]:
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
    return {
        "query": req.query,
        "strategy": req.strategy,
        "answer": answer,
        "sources": [d.page_content[:80] for d in docs],
    }
