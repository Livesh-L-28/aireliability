"""Unit tests for Phase 34 operational and risk ImpactAnalyzer."""

from __future__ import annotations

from aireliability.intelligence.impact import ImpactAnalyzer
from aireliability.intelligence.models import (
    FailureCluster,
    ImpactSeverity,
)


def _make_cluster(
    cluster_id: str,
    name: str,
    category: str,
    frequency: int,
    components: list[str] | None = None,
) -> FailureCluster:
    return FailureCluster(
        cluster_id=cluster_id,
        name=name,
        fingerprint=f"fp_{cluster_id}",
        representative_failure_id=f"rep_{cluster_id}",
        dominant_category=category,
        dominant_root_cause=f"{category}.root",
        frequency=frequency,
        affected_components=components or [],
    )


def test_safety_impact_critical() -> None:
    analyzer = ImpactAnalyzer()
    c = _make_cluster("c_saf", "Prompt injection", "safety", frequency=1)
    assessment = analyzer.assess_cluster(c, total_evaluations=100)

    assert assessment.observed_impact == ImpactSeverity.CRITICAL
    assert assessment.estimated_impact == ImpactSeverity.CRITICAL
    assert assessment.safety_critical is True
    assert assessment.impact_score == 1.0


def test_security_impact_critical() -> None:
    analyzer = ImpactAnalyzer()
    c = _make_cluster("c_sec", "Secret leak", "security", frequency=1)
    assessment = analyzer.assess_cluster(c, total_evaluations=50)

    assert assessment.observed_impact == ImpactSeverity.CRITICAL
    assert assessment.security_critical is True
    assert assessment.impact_score == 1.0


def test_high_impact_widespread() -> None:
    analyzer = ImpactAnalyzer()
    c = _make_cluster("c_high", "Widespread failure", "output", frequency=12)
    assessment = analyzer.assess_cluster(c, total_evaluations=30)

    assert assessment.observed_impact == ImpactSeverity.HIGH
    assert assessment.impact_score >= 0.80
    assert assessment.safety_critical is False


def test_medium_and_low_impact() -> None:
    analyzer = ImpactAnalyzer()
    c_med = _make_cluster("c_med", "Moderate failure", "tool", frequency=4)
    assessment_med = analyzer.assess_cluster(c_med, total_evaluations=100)
    assert assessment_med.observed_impact == ImpactSeverity.MEDIUM

    c_low = _make_cluster("c_low", "Isolated flake", "task", frequency=1)
    assessment_low = analyzer.assess_cluster(c_low, total_evaluations=100)
    assert assessment_low.observed_impact == ImpactSeverity.LOW


def test_prioritize_clusters() -> None:
    analyzer = ImpactAnalyzer()
    c_safe = _make_cluster("c1", "Safety breach", "safety", frequency=2)
    c_tool = _make_cluster("c2", "Tool crash", "tool", frequency=15)
    c_task = _make_cluster("c3", "Format issue", "task", frequency=1)

    ranked = analyzer.prioritize_clusters(
        [c_tool, c_task, c_safe], total_evaluations=50
    )
    assert len(ranked) == 3
    # Safety cluster must be top priority despite lower frequency
    top_cluster, top_impact, top_score = ranked[0]
    assert top_cluster.cluster_id == "c1"
    assert top_impact.safety_critical is True
