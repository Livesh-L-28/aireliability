"""Longitudinal trend analysis for reliability dimensions and metric series."""

from __future__ import annotations

import math
from collections.abc import Sequence

from aireliability.evaluation.models import EvaluationReport
from aireliability.intelligence.confidence import ConfidenceEngine
from aireliability.intelligence.models import (
    EvidenceReference,
    ReliabilityTrend,
    TrendDirection,
)


class TrendAnalyzer:
    """Computes rate of change, volatility, and direction over historical evaluation series."""

    def __init__(self, min_observations: int = 2) -> None:
        self.min_observations = min_observations

    def analyze_series(
        self,
        name: str,
        values: Sequence[float],
        evidence_pool: list[EvidenceReference] | None = None,
    ) -> ReliabilityTrend:
        """Analyze a sequence of values over time for a single metric or dimension."""
        obs_count = len(values)
        if obs_count < self.min_observations:
            return ReliabilityTrend(
                metric_or_dimension=name,
                direction=TrendDirection.INSUFFICIENT_DATA,
                rate_of_change=0.0,
                relative_change=0.0,
                volatility=0.0,
                observations_count=obs_count,
                historical_values=list(values),
                confidence=ConfidenceEngine.calculate(
                    evidence_count=obs_count, sample_size=obs_count
                ),
                description=f"Insufficient observations ({obs_count} < {self.min_observations}) to determine a trend.",
            )

        v_first = values[0]
        v_last = values[-1]
        slope = (v_last - v_first) / (obs_count - 1)
        rel_change = (v_last - v_first) / v_first if v_first != 0 else 0.0

        # Calculate volatility (standard deviation)
        mean_val = sum(values) / obs_count
        variance_val = sum((x - mean_val) ** 2 for x in values) / (obs_count - 1)
        volatility = math.sqrt(max(0.0, variance_val))

        # Classify direction
        if volatility > 0.15 and abs(slope) < 0.05:
            direction = TrendDirection.VOLATILE
            desc = f"Metric '{name}' exhibited volatile fluctuations (std dev: {volatility:.3f}) across {obs_count} runs."
        elif slope > 0.01:
            direction = TrendDirection.INCREASING
            desc = f"Metric '{name}' demonstrated an upward trajectory (+{slope:.3f}/run, total: {rel_change:+.1%})."
        elif slope < -0.01:
            direction = TrendDirection.DECREASING
            desc = f"Metric '{name}' demonstrated a downward trajectory ({slope:.3f}/run, total: {rel_change:+.1%})."
        else:
            direction = TrendDirection.STABLE
            desc = f"Metric '{name}' remained stable across {obs_count} runs (slope: {slope:.3f})."

        conf = ConfidenceEngine.calculate(
            evidence_count=obs_count,
            sample_size=obs_count,
            agreement_rate=0.95 if direction != TrendDirection.VOLATILE else 0.60,
        )

        return ReliabilityTrend(
            metric_or_dimension=name,
            direction=direction,
            rate_of_change=round(slope, 4),
            relative_change=round(rel_change, 4),
            volatility=round(volatility, 4),
            observations_count=obs_count,
            historical_values=list(values),
            confidence=conf,
            evidence=evidence_pool or [],
            description=desc,
        )

    def analyze_reports(
        self,
        reports: Sequence[EvaluationReport],
        metrics_to_track: list[str] | None = None,
    ) -> list[ReliabilityTrend]:
        """Extract metric trajectories across chronological evaluation reports and analyze trends."""
        if not reports:
            return []

        # Collect metrics across reports
        series_map: dict[str, list[float]] = {}
        for rep in reports:
            # Track test case pass rate
            pass_rate = rep.passed_test_cases / max(1, rep.total_test_cases)
            series_map.setdefault("pass_rate", []).append(pass_rate)

            for m_name, m_res in rep.metrics.items():
                if metrics_to_track is None or m_name in metrics_to_track:
                    series_map.setdefault(m_name, []).append(m_res.value)

        trends: list[ReliabilityTrend] = []
        for name, values in series_map.items():
            trend = self.analyze_series(name, values)
            trends.append(trend)

        return trends
