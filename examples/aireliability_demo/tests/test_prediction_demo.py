"""Tests for Reliability Prediction and Forecasting (Phase 42)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from aireliability_demo.app.reliability.integration import DemoReliabilityIntegrator


def test_prediction_stable_forecast() -> None:
    integrator = DemoReliabilityIntegrator()
    history = [0.99, 0.98, 0.98, 0.99, 0.98]
    pred = integrator.predict_reliability(history, target_id="test_stable")

    assert pred.target_id == "test_stable"
    assert 0.0 <= pred.reliability_forecast.forecasted_value <= 1.0
    assert (
        pred.reliability_forecast.lower_bound <= pred.reliability_forecast.upper_bound
    )
    assert pred.confidence.confidence > 0.0
    assert pred.risk_forecast.trend.value in (
        "STABLE",
        "IMPROVING",
        "DEGRADING",
        "VOLATILE",
    )


def test_prediction_degrading_trend() -> None:
    integrator = DemoReliabilityIntegrator()
    history = [0.98, 0.94, 0.88, 0.82, 0.75]
    pred = integrator.predict_reliability(history, target_id="test_degrading")

    assert pred.risk_forecast.trend.value == "DEGRADING"
    assert pred.risk_forecast.risk_score > 0.05
