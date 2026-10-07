"""Risk, severity, and operational impact assessment for reliability findings."""

from __future__ import annotations

from collections.abc import Sequence

from aireliability.intelligence.confidence import ConfidenceEngine
from aireliability.intelligence.models import (
    EvidenceReference,
    FailureCluster,
    ImpactAssessment,
    ImpactSeverity,
)


class ImpactAnalyzer:
    """Evaluates the risk, operational reach, and severity of failure clusters."""

    def assess_cluster(
        self,
        cluster: FailureCluster,
        total_evaluations: int = 1,
        evidence_pool: list[EvidenceReference] | None = None,
    ) -> ImpactAssessment:
        """Calculate the ImpactAssessment for a single FailureCluster."""
        is_safety = cluster.dominant_category == "safety"
        is_security = cluster.dominant_category == "security"

        # Base impact calculation
        # Safety / security violations are non-negotiable CRITICAL impacts
        if is_safety or is_security:
            observed_impact = ImpactSeverity.CRITICAL
            estimated_impact = ImpactSeverity.CRITICAL
            score = 1.0
            explanation = (
                f"Cluster '{cluster.name}' contains critical {cluster.dominant_category} "
                f"violations across {cluster.frequency} occurrences. Direct deployment block warranted."
            )
        elif cluster.frequency >= 10 or (
            total_evaluations > 0 and cluster.frequency / total_evaluations >= 0.30
        ):
            observed_impact = ImpactSeverity.HIGH
            estimated_impact = ImpactSeverity.HIGH
            score = 0.80
            explanation = (
                f"Cluster '{cluster.name}' demonstrates widespread impact affecting {cluster.frequency} "
                f"instances ({cluster.frequency / max(1, total_evaluations):.1%} of run)."
            )
        elif cluster.frequency >= 3:
            observed_impact = ImpactSeverity.MEDIUM
            estimated_impact = ImpactSeverity.MEDIUM
            score = 0.50
            explanation = f"Cluster '{cluster.name}' demonstrates moderate recurrence ({cluster.frequency} failures)."
        else:
            observed_impact = ImpactSeverity.LOW
            estimated_impact = ImpactSeverity.LOW
            score = 0.25
            explanation = f"Cluster '{cluster.name}' represents an isolated failure ({cluster.frequency} occurrence)."

        conf = ConfidenceEngine.calculate(
            evidence_count=len(cluster.evidence) or cluster.frequency,
            sample_size=total_evaluations,
            agreement_rate=1.0 if is_safety or is_security else 0.85,
        )

        return ImpactAssessment(
            target_id=cluster.cluster_id,
            observed_impact=observed_impact,
            estimated_impact=estimated_impact,
            impact_score=score,
            safety_critical=is_safety,
            security_critical=is_security,
            affected_evaluations_count=total_evaluations,
            affected_failures_count=cluster.frequency,
            affected_components=cluster.affected_components,
            explanation=explanation,
            confidence=conf,
            evidence=cluster.evidence,
        )

    def assess_all(
        self,
        clusters: Sequence[FailureCluster],
        total_evaluations: int = 1,
    ) -> list[ImpactAssessment]:
        """Assess all clusters and sort by impact score descending."""
        assessments = [
            self.assess_cluster(c, total_evaluations=total_evaluations)
            for c in clusters
        ]
        assessments.sort(key=lambda a: a.impact_score, reverse=True)
        return assessments

    def prioritize_clusters(
        self,
        clusters: Sequence[FailureCluster],
        total_evaluations: int = 1,
    ) -> list[tuple[FailureCluster, ImpactAssessment, float]]:
        """Rank clusters by prioritized urgency returning (cluster, assessment, priority_rank)."""
        ranked: list[tuple[FailureCluster, ImpactAssessment, float]] = []
        for c in clusters:
            assessment = self.assess_cluster(c, total_evaluations=total_evaluations)
            # Weighted rank combining impact score, frequency, and safety
            safety_multiplier = (
                2.0
                if (assessment.safety_critical or assessment.security_critical)
                else 1.0
            )
            rank_score = (
                assessment.impact_score * 0.6 + min(1.0, c.frequency / 20.0) * 0.4
            ) * safety_multiplier
            ranked.append((c, assessment, round(rank_score, 3)))

        ranked.sort(key=lambda item: item[2], reverse=True)
        return ranked
