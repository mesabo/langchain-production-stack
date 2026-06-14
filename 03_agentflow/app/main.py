"""AgentFlow FastAPI application — LangGraph stateful agent with tool registry."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
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
        "backbone": "HuggingFaceTB/SmolLM2-135M-Instruct",
        "max_new_tokens": 128,
        "temperature": 0.1,
        "max_steps": 5,
    }

from src.graph import build_math_registry, build_agent_graph, TraceWriter

app = FastAPI(title="AgentFlow", version="1.0.0", description="LangGraph stateful agent with tool dispatch.")
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


class RunRequest(BaseModel):
    task: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "agentflow"}


@app.post("/run")
def run(req: RunRequest) -> dict[str, Any]:
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
    return {
        "run_id": run_id,
        "task": req.task,
        "result": state["result"],
        "steps": state["steps"],
        "latency_ms": round(latency_ms),
    }
