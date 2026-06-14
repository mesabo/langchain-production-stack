"""RAGify pipeline unit tests."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from langchain_core.documents import Document

CORPUS = [
    ("d1", "FAISS is a library for efficient similarity search over dense vectors."),
    ("d2", "LangChain LCEL uses the pipe operator to compose runnables."),
    ("d3", "ChromaDB is a persistent vector database for AI applications."),
    ("d4", "RAG combines retrieval with generative language model synthesis."),
    ("d5", "RAGAS evaluates context recall, faithfulness, and semantic similarity."),
]

import pytest

@pytest.fixture(scope="module")
def pipeline():
    from src.pipeline import RAGifyPipeline
    cfg = {"embed_backbone": "sentence-transformers/all-MiniLM-L6-v2", "backbone": "HuggingFaceTB/SmolLM2-135M-Instruct", "max_new_tokens": 64, "temperature": 0.1}
    p = RAGifyPipeline(cfg)
    docs = [Document(page_content=text, metadata={"id": did}) for did, text in CORPUS]
    p.index(docs)
    return p

def test_similarity_retrieve(pipeline):
    r = pipeline.similarity_retrieve("What is FAISS?", k=2)
    assert len(r) == 2

def test_mmr_retrieve(pipeline):
    r = pipeline.mmr_retrieve("vector database", k=2, fetch_k=5)
    assert len(r) == 2

def test_top_result_relevance(pipeline):
    r = pipeline.similarity_retrieve("What is FAISS?", k=1)
    assert r[0].metadata["id"] == "d1"
