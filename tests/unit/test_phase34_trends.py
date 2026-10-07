"""Unit tests for Phase 34 longitudinal TrendAnalyzer."""

from __future__ import annotations

from aireliability.evaluation.models import EvaluationReport, MetricResult
from aireliability.intelligence.models import TrendDirection
from aireliability.intelligence.trends import TrendAnalyzer


def test_trend_insufficient_data() -> None:
    analyzer = TrendAnalyzer(min_observations=3)
    trend = analyzer.analyze_series("latency", [100.0, 110.0])
    assert trend.direction == TrendDirection.INSUFFICIENT_DATA
    assert trend.observations_count == 2


def test_trend_increasing() -> None:
    analyzer = TrendAnalyzer(min_observations=2)
    # Series increasing steadily
    trend = analyzer.analyze_series("hallucination_rate", [0.05, 0.10, 0.15, 0.20])
    assert trend.direction == TrendDirection.INCREASING
    assert trend.rate_of_change == 0.05
    assert trend.relative_change == 3.0  # (0.20 - 0.05) / 0.05


def test_trend_decreasing() -> None:
    analyzer = TrendAnalyzer(min_observations=2)
    trend = analyzer.analyze_series("error_rate", [0.30, 0.20, 0.10])
    assert trend.direction == TrendDirection.DECREASING
    assert trend.rate_of_change == -0.10


def test_trend_stable() -> None:
    analyzer = TrendAnalyzer(min_observations=2)
    trend = analyzer.analyze_series("groundedness", [0.95, 0.95, 0.95])
    assert trend.direction == TrendDirection.STABLE
    assert trend.rate_of_change == 0.0
    assert trend.volatility == 0.0


def test_trend_volatile() -> None:
    analyzer = TrendAnalyzer(min_observations=2)
    # High variance, start and end close to each other
    trend = analyzer.analyze_series("flaky_metric", [0.50, 0.90, 0.10, 0.85, 0.50])
    assert trend.direction == TrendDirection.VOLATILE
    assert trend.volatility > 0.15


def test_trend_analyze_reports() -> None:
    analyzer = TrendAnalyzer(min_observations=2)

    rep1 = EvaluationReport(
        report_id="r1",
        target_name="agent",
        dataset_id="golden",
        total_test_cases=10,
        passed_test_cases=9,
        failed_test_cases=1,
        metrics={"accuracy": MetricResult(name="accuracy", value=0.90)},
    )
    rep2 = EvaluationReport(
        report_id="r2",
        target_name="agent",
        dataset_id="golden",
        total_test_cases=10,
        passed_test_cases=7,
        failed_test_cases=3,
        metrics={"accuracy": MetricResult(name="accuracy", value=0.70)},
    )
    rep3 = EvaluationReport(
        report_id="r3",
        target_name="agent",
        dataset_id="golden",
        total_test_cases=10,
        passed_test_cases=5,
        failed_test_cases=5,
        metrics={"accuracy": MetricResult(name="accuracy", value=0.50)},
    )

    trends = analyzer.analyze_reports([rep1, rep2, rep3])
    trends_map = {t.metric_or_dimension: t for t in trends}

    assert "pass_rate" in trends_map
    assert trends_map["pass_rate"].direction == TrendDirection.DECREASING

    assert "accuracy" in trends_map
    assert trends_map["accuracy"].direction == TrendDirection.DECREASING
