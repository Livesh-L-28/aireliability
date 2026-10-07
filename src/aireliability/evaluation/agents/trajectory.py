"""Trajectory analysis, loop detection, and retry evaluation for agents."""

from __future__ import annotations

from typing import Any

from aireliability.core.models import (
    EvaluationResult,
    ExecutionTrace,
    StepType,
    TestCase,
    TraceStep,
)
from aireliability.evaluation.expectations import BaseExpectation


def _detect_loops(
    steps: list[TraceStep], max_repeated_calls: int = 3
) -> tuple[int, list[dict[str, Any]]]:
    """Detect repetitive calls or cycles in tool execution steps."""
    tool_steps = [s for s in steps if s.type == StepType.TOOL]
    loops_found: list[dict[str, Any]] = []

    # 1. Consecutive identical tool + args calls
    consecutive_count = 1
    for idx in range(1, len(tool_steps)):
        curr, prev = tool_steps[idx], tool_steps[idx - 1]
        if curr.name == prev.name and curr.input == prev.input:
            consecutive_count += 1
            if consecutive_count >= max_repeated_calls:
                loops_found.append(
                    {
                        "type": "consecutive_repetition",
                        "tool": curr.name,
                        "repetitions": consecutive_count,
                        "step_id": curr.id,
                    }
                )
        else:
            consecutive_count = 1

    # 2. Cycle detection (A -> B -> A -> B)
    names = [s.name for s in tool_steps]
    for pattern_len in (2, 3):
        if len(names) >= pattern_len * 2:
            for i in range(len(names) - pattern_len * 2 + 1):
                p1 = names[i : i + pattern_len]
                p2 = names[i + pattern_len : i + pattern_len * 2]
                if p1 == p2:
                    loops_found.append(
                        {
                            "type": "cyclic_pattern",
                            "pattern": p1,
                            "start_index": i,
                        }
                    )

    return len(loops_found), loops_found


def _count_retries(steps: list[TraceStep]) -> int:
    """Count retries where a tool failed and was immediately invoked again."""
    retries = 0
    tool_steps = [s for s in steps if s.type == StepType.TOOL]
    for idx in range(1, len(tool_steps)):
        curr, prev = tool_steps[idx], tool_steps[idx - 1]
        prev_failed = (
            prev.metadata.get("status") in ("failed", "error")
            or "error" in str(prev.output).lower()
        )
        if prev_failed and curr.name == prev.name:
            retries += 1
    return retries


class TrajectoryEvaluator(BaseExpectation):
    """Evaluates agent trajectory length, loop presence, retry counts, and execution efficiency."""

    def __init__(
        self,
        *,
        max_steps: int = 15,
        max_allowed_loops: int = 0,
        max_allowed_retries: int = 2,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(
            name=name or "TrajectoryEvaluator",
            max_steps=max_steps,
            max_allowed_loops=max_allowed_loops,
            max_allowed_retries=max_allowed_retries,
            **metadata,
        )
        self.max_steps = max_steps
        self.max_allowed_loops = max_allowed_loops
        self.max_allowed_retries = max_allowed_retries

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        steps_count = len(trace.steps)
        loop_count, loop_details = _detect_loops(trace.steps)
        retry_count = _count_retries(trace.steps)

        steps_ok = steps_count <= self.max_steps
        loops_ok = loop_count <= self.max_allowed_loops
        retries_ok = retry_count <= self.max_allowed_retries

        passed = steps_ok and loops_ok and retries_ok

        # Efficiency score: penalties for loops, retries, excessive steps
        score = 1.0
        if not steps_ok:
            score -= min(0.4, (steps_count - self.max_steps) * 0.05)
        if loop_count > 0:
            score -= min(0.4, loop_count * 0.2)
        if retry_count > 0:
            score -= min(0.2, retry_count * 0.05)
        score = max(0.0, round(score, 4))

        reasons: list[str] = []
        if not steps_ok:
            reasons.append(f"Exceeded max steps ({steps_count} > {self.max_steps})")
        if not loops_ok:
            reasons.append(f"Detected {loop_count} execution loops")
        if not retries_ok:
            reasons.append(
                f"Exceeded allowed retries ({retry_count} > {self.max_allowed_retries})"
            )

        msg = (
            f"Trajectory valid: {steps_count} steps, {loop_count} loops, {retry_count} retries."
            if passed
            else f"Trajectory FAILED: {'; '.join(reasons)}."
        )

        evidence = {
            "total_steps": steps_count,
            "max_steps": self.max_steps,
            "loop_count": loop_count,
            "loops": loop_details,
            "retry_count": retry_count,
            "max_allowed_retries": self.max_allowed_retries,
        }

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=score,
            metric="trajectory_efficiency",
            threshold=1.0,
            confidence=1.0,
            message=msg,
            evidence=evidence,
            metadata={
                **self.metadata,
                "failure_category": "task" if not steps_ok else "tool",
                "failure_type": "task_incomplete"
                if loop_count > 0
                else "unnecessary_tool",
                **evidence,
            },
        )
