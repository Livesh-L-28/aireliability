"""Unit tests for Phase 34 deterministic RecommendationEngine."""

from __future__ import annotations

from aireliability.intelligence.models import (
    CorrelationType,
    CrossRunCorrelation,
    FailureCluster,
    FailurePattern,
    PatternType,
    RecommendationPriority,
    ReliabilityTrend,
    TrendDirection,
)
from aireliability.intelligence.recommendations import RecommendationEngine


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


def test_safety_critical_recommendation() -> None:
    engine = RecommendationEngine()
    c_safe = _make_cluster("c_safe", "Jailbreak bypass", "safety", frequency=2)

    recs = engine.generate_recommendations(clusters=[c_safe])
    critical_recs = [r for r in recs if r.priority == RecommendationPriority.CRITICAL]

    assert len(critical_recs) >= 1
    rec = critical_recs[0]
    assert "Block" in rec.title or "Gate" in rec.title
    assert "regression" in rec.suggested_action.lower()
    assert rec.remediation_links.get("action") == "gate_block"


def test_worsening_trend_recommendation() -> None:
    engine = RecommendationEngine()
    trend = ReliabilityTrend(
        metric_or_dimension="hallucination_rate",
        direction=TrendDirection.INCREASING,
        rate_of_change=0.08,
        relative_change=1.5,
        observations_count=4,
    )

    recs = engine.generate_recommendations(clusters=[], trends=[trend])
    hallucination_recs = [r for r in recs if "hallucination" in r.title.lower()]

    assert len(hallucination_recs) >= 1
    rec = hallucination_recs[0]
    assert rec.priority in (
        RecommendationPriority.HIGH,
        RecommendationPriority.CRITICAL,
    )
    assert "retrieval" in rec.suggested_action.lower()


def test_tool_failure_recommendation() -> None:
    engine = RecommendationEngine()
    c_tool = _make_cluster(
        "c_t", "Tool arg error", "tool", frequency=3, components=["tool:sql_query"]
    )
    pattern = FailurePattern(
        pattern_type=PatternType.TOOL_SPECIFIC,
        title="Tool specific failure: tool:sql_query",
        description="Failures isolated to sql_query",
        fingerprint="fp_tool",
        frequency=3,
        affected_components=["tool:sql_query"],
    )

    recs = engine.generate_recommendations(clusters=[c_tool], patterns=[pattern])
    tool_recs = [r for r in recs if "tool" in r.title.lower()]

    assert len(tool_recs) >= 1
    assert "tool:sql_query" in tool_recs[0].affected_components


def test_retriever_correlation_recommendation() -> None:
    engine = RecommendationEngine()
    corr = CrossRunCorrelation(
        source_change_type="retriever_version",
        source_change_value="pinecone_v1 -> chroma_v2",
        observed_effect="Retrieval recall dropped by 25%",
        affected_metric_or_failure="context_recall",
        strength=0.9,
        relationship_type=CorrelationType.INFERRED,
    )

    recs = engine.generate_recommendations(clusters=[], correlations=[corr])
    ret_recs = [
        r
        for r in recs
        if "retriever" in r.title.lower() or "retrieval" in r.title.lower()
    ]

    assert len(ret_recs) >= 1
    assert "chroma_v2" in ret_recs[0].description
