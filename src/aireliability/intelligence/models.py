"""Strongly typed data models for AI Reliability Intelligence (Phase 34)."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def _generate_id(prefix: str = "intel") -> str:
    """Generate a unique identifier with a given prefix."""
    return f"{prefix}_{uuid4().hex[:12]}"


def _utc_now() -> datetime:
    """Return the current datetime in UTC timezone."""
    return datetime.now(UTC)


class ConfidenceLevel(StrEnum):
    """Categorical confidence rating for intelligence insights."""

    VERY_LOW = "VERY_LOW"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class PatternType(StrEnum):
    """Classification taxonomy for detected failure patterns."""

    RECURRING = "recurring"
    INCREASING = "increasing"
    DECREASING = "decreasing"
    NEW = "new"
    DISAPPEARING = "disappearing"
    PERSISTENT = "persistent"
    INTERMITTENT = "intermittent"
    ENVIRONMENT_SPECIFIC = "environment_specific"
    MODEL_SPECIFIC = "model_specific"
    PROMPT_SPECIFIC = "prompt_specific"
    DATASET_SPECIFIC = "dataset_specific"
    TOOL_SPECIFIC = "tool_specific"
    RETRIEVER_SPECIFIC = "retriever_specific"
    ANOMALOUS = "anomalous"


class TrendDirection(StrEnum):
    """Directional trend for reliability scores and failure metrics."""

    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"
    VOLATILE = "volatile"
    INSUFFICIENT_DATA = "insufficient_data"


class ImpactSeverity(StrEnum):
    """Severity classification for operational and user impact."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RecommendationPriority(StrEnum):
    """Priority level for automated reliability remediation actions."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class CorrelationType(StrEnum):
    """Empirical relationship classification distinguishing correlation from causation."""

    OBSERVED = "observed"
    CORRELATED = "correlated"
    LIKELY = "likely"
    INFERRED = "inferred"
    CONFIRMED = "confirmed"


class IntelligenceConfidence(BaseModel):
    """Deterministic confidence model explaining evidential certainty."""

    model_config = ConfigDict(frozen=True)

    score: float = Field(default=1.0, ge=0.0, le=1.0)
    level: ConfidenceLevel = ConfidenceLevel.HIGH
    evidence_count: int = 1
    sample_size: int = 1
    rationale: str = ""
    factors: dict[str, float] = Field(default_factory=dict)


class EvidenceReference(BaseModel):
    """Audit link connecting an intelligence finding to an underlying source artifact."""

    model_config = ConfigDict(frozen=True)

    reference_id: str = Field(default_factory=lambda: _generate_id("ev_ref"))
    source_type: (
        str  # e.g. "evaluation_report", "failure_report", "root_cause", "trace"
    )
    source_id: str
    description: str = ""
    timestamp: datetime = Field(default_factory=_utc_now)
    metric_name: str | None = None
    observed_value: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedFailure(BaseModel):
    """Sanitized, canonical representation of a failure for fingerprinting and comparison."""

    model_config = ConfigDict(frozen=True)

    fingerprint: str
    failure_id: str
    category: str
    failure_type: str
    root_cause_category: str | None = None
    root_cause_type: str | None = None
    evaluator: str | None = None
    metric: str | None = None
    component: str | None = None
    test_id: str | None = None
    trace_id: str | None = None
    severity: str = "MEDIUM"
    confidence: float = 1.0
    sanitized_message: str = ""
    timestamp: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FailureCluster(BaseModel):
    """Cluster of mathematically or structurally similar failures sharing common signatures."""

    model_config = ConfigDict(frozen=True)

    cluster_id: str = Field(default_factory=lambda: _generate_id("cluster"))
    name: str
    fingerprint: str
    representative_failure_id: str
    failure_ids: list[str] = Field(default_factory=list)
    dominant_category: str = "general"
    dominant_root_cause: str = "unknown"
    frequency: int = 1
    affected_components: list[str] = Field(default_factory=list)
    confidence: IntelligenceConfidence = Field(
        default_factory=lambda: IntelligenceConfidence(
            score=1.0, level=ConfidenceLevel.HIGH
        )
    )
    evidence: list[EvidenceReference] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FailurePattern(BaseModel):
    """Identified longitudinal pattern or anomaly across failures."""

    model_config = ConfigDict(frozen=True)

    pattern_id: str = Field(default_factory=lambda: _generate_id("pattern"))
    pattern_type: PatternType
    title: str
    description: str
    fingerprint: str
    frequency: int = 1
    affected_components: list[str] = Field(default_factory=list)
    first_seen: datetime = Field(default_factory=_utc_now)
    last_seen: datetime = Field(default_factory=_utc_now)
    confidence: IntelligenceConfidence = Field(
        default_factory=lambda: IntelligenceConfidence(
            score=1.0, level=ConfidenceLevel.HIGH
        )
    )
    evidence: list[EvidenceReference] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CrossRunCorrelation(BaseModel):
    """Correlation connecting configuration changes to metric deltas or failure clusters."""

    model_config = ConfigDict(frozen=True)

    correlation_id: str = Field(default_factory=lambda: _generate_id("corr"))
    source_change_type: (
        str  # e.g. "model_version", "prompt_version", "retriever_version"
    )
    source_change_value: str
    observed_effect: str
    affected_metric_or_failure: str
    strength: float = Field(default=0.0, ge=0.0, le=1.0)
    is_causal: bool = False
    relationship_type: CorrelationType = CorrelationType.CORRELATED
    confidence: IntelligenceConfidence = Field(
        default_factory=lambda: IntelligenceConfidence(
            score=0.8, level=ConfidenceLevel.MEDIUM
        )
    )
    evidence: list[EvidenceReference] = Field(default_factory=list)
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReliabilityTrend(BaseModel):
    """Historical trajectory and rate of change for a metric or dimension."""

    model_config = ConfigDict(frozen=True)

    trend_id: str = Field(default_factory=lambda: _generate_id("trend"))
    metric_or_dimension: str
    direction: TrendDirection
    rate_of_change: float = 0.0
    relative_change: float = 0.0
    volatility: float = 0.0
    observations_count: int = 0
    historical_values: list[float] = Field(default_factory=list)
    confidence: IntelligenceConfidence = Field(
        default_factory=lambda: IntelligenceConfidence(
            score=1.0, level=ConfidenceLevel.HIGH
        )
    )
    evidence: list[EvidenceReference] = Field(default_factory=list)
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ImpactAssessment(BaseModel):
    """Risk and operational impact evaluation for an identified issue or cluster."""

    model_config = ConfigDict(frozen=True)

    assessment_id: str = Field(default_factory=lambda: _generate_id("impact"))
    target_id: str
    observed_impact: ImpactSeverity = ImpactSeverity.LOW
    estimated_impact: ImpactSeverity = ImpactSeverity.LOW
    impact_score: float = Field(default=0.0, ge=0.0, le=1.0)
    safety_critical: bool = False
    security_critical: bool = False
    affected_evaluations_count: int = 0
    affected_failures_count: int = 0
    affected_components: list[str] = Field(default_factory=list)
    explanation: str = ""
    confidence: IntelligenceConfidence = Field(
        default_factory=lambda: IntelligenceConfidence(
            score=1.0, level=ConfidenceLevel.HIGH
        )
    )
    evidence: list[EvidenceReference] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReliabilityRecommendation(BaseModel):
    """Actionable, explainable, and evidence-backed remediation suggestion."""

    model_config = ConfigDict(frozen=True)

    recommendation_id: str = Field(default_factory=lambda: _generate_id("rec"))
    title: str
    description: str
    priority: RecommendationPriority = RecommendationPriority.MEDIUM
    suggested_action: str
    rationale: str
    confidence: IntelligenceConfidence = Field(
        default_factory=lambda: IntelligenceConfidence(
            score=1.0, level=ConfidenceLevel.HIGH
        )
    )
    evidence: list[EvidenceReference] = Field(default_factory=list)
    affected_components: list[str] = Field(default_factory=list)
    related_failures: list[str] = Field(default_factory=list)
    related_clusters: list[str] = Field(default_factory=list)
    related_patterns: list[str] = Field(default_factory=list)
    remediation_links: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntelligenceSummary(BaseModel):
    """Aggregated high-level overview of intelligence insights."""

    model_config = ConfigDict(frozen=True)

    total_failures_analyzed: int = 0
    total_clusters: int = 0
    total_patterns: int = 0
    total_correlations: int = 0
    total_trends: int = 0
    total_recommendations: int = 0
    critical_issues_count: int = 0
    dominant_failure_categories: dict[str, int] = Field(default_factory=dict)
    dominant_root_causes: dict[str, int] = Field(default_factory=dict)
    highest_priority_recommendations: list[str] = Field(default_factory=list)


class IntelligenceAnalysis(BaseModel):
    """Comprehensive intelligence report compiling clusters, patterns, trends, and recommendations."""

    model_config = ConfigDict(frozen=True)

    analysis_id: str = Field(default_factory=lambda: _generate_id("analysis"))
    target_name: str
    created_at: datetime = Field(default_factory=_utc_now)
    summary: IntelligenceSummary
    clusters: list[FailureCluster] = Field(default_factory=list)
    patterns: list[FailurePattern] = Field(default_factory=list)
    correlations: list[CrossRunCorrelation] = Field(default_factory=list)
    trends: list[ReliabilityTrend] = Field(default_factory=list)
    impacts: list[ImpactAssessment] = Field(default_factory=list)
    recommendations: list[ReliabilityRecommendation] = Field(default_factory=list)
    confidence: IntelligenceConfidence = Field(
        default_factory=lambda: IntelligenceConfidence(
            score=1.0, level=ConfidenceLevel.HIGH
        )
    )
    evidence: list[EvidenceReference] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
