"""Benchmark suite for Reliability Prediction Engine (Phase 42) across series scales."""

from __future__ import annotations

import sys
from pathlib import Path

# Path setup for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aireliability.prediction.confidence import PredictionConfidenceEngine
from aireliability.prediction.engine import ReliabilityPredictionEngine
from aireliability.prediction.evaluator import PredictionEvaluator
from aireliability.prediction.features import PredictionFeatureExtractor
from aireliability.prediction.models import (
    PredictionHorizon,
    PredictionInput,
    PredictionWindow,
)
from benchmarks.benchmark_config import BenchmarkConfig
from benchmarks.benchmark_utils import BenchmarkMetric, measure_benchmark


def make_prediction_input(points_count: int) -> PredictionInput:
    """Generate synthetic historical reliability signals with N data points."""
    rel_series = [0.98 - (i * 0.00005) for i in range(points_count)]
    fail_rate_series = [0.02 + (i * 0.00005) for i in range(points_count)]
    latency_series = [12.0 + ((i % 50) * 0.1) for i in range(points_count)]

    return PredictionInput(
        target_id="agent_assistant",
        target_type="agent",
        historical_signals={
            "reliability": rel_series,
            "failure_rate": fail_rate_series,
            "latency": latency_series,
        },
        current_metrics={
            "reliability": 0.94,
            "failure_rate": 0.06,
            "latency": 15.0,
        },
        window=PredictionWindow(sample_count=points_count),
    )


def run_prediction_benchmarks(config: BenchmarkConfig) -> list[BenchmarkMetric]:
    metrics: list[BenchmarkMetric] = []
    engine = ReliabilityPredictionEngine()
    feature_extractor = PredictionFeatureExtractor()
    confidence_engine = PredictionConfidenceEngine()
    evaluator = PredictionEvaluator()

    input_10 = make_prediction_input(config.sizes.SMALL)
    input_100 = make_prediction_input(config.sizes.MEDIUM)
    input_1000 = make_prediction_input(config.sizes.LARGE)
    input_10000 = make_prediction_input(config.sizes.XLARGE)

    # 1. Feature Generation - 100 points
    def bench_features_100() -> None:
        _ = feature_extractor.extract_features(input_100)

    metrics.append(
        measure_benchmark(
            operation="prediction_features_100",
            target_func=bench_features_100,
            input_size="100 data points signals",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("prediction_forecasting"),
            seed=config.seed,
        )
    )

    # 2. Feature Generation - 10,000 points (scaling check)
    def bench_features_10000() -> None:
        _ = feature_extractor.extract_features(input_10000)

    metrics.append(
        measure_benchmark(
            operation="prediction_features_10000",
            target_func=bench_features_10000,
            input_size="10,000 data points signals",
            iterations=config.iterations,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("prediction_forecasting"),
            seed=config.seed,
        )
    )

    # 3. Confidence Assessment - 100 points
    def bench_confidence() -> None:
        _ = confidence_engine.assess_confidence(input_100)

    metrics.append(
        measure_benchmark(
            operation="prediction_confidence_assessment",
            target_func=bench_confidence,
            input_size="100 data points",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("prediction_forecasting"),
            seed=config.seed,
        )
    )

    # 4. End-to-End Prediction - 10 points
    def bench_predict_10() -> None:
        _ = engine.predict(input_10, horizon=PredictionHorizon.SHORT_TERM)

    metrics.append(
        measure_benchmark(
            operation="prediction_e2e_10_points",
            target_func=bench_predict_10,
            input_size="10 points forecasting",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("prediction_forecasting"),
            seed=config.seed,
        )
    )

    # 5. End-to-End Prediction - 100 points
    def bench_predict_100() -> None:
        _ = engine.predict(input_100, horizon=PredictionHorizon.SHORT_TERM)

    metrics.append(
        measure_benchmark(
            operation="prediction_e2e_100_points",
            target_func=bench_predict_100,
            input_size="100 points forecasting",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("prediction_forecasting"),
            seed=config.seed,
        )
    )

    # 6. End-to-End Prediction - 1,000 points
    def bench_predict_1000() -> None:
        _ = engine.predict(input_1000, horizon=PredictionHorizon.SHORT_TERM)

    metrics.append(
        measure_benchmark(
            operation="prediction_e2e_1000_points",
            target_func=bench_predict_1000,
            input_size="1,000 points forecasting",
            iterations=config.iterations,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("prediction_forecasting"),
            seed=config.seed,
        )
    )

    # 7. End-to-End Prediction - 10,000 points
    def bench_predict_10000() -> None:
        _ = engine.predict(input_10000, horizon=PredictionHorizon.SHORT_TERM)

    metrics.append(
        measure_benchmark(
            operation="prediction_e2e_10000_points",
            target_func=bench_predict_10000,
            input_size="10,000 points forecasting",
            iterations=config.iterations,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("prediction_forecasting"),
            seed=config.seed,
        )
    )

    # 8. Prediction Evaluator (Brier & MAE calibration calculation)
    pred_res = engine.predict(input_100, horizon=PredictionHorizon.SHORT_TERM)

    def bench_evaluator() -> None:
        _ = evaluator.evaluate(pred_res, actual_failed=False, actual_reliability=0.93)

    metrics.append(
        measure_benchmark(
            operation="prediction_brier_evaluation",
            target_func=bench_evaluator,
            input_size="Prediction outcome evaluation",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("prediction_forecasting"),
            seed=config.seed,
        )
    )

    return metrics


if __name__ == "__main__":
    cfg = BenchmarkConfig.from_mode("quick")
    res = run_prediction_benchmarks(cfg)
    for m in res:
        print(
            f"[{m.status}] {m.operation}: p50={m.median_latency_ms}ms, p95={m.p95_latency_ms}ms, throughput={m.throughput_ops} ops/s"
        )
