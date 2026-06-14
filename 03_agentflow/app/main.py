"""AgentFlow FastAPI application — LangGraph stateful agent with tool registry."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

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
        "backbone": "HuggingFaceTB/SmolLM2-135M-Instruct",
        "max_new_tokens": 128,
        "temperature": 0.1,
        "max_steps": 5,
    }

from src.graph import build_math_registry, build_agent_graph, TraceWriter

_graph = None
_tracer: TraceWriter | None = None


def _make_llm():
    from langchain_huggingface import HuggingFacePipeline
    from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline as hf_pipeline
    model_name = _CFG.get("backbone", "HuggingFaceTB/SmolLM2-135M-Instruct")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    model = AutoModelForCausalLM.from_pretrained(model_name)
    pipe = hf_pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        max_new_tokens=_CFG.get("max_new_tokens", 128),
        temperature=_CFG.get("temperature", 0.1),
        do_sample=False,
        return_full_text=False,
    )
    return HuggingFacePipeline(pipeline=pipe)


def get_graph():
    global _graph, _tracer
    if _graph is None:
        llm = _make_llm()
        registry = build_math_registry()
        _graph = build_agent_graph(llm, registry, max_steps=_CFG.get("max_steps", 5))
        _tracer = TraceWriter(Path("/tmp/agentflow_traces.jsonl"))
    return _graph, _tracer


_TAGS = [
    {
        "name": "Agent",
        "description": (
            "Submit a task to the LangGraph ReAct agent. The agent reasons step-by-step, "
            "calls registered tools (math, calculator), and returns the final answer "
            "together with a full trace of its reasoning steps."
        ),
    },
    {
        "name": "System",
        "description": "Health check and liveness probe.",
    },
]

app = FastAPI(
    title="AgentFlow",
    version="1.0.0",
    description="""
## LangGraph stateful ReAct agent with tool dispatch

**AgentFlow** exposes a LangGraph-powered agent that follows the **ReAct** (Reason + Act) loop:
1. **Think** — the LLM reasons about the task.
2. **Act** — it selects a tool and calls it.
3. **Observe** — the tool result is appended to history.
4. **Repeat** until a `Final Answer` is produced or `max_steps` is reached.

### Available tools (math registry)
| Tool | Description | Example input |
|------|-------------|---------------|
| `calculator` | Evaluates a safe arithmetic expression | `"(12 * 8) + 4"` |
| `sqrt` | Square root of a number | `"144"` |
| `power` | `base ^ exponent` | `"2,10"` |

### Example tasks
```
"What is the square root of 144 plus 5?"
"Calculate (2^10) * 3"
"If a model has 135 million parameters and each takes 2 bytes, how many MB of VRAM does it need?"
```

### Response fields
| Field | Description |
|-------|-------------|
| `run_id` | UUID for this run — use to correlate traces in `/tmp/agentflow_traces.jsonl` |
| `result` | Final answer produced by the agent |
| `steps` | Full ReAct trace: each element has `thought`, `action`, `action_input`, `observation` |
| `latency_ms` | Wall-clock time including model inference and tool calls |
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

class RunRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "task": "What is the square root of 144, and then multiply the result by 7?"
        }
    })

    task: str = Field(
        ...,
        description=(
            "Natural language task for the ReAct agent. The agent has access to math tools "
            "(calculator, sqrt, power). Phrase your request as a question or instruction.\n\n"
            "**Good examples:**\n"
            "- `\"What is sqrt(256) + 100?\"`\n"
            "- `\"Calculate (2^8) * 3 then add 17\"`\n"
            "- `\"If a 7B model uses 2 bytes per parameter, how many GB of VRAM is needed?\"`"
        ),
        min_length=1,
        max_length=512,
        examples=["What is the square root of 144 multiplied by 7?"],
    )


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class AgentStep(BaseModel):
    thought: str = Field(
        ...,
        description="The agent's internal reasoning at this step.",
        examples=["I need to compute sqrt(144) first."],
    )
    action: str = Field(
        ...,
        description="Name of the tool the agent decided to call.",
        examples=["sqrt"],
    )
    action_input: str = Field(
        ...,
        description="String argument passed to the tool.",
        examples=["144"],
    )
    observation: str = Field(
        ...,
        description="Result returned by the tool after execution.",
        examples=["12.0"],
    )


class HealthResponse(BaseModel):
    status: str = Field(..., description="Always `ok` when running.", examples=["ok"])
    service: str = Field(..., description="Service name.", examples=["agentflow"])


class RunResponse(BaseModel):
    run_id: str = Field(
        ...,
        description="UUID for this agent run. Appears in `/tmp/agentflow_traces.jsonl` for offline inspection.",
        examples=["3f2a8b1c-4d5e-..."],
    )
    task: str = Field(..., description="Original task string echoed back.", examples=["What is sqrt(144) * 7?"])
    result: str = Field(
        ...,
        description=(
            "Final answer produced by the agent. If the agent exhausted `max_steps` without "
            "reaching a conclusion, this may be a partial or fallback response."
        ),
        examples=["The square root of 144 is 12, and 12 × 7 = 84."],
    )
    steps: list[dict[str, Any]] = Field(
        ...,
        description=(
            "Full ReAct trace — one dict per step. Each dict contains `thought`, `action`, "
            "`action_input`, and `observation`. Useful for debugging agent reasoning."
        ),
        examples=[[
            {"thought": "I need sqrt(144)", "action": "sqrt", "action_input": "144", "observation": "12.0"},
            {"thought": "Now multiply 12 * 7", "action": "calculator", "action_input": "12*7", "observation": "84"},
        ]],
    )
    latency_ms: int = Field(
        ...,
        description="Total wall-clock time in milliseconds, including model inference and all tool calls.",
        examples=[1240],
    )


_ERR_EMPTY_TASK = {
    "description": "Task string is empty or whitespace-only.",
    "content": {"application/json": {"example": {"detail": "task must be non-empty."}}},
}
_ERR_VALIDATION = {
    "description": "Request body failed validation.",
    "content": {"application/json": {"example": {"detail": [{"loc": ["body", "task"], "msg": "field required"}]}}},
}

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/health",
    summary="Health check",
    description="Lightweight liveness probe. Returns `ok` if the service is up.",
    tags=["System"],
    response_model=HealthResponse,
)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="agentflow")


@app.post(
    "/run",
    summary="Run agent task",
    description="""
Submit a natural language task to the **LangGraph ReAct agent**.

**What happens internally**

```
task
  └─► LangGraph graph.invoke()
        ├─► [think node]   LLM reasons → selects tool
        ├─► [act node]     tool is dispatched (calculator / sqrt / power)
        ├─► [observe node] result appended to history
        └─► ... (up to max_steps=5 iterations)
              └─► [end node]  Final Answer extracted → response
```

**Response fields explained**
- `result` — the agent's final answer
- `steps` — the full reasoning trace (thought → action → observation per step)
- `run_id` — UUID you can grep in `/tmp/agentflow_traces.jsonl`
- `latency_ms` — total wall-clock time (model + tools)

**Error cases**
- `400` if `task` is empty
- `422` if the request body is malformed
- If the agent cannot solve the task in `max_steps`, it returns whatever partial result it has

**Example tasks to try**
```
"What is 2 raised to the power of 10?"
"Calculate the square root of 225 and then add 50"
"If a 360M-parameter model uses 2 bytes per param, what is the total size in MB?"
```
""",
    tags=["Agent"],
    response_model=RunResponse,
    responses={400: _ERR_EMPTY_TASK, 422: _ERR_VALIDATION},
)
def run(req: RunRequest) -> RunResponse:
    if not req.task.strip():
        raise HTTPException(status_code=400, detail="task must be non-empty.")
    graph, tracer = get_graph()
    t0 = time.perf_counter()
    state = graph.invoke({
        "task": req.task,
        "steps": [],
        "result": "",
        "n_retries": 0,
        "done": False,
    })
    latency_ms = (time.perf_counter() - t0) * 1000
    run_id = tracer.record(req.task, state["result"], state["steps"], latency_ms)
    return RunResponse(
        run_id=run_id,
        task=req.task,
        result=state["result"],
        steps=state["steps"],
        latency_ms=round(latency_ms),
    )
