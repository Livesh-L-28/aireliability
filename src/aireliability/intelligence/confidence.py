"""Deterministic confidence calculation for AI Reliability Intelligence insights."""

from __future__ import annotations

import math

from aireliability.intelligence.models import ConfidenceLevel, IntelligenceConfidence


class ConfidenceEngine:
    """Computes explainable, deterministic confidence ratings for intelligence conclusions."""

    @classmethod
    def score_to_level(cls, score: float) -> ConfidenceLevel:
        """Map numerical confidence score to categorical ConfidenceLevel."""
        if score >= 0.85:
            return ConfidenceLevel.VERY_HIGH
        elif score >= 0.70:
            return ConfidenceLevel.HIGH
        elif score >= 0.50:
            return ConfidenceLevel.MEDIUM
        elif score >= 0.30:
            return ConfidenceLevel.LOW
        return ConfidenceLevel.VERY_LOW

    @classmethod
    def calculate(
        cls,
        evidence_count: int,
        sample_size: int = 1,
        agreement_rate: float = 1.0,
        data_completeness: float = 1.0,
        base_confidence: float = 0.5,
    ) -> IntelligenceConfidence:
        """Compute structured confidence score and categorical rating.

        Args:
            evidence_count: Number of independent evidence artifacts supporting the conclusion.
            sample_size: Number of test runs, evaluations, or traces in the observation pool.
            agreement_rate: Degree of consistency across signals (0.0 to 1.0).
            data_completeness: Ratio of expected fields present (0.0 to 1.0).
            base_confidence: Baseline prior confidence (default: 0.5).

        Returns:
            IntelligenceConfidence model with score, level, rationale, and factors.
        """
        # 1. Evidence factor: 0 evidence -> 0.2, 1 -> 0.55, 3+ -> up to 1.0
        ev_factor = min(1.0, 0.2 + 0.25 * math.log(max(1, evidence_count) + 1))

        # 2. Sample size scaling factor: small samples reduce confidence
        sample_factor = min(1.0, 0.3 + 0.35 * math.log10(max(1, sample_size) + 9))

        # 3. Agreement factor: penalizes conflicting signals
        ag_factor = max(0.1, min(1.0, agreement_rate))

        # 4. Data completeness: penalizes missing context or incomplete traces
        comp_factor = max(0.2, min(1.0, data_completeness))

        # 5. Composite weighted calculation
        raw_score = (
            0.35 * ev_factor
            + 0.25 * sample_factor
            + 0.25 * ag_factor
            + 0.15 * comp_factor
        )

        final_score = round(max(0.05, min(0.99, raw_score)), 3)
        level = cls.score_to_level(final_score)

        rationale = (
            f"Confidence {level.value} ({final_score:.2f}) based on {evidence_count} evidence "
            f"references across {sample_size} observed samples (agreement: {ag_factor:.0%}, "
            f"completeness: {comp_factor:.0%})."
        )

        return IntelligenceConfidence(
            score=final_score,
            level=level,
            evidence_count=evidence_count,
            sample_size=sample_size,
            rationale=rationale,
            factors={
                "evidence_factor": round(ev_factor, 3),
                "sample_factor": round(sample_factor, 3),
                "agreement_factor": round(ag_factor, 3),
                "completeness_factor": round(comp_factor, 3),
            },
        )
