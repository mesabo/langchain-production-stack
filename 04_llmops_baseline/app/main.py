"""LLMOps Baseline FastAPI application — semantic cache, cost tracking, retry."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import time

from fastapi import FastAPI
from pydantic import BaseModel

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
        "cache_threshold": 0.92,
    }

from src.stack import LLMOpsStack

app = FastAPI(title="LLMOps Baseline", version="1.0.0", description="Semantic caching, cost tracking, retry middleware.")
_stack: LLMOpsStack | None = None


def get_stack() -> LLMOpsStack:
    global _stack
    if _stack is None:
        _stack = LLMOpsStack(_CFG)
        _stack.enable_cache()
    return _stack


class QueryRequest(BaseModel):
    prompt: str
    bypass_cache: bool = False


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "llmops-baseline"}


@app.post("/query")
def query(req: QueryRequest) -> dict[str, Any]:
    stack = get_stack()
    if req.bypass_cache and stack.cache is not None:
        cached = None
    else:
        cached = stack.cache.get(req.prompt) if stack.cache else None

    if cached is not None:
        return {"response": cached, "cache_hit": True, "latency_ms": 0}

    t0 = time.perf_counter()
    response = stack.invoke(req.prompt)
    latency_ms = round((time.perf_counter() - t0) * 1000)
    return {"response": response, "cache_hit": False, "latency_ms": latency_ms}


@app.get("/metrics")
def metrics() -> dict[str, Any]:
    stack = get_stack()
    return stack.tracker.summary()
