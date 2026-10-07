"""Candidate evaluation loop, repeated sampling, baseline deltas, and caching."""

from __future__ import annotations

import logging
import math
import statistics
import time
from collections.abc import Callable
from typing import Any

from aireliability.evaluation.engine import EvaluationEngine
from aireliability.evaluation.models import (
    EvaluationRequest,
    EvaluationTarget,
)
from aireliability.optimization.models import (
    CandidateStatus,
    OptimizationCandidate,
    OptimizationExperiment,
    OptimizationProblem,
)

logger = logging.getLogger(__name__)


def _compute_baseline_deltas(
    candidate_metrics: dict[str, float],
    baseline_metrics: dict[str, float],
) -> dict[str, dict[str, float]]:
    """Compute absolute, relative, and percentage deltas against baseline metrics."""
    deltas: dict[str, dict[str, float]] = {}

    for metric, cand_val in candidate_metrics.items():
        base_val = baseline_metrics.get(metric)
        if base_val is None:
            continue

        abs_delta = cand_val - base_val
        rel_delta = (abs_delta / base_val) if abs(base_val) > 1e-9 else 0.0
        pct_delta = rel_delta * 100.0

        deltas[metric] = {
            "baseline": round(base_val, 6),
            "candidate": round(cand_val, 6),
            "absolute": round(abs_delta, 6),
            "relative": round(rel_delta, 6),
            "percentage": round(pct_delta, 2),
        }

    return deltas


def _default_synthetic_metric_eval(cfg: dict[str, Any]) -> dict[str, float]:
    """Fallback deterministic metric evaluator based on standard parameter sensitivities."""
    temp = float(cfg.get("temperature", 0.7))
    top_k = float(cfg.get("top_k", 5))
    timeout = float(cfg.get("tool_timeout", 5.0))
    chunk_sz = float(cfg.get("chunk_size", 256))
    max_steps = float(cfg.get("max_steps", 10))

    # Quality increases with moderate temperature and good top_k
    temp_penalty = abs(temp - 0.4) * 0.15
    quality = max(0.5, min(0.99, 0.90 + (min(top_k, 10) * 0.01) - temp_penalty))

    # Latency scales with top_k, chunk size, and max steps
    latency = round(
        0.4 + (top_k * 0.05) + (chunk_sz / 1000.0 * 0.2) + (max_steps * 0.03), 4
    )

    # Cost scales with chunk size and top_k
    cost = round(0.005 + (top_k * chunk_sz * 0.000005), 5)

    # Groundedness & faithfulness scale with top_k and lower temp
    groundedness = max(0.6, min(1.0, 0.85 + (min(top_k, 8) * 0.015) - (temp * 0.1)))
    faithfulness = max(0.6, min(1.0, 0.88 + (min(top_k, 8) * 0.01) - (temp * 0.08)))

    # Safety and security baseline high unless specifically degraded
    safety = 0.98 if temp <= 1.2 else 0.92
    security = 0.99
    error_rate = max(
        0.0, min(0.3, 0.02 + temp_penalty * 0.5 + (0.05 if timeout < 1.0 else 0.0))
    )
    reliability = max(0.5, min(1.0, 1.0 - error_rate))

    return {
        "quality": round(quality, 4),
        "reliability": round(reliability, 4),
        "latency": latency,
        "cost": cost,
        "groundedness": round(groundedness, 4),
        "faithfulness": round(faithfulness, 4),
        "safety": round(safety, 4),
        "security": round(security, 4),
        "error_rate": round(error_rate, 4),
        "throughput": round(1.0 / max(0.1, latency), 2),
    }


class OptimizationEvaluator:
    """Evaluates candidates, calculates statistics across repeated runs, and caches outcomes."""

    def __init__(
        self,
        evaluation_engine: EvaluationEngine | None = None,
        custom_evaluator_fn: (
            Callable[[dict[str, Any]], dict[str, float]] | None
        ) = None,
        eval_version: str = "0.7.0",
    ) -> None:
        self.evaluation_engine = evaluation_engine
        self.custom_evaluator_fn = custom_evaluator_fn
        self.eval_version = eval_version
        self._cache: dict[str, dict[str, Any]] = {}

    def _build_cache_key(
        self,
        candidate_fp: str,
        dataset_id: str,
        model_ver: str,
    ) -> str:
        """Construct a unique cache key based on configuration and evaluation context."""
        return f"{candidate_fp}::{dataset_id}::{model_ver}::{self.eval_version}"

    def evaluate_candidate(
        self,
        candidate: OptimizationCandidate,
        problem: OptimizationProblem,
        repeats: int = 1,
        seed: int = 42,
    ) -> tuple[OptimizationCandidate, list[OptimizationExperiment]]:
        """Evaluate a single candidate against problem objectives and baseline."""
        if not candidate.is_feasible or candidate.status == CandidateStatus.INVALID:
            return candidate, []

        cache_key = self._build_cache_key(
            candidate_fp=candidate.fingerprint,
            dataset_id=problem.dataset_id,
            model_ver=problem.model_version,
        )

        if cache_key in self._cache:
            cached = self._cache[cache_key]
            candidate.objective_values = dict(cached["objective_values"])
            candidate.metric_stats = dict(cached["metric_stats"])
            candidate.baseline_deltas = dict(cached["baseline_deltas"])
            candidate.confidence = cached.get("confidence", 1.0)
            candidate.status = CandidateStatus.EVALUATED
            candidate.metadata["cached"] = True
            return candidate, []

        experiments: list[OptimizationExperiment] = []
        metrics_per_run: dict[str, list[float]] = {}
        t_start = time.perf_counter()

        num_repeats = max(1, repeats)
        for run_idx in range(num_repeats):
            run_t0 = time.perf_counter()

            # Execute evaluation
            if self.custom_evaluator_fn:
                run_metrics = self.custom_evaluator_fn(candidate.configuration.values)
            elif self.evaluation_engine:
                run_metrics = self._evaluate_via_engine(
                    candidate.configuration.values, problem
                )
            else:
                run_metrics = _default_synthetic_metric_eval(
                    candidate.configuration.values
                )

            run_dur = time.perf_counter() - run_t0

            for k, val in run_metrics.items():
                if k not in metrics_per_run:
                    metrics_per_run[k] = []
                metrics_per_run[k].append(val)

            exp = OptimizationExperiment(
                optimization_id=problem.problem_id,
                candidate_id=candidate.candidate_id,
                configuration=candidate.configuration.values,
                run_index=run_idx,
                metrics=run_metrics,
                objective_scores={
                    o.objective_id: run_metrics.get(o.metric, 0.0)
                    for o in problem.objectives
                },
                execution_duration=round(run_dur, 4),
                resource_cost=run_metrics.get("cost", 0.0),
                seed=seed + run_idx,
            )
            experiments.append(exp)

        # Aggregate statistical measures (mean, median, variance, std_dev)
        aggregated_metrics: dict[str, float] = {}
        metric_stats: dict[str, dict[str, float]] = {}
        variances: list[float] = []

        for k, vals in metrics_per_run.items():
            mean_v = statistics.mean(vals)
            median_v = statistics.median(vals)
            var_v = statistics.variance(vals) if len(vals) > 1 else 0.0
            std_v = math.sqrt(var_v)

            aggregated_metrics[k] = round(mean_v, 6)
            metric_stats[k] = {
                "mean": round(mean_v, 6),
                "median": round(median_v, 6),
                "variance": round(var_v, 6),
                "std_dev": round(std_v, 6),
                "min": round(min(vals), 6),
                "max": round(max(vals), 6),
                "count": len(vals),
            }
            if len(vals) > 1:
                variances.append(var_v)

        # Map to problem objectives
        obj_values: dict[str, float] = {}
        for obj in problem.objectives:
            val = aggregated_metrics.get(
                obj.metric, aggregated_metrics.get(obj.objective_id, 0.0)
            )
            obj_values[obj.objective_id] = val

        # Compute baseline deltas
        deltas = _compute_baseline_deltas(
            candidate_metrics=aggregated_metrics,
            baseline_metrics=problem.baseline_metrics,
        )

        # Calculate explainable confidence based on repeats and metric variance
        avg_var = statistics.mean(variances) if variances else 0.0
        confidence = 1.0 / (1.0 + avg_var * 10.0) if num_repeats > 1 else 0.95
        confidence = round(max(0.1, min(1.0, confidence)), 4)

        candidate.objective_values = obj_values
        candidate.metric_stats = metric_stats
        candidate.baseline_deltas = deltas
        candidate.confidence = confidence
        candidate.status = CandidateStatus.EVALUATED
        candidate.metadata["duration_seconds"] = round(time.perf_counter() - t_start, 4)

        # Cache result
        self._cache[cache_key] = {
            "objective_values": obj_values,
            "metric_stats": metric_stats,
            "baseline_deltas": deltas,
            "confidence": confidence,
        }

        return candidate, experiments

    def _evaluate_via_engine(
        self, cfg: dict[str, Any], problem: OptimizationProblem
    ) -> dict[str, float]:
        """Execute evaluation using the underlying Phase 1-33 EvaluationEngine."""
        if not self.evaluation_engine:
            return _default_synthetic_metric_eval(cfg)

        try:
            req = EvaluationRequest(
                dataset=problem.dataset_id or "optimization_eval_dataset",
                target=EvaluationTarget(
                    name=f"optimization_candidate_{cfg.get('model_name', 'model')}",
                    metadata={"configuration": cfg},
                ),
            )
            report = self.evaluation_engine.evaluate(req)
            metrics: dict[str, float] = {}
            for k, m in report.metrics.items():
                metrics[k] = m.value
            if report.total_test_cases > 0:
                metrics["quality"] = report.passed_test_cases / report.total_test_cases
                metrics["error_rate"] = (
                    report.failed_test_cases / report.total_test_cases
                )
                metrics["reliability"] = 1.0 - metrics["error_rate"]
            return metrics if metrics else _default_synthetic_metric_eval(cfg)
        except Exception as exc:
            logger.warning(
                "EvaluationEngine run failed, falling back to synthetic evaluator: %s",
                exc,
            )
            return _default_synthetic_metric_eval(cfg)
