"""Online evaluation bridge connecting production traces to evaluation."""

from __future__ import annotations

import random

from aireliability.core.models import (
    EvaluationResult,
    ExecutionTrace,
    TestCase,
)
from aireliability.core.protocols import Evaluator


class ProductionSampler:
    """Samples production traces for continuous evaluation."""

    def __init__(
        self,
        sample_rate: float = 0.10,
        always_sample_errors: bool = True,
        seed: int = 42,
    ) -> None:
        self.sample_rate = sample_rate
        self.always_sample_errors = always_sample_errors
        self.rng = random.Random(seed)

    def should_sample(self, trace: ExecutionTrace) -> bool:
        """Determine whether trace should be sampled for evaluation."""
        if self.always_sample_errors and trace.status.value in ("failed", "error"):
            return True
        return self.rng.random() < self.sample_rate


class OnlineEvaluationBridge:
    """Bridges production traces into evaluation engines and metric recorders."""

    def __init__(
        self,
        evaluators: list[Evaluator],
        sampler: ProductionSampler | None = None,
    ) -> None:
        self.evaluators = list(evaluators)
        self.sampler = sampler or ProductionSampler()
        self.evaluated_results: list[EvaluationResult] = []

    def process_trace(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> list[EvaluationResult]:
        """Evaluate trace if sampled."""
        if not self.sampler.should_sample(trace):
            return []

        results: list[EvaluationResult] = []
        tc = test_case or TestCase(
            id=trace.test_id or "live_trace",
            name=f"trace_{trace.trace_id}",
            input=trace.input,
            expected_output=None,
        )

        for ev in self.evaluators:
            res = ev.evaluate(trace, tc)
            results.append(res)
            self.evaluated_results.append(res)

        return results
