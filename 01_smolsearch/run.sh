#!/usr/bin/env bash
# SmolSearch — local smoke run (index 5 docs, search, answer).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"

export HF_HOME="${HF_HOME:-${PROJECT_ROOT}/.cache/huggingface}"
export PYTHONPATH="${SCRIPT_DIR}:${PROJECT_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export TOKENIZERS_PARALLELISM=false

cd "${SCRIPT_DIR}"

echo "[smolsearch] Running unit tests..."
python -m pytest tests/ -q --tb=short

echo "[smolsearch] Smoke test: index + search + stream..."
python - <<'PYEOF'
import sys
sys.path.insert(0, ".")
import os; os.environ.setdefault("HF_HOME", os.environ.get("HF_HOME", ".cache/huggingface"))
from langchain_core.documents import Document
from src.pipeline import SmolSearchPipeline

cfg = {
    "embed_backbone": "sentence-transformers/all-MiniLM-L6-v2",
    "backbone": "HuggingFaceTB/SmolLM2-135M-Instruct",
    "max_new_tokens": 64,
    "temperature": 0.1,
}
p = SmolSearchPipeline(cfg)
docs = [
    Document(page_content="FAISS is a library for fast similarity search.", metadata={"id": "d1"}),
    Document(page_content="LangChain enables composable LLM pipelines.", metadata={"id": "d2"}),
    Document(page_content="ChromaDB is a vector database for AI applications.", metadata={"id": "d3"}),
    Document(page_content="RAG combines retrieval with generation.", metadata={"id": "d4"}),
    Document(page_content="LangGraph builds stateful multi-actor workflows.", metadata={"id": "d5"}),
]
p.index_documents(docs)
results = p.search("What is FAISS?", k=2)
assert len(results) == 2, f"Expected 2 results, got {len(results)}"
print(f"[ok] search: top result = '{results[0].page_content[:50]}...'")
chunks = list(p.stream_answer("Explain RAG briefly.", k=2))
assert len(chunks) > 0, "No stream chunks returned"
print(f"[ok] stream: {len(chunks)} chunks, first='{chunks[0][:30]}...'")
print("[PASS] SmolSearch smoke test complete.")
PYEOF
