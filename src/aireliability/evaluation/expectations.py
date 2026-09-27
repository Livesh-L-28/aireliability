"""Deterministic expectations and assertions for execution trace evaluation.

This module provides deterministic, non-LLM assertions to evaluate AI execution traces:
- Tool usage (ToolCalled, ToolNotCalled, ToolOrder, ToolArguments)
- Output checks (OutputEquals, OutputContains, SchemaMatch)
- Resource constraints (MaxLatency, MaxCost)
"""

import json
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from aireliability.core.models import (
    EvaluationResult,
    ExecutionTrace,
    StepType,
    TestCase,
    TraceStep,
)
from aireliability.core.protocols import Expectation


class BaseExpectation(ABC):
    """Abstract base class for deterministic expectations.

    Subclasses must define a name and implement `evaluate`.
    Provides a standardized foundation for building custom deterministic assertions
    against execution traces and test cases.
    """

    def __init__(self, name: str | None = None, **metadata: Any) -> None:
        self._name = name or self.__class__.__name__
        self.metadata = metadata

    @property
    def name(self) -> str:
        """Name of the expectation."""
        return self._name

    @abstractmethod
    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        """Evaluate the execution trace against the test case specification.

        Args:
            trace: The execution trace to evaluate.
            test_case: Optional test case specification containing input and expected
                criteria.

        Returns:
            An EvaluationResult capturing pass/fail status, score, message,
            and metadata.
        """
        ...


def _get_tool_steps(trace: ExecutionTrace) -> list[TraceStep]:
    """Extract all tool execution steps from a trace."""
    return [step for step in trace.steps if step.type == StepType.TOOL]


def _get_tool_names(trace: ExecutionTrace) -> list[str]:
    """Extract tool names in order from a trace."""
    return [step.name for step in trace.steps if step.type == StepType.TOOL]


class ToolCalled(BaseExpectation):
    """Asserts that a specific tool was called during execution."""

    def __init__(
        self,
        tool_name: str,
        *,
        min_calls: int = 1,
        max_calls: int | None = None,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(
            name=name or f"ToolCalled({tool_name})",
            tool_name=tool_name,
            min_calls=min_calls,
            max_calls=max_calls,
            **metadata,
        )
        self.tool_name = tool_name
        self.min_calls = min_calls
        self.max_calls = max_calls

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        tool_names = _get_tool_names(trace)
        actual_calls = tool_names.count(self.tool_name)

        passed = actual_calls >= self.min_calls
        if self.max_calls is not None:
            passed = passed and actual_calls <= self.max_calls

        if passed:
            msg = (
                f"Tool '{self.tool_name}' was called {actual_calls} time(s) "
                f"(expected >= {self.min_calls}"
                + (f" and <= {self.max_calls})" if self.max_calls is not None else ")")
            )
        else:
            msg = (
                f"Tool '{self.tool_name}' called {actual_calls} time(s); "
                f"expected >= {self.min_calls}"
                + (f" and <= {self.max_calls}" if self.max_calls is not None else "")
            )

        evidence = {
            "expected_tool": self.tool_name,
            "min_calls": self.min_calls,
            "max_calls": self.max_calls,
            "actual_calls": actual_calls,
            "called_tools": tool_names,
        }

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=1.0 if passed else 0.0,
            message=msg,
            evidence=evidence,
            metadata=self.metadata,
        )


class ToolNotCalled(BaseExpectation):
    """Asserts that a specific tool was never called during execution."""

    def __init__(
        self,
        tool_name: str,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(
            name=name or f"ToolNotCalled({tool_name})",
            tool_name=tool_name,
            **metadata,
        )
        self.tool_name = tool_name

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        tool_names = _get_tool_names(trace)
        actual_calls = tool_names.count(self.tool_name)
        passed = actual_calls == 0

        if passed:
            msg = f"Tool '{self.tool_name}' was not called as expected."
        else:
            msg = (
                f"Tool '{self.tool_name}' was called {actual_calls} time(s) "
                "but was expected not to be called."
            )

        evidence = {
            "forbidden_tool": self.tool_name,
            "actual_calls": actual_calls,
            "called_tools": tool_names,
        }

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=1.0 if passed else 0.0,
            message=msg,
            evidence=evidence,
            metadata=self.metadata,
        )


class ToolOrder(BaseExpectation):
    """Asserts that tools were called in an expected sequence.

    By default, exact_match=False checks that expected tools appear in the specified
    order as a subsequence (other intermediate tools may be called).
    When exact_match=True, the sequence of all called tools must match exactly.
    """

    def __init__(
        self,
        expected_order: list[str],
        *,
        exact_match: bool = False,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(
            name=name or "ToolOrder",
            expected_order=expected_order,
            exact_match=exact_match,
            **metadata,
        )
        self.expected_order = expected_order
        self.exact_match = exact_match

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        actual_tools = _get_tool_names(trace)
        expected_str = " → ".join(self.expected_order) if self.expected_order else "[]"
        actual_str = " → ".join(actual_tools) if actual_tools else "[]"

        if self.exact_match:
            passed = actual_tools == self.expected_order
            mismatch_reason = (
                "Exact tool sequence matched."
                if passed
                else f"Tool sequence did not match exactly.\n"
                f"Expected tool order: {expected_str}\n"
                f"Actual: {actual_str}"
            )
        else:
            # Subsequence check
            it = iter(actual_tools)
            passed = all(item in it for item in self.expected_order)
            mismatch_reason = (
                "Tool subsequence matched."
                if passed
                else f"Expected tool order subsequence not satisfied.\n"
                f"Expected tool order: {expected_str}\n"
                f"Actual: {actual_str}"
            )

        evidence = {
            "expected_order": self.expected_order,
            "actual_order": actual_tools,
            "exact_match": self.exact_match,
            "formatted_comparison": (
                f"Expected tool order:\n{expected_str}\n\nActual:\n{actual_str}"
            ),
        }

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=1.0 if passed else 0.0,
            message=mismatch_reason,
            evidence=evidence,
            metadata=self.metadata,
        )


class ToolArguments(BaseExpectation):
    """Asserts that a tool was called with expected arguments.

    Matches either exact dictionary equality or subset matching (match_subset=True).
    Can check arguments on the first call, all calls, or any call (match_mode='any').
    """

    def __init__(
        self,
        tool_name: str,
        expected_args: dict[str, Any],
        *,
        match_subset: bool = True,
        match_mode: str = "any",  # "any", "all", "first"
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(
            name=name or f"ToolArguments({tool_name})",
            tool_name=tool_name,
            expected_args=expected_args,
            match_subset=match_subset,
            match_mode=match_mode,
            **metadata,
        )
        self.tool_name = tool_name
        self.expected_args = expected_args
        self.match_subset = match_subset
        self.match_mode = match_mode

    def _matches_args(self, actual_input: Any) -> tuple[bool, str]:
        if not isinstance(actual_input, dict):
            return False, f"Actual input is not a dict: {type(actual_input).__name__}"

        if self.match_subset:
            for k, expected_v in self.expected_args.items():
                if k not in actual_input:
                    return False, f"Missing key '{k}' in tool arguments."
                if actual_input[k] != expected_v:
                    return (
                        False,
                        f"Argument '{k}' value mismatch: "
                        f"expected {expected_v!r}, got {actual_input[k]!r}",
                    )
            return True, "All expected argument keys and values matched."

        if actual_input == self.expected_args:
            return True, "Exact argument dictionary matched."
        return (
            False,
            f"Arguments mismatch: expected {self.expected_args!r}, "
            f"got {actual_input!r}",
        )

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        matching_steps = [s for s in _get_tool_steps(trace) if s.name == self.tool_name]

        if not matching_steps:
            return EvaluationResult(
                evaluator=self.name,
                passed=False,
                score=0.0,
                message=f"Tool '{self.tool_name}' was never called.",
                evidence={
                    "tool_name": self.tool_name,
                    "expected_args": self.expected_args,
                    "actual_calls": 0,
                },
                metadata=self.metadata,
            )

        step_evals: list[dict[str, Any]] = []
        for idx, step in enumerate(matching_steps):
            matched, reason = self._matches_args(step.input)
            step_evals.append(
                {
                    "call_index": idx,
                    "step_id": step.id,
                    "input": step.input,
                    "matched": matched,
                    "reason": reason,
                }
            )

        if self.match_mode == "first":
            passed = step_evals[0]["matched"]
            message = step_evals[0]["reason"]
        elif self.match_mode == "all":
            passed = all(ev["matched"] for ev in step_evals)
            failures = [ev for ev in step_evals if not ev["matched"]]
            if passed:
                message = (
                    f"All {len(step_evals)} call(s) to '{self.tool_name}' "
                    f"matched arguments."
                )
            else:
                message = (
                    f"{len(failures)} of {len(step_evals)} call(s) to "
                    f"'{self.tool_name}' failed argument checks: "
                    f"{failures[0]['reason']}"
                )
        else:  # "any"
            passed = any(ev["matched"] for ev in step_evals)
            if passed:
                message = f"Found a call to '{self.tool_name}' matching arguments."
            else:
                message = (
                    f"None of the {len(step_evals)} call(s) to '{self.tool_name}' "
                    f"matched arguments: {step_evals[0]['reason']}"
                )

        evidence = {
            "tool_name": self.tool_name,
            "expected_args": self.expected_args,
            "match_subset": self.match_subset,
            "match_mode": self.match_mode,
            "calls": step_evals,
        }

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=1.0 if passed else 0.0,
            message=message,
            evidence=evidence,
            metadata=self.metadata,
        )


class OutputEquals(BaseExpectation):
    """Asserts that the execution trace output exactly equals expected value."""

    def __init__(
        self,
        expected: Any = None,
        *,
        use_test_case_expected: bool = False,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(
            name=name or "OutputEquals",
            expected=expected,
            use_test_case_expected=use_test_case_expected,
            **metadata,
        )
        self.expected = expected
        self.use_test_case_expected = use_test_case_expected

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        expected = self.expected
        if (
            (self.use_test_case_expected or expected is None)
            and test_case is not None
            and test_case.expected_output is not None
        ):
            expected = test_case.expected_output

        actual = trace.output
        passed = actual == expected

        if passed:
            msg = f"Output matched expected value: {expected!r}"
        else:
            msg = f"Output mismatch.\nExpected: {expected!r}\nActual:   {actual!r}"

        evidence = {
            "expected": expected,
            "actual": actual,
        }

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=1.0 if passed else 0.0,
            message=msg,
            evidence=evidence,
            metadata=self.metadata,
        )


class OutputContains(BaseExpectation):
    """Asserts that the execution trace output contains a substring or item."""

    def __init__(
        self,
        expected_substring: str,
        *,
        case_sensitive: bool = True,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(
            name=name or f"OutputContains({expected_substring!r})",
            expected_substring=expected_substring,
            case_sensitive=case_sensitive,
            **metadata,
        )
        self.expected_substring = expected_substring
        self.case_sensitive = case_sensitive

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        if trace.output is None:
            return EvaluationResult(
                evaluator=self.name,
                passed=False,
                score=0.0,
                message=(
                    f"Trace output is None; expected to contain "
                    f"{self.expected_substring!r}"
                ),
                evidence={
                    "expected_substring": self.expected_substring,
                    "actual_output": None,
                },
                metadata=self.metadata,
            )

        actual_str = (
            trace.output
            if isinstance(trace.output, str)
            else json.dumps(trace.output, default=str)
        )

        if self.case_sensitive:
            passed = self.expected_substring in actual_str
        else:
            passed = self.expected_substring.lower() in actual_str.lower()

        if passed:
            msg = f"Output contains expected substring: {self.expected_substring!r}"
        else:
            msg = (
                f"Output does not contain expected substring.\n"
                f"Expected substring: {self.expected_substring!r}\n"
                f"Actual output:      {actual_str!r}"
            )

        evidence = {
            "expected_substring": self.expected_substring,
            "actual_output": actual_str,
            "case_sensitive": self.case_sensitive,
        }

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=1.0 if passed else 0.0,
            message=msg,
            evidence=evidence,
            metadata=self.metadata,
        )


class SchemaMatch(BaseExpectation):
    """Asserts that the trace output conforms to a Pydantic model or schema."""

    def __init__(
        self,
        schema: type[BaseModel] | type | dict[str, Any],
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        schema_name = getattr(schema, "__name__", str(schema))
        super().__init__(
            name=name or f"SchemaMatch({schema_name})",
            schema_name=schema_name,
            **metadata,
        )
        self.schema = schema

    def _validate(self, output: Any) -> tuple[bool, str, Any]:
        if isinstance(self.schema, type) and issubclass(self.schema, BaseModel):
            try:
                if isinstance(output, str):
                    self.schema.model_validate_json(output)
                elif isinstance(output, dict):
                    self.schema.model_validate(output)
                elif isinstance(output, self.schema):
                    return True, "Output is already a validated model instance.", None
                else:
                    return (
                        False,
                        f"Expected dict or json string for {self.schema.__name__}, "
                        f"got {type(output).__name__}",
                        None,
                    )
                return True, f"Output conforms to {self.schema.__name__} schema.", None
            except Exception as e:
                return (
                    False,
                    f"Schema validation failed for {self.schema.__name__}: {e}",
                    str(e),
                )

        if isinstance(self.schema, dict):
            # Dict type annotations check
            if not isinstance(output, dict):
                return False, f"Expected dictionary, got {type(output).__name__}", None
            for key, expected_type in self.schema.items():
                if key not in output:
                    return False, f"Missing required key: '{key}'", None
                if isinstance(expected_type, type) and not isinstance(
                    output[key], expected_type
                ):
                    return (
                        False,
                        f"Key '{key}' expected type {expected_type.__name__}, "
                        f"got {type(output[key]).__name__}",
                        None,
                    )
            return True, "Output matched dictionary schema.", None

        if isinstance(self.schema, type):
            if isinstance(output, self.schema):
                return True, f"Output is of type {self.schema.__name__}.", None
            return (
                False,
                f"Output expected type {self.schema.__name__}, "
                f"got {type(output).__name__}",
                None,
            )

        return False, f"Unsupported schema type: {type(self.schema).__name__}", None

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        passed, msg, err_details = self._validate(trace.output)
        evidence = {
            "schema": getattr(self.schema, "__name__", str(self.schema)),
            "actual_output": trace.output,
            "actual_type": type(trace.output).__name__,
            "validation_error": err_details,
        }

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=1.0 if passed else 0.0,
            message=msg,
            evidence=evidence,
            metadata=self.metadata,
        )


class MaxLatency(BaseExpectation):
    """Asserts that trace latency does not exceed a specified threshold in ms."""

    def __init__(
        self,
        max_latency_ms: float,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(
            name=name or f"MaxLatency({max_latency_ms}ms)",
            max_latency_ms=max_latency_ms,
            **metadata,
        )
        self.max_latency_ms = max_latency_ms

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        latency = trace.latency_ms

        if (
            latency is None
            and trace.completed_at is not None
            and trace.started_at is not None
        ):
            latency = (trace.completed_at - trace.started_at).total_seconds() * 1000.0

        if latency is None:
            return EvaluationResult(
                evaluator=self.name,
                passed=False,
                score=0.0,
                message="Trace does not contain latency_ms or completion timestamps.",
                evidence={
                    "max_latency_ms": self.max_latency_ms,
                    "actual_latency_ms": None,
                },
                metadata=self.metadata,
            )

        passed = latency <= self.max_latency_ms

        if passed:
            msg = (
                f"Latency {latency:.2f}ms is within the maximum allowed "
                f"{self.max_latency_ms:.2f}ms."
            )
        else:
            msg = (
                f"Latency {latency:.2f}ms exceeded maximum allowed "
                f"{self.max_latency_ms:.2f}ms "
                f"(by {latency - self.max_latency_ms:.2f}ms)."
            )

        evidence = {
            "max_latency_ms": self.max_latency_ms,
            "actual_latency_ms": latency,
            "diff_ms": latency - self.max_latency_ms,
        }

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=1.0 if passed else 0.0,
            message=msg,
            evidence=evidence,
            metadata=self.metadata,
        )


class MaxCost(BaseExpectation):
    """Asserts that execution trace cost does not exceed a specified threshold."""

    def __init__(
        self,
        max_cost: float,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(
            name=name or f"MaxCost(${max_cost:.4f})",
            max_cost=max_cost,
            **metadata,
        )
        self.max_cost = max_cost

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        cost = trace.cost

        if cost is None:
            return EvaluationResult(
                evaluator=self.name,
                passed=False,
                score=0.0,
                message="Trace does not contain cost data.",
                evidence={
                    "max_cost": self.max_cost,
                    "actual_cost": None,
                },
                metadata=self.metadata,
            )

        passed = cost <= self.max_cost

        if passed:
            msg = (
                f"Cost ${cost:.4f} is within the maximum allowed ${self.max_cost:.4f}."
            )
        else:
            msg = (
                f"Cost ${cost:.4f} exceeded maximum allowed "
                f"${self.max_cost:.4f} (by ${cost - self.max_cost:.4f})."
            )

        evidence = {
            "max_cost": self.max_cost,
            "actual_cost": cost,
            "diff": cost - self.max_cost,
        }

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=1.0 if passed else 0.0,
            message=msg,
            evidence=evidence,
            metadata=self.metadata,
        )


__all__ = [
    "BaseExpectation",
    "Expectation",
    "MaxCost",
    "MaxLatency",
    "OutputContains",
    "OutputEquals",
    "SchemaMatch",
    "ToolArguments",
    "ToolCalled",
    "ToolNotCalled",
    "ToolOrder",
]
