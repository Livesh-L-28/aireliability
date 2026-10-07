"""Retrieval repair generator tuning RAG components and retrieval configurations."""

from __future__ import annotations

from typing import Any

from aireliability.remediation.models import (
    RemediationPatch,
    RemediationRiskTier,
    RepairType,
)
from aireliability.remediation.repairs.base import BaseRepairGenerator


class RetrievalRepairer(BaseRepairGenerator):
    """Diagnoses retrieval deficiencies and synthesizes retrieval parameter patches."""

    def __init__(self) -> None:
        super().__init__(RepairType.RETRIEVAL)

    def can_handle(self, evidence: Any) -> bool:
        """Check if failure is related to retrieval, RAG, or context search."""
        text = self._extract_text_content(evidence)
        return any(
            kw in text
            for kw in [
                "retriev",
                "rag",
                "similarity",
                "embedding",
                "chunk",
                "rerank",
                "context_missing",
            ]
        )

    def generate_patches(
        self,
        evidence: Any,
        context: dict[str, Any] | None = None,
    ) -> list[RemediationPatch]:
        """Synthesize retrieval configuration tuning patches."""
        context = context or {}
        target_component = context.get("target_component", "default_retriever")
        original_config = context.get(
            "original_retrieval_config",
            {
                "top_k": 3,
                "similarity_threshold": 0.70,
                "reranking_enabled": False,
                "hybrid_search": False,
            },
        )

        error_msg = self._extract_text_content(evidence)

        patches: list[RemediationPatch] = []

        # Strategy 1: Missing context / low recall -> Increase top_k
        if (
            "missing" in error_msg
            or "recall" in error_msg
            or "no_result" in error_msg
            or "not_found" in error_msg
        ):
            current_top_k = original_config.get("top_k", 3)
            new_top_k = min(15, current_top_k + 4)
            patched_config = dict(original_config)
            patched_config["top_k"] = new_top_k
            patches.append(
                RemediationPatch(
                    repair_type=self.repair_type,
                    target_component_id=target_component,
                    target_component_type="retriever",
                    description=f"Increase retrieval top_k from {current_top_k} to {new_top_k} to improve document recall",
                    original_value=original_config,
                    patched_value=patched_config,
                    diff_summary=f"top_k: {current_top_k} -> {new_top_k}",
                    parameters={"action": "increase_top_k", "new_top_k": new_top_k},
                )
            )

        # Strategy 2: Irrelevant noise / hallucination -> Enable reranker and tighten similarity threshold
        elif (
            "noisy" in error_msg
            or "irrelevant" in error_msg
            or "threshold" in error_msg
        ):
            patched_config = dict(original_config)
            patched_config["similarity_threshold"] = 0.82
            patched_config["reranking_enabled"] = True
            patches.append(
                RemediationPatch(
                    repair_type=self.repair_type,
                    target_component_id=target_component,
                    target_component_type="retriever",
                    description="Enable neural reranker and increase similarity threshold to filter irrelevant documents",
                    original_value=original_config,
                    patched_value=patched_config,
                    diff_summary="similarity_threshold: 0.70 -> 0.82, reranking_enabled: True",
                    parameters={
                        "action": "filter_noise",
                        "similarity_threshold": 0.82,
                        "reranking_enabled": True,
                    },
                )
            )

        # Strategy 3: Hybrid search fallback
        else:
            patched_config = dict(original_config)
            patched_config["hybrid_search"] = True
            patches.append(
                RemediationPatch(
                    repair_type=self.repair_type,
                    target_component_id=target_component,
                    target_component_type="retriever",
                    description="Enable hybrid dense-sparse retrieval to capture exact keyword matches",
                    original_value=original_config,
                    patched_value=patched_config,
                    diff_summary="hybrid_search: False -> True",
                    parameters={
                        "action": "enable_hybrid_search",
                        "hybrid_search": True,
                    },
                )
            )

        return patches

    def estimate_risk(self, patches: list[RemediationPatch]) -> RemediationRiskTier:
        return RemediationRiskTier.MEDIUM
