"""Drift detection for quality, retrieval, safety, latency, cost, and distribution shifts."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from aireliability.evaluation.metrics.statistics import mean


class DriftReport(BaseModel):
    """Result of distribution or metric drift detection."""

    model_config = ConfigDict(frozen=True)

    metric: str
    psi_score: float
    drift_detected: bool
    severity: str  # "NONE", "MODERATE", "SIGNIFICANT"
    baseline_mean: float
    current_mean: float
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    details: dict[str, Any] = Field(default_factory=dict)


def calculate_psi(
    expected_values: list[float],
    actual_values: list[float],
    num_bins: int = 5,
) -> float:
    """Calculate Population Stability Index (PSI) between expected and actual distributions."""
    if not expected_values or not actual_values:
        return 0.0

    all_vals = expected_values + actual_values
    min_v, max_v = min(all_vals), max(all_vals)
    if min_v == max_v:
        return 0.0

    bin_width = (max_v - min_v) / num_bins

    # Compute frequencies
    exp_counts = [0] * num_bins
    act_counts = [0] * num_bins

    for v in expected_values:
        idx = min(num_bins - 1, int((v - min_v) / bin_width)) if bin_width > 0 else 0
        exp_counts[idx] += 1

    for v in actual_values:
        idx = min(num_bins - 1, int((v - min_v) / bin_width)) if bin_width > 0 else 0
        act_counts[idx] += 1

    n_exp = len(expected_values)
    n_act = len(actual_values)

    psi = 0.0
    epsilon = 1e-4

    for c_exp, c_act in zip(exp_counts, act_counts, strict=False):
        pct_exp = (c_exp / n_exp) if c_exp > 0 else epsilon
        pct_act = (c_act / n_act) if c_act > 0 else epsilon
        psi += (pct_act - pct_exp) * math.log(pct_act / pct_exp)

    return max(0.0, round(psi, 4))


class EvaluationDriftDetector:
    """Detects statistical metric drift and distribution shifts between baseline and online traffic."""

    def __init__(
        self,
        psi_threshold_moderate: float = 0.10,
        psi_threshold_significant: float = 0.25,
        *,
        psi_threshold: float | None = None,
    ) -> None:
        if psi_threshold is not None:
            psi_threshold_significant = psi_threshold
            psi_threshold_moderate = psi_threshold / 2.0
        self.psi_threshold_moderate = psi_threshold_moderate
        self.psi_threshold_significant = psi_threshold_significant
        self._baselines: dict[str, list[float]] = {}
        self._current_windows: dict[str, list[float]] = {}

    def set_baseline(self, metric: str, values: list[float]) -> None:
        """Set historical reference baseline for a metric."""
        self._baselines[metric] = list(values)

    def record_observation(self, metric: str, value: float) -> None:
        """Record live observation into rolling window."""
        if metric not in self._current_windows:
            self._current_windows[metric] = []
        self._current_windows[metric].append(float(value))
        if len(self._current_windows[metric]) > 500:
            self._current_windows[metric].pop(0)

    def detect_drift(
        self,
        metric: str,
        baseline_values: list[float] | None = None,
        current_values: list[float] | None = None,
    ) -> DriftReport:
        """Evaluate if recent observations have drifted from baseline."""
        baseline = (
            list(baseline_values)
            if baseline_values is not None
            else self._baselines.get(metric, [])
        )
        current = (
            list(current_values)
            if current_values is not None
            else self._current_windows.get(metric, [])
        )

        if not baseline or not current:
            return DriftReport(
                metric=metric,
                psi_score=0.0,
                drift_detected=False,
                severity="NONE",
                baseline_mean=mean(baseline),
                current_mean=mean(current),
                message="Insufficient data to compute drift.",
            )

        psi = calculate_psi(baseline, current)
        b_mean = mean(baseline)
        c_mean = mean(current)

        if psi >= self.psi_threshold_significant:
            severity = "SIGNIFICANT"
            drift = True
            msg = f"Significant drift detected in {metric}: PSI={psi:.4f} (>= {self.psi_threshold_significant})."
        elif psi >= self.psi_threshold_moderate:
            severity = "MODERATE"
            drift = True
            msg = f"Moderate drift detected in {metric}: PSI={psi:.4f} (>= {self.psi_threshold_moderate})."
        else:
            severity = "NONE"
            drift = False
            msg = f"No drift detected in {metric}: PSI={psi:.4f}."

        return DriftReport(
            metric=metric,
            psi_score=psi,
            drift_detected=drift,
            severity=severity,
            baseline_mean=round(b_mean, 4),
            current_mean=round(c_mean, 4),
            message=msg,
            details={
                "sample_size_current": len(current),
                "sample_size_baseline": len(baseline),
            },
        )
