"""Prediction evaluation and calibration metrics (Phase 42)."""

from __future__ import annotations

from aireliability.prediction.models import PredictionEvaluation, ReliabilityPrediction


class PredictionEvaluator:
    """Evaluates prediction performance, calibration, and accuracy against verified outcomes."""

    def evaluate(
        self,
        prediction: ReliabilityPrediction,
        actual_failed: bool | None = None,
        actual_reliability: float | None = None,
    ) -> PredictionEvaluation:
        """Calculate Brier score and MAE when ground truth outcomes are available."""
        brier_score = None
        mae = None
        trend_correct = True
        early_warning = True

        if actual_failed is not None:
            # Aggregate failure probability across categories
            avg_prob = (
                sum(fp.probability for fp in prediction.failure_probabilities)
                / len(prediction.failure_probabilities)
                if prediction.failure_probabilities
                else prediction.risk_forecast.risk_score
            )
            outcome = 1.0 if actual_failed else 0.0
            # Brier Score = (predicted_prob - actual_outcome)^2
            brier_score = round((avg_prob - outcome) ** 2, 4)
            early_warning = bool(avg_prob >= 0.5) == actual_failed

        if actual_reliability is not None:
            forecasted = prediction.reliability_forecast.forecasted_value
            mae = round(abs(forecasted - actual_reliability), 4)
            # Trend is correct if projected direction matches reality
            if prediction.risk_forecast.projected_degradation > 0:
                trend_correct = actual_reliability < 1.0

        return PredictionEvaluation(
            prediction_id=prediction.prediction_id,
            brier_score=brier_score,
            mae=mae,
            trend_correct=trend_correct,
            early_warning_effective=early_warning,
        )
