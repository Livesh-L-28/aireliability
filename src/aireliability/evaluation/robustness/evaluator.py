"""Robustness evaluator testing behavioral stability across input perturbations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from aireliability.core.models import (
    EvaluationResult,
    ExecutionTrace,
    RunResult,
    TestCase,
)
from aireliability.evaluation.expectations import BaseExpectation
from aireliability.evaluation.metrics.statistics import variance
from aireliability.evaluation.robustness.perturbations import (
    PerturbationGenerator,
    PerturbationType,
)
from aireliability.execution.runner import ReliabilityRunner


class RobustnessEvaluator(BaseExpectation):
    """Evaluates agent stability under typos, case changes, noise, and adversarial perturbations."""

    def __init__(
        self,
        *,
        min_stability_score: float = 0.80,
        max_flip_rate: float = 0.20,
        perturbation_types: list[PerturbationType] | None = None,
        generator: PerturbationGenerator | None = None,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(
            name=name or "RobustnessEvaluator",
            min_stability_score=min_stability_score,
            max_flip_rate=max_flip_rate,
            **metadata,
        )
        self.min_stability_score = min_stability_score
        self.max_flip_rate = max_flip_rate
        self.perturbation_types = perturbation_types
        self.generator = generator or PerturbationGenerator()

    def evaluate_agent_robustness(
        self,
        agent: Callable[[Any], Any],
        test_case: TestCase,
        evaluators: list[Any] | None = None,
    ) -> EvaluationResult:
        """Execute agent against original test case and its perturbed variants."""
        runner = ReliabilityRunner(
            agent=agent, evaluators=evaluators, suppress_agent_exceptions=True
        )

        orig_result: RunResult = runner.run(test_case)
        variants = self.generator.generate_variants(test_case, self.perturbation_types)

        variant_results: list[RunResult] = [runner.run(v) for v in variants]

        flips = 0
        variant_scores: list[float] = []

        for r in variant_results:
            passed = bool(r.passed)
            # Flip is when original passed, but variant failed
            if orig_result.passed and not passed:
                flips += 1
            variant_scores.append(1.0 if passed else 0.0)

        total_variants = max(1, len(variants))
        flip_rate = flips / total_variants
        stability_score = sum(variant_scores) / total_variants
        score_var = variance(variant_scores) if len(variant_scores) > 1 else 0.0

        passed = (
            stability_score >= self.min_stability_score
            and flip_rate <= self.max_flip_rate
        )

        msg = (
            f"Robustness PASSED: stability {stability_score:.2%}, flip rate {flip_rate:.2%} "
            f"across {len(variants)} perturbations."
            if passed
            else f"Robustness FAILED: stability {stability_score:.2%} (min {self.min_stability_score:.2%}), "
            f"flip rate {flip_rate:.2%} (max allowed {self.max_flip_rate:.2%})."
        )

        evidence = {
            "total_perturbations": len(variants),
            "original_passed": orig_result.passed,
            "stability_score": round(stability_score, 4),
            "flip_rate": round(flip_rate, 4),
            "score_variance": round(score_var, 4),
            "variant_outcomes": [
                {
                    "test_id": r.test.id,
                    "perturbation": r.test.metadata.get("perturbation_type"),
                    "passed": r.passed,
                    "output": str(r.trace.output)[:100],
                }
                for r in variant_results
            ],
        }

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=round(stability_score, 4),
            metric="robustness_stability",
            threshold=self.min_stability_score,
            confidence=1.0,
            message=msg,
            evidence=evidence,
            metadata={
                **self.metadata,
                "failure_category": "task",
                "failure_type": "task_incomplete" if flip_rate > 0 else "none",
                **evidence,
            },
        )

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        """Trace-level evaluation hook (passes if trace completed without errors)."""
        return EvaluationResult(
            evaluator=self.name,
            passed=trace.status.value != "failed",
            score=1.0 if trace.status.value != "failed" else 0.0,
            metric="robustness_stability",
            message="Trace evaluation for robustness requires agent execution via evaluate_agent_robustness.",
            metadata=self.metadata,
        )
