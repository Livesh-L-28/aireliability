"""Statistical Drift Detector for queries, embeddings, retrieval scores, and grounding."""

from __future__ import annotations

from typing import Any

from aireliability.rag.models import (
    FailureSeverity,
    RAGDriftResult,
    RAGFailure,
    RAGFailureCategory,
    RAGStage,
)


class RAGDriftDetector:
    """Detects statistical distribution drift across queries, retrieval, and grounding outputs."""

    def __init__(
        self,
        drift_threshold: float = 0.20,
        threshold_delta: float | None = None,
    ) -> None:
        self.drift_threshold = (
            threshold_delta if threshold_delta is not None else drift_threshold
        )

    def detect_embedding_drift(
        self,
        baseline_embedding_model: str,
        observed_embedding_model: str,
    ) -> tuple[RAGDriftResult, list[RAGFailure]]:
        """Convenience method comparing baseline and observed embedding models."""
        drifts, fails = self.detect_drift(
            baseline_metrics={},
            observed_metrics={},
            embedding_version_baseline=baseline_embedding_model,
            embedding_version_observed=observed_embedding_model,
        )
        if drifts:
            return drifts[0], fails
        res = RAGDriftResult(
            drift_type="EMBEDDING_MODEL_CHANGE",
            metric_name="embedding_model_version",
            baseline_value=1.0,
            observed_value=0.0,
            delta=-1.0,
            drift_detected=True,
            trend="CHANGED",
        )
        return res, fails

    def detect_drift(
        self,
        baseline_metrics: dict[str, float],
        observed_metrics: dict[str, float],
        embedding_version_baseline: str | None = None,
        embedding_version_observed: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[list[RAGDriftResult], list[RAGFailure]]:
        """Compare baseline metric distributions against observed metrics.

        Returns (drift_results, failures).
        """
        results: list[RAGDriftResult] = []
        failures: list[RAGFailure] = []

        # 1. Embedding Model Version Change
        if (
            embedding_version_baseline
            and embedding_version_observed
            and embedding_version_baseline != embedding_version_observed
        ):
            results.append(
                RAGDriftResult(
                    drift_type="EMBEDDING_DRIFT",
                    metric_name="model_version",
                    baseline_value=1.0,
                    observed_value=0.0,
                    delta=1.0,
                    drift_detected=True,
                    trend="CHANGED",
                    confidence=1.0,
                    details={
                        "baseline_version": embedding_version_baseline,
                        "observed_version": embedding_version_observed,
                    },
                )
            )
            failures.append(
                RAGFailure(
                    stage=RAGStage.RETRIEVAL,
                    category=RAGFailureCategory.EMBEDDING_DRIFT,
                    severity=FailureSeverity.CRITICAL,
                    message=(
                        f"EMBEDDING_MODEL_CHANGE: Detected model version change from "
                        f"'{embedding_version_baseline}' to '{embedding_version_observed}'. "
                        f"Index re-embedding is required."
                    ),
                    confidence=1.0,
                )
            )

        # 2. Metric Drift Checks
        monitored_metrics = [
            ("query_length", "QUERY_DRIFT"),
            ("retrieval_score", "RETRIEVAL_DRIFT"),
            ("grounding_score", "GROUNDING_DRIFT"),
            ("hallucination_rate", "GROUNDING_DRIFT"),
            ("citation_score", "CITATION_DRIFT"),
        ]

        for metric_name, drift_type in monitored_metrics:
            if metric_name in baseline_metrics and metric_name in observed_metrics:
                base_v = baseline_metrics[metric_name]
                obs_v = observed_metrics[metric_name]
                delta = obs_v - base_v
                rel_delta = (abs(delta) / base_v) if abs(base_v) > 1e-6 else abs(delta)

                is_drift = rel_delta > self.drift_threshold
                trend = (
                    "INCREASING"
                    if delta > 0.05
                    else ("DECREASING" if delta < -0.05 else "STABLE")
                )

                res = RAGDriftResult(
                    drift_type=drift_type,
                    metric_name=metric_name,
                    baseline_value=round(base_v, 4),
                    observed_value=round(obs_v, 4),
                    delta=round(delta, 4),
                    drift_detected=is_drift,
                    trend=trend,
                    confidence=0.90,
                )
                results.append(res)

                if is_drift:
                    cat = (
                        RAGFailureCategory.RETRIEVAL_DRIFT
                        if drift_type == "RETRIEVAL_DRIFT"
                        else RAGFailureCategory.GROUNDING_FAILURE
                    )
                    failures.append(
                        RAGFailure(
                            stage=RAGStage.OVERALL,
                            category=cat,
                            severity=FailureSeverity.HIGH
                            if "grounding" in metric_name
                            else FailureSeverity.MEDIUM,
                            message=(
                                f"STATISTICAL_DRIFT: Significant shift detected in '{metric_name}' "
                                f"({base_v:.3f} -> {obs_v:.3f}, delta: {delta:+.3f})."
                            ),
                            confidence=0.88,
                        )
                    )

        return results, failures
