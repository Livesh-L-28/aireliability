"""Feature extraction and statistical signal synthesis for reliability prediction (Phase 42)."""

from __future__ import annotations

import math

from aireliability.prediction.models import PredictionFeature, PredictionInput


class PredictionFeatureExtractor:
    """Extracts normalized statistical features from historical execution telemetry."""

    def extract_features(self, pred_input: PredictionInput) -> list[PredictionFeature]:
        """Convert raw signals and current metrics into weighted PredictionFeatures."""
        features: list[PredictionFeature] = []
        signals = pred_input.historical_signals
        metrics = pred_input.current_metrics

        # Standard signals to process
        signal_names = [
            ("failure_rate", 1.5, "Ratio of failed executions to total"),
            ("error_rate", 1.2, "Ratio of unhandled runtime errors"),
            ("incident_rate", 2.0, "Severity incidents per 100 runs"),
            ("regression_rate", 1.8, "Ratio of regression test breaks"),
            ("safety_issue_rate", 2.5, "Ratio of safety boundary failures"),
            ("retrieval_failure_rate", 1.4, "RAG context retrieval failure rate"),
            ("grounding_failure_rate", 1.5, "RAG grounding/faithfulness failure rate"),
            ("agent_failure_rate", 1.6, "Agent trajectory failure rate"),
            ("tool_failure_rate", 1.3, "Tool invocation exception rate"),
            ("retry_rate", 1.1, "Tool and API retry frequency"),
            ("timeout_rate", 1.3, "Gateway and execution timeout frequency"),
            ("latency", 0.8, "Mean execution latency in seconds"),
            ("cost", 0.7, "Mean cost in USD"),
            ("token_usage", 0.5, "Mean tokens consumed per run"),
            ("volatility", 1.2, "Coefficient of variance in reliability scores"),
            ("failure_persistence", 1.4, "Autocorrelation of consecutive failures"),
            ("remediation_frequency", 0.9, "Frequency of self-healing patches"),
            ("test_coverage", 0.8, "Regression test suite coverage ratio"),
            ("safety_coverage", 1.0, "Safety category coverage ratio"),
        ]

        for name, weight, desc in signal_names:
            val = 0.0
            if name in metrics:
                val = metrics[name]
            elif name in signals and signals[name]:
                val = sum(signals[name]) / len(signals[name])
            elif (
                name == "volatility"
                and "reliability" in signals
                and len(signals["reliability"]) > 1
            ):
                series = signals["reliability"]
                mean_val = sum(series) / len(series)
                var = sum((x - mean_val) ** 2 for x in series) / len(series)
                val = (math.sqrt(var) / mean_val) if mean_val > 0 else 0.0

            # Calculate relative contribution (higher risk signals contribute more)
            contribution = min(1.0, val * weight)
            features.append(
                PredictionFeature(
                    name=name,
                    value=round(val, 4),
                    unit="ratio" if "rate" in name or "coverage" in name else "value",
                    weight=weight,
                    contribution=round(contribution, 4),
                    description=desc,
                )
            )

        return features
