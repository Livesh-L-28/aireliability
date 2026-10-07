"""Observability integration emitting metrics and distributed spans for Phase 38."""

from __future__ import annotations

import logging

from aireliability.observability.manager import ObservabilityManager
from aireliability.optimization.models import OptimizationResult, StoppingReason

logger = logging.getLogger(__name__)


class OptimizationObservabilityBridge:
    """Emits Phase 38 optimization metrics, timers, and trace spans to ObservabilityManager."""

    def __init__(self, manager: ObservabilityManager | None = None) -> None:
        self.manager = manager or ObservabilityManager()

    def record_run_started(self, problem_id: str, strategy: str) -> None:
        """Record the initiation of an optimization search run."""
        try:
            self.manager.metrics.counter("optimization_runs_total").increment(
                1.0, strategy=strategy
            )
        except Exception as exc:
            logger.debug("Failed recording metric optimization_runs_total: %s", exc)

    def record_candidate_generated(self, strategy: str) -> None:
        """Increment count of generated candidate configurations."""
        try:
            self.manager.metrics.counter("optimization_candidates_total").increment(
                1.0, strategy=strategy
            )
        except Exception as exc:
            logger.debug("Failed recording optimization_candidates_total: %s", exc)

    def record_evaluation(self, candidate_id: str, duration: float) -> None:
        """Record execution and duration of candidate evaluation."""
        try:
            self.manager.metrics.counter("optimization_evaluations_total").increment(
                1.0
            )
            self.manager.metrics.histogram(
                "optimization_candidate_duration_seconds"
            ).observe(duration)
        except Exception as exc:
            logger.debug("Failed recording evaluation metrics: %s", exc)

    def record_run_completed(self, result: OptimizationResult) -> None:
        """Record completion metrics and Pareto frontier dimensions."""
        try:
            strat = result.problem.metadata.get("strategy", "unknown")
            if result.selected_candidate:
                self.manager.metrics.counter("optimization_success_total").increment(
                    1.0, strategy=strat
                )
            else:
                self.manager.metrics.counter("optimization_failed_total").increment(
                    1.0, strategy=strat
                )

            if result.stopping_reason == StoppingReason.BUDGET_EXHAUSTED:
                self.manager.metrics.counter(
                    "optimization_budget_exhausted_total"
                ).increment(1.0)

            self.manager.metrics.histogram("optimization_duration_seconds").observe(
                result.duration_seconds
            )
            self.manager.metrics.gauge("optimization_pareto_size").set(
                float(len(result.pareto_frontier.non_dominated_candidate_ids))
            )
        except Exception as exc:
            logger.debug("Failed recording run completion metrics: %s", exc)

    def record_deployment(self, strategy: str) -> None:
        """Increment deployment metric when candidate is deployed."""
        try:
            self.manager.metrics.counter("optimization_deployments_total").increment(
                1.0, strategy=strategy
            )
        except Exception as exc:
            logger.debug("Failed recording optimization_deployments_total: %s", exc)

    def record_rollback(self, reason: str) -> None:
        """Increment rollback metric when deployment is reverted."""
        try:
            self.manager.metrics.counter("optimization_rollbacks_total").increment(
                1.0, reason=reason
            )
        except Exception as exc:
            logger.debug("Failed recording optimization_rollbacks_total: %s", exc)
