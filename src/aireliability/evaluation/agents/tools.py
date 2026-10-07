"""Tool execution metrics, error rates, and selection evaluation."""

from __future__ import annotations

from typing import Any

from aireliability.core.models import (
    EvaluationResult,
    ExecutionTrace,
    StepType,
    TestCase,
)
from aireliability.evaluation.expectations import BaseExpectation


class ToolUsageEvaluator(BaseExpectation):
    """Evaluates comprehensive tool usage: selection, arguments, error rate, and efficiency."""

    def __init__(
        self,
        *,
        required_tools: list[str] | None = None,
        forbidden_tools: list[str] | None = None,
        max_tool_error_rate: float = 0.0,
        expected_tool_order: list[str] | None = None,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(
            name=name or "ToolUsageEvaluator",
            required_tools=required_tools,
            forbidden_tools=forbidden_tools,
            max_tool_error_rate=max_tool_error_rate,
            **metadata,
        )
        self.required_tools = list(required_tools or [])
        self.forbidden_tools = list(forbidden_tools or [])
        self.max_tool_error_rate = max_tool_error_rate
        self.expected_tool_order = expected_tool_order

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        tool_steps = [s for s in trace.steps if s.type == StepType.TOOL]
        called_names = [s.name for s in tool_steps]

        # 1. Error rate calculation
        failed_calls = 0
        for s in tool_steps:
            is_err = (
                s.metadata.get("status") in ("failed", "error")
                or "error" in str(s.output).lower()
                or s.metadata.get("error") is not None
            )
            if is_err:
                failed_calls += 1

        total_calls = len(tool_steps)
        error_rate = (failed_calls / total_calls) if total_calls > 0 else 0.0
        success_rate = 1.0 - error_rate

        # 2. Required and forbidden tools
        missing_required = [t for t in self.required_tools if t not in called_names]
        called_forbidden = [t for t in self.forbidden_tools if t in called_names]

        # 3. Order check
        order_ok = True
        if self.expected_tool_order:
            it = iter(called_names)
            order_ok = all(t in it for t in self.expected_tool_order)

        # 4. Unnecessary tool calls (forbidden or unexpected if strict)
        unnecessary_calls = list(called_forbidden)

        passed = (
            error_rate <= self.max_tool_error_rate
            and len(missing_required) == 0
            and len(called_forbidden) == 0
            and order_ok
        )

        score = success_rate
        if missing_required:
            score -= 0.3 * (len(missing_required) / max(1, len(self.required_tools)))
        if called_forbidden:
            score -= 0.3
        if not order_ok:
            score -= 0.2
        score = max(0.0, round(score, 4))

        failures: list[str] = []
        if error_rate > self.max_tool_error_rate:
            failures.append(
                f"Tool error rate {error_rate:.2%} exceeded max {self.max_tool_error_rate:.2%}"
            )
        if missing_required:
            failures.append(f"Missing required tools: {missing_required}")
        if called_forbidden:
            failures.append(f"Called forbidden tools: {called_forbidden}")
        if not order_ok:
            failures.append("Tool sequence order violated")

        msg = (
            f"Tool usage passed: {total_calls} calls, success rate {success_rate:.2%}."
            if passed
            else f"Tool usage FAILED: {'; '.join(failures)}."
        )

        evidence = {
            "total_tool_calls": total_calls,
            "failed_calls": failed_calls,
            "tool_success_rate": round(success_rate, 4),
            "tool_error_rate": round(error_rate, 4),
            "called_tools": called_names,
            "missing_required": missing_required,
            "called_forbidden": called_forbidden,
            "order_ok": order_ok,
            "unnecessary_calls": unnecessary_calls,
        }

        # Failure category mapping
        fail_type = "wrong_tool"
        if error_rate > 0:
            fail_type = "wrong_argument"
        elif not order_ok:
            fail_type = "wrong_order"
        elif called_forbidden:
            fail_type = "unnecessary_tool"

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=score,
            metric="tool_success_rate",
            threshold=1.0 - self.max_tool_error_rate,
            confidence=1.0,
            message=msg,
            evidence=evidence,
            metadata={
                **self.metadata,
                "failure_category": "tool",
                "failure_type": fail_type,
                **evidence,
            },
        )
