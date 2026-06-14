"""SmolSearch FastAPI application — streaming semantic search API."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

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

app = FastAPI(title="SmolSearch", version="1.0.0", description="Semantic search with LCEL streaming.")
_pipeline: SmolSearchPipeline | None = None


def get_pipeline() -> SmolSearchPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = SmolSearchPipeline(_CFG)
    return _pipeline


class IndexRequest(BaseModel):
    documents: list[str]
    ids: list[str] | None = None


class SearchRequest(BaseModel):
    query: str
    k: int = 3
    mode: str = "similarity"


class AnswerRequest(BaseModel):
    query: str
    k: int = 3


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "smolsearch"}


@app.post("/index")
def index_documents(req: IndexRequest) -> dict[str, Any]:
    pipeline = get_pipeline()
    docs = [
        Document(page_content=text, metadata={"id": req.ids[i] if req.ids else f"doc_{i}"})
        for i, text in enumerate(req.documents)
    ]
    pipeline.add_documents(docs)
    return {"indexed": len(docs), "total": len(req.documents)}


@app.post("/search")
def search(req: SearchRequest) -> dict[str, Any]:
    pipeline = get_pipeline()
    if pipeline.index is None:
        raise HTTPException(status_code=400, detail="No documents indexed yet.")
    if req.mode == "mmr":
        results = pipeline.search_mmr(req.query, k=req.k)
    else:
        results = pipeline.search(req.query, k=req.k)
    return {
        "query": req.query,
        "results": [{"content": d.page_content, "id": d.metadata.get("id", "")} for d in results],
    }


@app.post("/answer")
def answer(req: AnswerRequest) -> dict[str, str]:
    pipeline = get_pipeline()
    if pipeline.index is None:
        raise HTTPException(status_code=400, detail="No documents indexed yet.")
    ans = pipeline.answer(req.query, k=req.k)
    return {"query": req.query, "answer": ans}


@app.post("/stream")
def stream_answer(req: AnswerRequest) -> StreamingResponse:
    pipeline = get_pipeline()
    if pipeline.index is None:
        raise HTTPException(status_code=400, detail="No documents indexed yet.")

    def _generate():
        for chunk in pipeline.stream_answer(req.query, k=req.k):
            yield chunk

    return StreamingResponse(_generate(), media_type="text/plain")
