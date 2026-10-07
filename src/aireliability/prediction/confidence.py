"""Confidence and uncertainty estimation engine for predictions (Phase 42)."""

from __future__ import annotations

import math

from aireliability.prediction.models import PredictionConfidence, PredictionInput


class PredictionConfidenceEngine:
    """Computes rigorous uncertainty and confidence bounds for statistical forecasts."""

    def assess_confidence(self, pred_input: PredictionInput) -> PredictionConfidence:
        """Estimate confidence based on sample size, variance, and data density."""
        uncertainty_factors: list[str] = []
        signals = pred_input.historical_signals

        # 1. Sample Size Adequacy
        total_samples = sum(len(v) for v in signals.values()) if signals else 0
        if total_samples >= 50:
            sample_adequacy = 1.0
        elif total_samples >= 20:
            sample_adequacy = 0.85
        elif total_samples >= 5:
            sample_adequacy = 0.60
            uncertainty_factors.append("Low sample size: under 20 historical runs")
        elif total_samples > 0:
            sample_adequacy = 0.35
            uncertainty_factors.append("Critically low sample size: under 5 runs")
        else:
            sample_adequacy = 0.20
            uncertainty_factors.append(
                "No historical timeseries available: relying on point metrics"
            )

        # 2. Variance Penalty
        variance_penalty = 0.0
        if "reliability" in signals and len(signals["reliability"]) > 2:
            rel = signals["reliability"]
            mean = sum(rel) / len(rel)
            var = sum((x - mean) ** 2 for x in rel) / len(rel)
            std = math.sqrt(var)
            if std > 0.25:
                variance_penalty = 0.30
                uncertainty_factors.append(
                    f"High historical volatility (std={std:.2f})"
                )
            elif std > 0.15:
                variance_penalty = 0.15
                uncertainty_factors.append(
                    f"Moderate historical volatility (std={std:.2f})"
                )

        # 3. Missing Critical Signals
        critical_keys = ["failure_rate", "error_rate"]
        missing_critical = [
            k
            for k in critical_keys
            if k not in pred_input.current_metrics and k not in signals
        ]
        if missing_critical:
            sample_adequacy = max(0.1, sample_adequacy - 0.15)
            uncertainty_factors.append(
                f"Missing core signals: {', '.join(missing_critical)}"
            )

        # Calculate final calibrated confidence
        raw_confidence = max(0.10, min(1.0, sample_adequacy - variance_penalty))

        return PredictionConfidence(
            confidence=round(raw_confidence, 4),
            sample_adequacy=round(sample_adequacy, 4),
            variance_penalty=round(variance_penalty, 4),
            uncertainty_factors=uncertainty_factors,
        )
