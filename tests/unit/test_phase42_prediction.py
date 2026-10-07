"""Unit tests for Phase 42 Reliability Prediction."""

from __future__ import annotations

from aireliability.prediction.engine import ReliabilityPredictionEngine
from aireliability.prediction.evaluator import PredictionEvaluator
from aireliability.prediction.models import (
    PredictionHorizon,
    PredictionInput,
    PredictionTrend,
)


def test_prediction_engine_basic_forecast():
    engine = ReliabilityPredictionEngine()
    historical_signals = {
        "reliability": [0.99, 0.98, 0.97, 0.96, 0.95],
        "failure_rate": [0.01, 0.02, 0.03, 0.04, 0.05],
    }
    pred_input = PredictionInput(
        target_id="agent_123",
        historical_signals=historical_signals,
        current_metrics={"reliability": 0.95, "failure_rate": 0.05},
    )

    pred = engine.predict(pred_input, horizon=PredictionHorizon.SHORT_TERM)
    assert pred.target_id == "agent_123"
    assert pred.horizon == PredictionHorizon.SHORT_TERM
    assert 0.0 <= pred.reliability_forecast.forecasted_value <= 1.0
    assert (
        pred.reliability_forecast.lower_bound <= pred.reliability_forecast.upper_bound
    )
    assert pred.confidence.confidence > 0.0
    assert pred.risk_forecast.risk_score >= 0.0
    assert pred.risk_forecast.trend in (
        PredictionTrend.DEGRADING,
        PredictionTrend.STABLE,
        PredictionTrend.VOLATILE,
    )


def test_prediction_confidence_penalty_on_sparse_data():
    engine = ReliabilityPredictionEngine()
    # Sparse data with only 2 runs
    sparse_input = PredictionInput(
        target_id="sparse_agent",
        historical_signals={"reliability": [0.9, 0.8]},
        current_metrics={},
    )
    pred = engine.predict(sparse_input)
    assert pred.confidence.confidence < 0.65
    assert len(pred.confidence.uncertainty_factors) >= 1


def test_prediction_evaluator_brier_and_mae():
    engine = ReliabilityPredictionEngine()
    pred_input = PredictionInput(
        target_id="eval_target",
        historical_signals={"reliability": [0.90, 0.90]},
        current_metrics={"reliability": 0.90, "failure_rate": 0.10},
    )
    pred = engine.predict(pred_input)

    evaluator = PredictionEvaluator()
    eval_res = evaluator.evaluate(
        pred,
        actual_failed=False,
        actual_reliability=0.92,
    )

    assert eval_res.brier_score is not None
    assert 0.0 <= eval_res.brier_score <= 1.0
    assert eval_res.mae is not None
    assert eval_res.mae >= 0.0
