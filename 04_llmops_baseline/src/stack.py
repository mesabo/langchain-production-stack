"""LLMOps Baseline — production stack: caching, streaming, retry, cost tracking."""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def count_tokens(text: str) -> int:
    try:
        import tiktoken
        enc = tiktoken.get_encoding("gpt2")
        return len(enc.encode(text))
    except Exception:
        return len(text.split())


class SemanticCache:
    """In-memory semantic cache backed by cosine similarity."""

    def __init__(self, embeddings: Any, threshold: float = 0.95) -> None:
        self.embeddings = embeddings
        self.threshold = threshold
        self._store: list[tuple[list[float], str]] = []

    def _embed(self, text: str) -> list[float]:
        return self.embeddings.embed_query(text)

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        import math
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        return dot / (na * nb + 1e-9)

    def get(self, query: str) -> str | None:
        q_emb = self._embed(query)
        for emb, resp in self._store:
            if self._cosine(q_emb, emb) >= self.threshold:
                return resp
        return None

    def set(self, query: str, response: str) -> None:
        self._store.append((self._embed(query), response))

    def __len__(self) -> int:
        return len(self._store)


class CostTracker:
    """Accumulates token costs across calls."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def record(self, prompt: str, response: str, latency_ms: float) -> None:
        self.calls.append({
            "run_id": str(uuid.uuid4())[:8],
            "n_tokens_in": count_tokens(prompt),
            "n_tokens_out": count_tokens(response),
            "latency_ms": round(latency_ms),
        })

    @property
    def total_tokens(self) -> int:
        return sum(c["n_tokens_in"] + c["n_tokens_out"] for c in self.calls)

    @property
    def avg_latency_ms(self) -> float:
        if not self.calls:
            return 0.0
        return sum(c["latency_ms"] for c in self.calls) / len(self.calls)

    def summary(self) -> dict[str, Any]:
        return {
            "n_calls": len(self.calls),
            "total_tokens": self.total_tokens,
            "avg_latency_ms": round(self.avg_latency_ms),
        }


class LLMOpsStack:
    """Production LLM stack with caching, retry, streaming, and cost tracking."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg
        self._llm = None
        self._embeddings = None
        self.cache: SemanticCache | None = None
        self.tracker = CostTracker()

    def _get_llm(self):
        if self._llm is None:
            from langchain_huggingface import HuggingFacePipeline
            from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline as hf_pipeline
            model_name = self.cfg.get("backbone", "HuggingFaceTB/SmolLM2-135M-Instruct")
            tokenizer = AutoTokenizer.from_pretrained(model_name)
            model = AutoModelForCausalLM.from_pretrained(model_name)
            pipe = hf_pipeline(
                "text-generation",
                model=model,
                tokenizer=tokenizer,
                max_new_tokens=self.cfg.get("max_new_tokens", 64),
                temperature=max(self.cfg.get("temperature", 0.1), 1e-6),
                do_sample=False,
                return_full_text=False,
            )
            self._llm = HuggingFacePipeline(pipeline=pipe)
        return self._llm

    def _get_embeddings(self):
        if self._embeddings is None:
            from langchain_huggingface import HuggingFaceEmbeddings
            self._embeddings = HuggingFaceEmbeddings(
                model_name=self.cfg.get("embed_backbone", "sentence-transformers/all-MiniLM-L6-v2"),
                encode_kwargs={"normalize_embeddings": True},
            )
        return self._embeddings

    def enable_cache(self) -> None:
        self.cache = SemanticCache(self._get_embeddings(), threshold=self.cfg.get("cache_threshold", 0.95))

    def invoke(self, prompt: str) -> str:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import StrOutputParser

        if self.cache is not None:
            hit = self.cache.get(prompt)
            if hit is not None:
                return hit

        chain = (
            ChatPromptTemplate.from_template("{prompt}") | self._get_llm() | StrOutputParser()
        ).with_retry(stop_after_attempt=3)

        t0 = time.monotonic()
        response = chain.invoke({"prompt": prompt})
        latency_ms = (time.monotonic() - t0) * 1000
        self.tracker.record(prompt, response, latency_ms)

        if self.cache is not None:
            self.cache.set(prompt, response)

        return response

    def stream(self, prompt: str) -> Iterator[str]:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import StrOutputParser

        chain = ChatPromptTemplate.from_template("{prompt}") | self._get_llm() | StrOutputParser()
        yield from chain.stream({"prompt": prompt})
