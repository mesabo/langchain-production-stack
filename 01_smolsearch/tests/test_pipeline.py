"""SmolSearch pipeline unit tests (CPU, no LLM calls for speed)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langchain_core.documents import Document


CORPUS = [
    ("doc_001", "FAISS is a library for efficient similarity search over dense vectors."),
    ("doc_002", "LangChain Expression Language uses the pipe operator to compose runnables."),
    ("doc_003", "ChromaDB is a persistent vector database for AI embeddings."),
    ("doc_004", "Embedding models map text to fixed-size dense vectors capturing semantic meaning."),
    ("doc_005", "RAG combines document retrieval with generative language model synthesis."),
]


@pytest.fixture(scope="module")
def pipeline():
    from src.pipeline import SmolSearchPipeline, build_embeddings
    cfg = {
        "embed_backbone": "sentence-transformers/all-MiniLM-L6-v2",
        "backbone": "HuggingFaceTB/SmolLM2-135M-Instruct",
        "max_new_tokens": 64,
        "temperature": 0.1,
    }
    p = SmolSearchPipeline(cfg)
    docs = [Document(page_content=text, metadata={"id": doc_id}) for doc_id, text in CORPUS]
    p.index_documents(docs)
    return p


def test_index_not_none(pipeline):
    assert pipeline.index is not None


def test_search_returns_k_results(pipeline):
    results = pipeline.search("What is FAISS?", k=3)
    assert len(results) == 3


def test_search_top_result_relevant(pipeline):
    results = pipeline.search("What is FAISS?", k=1)
    assert results[0].metadata["id"] == "doc_001"


def test_mmr_returns_k_results(pipeline):
    results = pipeline.search_mmr("What is a vector database?", k=2, fetch_k=5)
    assert len(results) == 2


def test_search_returns_documents(pipeline):
    results = pipeline.search("RAG retrieval augmented generation", k=2)
    assert all(hasattr(r, "page_content") for r in results)
    assert all(hasattr(r, "metadata") for r in results)
