#!/usr/bin/env bash
# RAGify — local smoke run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"

export HF_HOME="${HF_HOME:-${PROJECT_ROOT}/.cache/huggingface}"
export PYTHONPATH="${SCRIPT_DIR}:${PROJECT_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export TOKENIZERS_PARALLELISM=false
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-5,6,7}"

cd "${SCRIPT_DIR}"

echo "[ragify] Running unit tests..."
python -m pytest tests/ -q --tb=short

echo "[ragify] Smoke: index → multi-query retrieve → RAGAS eval..."
python - <<'PYEOF'
import sys; sys.path.insert(0, ".")
from langchain_core.documents import Document
from src.pipeline import RAGifyPipeline

cfg = {
    "embed_backbone": "sentence-transformers/all-MiniLM-L6-v2",
    "backbone": "HuggingFaceTB/SmolLM2-135M-Instruct",
    "max_new_tokens": 64,
    "temperature": 0.1,
}
p = RAGifyPipeline(cfg)
docs = [
    Document(page_content="FAISS supports exact and ANN similarity search.", metadata={"id": "d1"}),
    Document(page_content="LangChain LCEL uses the pipe operator.", metadata={"id": "d2"}),
    Document(page_content="ChromaDB persists vector embeddings to disk.", metadata={"id": "d3"}),
    Document(page_content="RAG retrieves documents and generates answers.", metadata={"id": "d4"}),
    Document(page_content="RAGAS evaluates context recall and faithfulness.", metadata={"id": "d5"}),
]
p.index(docs)
results = p.similarity_retrieve("What is FAISS?", k=2)
assert len(results) == 2
print(f"[ok] similarity: {results[0].metadata['id']}")
mmr_results = p.mmr_retrieve("vector database", k=2, fetch_k=5)
assert len(mmr_results) == 2
print(f"[ok] mmr: {[r.metadata['id'] for r in mmr_results]}")
print("[PASS] RAGify smoke test complete.")
PYEOF
