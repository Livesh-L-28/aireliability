"""Unit tests for Phase 34 Intelligence data models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aireliability.intelligence.models import (
    ConfidenceLevel,
    CorrelationType,
    CrossRunCorrelation,
    EvidenceReference,
    FailureCluster,
    FailurePattern,
    ImpactAssessment,
    ImpactSeverity,
    IntelligenceAnalysis,
    IntelligenceConfidence,
    IntelligenceSummary,
    NormalizedFailure,
    PatternType,
    RecommendationPriority,
    ReliabilityRecommendation,
    ReliabilityTrend,
    TrendDirection,
)


def test_confidence_level_enums() -> None:
    assert ConfidenceLevel.VERY_LOW == "VERY_LOW"
    assert ConfidenceLevel.LOW == "LOW"
    assert ConfidenceLevel.MEDIUM == "MEDIUM"
    assert ConfidenceLevel.HIGH == "HIGH"
    assert ConfidenceLevel.VERY_HIGH == "VERY_HIGH"


def test_pattern_type_enums() -> None:
    assert PatternType.RECURRING == "recurring"
    assert PatternType.INCREASING == "increasing"
    assert PatternType.DECREASING == "decreasing"
    assert PatternType.NEW == "new"
    assert PatternType.DISAPPEARING == "disappearing"
    assert PatternType.PERSISTENT == "persistent"
    assert PatternType.INTERMITTENT == "intermittent"
    assert PatternType.TOOL_SPECIFIC == "tool_specific"
    assert PatternType.RETRIEVER_SPECIFIC == "retriever_specific"


def test_intelligence_confidence_validation() -> None:
    conf = IntelligenceConfidence(
        score=0.92,
        level=ConfidenceLevel.VERY_HIGH,
        evidence_count=5,
        sample_size=20,
        rationale="Strong signal",
        factors={"evidence": 0.9, "agreement": 0.95},
    )
    assert conf.score == 0.92
    assert conf.level == ConfidenceLevel.VERY_HIGH
    assert conf.evidence_count == 5

    # Out of bounds validation
    with pytest.raises(ValidationError):
        IntelligenceConfidence(score=1.5)
    with pytest.raises(ValidationError):
        IntelligenceConfidence(score=-0.1)


def test_evidence_reference_serialization() -> None:
    ref = EvidenceReference(
        source_type="evaluation_report",
        source_id="rep_12345",
        description="Run on golden benchmark",
        metric_name="accuracy",
        observed_value=0.88,
        metadata={"run": 1},
    )
    data = ref.model_dump()
    assert data["source_type"] == "evaluation_report"
    assert data["source_id"] == "rep_12345"
    assert data["observed_value"] == 0.88

    json_str = ref.model_dump_json()
    loaded = EvidenceReference.model_validate_json(json_str)
    assert loaded.reference_id == ref.reference_id
    assert loaded.source_id == ref.source_id


def test_normalized_failure_model() -> None:
    nf = NormalizedFailure(
        fingerprint="fp_abc123",
        failure_id="fail_001",
        category="retrieval",
        failure_type="missing_context",
        root_cause_category="retrieval",
        root_cause_type="missing_context",
        evaluator="GroundednessEvaluator",
        metric="groundedness",
        component="retriever:vector_store",
        severity="HIGH",
        sanitized_message="Retrieved context omitted vital fact.",
    )
    assert nf.fingerprint == "fp_abc123"
    assert nf.component == "retriever:vector_store"
    assert nf.sanitized_message == "Retrieved context omitted vital fact."


def test_failure_cluster_model() -> None:
    cluster = FailureCluster(
        name="Cluster: Retrieval Failure",
        fingerprint="fp_retrieval_01",
        representative_failure_id="fail_1",
        failure_ids=["fail_1", "fail_2", "fail_3"],
        dominant_category="retrieval",
        dominant_root_cause="retrieval.missing_context",
        frequency=3,
        affected_components=["retriever:faiss"],
    )
    assert cluster.frequency == 3
    assert len(cluster.failure_ids) == 3
    assert "retriever:faiss" in cluster.affected_components


def test_failure_pattern_model() -> None:
    pattern = FailurePattern(
        pattern_type=PatternType.INCREASING,
        title="Increasing Hallucinations",
        description="Hallucinations escalated from 2 to 14 across 3 evaluations.",
        fingerprint="fp_hallucination",
        frequency=14,
        affected_components=["model:gpt-4o"],
    )
    assert pattern.pattern_type == PatternType.INCREASING
    assert pattern.frequency == 14


def test_cross_run_correlation_model() -> None:
    corr = CrossRunCorrelation(
        source_change_type="model_version",
        source_change_value="gpt-4o -> gpt-4o-mini",
        observed_effect="Accuracy dropped by 12%",
        affected_metric_or_failure="accuracy",
        strength=0.75,
        is_causal=False,
        relationship_type=CorrelationType.CORRELATED,
        description="Model downgrade correlates with accuracy degradation.",
    )
    assert corr.is_causal is False
    assert corr.relationship_type == CorrelationType.CORRELATED
    assert corr.strength == 0.75

    # Out of bounds strength
    with pytest.raises(ValidationError):
        CrossRunCorrelation(
            source_change_type="a",
            source_change_value="b",
            observed_effect="c",
            affected_metric_or_failure="d",
            strength=1.5,
        )


def test_reliability_trend_model() -> None:
    trend = ReliabilityTrend(
        metric_or_dimension="latency",
        direction=TrendDirection.INCREASING,
        rate_of_change=12.5,
        relative_change=0.25,
        volatility=3.2,
        observations_count=5,
        historical_values=[100.0, 110.0, 118.0, 122.0, 125.0],
    )
    assert trend.direction == TrendDirection.INCREASING
    assert trend.observations_count == 5
    assert len(trend.historical_values) == 5


def test_impact_assessment_model() -> None:
    impact = ImpactAssessment(
        target_id="cluster_123",
        observed_impact=ImpactSeverity.CRITICAL,
        estimated_impact=ImpactSeverity.CRITICAL,
        impact_score=1.0,
        safety_critical=True,
        security_critical=False,
        affected_evaluations_count=2,
        affected_failures_count=5,
        explanation="Severe safety breach identified.",
    )
    assert impact.safety_critical is True
    assert impact.impact_score == 1.0
    assert impact.observed_impact == ImpactSeverity.CRITICAL


def test_reliability_recommendation_model() -> None:
    rec = ReliabilityRecommendation(
        title="Block deployment and pin retriever prompt",
        description="High hallucination rate caused by missing context.",
        priority=RecommendationPriority.CRITICAL,
        suggested_action="Review retrieval indexing and block pipeline gate.",
        rationale="Critical safety regression detected.",
        affected_components=["retriever:pinecone"],
        remediation_links={"gate_engine": "airel gate --policy strict"},
    )
    assert rec.priority == RecommendationPriority.CRITICAL
    assert rec.remediation_links["gate_engine"] == "airel gate --policy strict"


def test_full_intelligence_analysis_roundtrip() -> None:
    summary = IntelligenceSummary(
        total_failures_analyzed=10,
        total_clusters=2,
        total_patterns=1,
        total_correlations=1,
        total_trends=1,
        total_recommendations=2,
        critical_issues_count=1,
        dominant_failure_categories={"retrieval": 8, "safety": 2},
        dominant_root_causes={"retrieval.missing_context": 8},
        highest_priority_recommendations=["Block deployment"],
    )

    analysis = IntelligenceAnalysis(
        target_name="agent_v2",
        summary=summary,
        clusters=[],
        patterns=[],
        correlations=[],
        trends=[],
        impacts=[],
        recommendations=[],
    )

    json_str = analysis.model_dump_json()
    loaded = IntelligenceAnalysis.model_validate_json(json_str)
    assert loaded.target_name == "agent_v2"
    assert loaded.summary.total_failures_analyzed == 10
    assert loaded.summary.critical_issues_count == 1
    assert loaded.summary.dominant_failure_categories["retrieval"] == 8
