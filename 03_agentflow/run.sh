#!/usr/bin/env bash
# AgentFlow — local smoke run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"

export HF_HOME="${HF_HOME:-${PROJECT_ROOT}/.cache/huggingface}"
export PYTHONPATH="${SCRIPT_DIR}:${PROJECT_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export TOKENIZERS_PARALLELISM=false
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-5,6,7}"

cd "${SCRIPT_DIR}"

echo "[agentflow] Running unit tests..."
python -m pytest tests/ -q --tb=short

echo "[agentflow] Smoke: tool registry + graph compile..."
python - <<'PYEOF'
import sys; sys.path.insert(0, ".")
from src.graph import build_math_registry, ToolRegistry

# Test tool registry directly
registry = build_math_registry()
result = registry.dispatch("add", {"a": 3.0, "b": 4.0})
assert abs(result - 7.0) < 1e-9, f"Expected 7.0, got {result}"
print(f"[ok] add: {result}")

result = registry.dispatch("sqrt", {"x": 16.0})
assert abs(result - 4.0) < 1e-9, f"Expected 4.0, got {result}"
print(f"[ok] sqrt: {result}")

result = registry.dispatch("lookup", {"topic": "pi"})
assert "3.14" in result, f"Expected pi fact, got {result}"
print(f"[ok] lookup: {result}")

print("[ok] Tool schemas:")
for t in registry.all():
    print(f"  {t.name}: {t.description[:50]}...")

print("[PASS] AgentFlow tool smoke complete.")
PYEOF
