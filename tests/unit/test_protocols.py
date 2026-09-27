"""Unit tests for Phase 3 protocols and interfaces."""

from typing import Any

from aireliability.core.models import (
    EvaluationResult,
    ExecutionStatus,
    ExecutionTrace,
    StepType,
    TestCase,
    TraceStep,
)
from aireliability.core.protocols import (
    Evaluator,
    ExecutionAdapter,
    Expectation,
    Traceable,
)
from aireliability.evaluation.expectations import BaseExpectation


class MockEchoAgent:
    """A minimal mock agent for testing adapter execution."""

    def run(self, prompt: str) -> str:
        return f"Echo: {prompt}"


class MockExecutionAdapter:
    """Mock adapter conforming to ExecutionAdapter protocol."""

    def execute(self, agent: Any, test_case: TestCase) -> ExecutionTrace:
        output = agent.run(test_case.input)
        step = TraceStep(
            name="mock_execution",
            type=StepType.AGENT,
            input={"input": test_case.input},
            output={"output": output},
        )
        return ExecutionTrace(
            test_id=test_case.id,
            input=test_case.input,
            output=output,
            status=ExecutionStatus.COMPLETED,
            steps=[step],
        )


class MockEvaluator:
    """Mock evaluator conforming to Evaluator protocol."""

    name: str = "mock_output_evaluator"

    def evaluate(self, trace: ExecutionTrace, test_case: TestCase) -> EvaluationResult:
        passed = trace.output == test_case.expected_output
        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=1.0 if passed else 0.0,
            message="Output matched expected" if passed else "Output did not match",
            evidence={"expected": test_case.expected_output, "actual": trace.output},
        )


class MockLengthExpectation(BaseExpectation):
    """Mock expectation derived from BaseExpectation checking output length."""

    def __init__(self, min_len: int = 1) -> None:
        super().__init__(name="min_length_expectation", min_len=min_len)
        self.min_len = min_len

    def evaluate(self, trace: ExecutionTrace, test_case: TestCase) -> EvaluationResult:
        actual_len = len(str(trace.output or ""))
        passed = actual_len >= self.min_len
        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=1.0 if passed else 0.0,
            message=f"Length {actual_len} >= {self.min_len}",
            evidence={"actual_len": actual_len, "min_len": self.min_len},
        )


def test_mock_adapter_satisfies_protocol() -> None:
    """Test that a custom adapter satisfies the ExecutionAdapter protocol."""
    adapter = MockExecutionAdapter()
    assert isinstance(adapter, ExecutionAdapter)

    agent = MockEchoAgent()
    tc = TestCase(name="echo_test", input="hello", expected_output="Echo: hello")

    trace = adapter.execute(agent, tc)
    assert trace.test_id == tc.id
    assert trace.output == "Echo: hello"
    assert trace.status == ExecutionStatus.COMPLETED
    assert len(trace.steps) == 1
    assert trace.steps[0].type == StepType.AGENT


def test_mock_evaluator_satisfies_protocol() -> None:
    """Test that a custom evaluator satisfies the Evaluator protocol."""
    evaluator = MockEvaluator()
    assert isinstance(evaluator, Evaluator)
    assert evaluator.name == "mock_output_evaluator"

    tc = TestCase(name="eval_test", input="ping", expected_output="pong")
    passing_trace = ExecutionTrace(input="ping", output="pong")
    failing_trace = ExecutionTrace(input="ping", output="wrong")

    pass_result = evaluator.evaluate(passing_trace, tc)
    assert pass_result.passed is True
    assert pass_result.score == 1.0
    assert pass_result.evaluator == "mock_output_evaluator"

    fail_result = evaluator.evaluate(failing_trace, tc)
    assert fail_result.passed is False
    assert fail_result.score == 0.0


def test_base_expectation_and_protocol() -> None:
    """Test that BaseExpectation subclasses satisfy the Expectation protocol."""
    exp = MockLengthExpectation(min_len=5)
    assert isinstance(exp, Expectation)
    assert isinstance(exp, BaseExpectation)
    assert exp.name == "min_length_expectation"
    assert exp.metadata == {"min_len": 5}

    tc = TestCase(name="length_test", input="foo")
    short_trace = ExecutionTrace(output="hi")
    long_trace = ExecutionTrace(output="hello world")

    fail_res = exp.evaluate(short_trace, tc)
    assert fail_res.passed is False
    assert fail_res.score == 0.0

    pass_res = exp.evaluate(long_trace, tc)
    assert pass_res.passed is True
    assert pass_res.score == 1.0


def test_custom_class_structural_typing_without_subclassing() -> None:
    """Verify structural subtyping works for custom classes without inheritance."""

    class StandaloneExpectation:
        name = "standalone"

        def evaluate(
            self, trace: ExecutionTrace, test_case: TestCase
        ) -> EvaluationResult:
            return EvaluationResult(evaluator=self.name, passed=True)

    standalone = StandaloneExpectation()
    assert isinstance(standalone, Expectation)
    assert isinstance(standalone, Evaluator)


def test_traceable_protocol_satisfaction() -> None:
    """Verify Traceable protocol works as expected."""

    class ComponentWithTrace:
        def to_trace(self) -> ExecutionTrace:
            return ExecutionTrace(status=ExecutionStatus.COMPLETED)

    comp = ComponentWithTrace()
    assert isinstance(comp, Traceable)
    assert comp.to_trace().status == ExecutionStatus.COMPLETED
