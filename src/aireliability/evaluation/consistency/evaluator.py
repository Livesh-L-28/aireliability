"""Consistency evaluation across repeated N-run executions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from aireliability.core.models import (
    EvaluationResult,
    ExecutionTrace,
    RunResult,
    StepType,
    TestCase,
)
from aireliability.evaluation.expectations import BaseExpectation
from aireliability.evaluation.metrics.statistics import variance
from aireliability.execution.runner import ReliabilityRunner


class ConsistencyEvaluator(BaseExpectation):
    """Measures behavioral, output, tool, and evaluation score consistency across N runs."""

    def __init__(
        self,
        *,
        num_runs: int = 5,
        min_consistency: float = 0.80,
        max_score_variance: float = 0.05,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(
            name=name or f"ConsistencyEvaluator(N={num_runs})",
            num_runs=num_runs,
            min_consistency=min_consistency,
            max_score_variance=max_score_variance,
            **metadata,
        )
        self.num_runs = num_runs
        self.min_consistency = min_consistency
        self.max_score_variance = max_score_variance

    def evaluate_agent_consistency(
        self,
        agent: Callable[[Any], Any],
        test_case: TestCase,
        evaluators: list[Any] | None = None,
    ) -> EvaluationResult:
        """Run agent N times with identical inputs and measure consistency."""
        runner = ReliabilityRunner(
            agent=agent, evaluators=evaluators, suppress_agent_exceptions=True
        )

        results: list[RunResult] = [runner.run(test_case) for _ in range(self.num_runs)]

        outputs = [str(r.trace.output or "").strip() for r in results]
        tool_sequences = [
            [s.name for s in r.trace.steps if s.type == StepType.TOOL] for r in results
        ]
        scores = [1.0 if r.passed else 0.0 for r in results]

        # 1. Output consistency: mode frequency / N
        output_counts: dict[str, int] = {}
        for out in outputs:
            output_counts[out] = output_counts.get(out, 0) + 1
        most_common_out_count = max(output_counts.values()) if output_counts else 0
        output_consistency = most_common_out_count / max(1, self.num_runs)

        # 2. Tool consistency: identical sequences
        str_tool_seqs = [tuple(seq) for seq in tool_sequences]
        seq_counts: dict[tuple[str, ...], int] = {}
        for s in str_tool_seqs:
            seq_counts[s] = seq_counts.get(s, 0) + 1
        most_common_tool_count = max(seq_counts.values()) if seq_counts else 0
        tool_consistency = most_common_tool_count / max(1, self.num_runs)

        # 3. Score variance
        score_var = variance(scores) if len(scores) > 1 else 0.0

        composite_consistency = round((output_consistency + tool_consistency) / 2.0, 4)
        passed = (
            composite_consistency >= self.min_consistency
            and score_var <= self.max_score_variance
        )

        msg = (
            f"Consistency PASSED across {self.num_runs} runs: output={output_consistency:.2%}, "
            f"tool={tool_consistency:.2%}, score_var={score_var:.4f}."
            if passed
            else f"Consistency FAILED: composite={composite_consistency:.2%} (min {self.min_consistency:.2%}), "
            f"score_var={score_var:.4f} (max {self.max_score_variance:.4f})."
        )

        evidence = {
            "num_runs": self.num_runs,
            "output_consistency": round(output_consistency, 4),
            "tool_consistency": round(tool_consistency, 4),
            "score_variance": round(score_var, 4),
            "unique_outputs_count": len(output_counts),
            "unique_tool_patterns_count": len(seq_counts),
        }

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=composite_consistency,
            metric="consistency_score",
            threshold=self.min_consistency,
            confidence=1.0,
            message=msg,
            evidence=evidence,
            metadata={
                **self.metadata,
                "failure_category": "task",
                "failure_type": "task_incomplete" if not passed else "none",
                **evidence,
            },
        )

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        """Trace-level evaluation hook."""
        return EvaluationResult(
            evaluator=self.name,
            passed=trace.status.value != "failed",
            score=1.0,
            metric="consistency_score",
            message="Consistency evaluation requires multi-run harness via evaluate_agent_consistency.",
            metadata=self.metadata,
        )
