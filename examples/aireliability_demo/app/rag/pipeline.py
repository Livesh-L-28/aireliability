"""End-to-end RAG Pipeline with controlled failure scenarios."""

from __future__ import annotations

import time
from typing import Any

from aireliability.rag.models import (
    RetrievedChunk,
    RetrievedDocument,
)
from aireliability_demo.app.llm.deterministic import DeterministicLLM
from aireliability_demo.app.llm.interface import LLMProvider
from aireliability_demo.app.rag.documents import load_documents
from aireliability_demo.app.rag.retriever import DeterministicRetriever


class RAGPipeline:
    """Production-grade demo RAG pipeline orchestrating retrieval, context assembly,

    and generation with deterministic failure scenario control.
    """

    def __init__(
        self,
        retriever: DeterministicRetriever | None = None,
        llm: LLMProvider | None = None,
    ) -> None:
        if retriever is None:
            docs = load_documents()
            self.retriever = DeterministicRetriever(docs)
        else:
            self.retriever = retriever

        self.llm = llm or DeterministicLLM()

    def run(
        self,
        query_text: str,
        scenario: str = "NORMAL_RETRIEVAL",
        top_k: int = 3,
        expected_document_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Execute the RAG pipeline under a specified scenario."""
        scenario_upper = scenario.upper()

        # 1. Retrieval Stage with Scenario Injections
        if scenario_upper == "MISSING_DOCUMENT":
            retrieved_docs: list[RetrievedDocument] = []
            retrieved_chunks: list[RetrievedChunk] = []
        elif scenario_upper == "LOW_RELEVANCE_RETRIEVAL":
            # Synthesize irrelevant chunks with low scores
            retrieved_docs = [
                RetrievedDocument(
                    document_id="irrelevant_doc.md",
                    title="Irrelevant Topic",
                    text="Discussion about planetary orbits and astronomy.",
                    source="unrelated_kb",
                )
            ]
            retrieved_chunks = [
                RetrievedChunk(
                    chunk_id="irr_c1",
                    document_id="irrelevant_doc.md",
                    text="Mars has an orbital eccentricity of 0.0934.",
                    rank=1,
                    retrieval_score=0.12,
                )
            ]
        elif scenario_upper == "CONFLICTING_DOCUMENT":
            retrieved_docs, retrieved_chunks = self.retriever.retrieve(
                query_text, top_k=top_k
            )
            # Inject conflicting statements
            conflict_chunk = RetrievedChunk(
                chunk_id="conflict_chk_1",
                document_id="conflicting_policy.md",
                text="The hard safety veto has been deprecated and now allows critical violations without blocking.",
                rank=len(retrieved_chunks) + 1,
                retrieval_score=0.88,
                metadata={"conflict_status": "CONTRADICTION"},
            )
            retrieved_chunks.append(conflict_chunk)
            retrieved_docs.append(
                RetrievedDocument(
                    document_id="conflicting_policy.md",
                    title="Conflicting Policy",
                    text=conflict_chunk.text,
                    source="conflicting_source",
                )
            )
        elif scenario_upper == "STALE_DOCUMENT":
            retrieved_docs, retrieved_chunks = self.retriever.retrieve(
                query_text, top_k=top_k
            )
            # Mark chunks as stale (timestamp 3 years ago)
            stale_time = time.time() - (365 * 3 * 86400)
            for c in retrieved_chunks:
                c.metadata["timestamp"] = stale_time
                c.metadata["last_updated"] = "2021-01-01T00:00:00Z"
        elif scenario_upper == "INSUFFICIENT_CONTEXT":
            retrieved_docs, retrieved_chunks = self.retriever.retrieve(
                query_text, top_k=1
            )
            if retrieved_chunks:
                # Truncate text to incomplete snippet
                retrieved_chunks[0].text = retrieved_chunks[0].text[:30] + "..."
        else:
            # NORMAL_RETRIEVAL or GROUNDING_FAILURE
            retrieved_docs, retrieved_chunks = self.retriever.retrieve(
                query_text, top_k=top_k
            )

        # 2. Context Window Construction
        context_parts = []
        for i, chk in enumerate(retrieved_chunks, start=1):
            context_parts.append(f"[{i}] {chk.text}")
        context_text = "\n\n".join(context_parts)

        # 3. Answer Generation
        if scenario_upper == "GROUNDING_FAILURE":
            # Generate hallucinated answer containing claims not present in context
            answer_text = (
                "The AI reliability platform was created in 1842 by Charles Babbage [1]. "
                "It guarantees quantum zero-point stability across all neural layers [2]."
            )
        elif scenario_upper == "MISSING_DOCUMENT":
            answer_text = (
                "I cannot find any relevant documentation to answer this question."
            )
        elif scenario_upper == "LOW_RELEVANCE_RETRIEVAL":
            answer_text = (
                "Based on the documents, Mars has an eccentricity of 0.0934 [1], "
                "which is not directly related to your reliability question."
            )
        else:
            # Normal / Grounded Generation with Citations
            if retrieved_chunks:
                answer_text = (
                    f"According to the documentation [1], {retrieved_chunks[0].text[:180]}. "
                    "This is verified under enterprise reliability controls."
                )
            else:
                answer_text = self.llm.generate(query_text)

        return {
            "query": query_text,
            "scenario": scenario_upper,
            "retrieved_documents": retrieved_docs,
            "retrieved_chunks": retrieved_chunks,
            "context_text": context_text,
            "generated_answer": answer_text,
            "expected_document_ids": expected_document_ids or [],
        }
