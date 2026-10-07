"""Regression scenario demonstrating baseline comparison and degradation detection."""

from __future__ import annotations

from typing import Any

from aireliability.core.models import FailureReport, FailureSeverity
from aireliability.evaluation.models import MetricResult


def run_regression_scenario() -> dict[str, Any]:
    """Execute regression comparison between baseline model and degraded candidate."""
    baseline_metrics = {
        "accuracy": MetricResult(name="accuracy", value=0.96),
        "groundedness": MetricResult(name="groundedness", value=0.94),
        "latency_p95": MetricResult(name="latency_p95", value=0.45),
    }
    candidate_metrics = {
        "accuracy": MetricResult(name="accuracy", value=0.78),  # 18% regression!
        "groundedness": MetricResult(
            name="groundedness", value=0.72
        ),  # 22% regression!
        "latency_p95": MetricResult(
            name="latency_p95", value=1.85
        ),  # 4x latency regression!
    }

    regressions = []
    for metric_name, base_m in baseline_metrics.items():
        cand_m = candidate_metrics[metric_name]
        delta = cand_m.value - base_m.value
        # If accuracy/groundedness dropped or latency increased
        if (metric_name in ("accuracy", "groundedness") and delta < -0.05) or (
            metric_name == "latency_p95" and delta > 0.5
        ):
            regressions.append(
                {
                    "metric": metric_name,
                    "baseline": base_m.value,
                    "candidate": cand_m.value,
                    "delta": round(delta, 4),
                    "status": "REGRESSION_DETECTED",
                }
            )

    failure_reports = [
        FailureReport(
            failure_id="fail_reg_acc_01",
            trace_id="tr_reg_eval",
            category="regression",
            type="accuracy_drop",
            message="Candidate accuracy dropped from 0.96 to 0.78 (-18.7%)",
            severity=FailureSeverity.CRITICAL,
            metadata={"baseline": 0.96, "candidate": 0.78, "delta": -0.18},
        ),
        FailureReport(
            failure_id="fail_reg_ground_01",
            trace_id="tr_reg_eval",
            category="regression",
            type="groundedness_drop",
            message="Candidate groundedness dropped from 0.94 to 0.72 (-23.4%)",
            severity=FailureSeverity.HIGH,
            metadata={"baseline": 0.94, "candidate": 0.72, "delta": -0.22},
        ),
    ]

    return {
        "scenario": "REGRESSION_DETECTED",
        "baseline_version": "v1.3.0",
        "candidate_version": "v1.4.0-candidate-degraded",
        "regressions": regressions,
        "is_regression": len(regressions) > 0,
        "failure_reports": failure_reports,
    }
