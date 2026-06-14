# AgentFlow — Stateful Multi-Tool LLM Agent

Production stateful agent system. LangGraph StateGraph with conditional routing, retry cycles, and LangSmith-compatible tracing. Tool registry with Pydantic-validated schemas and AgentExecutor iteration guards.

## Architecture

```
User Task
    │
    ▼
FastAPI /task
    │
    ▼
LangGraph StateGraph (AgentState)
    ├── Node: run_agent (AgentExecutor + tool_calling_agent)
    │       └── ToolRegistry: add, subtract, multiply, sqrt, lookup
    └── Node: end → return result
    │
TraceWriter ──► traces.jsonl (offline) or LangSmith (live)
    │
Response + intermediate steps
```

**Stack:** LangGraph · LangSmith · AgentExecutor · LangChain tools · FastAPI · GKE

## API

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Service check |
| POST | `/task` | Submit a task (returns result + steps) |
| GET | `/traces` | Last N trace records from JSONL |

## Example

```bash
curl -X POST http://localhost:8080/task \
  -H "Content-Type: application/json" \
  -d '{"task": "What is the square root of 3 multiplied by 48?"}'

# Response:
# {"result": "12.0", "steps": [{"tool": "multiply", ...}, {"tool": "sqrt", ...}], "run_id": "..."}
```

## Run

```bash
bash run.sh
uvicorn app.main:app --port 8080
```

## LangSmith integration

Set `LANGSMITH_API_KEY` to enable live tracing. Without it, traces go to `traces/agent_traces.jsonl`.
