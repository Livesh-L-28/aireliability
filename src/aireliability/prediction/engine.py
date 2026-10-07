"""Statistical reliability prediction engine with trend forecasting and degradation modeling (Phase 42)."""

from __future__ import annotations

import math

from aireliability.prediction.confidence import PredictionConfidenceEngine
from aireliability.prediction.features import PredictionFeatureExtractor
from aireliability.prediction.models import (
    FailureProbability,
    PredictionEvidence,
    PredictionExplanation,
    PredictionHorizon,
    PredictionInput,
    PredictionRecommendation,
    PredictionRiskLevel,
    PredictionTrend,
    ReliabilityForecast,
    ReliabilityPrediction,
    RiskForecast,
)


class ReliabilityPredictionEngine:
    """Deterministic statistical prediction engine for AI reliability forecasting."""

    def __init__(self) -> None:
        self.feature_extractor = PredictionFeatureExtractor()
        self.confidence_engine = PredictionConfidenceEngine()

    def predict(
        self,
        pred_input: PredictionInput,
        horizon: PredictionHorizon = PredictionHorizon.SHORT_TERM,
    ) -> ReliabilityPrediction:
        """Generate comprehensive reliability prediction for the given target."""
        features = self.feature_extractor.extract_features(pred_input)
        confidence = self.confidence_engine.assess_confidence(pred_input)

        # 1. Historical Reliability Trend Projection (EMA / Linear Slope)
        rel_series = pred_input.historical_signals.get("reliability", [])
        if rel_series:
            # Exponential Moving Average with alpha=0.3
            ema = rel_series[0]
            alpha = 0.3
            for val in rel_series[1:]:
                ema = alpha * val + (1 - alpha) * ema

            # Linear trend slope
            n = len(rel_series)
            if n > 1:
                x_mean = (n - 1) / 2.0
                y_mean = sum(rel_series) / n
                slope_num = sum(
                    (i - x_mean) * (rel_series[i] - y_mean) for i in range(n)
                )
                slope_den = sum((i - x_mean) ** 2 for i in range(n))
                slope = slope_num / slope_den if slope_den > 0 else 0.0
            else:
                slope = 0.0
            current_rel = ema
        else:
            current_rel = pred_input.current_metrics.get("reliability", 0.95)
            slope = 0.0

        # Adjust projection based on horizon multiplier
        horizon_steps = {
            PredictionHorizon.NEXT_EXECUTION: 1,
            PredictionHorizon.SHORT_TERM: 3,
            PredictionHorizon.MEDIUM_TERM: 10,
            PredictionHorizon.LONG_TERM: 30,
        }[horizon]

        projected_rel = max(0.0, min(1.0, current_rel + (slope * horizon_steps * 0.1)))

        # 2. Risk Forecast
        # Weighted aggregate of failure features
        total_risk_contribution = sum(
            f.contribution for f in features if f.unit == "ratio"
        )
        risk_score = min(
            1.0,
            max(
                0.0,
                (1.0 - projected_rel) * 0.6
                + (total_risk_contribution / max(1, len(features))) * 0.4,
            ),
        )

        if slope < -0.02:
            trend = PredictionTrend.DEGRADING
        elif slope > 0.02:
            trend = PredictionTrend.IMPROVING
        elif (
            "volatility" in pred_input.current_metrics
            and pred_input.current_metrics["volatility"] > 0.2
        ):
            trend = PredictionTrend.VOLATILE
        else:
            trend = PredictionTrend.STABLE

        if risk_score >= 0.70:
            risk_level = PredictionRiskLevel.CRITICAL
        elif risk_score >= 0.45:
            risk_level = PredictionRiskLevel.HIGH
        elif risk_score >= 0.20:
            risk_level = PredictionRiskLevel.MEDIUM
        else:
            risk_level = PredictionRiskLevel.LOW

        risk_forecast = RiskForecast(
            risk_score=round(risk_score, 4),
            risk_level=risk_level,
            trend=trend,
            projected_degradation=round(max(0.0, current_rel - projected_rel), 4),
            horizon=horizon,
        )

        # 3. Confidence Interval for Reliability Forecast
        # Margin of error expands as confidence decreases and horizon lengthens
        margin = (1.0 - confidence.confidence) * 0.25 * math.sqrt(horizon_steps)
        reliability_forecast = ReliabilityForecast(
            metric_name="overall_reliability",
            forecasted_value=round(projected_rel, 4),
            lower_bound=round(max(0.0, projected_rel - margin), 4),
            upper_bound=round(min(1.0, projected_rel + margin), 4),
            horizon=horizon,
        )

        # 4. Failure Probabilities across core categories
        failure_categories = [
            ("agent_reasoning", "agent_failure_rate", 0.3),
            ("tool_execution", "tool_failure_rate", 0.25),
            ("retrieval_grounding", "retrieval_failure_rate", 0.2),
            ("safety_boundary", "safety_issue_rate", 0.15),
            ("timeout_latency", "timeout_rate", 0.1),
        ]
        fail_probs: list[FailureProbability] = []
        for cat_name, feat_name, base_weight in failure_categories:
            matching_feat = next((f for f in features if f.name == feat_name), None)
            feat_val = matching_feat.value if matching_feat else 0.05
            cat_prob = min(
                1.0, max(0.0, (feat_val * 0.7) + (risk_score * 0.3 * base_weight))
            )
            fail_probs.append(
                FailureProbability(
                    category=cat_name,
                    probability=round(cat_prob, 4),
                    horizon=horizon,
                    confidence=confidence.confidence,
                    contributing_signals=[feat_name],
                )
            )

        # 5. Evidence & Recommendations
        evidence: list[PredictionEvidence] = []
        for f in features:
            if f.value > 0.15:
                evidence.append(
                    PredictionEvidence(
                        signal_name=f.name,
                        observed_value=f.value,
                        baseline_value=0.05,
                        z_score=1.5,
                        impact="negative",
                    )
                )

        recommendations: list[PredictionRecommendation] = []
        if risk_level in (PredictionRiskLevel.HIGH, PredictionRiskLevel.CRITICAL):
            recommendations.append(
                PredictionRecommendation(
                    action="remediation",
                    urgency=risk_level,
                    affected_component=pred_input.target_id,
                    description=f"Predicted elevated risk ({risk_score:.2f}) with {trend.value} trend.",
                    suggested_mitigation="Increase evaluation sampling rate and inspect degrading features.",
                )
            )

        # 6. Explanation
        top_factors = sorted(features, key=lambda x: x.contribution, reverse=True)[:3]
        summary = (
            f"Forecasted reliability is {projected_rel:.2f} ({trend.value}) with {risk_level.value} risk "
            f"over horizon {horizon.value}. Confidence is {confidence.confidence * 100:.1f}%."
        )
        explanation = PredictionExplanation(
            summary=summary,
            top_factors=top_factors,
            limitations=confidence.uncertainty_factors,
        )

        return ReliabilityPrediction(
            target_id=pred_input.target_id,
            target_type=pred_input.target_type,
            horizon=horizon,
            failure_probabilities=fail_probs,
            risk_forecast=risk_forecast,
            reliability_forecast=reliability_forecast,
            confidence=confidence,
            evidence=evidence,
            explanation=explanation,
            recommendations=recommendations,
        )
