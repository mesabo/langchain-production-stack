"""AgentFlow — LangGraph stateful agent with tool registry and LangSmith tracing."""

from __future__ import annotations

import ast
import json
import math
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Literal, TypedDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
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


def _build_react_prompt(task: str, tools: list, history: str) -> str:
    tool_descs = "\n".join(f"  {t.name}: {t.description}" for t in tools)
    tool_names = ", ".join(t.name for t in tools)
    return (
        f"You have tools: [{tool_names}]\n\n"
        f"Tool descriptions:\n{tool_descs}\n\n"
        "Respond ONLY in this exact format:\n"
        "Thought: <reasoning>\n"
        "Action: <tool_name>\n"
        "Action Input: <number or string>\n"
        "...repeat Thought/Action/Action Input as needed...\n"
        "Final Answer: <answer>\n\n"
        f"Task: {task}\n"
        f"{history}"
        "Thought:"
    )


def _parse_tool_args(raw_input: str, schema: dict) -> dict:
    """Parse raw input string into tool argument dict."""
    keys = list(schema.keys())
    if len(keys) == 1:
        try:
            return {keys[0]: ast.literal_eval(raw_input)}
        except Exception:
            return {keys[0]: raw_input}
    # Multi-arg: try "a, b" or "(a, b)" forms
    try:
        val = ast.literal_eval(raw_input)
        if isinstance(val, (tuple, list)) and len(val) >= len(keys):
            return dict(zip(keys, val))
    except Exception:
        pass
    try:
        parts = [ast.literal_eval(x.strip()) for x in raw_input.split(",")]
        if len(parts) >= len(keys):
            return dict(zip(keys, parts))
    except Exception:
        pass
    return {keys[0]: raw_input}


def build_agent_graph(llm, registry: ToolRegistry, max_steps: int = 5):
    from langgraph.graph import StateGraph, END
    from langchain_core.prompts import PromptTemplate
    from langchain_core.output_parsers import StrOutputParser

    _chain = PromptTemplate.from_template("{text}") | llm | StrOutputParser()

    def run_agent(state: AgentState) -> AgentState:
        tools = registry.all()
        history = ""
        steps: list[dict] = []
        result = ""

        for _ in range(max_steps):
            prompt_text = _build_react_prompt(state["task"], tools, history)
            try:
                raw = _chain.invoke({"text": prompt_text})
            except Exception as exc:
                result = f"LLM error: {exc}"
                break

            fa = re.search(r"Final Answer[:\s]+(.+?)(?:\n|$)", raw, re.IGNORECASE)
            if fa:
                result = fa.group(1).strip()
                break

            action_m = re.search(r"Action[:\s]+(\w+)", raw, re.IGNORECASE)
            ainput_m = re.search(r"Action Input[:\s]+(.+?)(?:\n|$)", raw, re.IGNORECASE)

            if not action_m:
                result = raw.strip()[:200] if raw.strip() else "No parseable action"
                break

            tool_name = action_m.group(1).strip()
            raw_input = ainput_m.group(1).strip() if ainput_m else ""
            tool = registry.get(tool_name)

            if tool is None:
                obs = f"Tool '{tool_name}' not found. Available: {', '.join(t.name for t in tools)}"
            else:
                try:
                    args = _parse_tool_args(raw_input, tool.args)
                    obs = str(registry.dispatch(tool_name, args))
                    steps.append({"tool": tool_name, "input": raw_input, "result": obs})
                except Exception as exc:
                    obs = f"Tool error: {exc}"

            history += f" {raw}\nObservation: {obs}\nThought:"

        if not result:
            result = f"Completed {len(steps)} step(s)" if steps else "No result"

        return {**state, "result": result, "steps": steps, "done": True}

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
