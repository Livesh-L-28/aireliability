from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from aireliability.rag.models import (
    FailureSeverity,
    RAGFailure,
    RAGFailureCategory,
    RAGStage,
    RetrievedChunk,
)


class MultiHopChain(BaseModel):
    """Structured representation of a multi-hop reasoning path."""

    is_complete: bool
    steps: list[dict[str, Any]] = Field(default_factory=list)


class MultiHopAnalyzer:
    """Analyzes intermediate entity hops and detects broken multi-document reasoning paths."""

    def analyze_multihop(
        self,
        query: str,
        answer: str,
        chunks: list[RetrievedChunk],
        expected_hops: list[str] | None = None,
    ) -> tuple[MultiHopChain, list[RAGFailure]]:
        """Verify presence of intermediate entity links connecting query to final answer."""
        full_context = " ".join(c.text for c in chunks)
        failures: list[RAGFailure] = []
        steps: list[dict[str, Any]] = []
        is_complete = True

        if expected_hops:
            for idx, hop in enumerate(expected_hops, start=1):
                found = hop.lower() in full_context.lower()
                steps.append({"hop": hop, "found": found, "step_index": idx})
                if not found:
                    is_complete = False
                    failures.append(
                        RAGFailure(
                            stage=RAGStage.RETRIEVAL,
                            category=RAGFailureCategory.BROKEN_MULTIHOP_CHAIN,
                            severity=FailureSeverity.HIGH,
                            message=f"BROKEN_MULTI_HOP_CHAIN: Missing intermediate bridge entity '{hop}' in retrieved context.",
                            affected_component=hop,
                            confidence=0.95,
                        )
                    )
        else:
            steps.append({"step_index": 1, "context_length": len(full_context)})

        chain = MultiHopChain(is_complete=is_complete, steps=steps)
        return chain, failures

    def analyze_chain(
        self,
        query_text: str,
        chunks: list[RetrievedChunk],
        answer_text: str = "",
        expected_hops: list[str] | None = None,
    ) -> tuple[dict[str, Any], list[RAGFailure], bool]:
        """Verify presence of intermediate entity links connecting query to final answer.

        Returns (chain_details, failures, is_valid_chain).
        """
        failures: list[RAGFailure] = []

        # Extract entities from query
        query_entities = re.findall(r"\b[A-Z][a-zA-Z0-9_\-]+\b", query_text)
        answer_entities = re.findall(r"\b[A-Z][a-zA-Z0-9_\-]+\b", answer_text)

        # Build chunk text map
        chunk_texts = [c.text for c in chunks]
        full_context = " ".join(chunk_texts)

        hops_detected: list[dict[str, Any]] = []
        broken_hop = False

        if expected_hops:
            for idx, hop_entity in enumerate(expected_hops, start=1):
                found_in_context = hop_entity.lower() in full_context.lower()
                hops_detected.append(
                    {
                        "hop_index": idx,
                        "entity": hop_entity,
                        "present_in_context": found_in_context,
                    }
                )
                if not found_in_context:
                    broken_hop = True
                    failures.append(
                        RAGFailure(
                            stage=RAGStage.RETRIEVAL,
                            category=RAGFailureCategory.RETRIEVAL_FAILURE,
                            severity=FailureSeverity.HIGH,
                            message=f"BROKEN_MULTI_HOP_CHAIN: Missing intermediate bridge entity '{hop_entity}' in retrieved documents.",
                            affected_component=hop_entity,
                            confidence=0.92,
                        )
                    )
        else:
            # Empirical check: Check if at least 2 distinct chunks contribute intermediate entities
            distinct_docs = {c.document_id for c in chunks}
            if len(distinct_docs) < 2 and len(query_entities) >= 2:
                failures.append(
                    RAGFailure(
                        stage=RAGStage.RETRIEVAL,
                        category=RAGFailureCategory.RETRIEVAL_FAILURE,
                        severity=FailureSeverity.MEDIUM,
                        message="POTENTIAL_MISSING_HOP: Query suggests multi-hop reasoning, but only 1 document was retrieved.",
                        confidence=0.75,
                    )
                )

        chain_info = {
            "query_entities": query_entities,
            "answer_entities": answer_entities,
            "hops": hops_detected,
            "is_broken": broken_hop,
        }

        return chain_info, failures, not broken_hop
