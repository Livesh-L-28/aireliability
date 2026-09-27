"""Lightweight statistical anomaly detection without external ML dependencies."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from aireliability.observability.models import AnomalySeverity


class AnomalyReport(BaseModel):
    """Result of anomaly evaluation."""

    metric: str
    observed_value: float
    baseline: float
    deviation: float
    severity: AnomalySeverity
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    details: dict[str, Any] = Field(default_factory=dict)


class StatisticalAnomalyDetector:
    """Detects metric anomalies using moving average, z-scores, and EWMA."""

    def __init__(
        self,
        z_threshold_warning: float = 2.0,
        z_threshold_anomaly: float = 3.0,
        ewma_alpha: float = 0.3,
        min_samples: int = 5,
    ) -> None:
        self.z_threshold_warning = z_threshold_warning
        self.z_threshold_anomaly = z_threshold_anomaly
        self.ewma_alpha = ewma_alpha
        self.min_samples = min_samples
        self._history: dict[str, list[float]] = {}
        self._ewma: dict[str, float] = {}

    def record_observation(self, metric: str, value: float) -> None:
        """Record an observed metric value."""
        if metric not in self._history:
            self._history[metric] = []
        self._history[metric].append(float(value))
        if len(self._history[metric]) > 1000:
            self._history[metric].pop(0)

        # Update EWMA
        if metric not in self._ewma:
            self._ewma[metric] = float(value)
        else:
            self._ewma[metric] = (
                self.ewma_alpha * float(value)
                + (1.0 - self.ewma_alpha) * self._ewma[metric]
            )

    def detect(
        self,
        metric: str,
        current_value: float | None = None,
    ) -> AnomalyReport:
        """Evaluate if current or latest observation is anomalous."""
        history = self._history.get(metric, [])
        if current_value is not None:
            observed = float(current_value)
            # Record it
            self.record_observation(metric, observed)
        elif history:
            observed = history[-1]
        else:
            return AnomalyReport(
                metric=metric,
                observed_value=0.0,
                baseline=0.0,
                deviation=0.0,
                severity=AnomalySeverity.NORMAL,
                details={"reason": "no_data"},
            )

        if len(history) < self.min_samples:
            return AnomalyReport(
                metric=metric,
                observed_value=observed,
                baseline=observed,
                deviation=0.0,
                severity=AnomalySeverity.NORMAL,
                details={"reason": "insufficient_samples"},
            )

        # Calculate mean and sample std dev
        mean = sum(history) / len(history)
        variance = sum((x - mean) ** 2 for x in history) / len(history)
        std_dev = math.sqrt(variance)

        if std_dev == 0.0:
            # Constant history
            deviation = abs(observed - mean)
            severity = (
                AnomalySeverity.NORMAL if deviation == 0.0 else AnomalySeverity.ANOMALY
            )
            z_score = 0.0 if deviation == 0.0 else float("inf")
        else:
            z_score = abs(observed - mean) / std_dev
            if z_score >= self.z_threshold_anomaly:
                severity = AnomalySeverity.ANOMALY
            elif z_score >= self.z_threshold_warning:
                severity = AnomalySeverity.WARNING
            else:
                severity = AnomalySeverity.NORMAL

        ewma_val = self._ewma.get(metric, mean)

        return AnomalyReport(
            metric=metric,
            observed_value=observed,
            baseline=mean,
            deviation=abs(observed - mean),
            severity=severity,
            details={
                "std_dev": std_dev,
                "z_score": z_score,
                "ewma": ewma_val,
                "sample_count": len(history),
            },
        )
