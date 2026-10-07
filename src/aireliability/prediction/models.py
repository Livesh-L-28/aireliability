"""Strongly typed data models for Reliability Prediction (Phase 42)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def _generate_id(prefix: str = "pred") -> str:
    """Generate a unique ID with a given prefix."""
    return f"{prefix}_{uuid4().hex[:12]}"


def _utc_now() -> datetime:
    """Return current UTC timestamp."""
    return datetime.now(UTC)


class PredictionHorizon(StrEnum):
    """Forecasting time horizons."""

    NEXT_EXECUTION = "NEXT_EXECUTION"
    SHORT_TERM = "SHORT_TERM"  # e.g., next hour / 100 runs
    MEDIUM_TERM = "MEDIUM_TERM"  # e.g., next 24 hours / 1,000 runs
    LONG_TERM = "LONG_TERM"  # e.g., next 7 days / 10,000 runs


class PredictionRiskLevel(StrEnum):
    """Risk tiers for predicted reliability outcomes."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PredictionTrend(StrEnum):
    """Directional trajectory of predicted reliability signals."""

    IMPROVING = "IMPROVING"
    STABLE = "STABLE"
    DEGRADING = "DEGRADING"
    VOLATILE = "VOLATILE"


class PredictionFeature(BaseModel):
    """A feature metric consumed by the prediction engine."""

    model_config = ConfigDict(frozen=True)

    name: str
    value: float
    unit: str = "ratio"  # ratio, ms, usd, count
    weight: float = 1.0
    contribution: float = 0.0
    description: str = ""


class PredictionWindow(BaseModel):
    """Temporal or count-based sampling window."""

    model_config = ConfigDict(frozen=True)

    start_time: datetime | None = None
    end_time: datetime | None = None
    sample_count: int = 0
    step_interval: str = "1h"


class PredictionInput(BaseModel):
    """Input historical signals and context for reliability prediction."""

    model_config = ConfigDict(frozen=True)

    target_id: str
    target_type: str = "agent"  # agent, rag, model, tool, pipeline
    historical_signals: dict[str, list[float]] = Field(default_factory=dict)
    current_metrics: dict[str, float] = Field(default_factory=dict)
    window: PredictionWindow = Field(default_factory=PredictionWindow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FailureProbability(BaseModel):
    """Predicted probability of specific failure modes."""

    model_config = ConfigDict(frozen=True)

    category: str
    probability: float = Field(ge=0.0, le=1.0)
    horizon: PredictionHorizon
    confidence: float = Field(ge=0.0, le=1.0)
    contributing_signals: list[str] = Field(default_factory=list)


class RiskForecast(BaseModel):
    """Forecast of overall reliability risk."""

    model_config = ConfigDict(frozen=True)

    risk_score: float = Field(ge=0.0, le=1.0)
    risk_level: PredictionRiskLevel
    trend: PredictionTrend
    projected_degradation: float = 0.0
    horizon: PredictionHorizon


class ReliabilityForecast(BaseModel):
    """Forecasted numeric reliability metric score with confidence interval."""

    model_config = ConfigDict(frozen=True)

    metric_name: str = "overall_reliability"
    forecasted_value: float = Field(ge=0.0, le=1.0)
    lower_bound: float = Field(ge=0.0, le=1.0)
    upper_bound: float = Field(ge=0.0, le=1.0)
    horizon: PredictionHorizon


class PredictionEvidence(BaseModel):
    """Empirical evidence supporting a prediction."""

    model_config = ConfigDict(frozen=True)

    signal_name: str
    observed_value: float
    baseline_value: float
    z_score: float = 0.0
    impact: str = "negative"  # positive, neutral, negative


class PredictionExplanation(BaseModel):
    """Explainability record for a prediction."""

    model_config = ConfigDict(frozen=True)

    summary: str
    top_factors: list[PredictionFeature] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class PredictionConfidence(BaseModel):
    """Uncertainty and confidence assessment for predictions."""

    model_config = ConfigDict(frozen=True)

    confidence: float = Field(ge=0.0, le=1.0)
    sample_adequacy: float = Field(ge=0.0, le=1.0)
    variance_penalty: float = 0.0
    uncertainty_factors: list[str] = Field(default_factory=list)


class PredictionBaseline(BaseModel):
    """Historical baseline metrics for comparing drift and degradation."""

    baseline_id: str = Field(default_factory=lambda: _generate_id("pbase"))
    target_id: str
    baseline_reliability: float = 1.0
    baseline_error_rate: float = 0.0
    baseline_latency_ms: float = 0.0
    sample_size: int = 0
    created_at: datetime = Field(default_factory=_utc_now)


class PredictionDrift(BaseModel):
    """Drift metrics detected between baseline and current trends."""

    signal_name: str
    baseline_mean: float
    current_mean: float
    drift_detected: bool
    p_value: float = 1.0


class PredictionRecommendation(BaseModel):
    """Preventative recommendation triggered by high predicted risk."""

    model_config = ConfigDict(frozen=True)

    recommendation_id: str = Field(default_factory=lambda: _generate_id("prec"))
    action: (
        str  # remediation, optimization, scale_resource, safety_audit, warn_operator
    )
    urgency: PredictionRiskLevel = PredictionRiskLevel.HIGH
    affected_component: str
    description: str
    suggested_mitigation: str = ""


class ReliabilityPrediction(BaseModel):
    """Comprehensive prediction entity emitted by the engine."""

    model_config = ConfigDict(frozen=True)

    prediction_id: str = Field(default_factory=lambda: _generate_id("pred"))
    target_id: str
    target_type: str = "agent"
    horizon: PredictionHorizon
    failure_probabilities: list[FailureProbability] = Field(default_factory=list)
    risk_forecast: RiskForecast
    reliability_forecast: ReliabilityForecast
    confidence: PredictionConfidence
    evidence: list[PredictionEvidence] = Field(default_factory=list)
    explanation: PredictionExplanation
    recommendations: list[PredictionRecommendation] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)

    def fingerprint(self) -> str:
        """Deterministic fingerprint of this prediction."""
        data = f"{self.target_id}:{self.horizon.value}:{self.risk_forecast.risk_score:.4f}:{self.confidence.confidence:.4f}"
        return hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]


class PredictionEvaluation(BaseModel):
    """Evaluation of prediction accuracy against observed real outcomes."""

    model_config = ConfigDict(frozen=True)

    evaluation_id: str = Field(default_factory=lambda: _generate_id("peval"))
    prediction_id: str
    brier_score: float | None = None
    mae: float | None = None
    trend_correct: bool = True
    early_warning_effective: bool = True
    evaluated_at: datetime = Field(default_factory=_utc_now)


class PredictionReport(BaseModel):
    """Aggregated prediction report for auditing and dashboard ingestion."""

    report_id: str = Field(default_factory=lambda: _generate_id("prep"))
    target_id: str
    predictions: list[ReliabilityPrediction] = Field(default_factory=list)
    overall_risk_level: PredictionRiskLevel = PredictionRiskLevel.LOW
    summary: str = ""
    generated_at: datetime = Field(default_factory=_utc_now)
