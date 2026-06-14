#!/usr/bin/env bash
# LLMOps Baseline — local smoke run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"

export HF_HOME="${HF_HOME:-${PROJECT_ROOT}/.cache/huggingface}"
export PYTHONPATH="${SCRIPT_DIR}:${PROJECT_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export TOKENIZERS_PARALLELISM=false
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-5,6,7}"

cd "${SCRIPT_DIR}"

echo "[llmops] Running unit tests..."
python -m pytest tests/ -q --tb=short

echo "[llmops] Smoke: cache + cost tracker + token counting..."
python - <<'PYEOF'
import sys; sys.path.insert(0, ".")
from src.stack import count_tokens, CostTracker

# Token counting
n = count_tokens("LangChain is a framework for building LLM applications.")
assert n > 0, "Token count must be positive"
print(f"[ok] count_tokens: {n}")

# Cost tracker
tracker = CostTracker()
tracker.record("Hello world", "Hi there!", 123.0)
tracker.record("What is FAISS?", "FAISS is a library for fast similarity search.", 456.0)
assert tracker.total_tokens > 0
assert len(tracker.calls) == 2
s = tracker.summary()
print(f"[ok] tracker: {s}")

print("[PASS] LLMOps smoke test complete.")
PYEOF
