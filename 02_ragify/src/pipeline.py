"""RAGify core pipeline — multi-strategy RAG with RAGAS evaluation."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings


def build_embeddings(model_name: str) -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(
        model_name=model_name,
        encode_kwargs={"normalize_embeddings": True},
    )


class RAGifyPipeline:
    """Multi-strategy retriever: similarity, MMR, multi-query, compression."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg
        self.embeddings = build_embeddings(
            cfg.get("embed_backbone", "sentence-transformers/all-MiniLM-L6-v2")
        )
        self.store: FAISS | None = None
        self._llm = None

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
                max_new_tokens=self.cfg.get("max_new_tokens", 128),
                temperature=max(self.cfg.get("temperature", 0.1), 1e-6),
                do_sample=False,
                return_full_text=False,
            )
            self._llm = HuggingFacePipeline(pipeline=pipe)
        return self._llm

    def index(self, docs: list[Document]) -> None:
        self.store = FAISS.from_documents(docs, self.embeddings)

    def similarity_retrieve(self, query: str, k: int = 3) -> list[Document]:
        return self.store.similarity_search(query, k=k)

    def mmr_retrieve(self, query: str, k: int = 3, fetch_k: int = 10) -> list[Document]:
        return self.store.max_marginal_relevance_search(query, k=k, fetch_k=fetch_k)

    def multi_query_retrieve(self, query: str, k: int = 3) -> list[Document]:
        from langchain_classic.retrievers.multi_query import MultiQueryRetriever
        base = self.store.as_retriever(search_kwargs={"k": k})
        mq = MultiQueryRetriever.from_llm(retriever=base, llm=self._get_llm())
        results = mq.invoke(query)
        seen = set()
        deduped = []
        for r in results:
            key = r.page_content[:50]
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        return deduped

    def compression_retrieve(self, query: str, k: int = 3) -> list[Document]:
        from langchain_classic.retrievers.contextual_compression import ContextualCompressionRetriever
        from langchain_classic.retrievers.document_compressors import EmbeddingsFilter
        base = self.store.as_retriever(search_kwargs={"k": k})
        ef = EmbeddingsFilter(embeddings=self.embeddings, similarity_threshold=0.7)
        cr = ContextualCompressionRetriever(base_compressor=ef, base_retriever=base)
        return cr.invoke(query)

    def rag_answer(self, query: str, docs: list[Document]) -> str:
        context = "\n\n".join(d.page_content for d in docs)
        prompt = ChatPromptTemplate.from_template(
            "Answer using only the provided context. Be concise.\n\n"
            "Context:\n{context}\n\nQuestion: {query}\n\nAnswer:"
        )
        chain = prompt | self._get_llm() | StrOutputParser()
        return chain.invoke({"context": context, "query": query})

    def evaluate_ragas(self, eval_rows: list[dict]) -> dict[str, float]:
        """Run RAGAS metrics on eval_rows. Falls back to simple overlap if unavailable."""
        try:
            from ragas import EvaluationDataset, evaluate
            from ragas.metrics import ContextRecall, SemanticSimilarity
            from ragas.llms import LangchainLLMWrapper
            from ragas.embeddings import LangchainEmbeddingsWrapper
            dataset = EvaluationDataset.from_list(eval_rows)
            result = evaluate(
                dataset,
                metrics=[ContextRecall(), SemanticSimilarity()],
                llm=LangchainLLMWrapper(self._get_llm()),
                embeddings=LangchainEmbeddingsWrapper(self.embeddings),
            )
            df = result.to_pandas()
            return {
                "context_recall": float(df["context_recall"].mean()) if "context_recall" in df.columns else 0.0,
                "semantic_similarity": float(df["semantic_similarity"].mean()) if "semantic_similarity" in df.columns else 0.0,
            }
        except Exception:
            recalls = []
            for row in eval_rows:
                ref = row.get("reference", "")[:30].lower()
                hits = sum(1 for c in row.get("retrieved_contexts", []) if ref in c.lower())
                recalls.append(min(hits, 1))
            return {"context_recall": sum(recalls) / max(len(recalls), 1), "semantic_similarity": 0.0}
