"""Grounding, Faithfulness, and Hallucination Evaluator."""

from __future__ import annotations

from pydantic import BaseModel

from aireliability.rag.models import (
    Citation,
    CitationStatus,
    Claim,
    ClaimSupportStatus,
    ConfidenceLevel,
    FailureSeverity,
    RAGFailure,
    RAGFailureCategory,
    RAGStage,
)


class GroundingResult(BaseModel):
    """Structured result of grounding evaluation."""

    grounding_score: float
    faithfulness_score: float
    hallucination_rate: float
    confidence: ConfidenceLevel = ConfidenceLevel.HIGH
    explanation: str = ""


class GroundingEvaluator:
    """Evaluates answer grounding, faithfulness to retrieved context, and hallucination rates."""

    def __init__(
        self,
        min_grounding_score: float = 0.75,
        min_faithfulness_score: float = 0.80,
        max_hallucination_rate: float = 0.10,
    ) -> None:
        self.min_grounding_score = min_grounding_score
        self.min_faithfulness_score = min_faithfulness_score
        self.max_hallucination_rate = max_hallucination_rate

    def evaluate_grounding(
        self,
        claims: list[Claim],
        citations: list[Citation],
        evidence_coverage_metrics: dict[str, float] | None = None,
    ) -> tuple[GroundingResult, list[RAGFailure]]:
        """Evaluate answer grounding and return (GroundingResult, failures)."""
        g_score, f_score, h_rate, failures, explanation = self.evaluate(
            claims, citations, evidence_coverage_metrics
        )
        total_claims = max(1, len(claims))
        supported_count = sum(
            1 for c in claims if c.support_status == ClaimSupportStatus.SUPPORTED
        )
        partial_count = sum(
            1
            for c in claims
            if c.support_status == ClaimSupportStatus.PARTIALLY_SUPPORTED
        )
        supported_ratio = (
            (supported_count + 0.5 * partial_count) / total_claims if claims else 1.0
        )

        res = GroundingResult(
            grounding_score=round(supported_ratio, 2),
            faithfulness_score=f_score,
            hallucination_rate=h_rate,
            confidence=ConfidenceLevel.HIGH
            if len(claims) >= 3
            else ConfidenceLevel.MEDIUM,
            explanation=explanation,
        )
        return res, failures

    def evaluate(
        self,
        claims: list[Claim],
        citations: list[Citation],
        evidence_coverage_metrics: dict[str, float] | None = None,
    ) -> tuple[float, float, float, list[RAGFailure], str]:
        """Compute Grounding Score, Faithfulness Score, Hallucination Rate, and failure attributions.

        Returns (grounding_score, faithfulness_score, hallucination_rate, list_of_failures, explanation).
        """
        failures: list[RAGFailure] = []
        cov_metrics = evidence_coverage_metrics or {}

        if not claims:
            # If no claims extracted, neutral grounding
            return (
                1.0,
                1.0,
                0.0,
                [],
                "No factual claims identified in generated answer.",
            )

        total_claims = len(claims)
        supported_count = sum(
            1 for c in claims if c.support_status == ClaimSupportStatus.SUPPORTED
        )
        partial_count = sum(
            1
            for c in claims
            if c.support_status == ClaimSupportStatus.PARTIALLY_SUPPORTED
        )
        contradicted_count = sum(
            1 for c in claims if c.support_status == ClaimSupportStatus.CONTRADICTED
        )
        unsupported_count = sum(
            1 for c in claims if c.support_status == ClaimSupportStatus.UNSUPPORTED
        )

        # 1. Hallucination Rate
        hallucination_rate = (
            unsupported_count + 1.5 * contradicted_count
        ) / total_claims
        hallucination_rate = round(max(0.0, min(1.0, hallucination_rate)), 4)

        # 2. Faithfulness Score (accuracy representing retrieved evidence)
        penalized_denom = (
            supported_count
            + partial_count
            + unsupported_count
            + (2.0 * contradicted_count)
        )
        faithfulness = (supported_count + 0.5 * partial_count) / max(
            1.0, penalized_denom
        )
        faithfulness_score = round(max(0.0, min(1.0, faithfulness)), 4)

        # 3. Grounding Score
        supported_ratio = (supported_count + 0.5 * partial_count) / total_claims
        citation_validity = (
            sum(1 for cit in citations if cit.status == CitationStatus.VALID)
            / len(citations)
            if citations
            else 0.5
        )
        evidence_coverage = cov_metrics.get("evidence_coverage", supported_ratio)

        # Weighted grounding formula
        grounding = (
            (0.5 * supported_ratio)
            + (0.3 * evidence_coverage)
            + (0.2 * citation_validity)
        )
        if contradicted_count > 0:
            grounding -= min(0.5, contradicted_count * 0.25)
        grounding_score = round(max(0.0, min(1.0, grounding)), 4)

        # 4. Confidence assessment
        conf_level = (
            ConfidenceLevel.HIGH if total_claims >= 3 else ConfidenceLevel.MEDIUM
        )

        # 5. Attributions and Failures
        if contradicted_count > 0:
            failures.append(
                RAGFailure(
                    stage=RAGStage.FAITHFULNESS,
                    category=RAGFailureCategory.FAITHFULNESS_FAILURE,
                    severity=FailureSeverity.CRITICAL,
                    message=(
                        f"CONTRADICTION_DETECTED: Answer explicitly contradicts retrieved evidence in "
                        f"{contradicted_count} claim(s)."
                    ),
                    confidence=0.95,
                )
            )

        if (
            contradicted_count > 0
            or unsupported_count > 0
            or grounding_score < self.min_grounding_score
        ):
            failures.append(
                RAGFailure(
                    stage=RAGStage.GROUNDING,
                    category=RAGFailureCategory.GROUNDING_FAILURE,
                    severity=FailureSeverity.CRITICAL
                    if contradicted_count > 0
                    else (
                        FailureSeverity.HIGH
                        if unsupported_count > 1
                        else FailureSeverity.MEDIUM
                    ),
                    message=(
                        f"GROUNDING_FAILURE: Grounding score {grounding_score:.2f} is compromised by "
                        f"{unsupported_count} unsupported and {contradicted_count} contradicted claim(s)."
                    ),
                    confidence=0.90,
                )
            )

        if hallucination_rate > self.max_hallucination_rate:
            failures.append(
                RAGFailure(
                    stage=RAGStage.GROUNDING,
                    category=RAGFailureCategory.HALLUCINATION,
                    severity=FailureSeverity.HIGH,
                    message=(
                        f"HALLUCINATION_THRESHOLD_EXCEEDED: Hallucination rate {hallucination_rate:.2f} "
                        f"exceeds tolerance {self.max_hallucination_rate:.2f}."
                    ),
                    confidence=0.90,
                )
            )

        explanation = (
            f"Grounding: {grounding_score:.2f}, Faithfulness: {faithfulness_score:.2f}, "
            f"Hallucination rate: {hallucination_rate:.2f}. "
            f"Claims: {supported_count} supported, {partial_count} partial, "
            f"{unsupported_count} unsupported, {contradicted_count} contradicted. "
            f"Confidence: {conf_level.value.upper()}."
        )

        return (
            grounding_score,
            faithfulness_score,
            hallucination_rate,
            failures,
            explanation,
        )
