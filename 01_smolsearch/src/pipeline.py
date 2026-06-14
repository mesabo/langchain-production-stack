"""SmolSearch core pipeline — FAISS + LCEL streaming search."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings, HuggingFacePipeline
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline


def build_embeddings(model_name: str, device: str = "cpu") -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"device": device},
        encode_kwargs={"normalize_embeddings": True},
    )


def build_llm(model_name: str, max_new_tokens: int, temperature: float) -> HuggingFacePipeline:
    from langchain_huggingface import ChatHuggingFace
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(model_name)
    pipe = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        max_new_tokens=max_new_tokens,
        temperature=max(temperature, 1e-6),
        do_sample=temperature > 0,
    )
    return HuggingFacePipeline(pipeline=pipe)


class SmolSearchPipeline:
    """FAISS-backed semantic search with LCEL streaming answer synthesis."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg
        embed_model = cfg.get("embed_backbone", "sentence-transformers/all-MiniLM-L6-v2")
        self.embeddings = build_embeddings(embed_model)
        self.index: FAISS | None = None
        self._chain = None

    def index_documents(self, docs: list[Document]) -> None:
        self.index = FAISS.from_documents(docs, self.embeddings)

    def add_documents(self, docs: list[Document]) -> None:
        if self.index is None:
            self.index_documents(docs)
        else:
            self.index.add_documents(docs)

    def _get_chain(self):
        if self._chain is None:
            llm = build_llm(
                self.cfg.get("backbone", "HuggingFaceTB/SmolLM2-135M-Instruct"),
                self.cfg.get("max_new_tokens", 128),
                self.cfg.get("temperature", 0.1),
            )
            prompt = ChatPromptTemplate.from_template(
                "Answer based on the retrieved documents below. Be concise.\n\n"
                "Documents:\n{context}\n\n"
                "Question: {query}\n\nAnswer:"
            )
            self._chain = prompt | llm | StrOutputParser()
        return self._chain

    def search(self, query: str, k: int = 3) -> list[Document]:
        if self.index is None:
            raise RuntimeError("No documents indexed. Call index_documents() first.")
        return self.index.similarity_search(query, k=k)

    def search_mmr(self, query: str, k: int = 3, fetch_k: int = 10) -> list[Document]:
        if self.index is None:
            raise RuntimeError("No documents indexed.")
        return self.index.max_marginal_relevance_search(query, k=k, fetch_k=fetch_k)

    def answer(self, query: str, k: int = 3) -> str:
        docs = self.search(query, k=k)
        context = "\n\n".join(d.page_content for d in docs)
        return self._get_chain().invoke({"query": query, "context": context})

    def stream_answer(self, query: str, k: int = 3) -> Iterator[str]:
        docs = self.search(query, k=k)
        context = "\n\n".join(d.page_content for d in docs)
        yield from self._get_chain().stream({"query": query, "context": context})
