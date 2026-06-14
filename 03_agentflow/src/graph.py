"""AgentFlow — LangGraph stateful agent with tool registry and LangSmith tracing."""

from __future__ import annotations

import json
import math
import sys
import uuid
from pathlib import Path
from typing import Any, Literal, TypedDict

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

class ToolRegistry:
    """Runtime tool registry with Pydantic-validated schemas."""

    def __init__(self) -> None:
        self._tools: dict[str, Any] = {}

    def register(self, tool: Any) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Any | None:
        return self._tools.get(name)

    def all(self) -> list[Any]:
        return list(self._tools.values())

    def dispatch(self, name: str, args: dict) -> Any:
        tool = self.get(name)
        if tool is None:
            return f"ERROR: tool '{name}' not found"
        return tool.invoke(args)


def build_math_registry() -> ToolRegistry:
    from langchain_core.tools import tool

    @tool
    def add(a: float, b: float) -> float:
        """Add two numbers."""
        return a + b

    @tool
    def subtract(a: float, b: float) -> float:
        """Subtract b from a."""
        return a - b

    @tool
    def multiply(a: float, b: float) -> float:
        """Multiply two numbers."""
        return a * b

    @tool
    def sqrt(x: float) -> float:
        """Return the square root of x."""
        return math.sqrt(x)

    @tool
    def lookup(topic: str) -> str:
        """Look up facts. Topics: pi, e, golden_ratio."""
        facts = {
            "pi": "Pi ≈ 3.14159",
            "e": "Euler's number e ≈ 2.71828",
            "golden_ratio": "Golden ratio ≈ 1.61803",
        }
        return facts.get(topic.lower(), f"No fact for '{topic}'.")

    registry = ToolRegistry()
    for t in [add, subtract, multiply, sqrt, lookup]:
        registry.register(t)
    return registry


# ---------------------------------------------------------------------------
# LangGraph state and nodes
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    task: str
    steps: list[dict]
    result: str
    n_retries: int
    done: bool


def build_agent_graph(llm, registry: ToolRegistry, max_steps: int = 5):
    from langgraph.graph import StateGraph, END
    from langchain_classic.agents import create_tool_calling_agent, AgentExecutor
    from langchain_core.prompts import ChatPromptTemplate

    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a precise assistant. Use tools to solve the task step by step."),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])
    tools = registry.all()
    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        max_iterations=max_steps,
        handle_parsing_errors=True,
        return_intermediate_steps=True,
        verbose=False,
    )

    def run_agent(state: AgentState) -> AgentState:
        try:
            out = executor.invoke({"input": state["task"]})
            steps = [
                {"tool": s[0].tool, "args": s[0].tool_input, "result": str(s[1])}
                for s in out.get("intermediate_steps", [])
            ]
            return {**state, "result": out.get("output", ""), "steps": steps, "done": True}
        except Exception as exc:
            return {**state, "result": f"ERROR: {exc}", "n_retries": state["n_retries"] + 1, "done": True}

    def route(state: AgentState) -> Literal["end"]:
        return "end"

    graph = StateGraph(AgentState)
    graph.add_node("agent", run_agent)
    graph.add_node("end", lambda s: s)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", route, {"end": "end"})
    graph.add_edge("end", END)
    return graph.compile()


# ---------------------------------------------------------------------------
# LangSmith-compatible trace writer
# ---------------------------------------------------------------------------

class TraceWriter:
    """Writes trace records to JSONL (offline) or LangSmith (live)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, task: str, result: str, steps: list[dict], latency_ms: float) -> str:
        run_id = str(uuid.uuid4())
        record = {
            "run_id": run_id,
            "task": task,
            "result": result[:200],
            "n_steps": len(steps),
            "latency_ms": round(latency_ms),
        }
        with self.path.open("a") as f:
            f.write(json.dumps(record) + "\n")
        return run_id
