"""LLMOps Baseline FastAPI application — semantic cache, cost tracking, retry."""
# mesabo · https://mesabo.github.io

from __future__ import annotations

import sys
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
        "cache_threshold": 0.92,
    }

from src.stack import LLMOpsStack

_stack: LLMOpsStack | None = None


def get_stack() -> LLMOpsStack:
    global _stack
    if _stack is None:
        _stack = LLMOpsStack(_CFG)
        _stack.enable_cache()
    return _stack


_TAGS = [
    {
        "name": "Inference",
        "description": (
            "LLM inference with semantic caching. "
            "The first call for a prompt embeds it and queries the sLM. "
            "Semantically similar subsequent prompts (cosine ≥ 0.92) return the cached response "
            "instantly with `cache_hit: true` and `latency_ms: 0`."
        ),
    },
    {
        "name": "Metrics",
        "description": (
            "Operational metrics: total calls, token counts, and average latency. "
            "Use this to track cost and performance over a session."
        ),
    },
    {
        "name": "System",
        "description": "Health check and liveness probe.",
    },
]

app = FastAPI(
    title="LLMOps Baseline",
    version="1.0.0",
    description="""
## Production LLM operations stack — semantic cache · cost tracking · retry

**LLMOps Baseline** is a reference implementation of the three core production patterns
every LLM API should have:

| Pattern | What it does |
|---------|-------------|
| **Semantic cache** | Stores (embedding, response) pairs. Re-uses cached answers for semantically equivalent prompts (cosine ≥ 0.92), reducing LLM calls and latency to ~0 ms. |
| **Cost tracker** | Counts input/output tokens and accumulates totals across all calls in this session. |
| **Retry middleware** | Wraps the LLM call with exponential back-off on transient errors (rate limits, timeouts). |

### How the semantic cache works
```
prompt
  └─► embed (MiniLM-L6-v2, 384-dim)
        └─► cosine search in cache store
              ├─► hit (≥ 0.92)  → return cached response immediately  ← latency ≈ 0 ms
              └─► miss          → call SmolLM2 → cache result → return
```

### Quick experiment
1. Call `POST /query` with `"What is LoRA?"` — first call hits the model.
2. Call again with `"Explain LoRA to me"` — semantically close, should be a **cache hit**.
3. Call `GET /metrics` to see token counts and average latency.
4. Set `bypass_cache: true` to force a fresh model call regardless of cache state.

### Cache threshold
Configured via `configs/app.yaml` → `cache_threshold` (default **0.92**).
Lower values → more cache hits but risk serving slightly mismatched answers.
Higher values → fewer hits but more precise cache matching.
""",
    openapi_tags=_TAGS,
    contact={
        "name": "mesabo",
        "url": "https://mesabo.github.io",
        "email": "mesabo18@gmail.com",
    },
    license_info={"name": "MIT"},
    externalDocs={
        "description": "Portfolio & source",
        "url": "https://mesabo.github.io",
    },
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "prompt": "Explain LoRA fine-tuning in one sentence.",
            "bypass_cache": False,
        }
    })

    prompt: str = Field(
        ...,
        description=(
            "Instruction or question to send to the sLM. "
            "The service first checks the semantic cache; if a sufficiently similar prompt "
            "was answered before (cosine ≥ threshold), the cached answer is returned instantly."
        ),
        min_length=1,
        max_length=1024,
        examples=["Explain LoRA fine-tuning in one sentence."],
    )
    bypass_cache: bool = Field(
        False,
        description=(
            "Set to `true` to skip the semantic cache and force a fresh model inference call. "
            "Useful for testing or when you need a freshly generated response."
        ),
        examples=[False],
    )


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str = Field(..., description="Always `ok` when running.", examples=["ok"])
    service: str = Field(..., description="Service name.", examples=["llmops-baseline"])


class QueryResponse(BaseModel):
    response: str = Field(
        ...,
        description="Text response from the sLM (or from the semantic cache if `cache_hit` is `true`).",
        examples=["LoRA (Low-Rank Adaptation) fine-tunes a model by injecting small trainable matrices..."],
    )
    cache_hit: bool = Field(
        ...,
        description=(
            "`true` if the response came from the semantic cache (a previous similar prompt). "
            "`false` if the sLM was called for this prompt."
        ),
        examples=[False],
    )
    latency_ms: int = Field(
        ...,
        description=(
            "Wall-clock inference time in milliseconds. "
            "`0` when `cache_hit` is `true` (cache lookup is near-instant)."
        ),
        examples=[1340],
    )


class MetricsResponse(BaseModel):
    n_calls: int = Field(
        ...,
        description="Total number of LLM inference calls made in this session (cache hits excluded).",
        examples=[5],
    )
    total_tokens: int = Field(
        ...,
        description="Cumulative input + output token count across all LLM calls (cache hits excluded).",
        examples=[1280],
    )
    avg_latency_ms: int = Field(
        ...,
        description="Average LLM inference latency in milliseconds (cache hits excluded).",
        examples=[980],
    )


_ERR_VALIDATION = {
    "description": "Request body failed validation.",
    "content": {"application/json": {"example": {"detail": [{"loc": ["body", "prompt"], "msg": "field required"}]}}},
}

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/health",
    summary="Health check",
    description="Lightweight liveness probe. Returns `ok` if the service is running.",
    tags=["System"],
    response_model=HealthResponse,
)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="llmops-baseline")


@app.post(
    "/query",
    summary="LLM inference with semantic cache",
    description="""
Send a prompt to the sLM with automatic semantic caching.

**Caching behaviour**

| Scenario | What happens | `cache_hit` | `latency_ms` |
|----------|-------------|-------------|--------------|
| First time this prompt (or similar) is seen | Model is called; result stored in cache | `false` | ~500–5000 ms |
| Semantically similar prompt (cosine ≥ 0.92) | Cached answer returned | `true` | `0` |
| `bypass_cache: true` | Model always called regardless | `false` | ~500–5000 ms |

**Try it:** submit the same question twice — the second response should have `cache_hit: true` and `latency_ms: 0`.

**Then try:** a paraphrase of the same question (e.g. `"What is LoRA?"` → `"Tell me about LoRA"`) — if cosine similarity ≥ 0.92, it will also be a cache hit.
""",
    tags=["Inference"],
    response_model=QueryResponse,
    responses={422: _ERR_VALIDATION},
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "first_call": {
                            "summary": "1st call — cache miss (LLM invoked)",
                            "description": "Run this first. The model is called and the result is stored in the cache.",
                            "value": {
                                "prompt": "Explain LoRA fine-tuning in one sentence.",
                                "bypass_cache": False,
                            },
                        },
                        "paraphrase_cache_hit": {
                            "summary": "2nd call — paraphrase → cache HIT",
                            "description": (
                                "Run this after the first call. "
                                "Semantically similar to the first prompt (cosine ≥ 0.92) — should return "
                                "cache_hit=true and latency_ms=0 without calling the model."
                            ),
                            "value": {
                                "prompt": "What is LoRA and how does it fine-tune a model efficiently?",
                                "bypass_cache": False,
                            },
                        },
                        "bypass_cache": {
                            "summary": "Force fresh generation — bypass_cache=true",
                            "description": "Forces the model to run even if a cached answer exists. Use to refresh a stale cached response.",
                            "value": {
                                "prompt": "Explain LoRA fine-tuning in one sentence.",
                                "bypass_cache": True,
                            },
                        },
                        "different_topic": {
                            "summary": "New topic — cache miss on a different concept",
                            "description": "Unrelated to the LoRA prompt — will be a fresh cache miss.",
                            "value": {
                                "prompt": "What is DPO and how does it differ from RLHF?",
                                "bypass_cache": False,
                            },
                        },
                    }
                }
            }
        }
    },
)
def query(req: QueryRequest) -> QueryResponse:
    stack = get_stack()
    if req.bypass_cache and stack.cache is not None:
        cached = None
    else:
        cached = stack.cache.get(req.prompt) if stack.cache else None

    if cached is not None:
        return QueryResponse(response=cached, cache_hit=True, latency_ms=0)

    t0 = time.perf_counter()
    response = stack.invoke(req.prompt)
    latency_ms = round((time.perf_counter() - t0) * 1000)
    return QueryResponse(response=response, cache_hit=False, latency_ms=latency_ms)


@app.get(
    "/metrics",
    summary="Operational metrics",
    description="""
Returns cumulative token and latency metrics for **LLM inference calls only** (cache hits are excluded).

**Fields**
| Field | Description |
|-------|-------------|
| `n_calls` | Number of times the sLM was actually invoked (bypasses + misses) |
| `total_tokens` | Sum of all input and output tokens across those calls |
| `avg_latency_ms` | Average inference latency (wall-clock, ms) |

**Use case:** call this after a batch of queries to estimate token cost and throughput.

**Reset:** metrics accumulate for the lifetime of the process; restart the service to reset.
""",
    tags=["Metrics"],
    response_model=MetricsResponse,
)
def metrics() -> MetricsResponse:
    stack = get_stack()
    raw = stack.tracker.summary()
    return MetricsResponse(
        n_calls=raw["n_calls"],
        total_tokens=raw["total_tokens"],
        avg_latency_ms=raw["avg_latency_ms"],
    )
