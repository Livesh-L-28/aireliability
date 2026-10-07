"""Configurable reliability release gates supporting PASS, FAIL, and BLOCK decisions."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aireliability.evaluation.governance.scoring import (
    ReliabilityDimension,
    ReliabilityScoringEngine,
    UnifiedReliabilityScore,
)
from aireliability.evaluation.models import EvaluationReport


class GateDecision(StrEnum):
    """Release gate evaluation verdict."""

    PASS = "PASS"
    FAIL = "FAIL"
    BLOCK = "BLOCK"


class GatePolicy(BaseModel):
    """Policy specification defining release gate thresholds and blocking criteria."""

    model_config = ConfigDict(frozen=True)

    name: str = "Standard Release Policy"
    min_overall_score: float = 0.75
    min_faithfulness: float = 0.85
    min_groundedness: float = 0.80
    min_relevance: float = 0.70
    max_hallucination_rate: float = 0.05
    max_p95_latency_ms: float = 2500.0
    max_cost_per_request: float = 0.05
    max_regression_count: int = 0
    block_on_critical_safety: bool = True
    block_on_security_violation: bool = True
    block_on_severe_regression: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _remap_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = dict(data)
            if "min_composite_score" in data and "min_overall_score" not in data:
                data["min_overall_score"] = data.pop("min_composite_score")
            if "fail_on_regression" in data:
                flag = data.pop("fail_on_regression")
                if flag and "max_regression_count" not in data:
                    data["max_regression_count"] = 0
                elif not flag and "max_regression_count" not in data:
                    data["max_regression_count"] = 999999
        return data

    @property
    def min_composite_score(self) -> float:
        """Alias for min_overall_score."""
        return self.min_overall_score


class GateResult(BaseModel):
    """Result of gate evaluation."""

    model_config = ConfigDict(frozen=True)

    policy_name: str
    decision: GateDecision
    passed: bool
    blocked: bool
    reasons: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    metrics_evaluated: dict[str, float] = Field(default_factory=dict)
    reliability_score: float | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReliabilityGateEngine:
    """Evaluates evaluation reports and reliability scores against release policies."""

    def __init__(
        self,
        default_policy: GatePolicy | None = None,
        scoring_engine: ReliabilityScoringEngine | None = None,
    ) -> None:
        self.default_policy = default_policy or GatePolicy()
        self.scoring_engine = scoring_engine or ReliabilityScoringEngine()

    def evaluate_gate(
        self,
        report: EvaluationReport,
        policy: GatePolicy | None = None,
        reliability_score: UnifiedReliabilityScore | None = None,
    ) -> GateResult:
        """Apply gate policy to report and produce a PASS, FAIL, or BLOCK decision."""
        pol = policy or self.default_policy
        score = reliability_score or self.scoring_engine.compute_score(report)

        reasons: list[str] = []
        blocking_reasons: list[str] = []
        metrics: dict[str, float] = {
            "overall_score": score.composite_score,
            "failed_test_cases": float(report.failed_test_cases),
            "failure_count": float(len(report.failures)),
            "regression_count": float(len(report.regressions)),
        }

        # 1. Critical safety blocking
        safety_dim = score.dimensional_scores.get(ReliabilityDimension.SAFETY.value)
        if safety_dim and not safety_dim.passed and pol.block_on_critical_safety:
            msg = f"BLOCK: Safety violation detected ({safety_dim.failure_count} failures)."
            blocking_reasons.append(msg)
            reasons.append(msg)

        # 2. Critical security blocking
        security_dim = score.dimensional_scores.get(ReliabilityDimension.SECURITY.value)
        if security_dim and not security_dim.passed and pol.block_on_security_violation:
            msg = f"BLOCK: Security violation detected ({security_dim.failure_count} failures)."
            blocking_reasons.append(msg)
            reasons.append(msg)

        # 3. Veto triggered in scoring
        if score.veto_triggered and not blocking_reasons:
            msg = f"BLOCK: Reliability veto triggered: {'; '.join(score.veto_reasons)}."
            blocking_reasons.append(msg)
            reasons.append(msg)

        # 4. Overall score threshold
        if score.composite_score < pol.min_overall_score:
            reasons.append(
                f"FAIL: Overall reliability score {score.composite_score:.2f} < required {pol.min_overall_score:.2f}."
            )

        # 5. Faithfulness threshold
        faith_dim = score.dimensional_scores.get(
            ReliabilityDimension.FAITHFULNESS.value
        )
        if faith_dim:
            metrics["faithfulness"] = faith_dim.score
            if faith_dim.score < pol.min_faithfulness:
                reasons.append(
                    f"FAIL: Faithfulness {faith_dim.score:.2f} < required {pol.min_faithfulness:.2f}."
                )

        # 6. Groundedness threshold
        ground_dim = score.dimensional_scores.get(
            ReliabilityDimension.GROUNDEDNESS.value
        )
        if ground_dim:
            metrics["groundedness"] = ground_dim.score
            if ground_dim.score < pol.min_groundedness:
                reasons.append(
                    f"FAIL: Groundedness {ground_dim.score:.2f} < required {pol.min_groundedness:.2f}."
                )

        # 7. Regressions check
        reg_count = len(report.regressions)
        if reg_count > pol.max_regression_count:
            msg = f"Regression check: detected {reg_count} regression(s) (allowed: {pol.max_regression_count})."
            reasons.append(msg)
            if pol.block_on_severe_regression and reg_count >= 2:
                blocking_reasons.append(
                    f"BLOCK: Severe regressions encountered ({reg_count})."
                )

        # Determine decision
        if blocking_reasons:
            decision = GateDecision.BLOCK
            passed = False
            blocked = True
        elif reasons:
            decision = GateDecision.FAIL
            passed = False
            blocked = False
        else:
            decision = GateDecision.PASS
            passed = True
            blocked = False

        return GateResult(
            policy_name=pol.name,
            decision=decision,
            passed=passed,
            blocked=blocked,
            reasons=reasons,
            blocking_reasons=blocking_reasons,
            metrics_evaluated=metrics,
            reliability_score=score.composite_score,
            metadata={
                "status": score.status,
                "dataset_id": report.dataset_id,
                "target_name": report.target_name,
            },
        )

    def evaluate(
        self,
        report: EvaluationReport,
        policy_or_score: GatePolicy | UnifiedReliabilityScore | None = None,
        reliability_score: UnifiedReliabilityScore | None = None,
    ) -> GateResult:
        """Evaluate gate with flexible argument routing for policy and score."""
        if isinstance(policy_or_score, UnifiedReliabilityScore):
            return self.evaluate_gate(
                report=report,
                policy=None,
                reliability_score=policy_or_score,
            )
        return self.evaluate_gate(
            report=report,
            policy=policy_or_score,
            reliability_score=reliability_score,
        )
