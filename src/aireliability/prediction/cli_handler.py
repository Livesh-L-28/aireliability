"""CLI handler for Phase 42 Reliability Prediction commands."""

from __future__ import annotations

import argparse
import json

from aireliability.prediction.engine import ReliabilityPredictionEngine
from aireliability.prediction.models import PredictionHorizon, PredictionInput


def handle_prediction_cli(args: argparse.Namespace) -> int:
    """Entry point for `airel predict` subcommands."""
    _action = getattr(args, "predict_action", "forecast") or "forecast"
    target_id = getattr(args, "target", None) or "target_pipeline"
    horizon_str = getattr(args, "horizon", "SHORT_TERM") or "SHORT_TERM"

    horizon_map = {
        "NEXT_EXECUTION": PredictionHorizon.NEXT_EXECUTION,
        "SHORT_TERM": PredictionHorizon.SHORT_TERM,
        "MEDIUM_TERM": PredictionHorizon.MEDIUM_TERM,
        "LONG_TERM": PredictionHorizon.LONG_TERM,
    }
    horizon = horizon_map.get(horizon_str.upper(), PredictionHorizon.SHORT_TERM)

    engine = ReliabilityPredictionEngine()
    # Mock historical signals if not provided via input file
    historical_signals = {
        "reliability": [0.98, 0.97, 0.96, 0.95, 0.94],
        "failure_rate": [0.02, 0.03, 0.04, 0.05, 0.06],
        "latency": [1.2, 1.3, 1.4, 1.5, 1.6],
    }
    pred_input = PredictionInput(
        target_id=target_id,
        historical_signals=historical_signals,
        current_metrics={"reliability": 0.94, "failure_rate": 0.06},
    )

    pred = engine.predict(pred_input, horizon=horizon)

    if getattr(args, "json", False) or getattr(args, "format", "terminal") == "json":
        out_dict = {
            "prediction_id": pred.prediction_id,
            "target_id": pred.target_id,
            "horizon": pred.horizon.value,
            "forecasted_reliability": pred.reliability_forecast.forecasted_value,
            "confidence": pred.confidence.confidence,
            "risk_score": pred.risk_forecast.risk_score,
            "risk_level": pred.risk_forecast.risk_level.value,
            "trend": pred.risk_forecast.trend.value,
        }
        print(json.dumps(out_dict, indent=2))
    else:
        print("\n=======================================================")
        print("        RELIABILITY PREDICTION REPORT (PHASE 42)")
        print("=======================================================")
        print(f"Target ID:               {pred.target_id}")
        print(f"Horizon:                 {pred.horizon.value}")
        print(
            f"Forecasted Reliability:  {pred.reliability_forecast.forecasted_value:.3f} "
            f"[{pred.reliability_forecast.lower_bound:.2f} - {pred.reliability_forecast.upper_bound:.2f}]"
        )
        print(
            f"Risk Level:              {pred.risk_forecast.risk_level.value} (Score: {pred.risk_forecast.risk_score:.3f})"
        )
        print(f"Trend:                   {pred.risk_forecast.trend.value}")
        print(f"Confidence:              {pred.confidence.confidence * 100:.1f}%")
        print(f"Summary:                 {pred.explanation.summary}")
        if pred.recommendations:
            print("Recommendations:")
            for r in pred.recommendations:
                print(f"  * [{r.urgency.value}] {r.description}")
        print("=======================================================\n")

    return 0
