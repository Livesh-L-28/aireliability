"""RAG Reliability Scoring, Failure Taxonomy, and Stage Root Cause Attribution."""

from __future__ import annotations

from aireliability.rag.models import (
    RAGFailure,
    RAGFailureCategory,
    RAGReliabilityScore,
    RAGStage,
    RAGStageScore,
)


class RAGReliabilityScorer:
    """Aggregates stage-level scores into an explainable overall RAG reliability score with hard vetoes."""

    def __init__(
        self,
        retrieval_weight: float = 0.25,
        ranking_weight: float = 0.10,
        context_weight: float = 0.10,
        grounding_weight: float = 0.25,
        faithfulness_weight: float = 0.15,
        citation_weight: float = 0.10,
        freshness_weight: float = 0.05,
    ) -> None:
        self.retrieval_weight = retrieval_weight
        self.ranking_weight = ranking_weight
        self.context_weight = context_weight
        self.grounding_weight = grounding_weight
        self.faithfulness_weight = faithfulness_weight
        self.citation_weight = citation_weight
        self.freshness_weight = freshness_weight

    def compute_score(
        self,
        stage_scores: dict[str, RAGStageScore],
        failures: list[RAGFailure],
        security_passed: bool = True,
    ) -> RAGReliabilityScore:
        """Compute multidimensional RAG reliability score with non-compensatory critical veto."""
        weights = {
            RAGStage.RETRIEVAL.value: self.retrieval_weight,
            RAGStage.RANKING.value: self.ranking_weight,
            RAGStage.CONTEXT.value: self.context_weight,
            RAGStage.GROUNDING.value: self.grounding_weight,
            RAGStage.FAITHFULNESS.value: self.faithfulness_weight,
            RAGStage.CITATION.value: self.citation_weight,
            RAGStage.FRESHNESS.value: self.freshness_weight,
        }

        weighted_sum = 0.0
        total_weight = 0.0

        for stage_name, weight in weights.items():
            if stage_name in stage_scores:
                st_score = stage_scores[stage_name].score
                weighted_sum += st_score * weight
                total_weight += weight

        raw_overall = (weighted_sum / total_weight) if total_weight > 0 else 1.0

        # Check for critical veto (security failure or severe factual contradiction)
        has_security_failure = not security_passed or any(
            f.category == RAGFailureCategory.SECURITY_VIOLATION for f in failures
        )
        has_critical_hallucination = any(
            f.category == RAGFailureCategory.FAITHFULNESS_FAILURE
            and f.severity.value == "critical"
            for f in failures
        )

        critical_veto = has_security_failure or has_critical_hallucination
        final_score = raw_overall
        explanation_parts = []

        if critical_veto:
            final_score = min(0.30, raw_overall)
            explanation_parts.append(
                "CRITICAL_VETO_TRIGGERED: Overall reliability score capped at 0.30 due to security or critical contradiction violation."
            )

        for st_name, st_res in stage_scores.items():
            explanation_parts.append(f"{st_name.capitalize()}: {st_res.score:.2f}")

        explanation = " | ".join(explanation_parts)

        return RAGReliabilityScore(
            overall_score=round(max(0.0, min(1.0, final_score)), 4),
            stage_scores=stage_scores,
            safety_passed=not has_security_failure,
            security_passed=security_passed and not has_security_failure,
            critical_veto=critical_veto,
            explanation=explanation,
        )
