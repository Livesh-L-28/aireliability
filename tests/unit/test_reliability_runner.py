"""Unit tests for Phase 5 ReliabilityRunner execution engine."""

import time
from typing import Any

import pytest

from aireliability.core.models import (
    EvaluationResult,
    ExecutionStatus,
    ExecutionTrace,
    RunResult,
    StepType,
    TestCase,
    TraceStep,
)
from aireliability.evaluation import (
    MaxLatency,
    OutputContains,
    OutputEquals,
    ToolCalled,
)
from aireliability.execution import ReliabilityRunner


def test_successful_execution_callable_agent() -> None:
    """Test standard execution with a simple Python callable agent."""

    def simple_agent(prompt: str) -> str:
        return f"Hello, {prompt}!"

    runner = ReliabilityRunner(
        agent=simple_agent,
        evaluators=[OutputContains("Hello, Alice!"), OutputEquals("Hello, Alice!")],
    )
    test = TestCase(
        name="greeting_test", input="Alice", expected_output="Hello, Alice!"
    )
    result = runner.run(test)

    assert isinstance(result, RunResult)
    assert result.passed is True
    assert result.trace.status == ExecutionStatus.COMPLETED
    assert result.trace.input == "Alice"
    assert result.trace.output == "Hello, Alice!"
    assert result.trace.started_at is not None
    assert result.trace.completed_at is not None
    assert result.trace.latency_ms is not None
    assert result.trace.latency_ms >= 0.0
    assert len(result.evaluations) == 2
    assert all(ev.passed for ev in result.evaluations)
    assert len(result.failures) == 0


def test_successful_execution_with_object_agent_having_run() -> None:
    """Test execution with an agent object having a .run() method."""

    class ClassBasedAgent:
        def run(self, user_input: str) -> dict[str, str]:
            return {"reply": f"Processed: {user_input}"}

    runner = ReliabilityRunner(agent=ClassBasedAgent())
    test = TestCase(name="obj_agent_test", input="sample_data")
    result = runner.run(test)

    assert result.passed is True
    assert result.trace.output == {"reply": "Processed: sample_data"}
    assert result.trace.status == ExecutionStatus.COMPLETED


def test_failed_evaluation_marks_run_as_failed() -> None:
    """Test that a failing evaluator properly marks RunResult.passed as False."""

    def echo_agent(text: str) -> str:
        return "incorrect_response"

    runner = ReliabilityRunner(
        agent=echo_agent,
        evaluators=[OutputEquals("expected_response")],
    )
    test = TestCase(name="failing_eval_test", input="ping")
    result = runner.run(test)

    assert result.passed is False
    assert len(result.evaluations) == 1
    assert result.evaluations[0].passed is False
    assert len(result.failures) == 1
    assert result.failures[0].category == "task"
    assert result.failures[0].type == "task_incorrect"


def test_multiple_evaluators_execution() -> None:
    """Test running multiple evaluators combining tool checks, output, and latency."""

    def math_agent(expr: str) -> str:
        return "Result is 42"

    runner = ReliabilityRunner(
        agent=math_agent,
        evaluators=[
            OutputContains("42"),
            OutputContains("Result"),
            MaxLatency(max_latency_ms=5000.0),
            ToolCalled("missing_tool"),  # This will fail
        ],
    )
    test = TestCase(name="math_test", input="6 * 7")
    result = runner.run(test)

    assert len(result.evaluations) == 4
    # First 3 evaluators pass, 4th fails
    assert result.evaluations[0].passed is True
    assert result.evaluations[1].passed is True
    assert result.evaluations[2].passed is True
    assert result.evaluations[3].passed is False
    assert result.passed is False
    assert len(result.failures) == 1
    assert result.failures[0].category == "tool"
    assert result.failures[0].type == "wrong_tool"


def test_exception_handling_re_raises_by_default() -> None:
    """Test that agent exceptions are captured in trace, metadata, and re-raised."""

    def broken_agent(inp: Any) -> Any:
        raise ValueError("Simulated agent runtime crash")

    runner = ReliabilityRunner(
        agent=broken_agent,
        evaluators=[OutputContains("anything")],
        suppress_agent_exceptions=False,
    )
    test = TestCase(name="crash_test", input="explode")

    with pytest.raises(ValueError, match="Simulated agent runtime crash") as exc_info:
        runner.run(test)

    # Check attached RunResult on the exception
    attached_result: RunResult = exc_info.value.run_result  # type: ignore[attr-defined]
    assert attached_result.passed is False
    assert attached_result.trace.status == ExecutionStatus.FAILED
    assert attached_result.trace.output == {
        "error": "Simulated agent runtime crash",
        "error_type": "ValueError",
    }
    assert attached_result.trace.metadata["error_details"] == (
        "Simulated agent runtime crash"
    )
    assert len(attached_result.failures) >= 1
    assert attached_result.failures[0].category == "task"
    assert attached_result.failures[0].type == "task_incomplete"


def test_exception_handling_with_suppression() -> None:
    """Test running with suppress_agent_exceptions=True safely returns RunResult."""

    def broken_agent(inp: Any) -> Any:
        raise RuntimeError("Agent failure")

    runner = ReliabilityRunner(
        agent=broken_agent,
        evaluators=[],
        suppress_agent_exceptions=True,
    )
    test = TestCase(name="suppressed_crash_test", input="data")
    result = runner.run(test)

    assert result.passed is False
    assert result.trace.status == ExecutionStatus.FAILED
    assert len(result.failures) == 1
    assert result.failures[0].category == "task"
    assert result.failures[0].type == "task_incomplete"


def test_evaluator_internal_exception_captured_gracefully() -> None:
    """Test evaluator exceptions are caught and recorded as failed evaluations."""

    class BrokenEvaluator:
        name = "exploding_evaluator"

        def evaluate(
            self, trace: ExecutionTrace, test_case: TestCase
        ) -> EvaluationResult:
            raise KeyError("Malformed evaluator bug")

        def __getattr__(self, name: str) -> Any:
            raise AttributeError(name)

    runner = ReliabilityRunner(
        agent=lambda x: "ok",
        evaluators=[BrokenEvaluator()],
    )
    test = TestCase(name="broken_eval_test", input="in")
    result = runner.run(test)

    assert result.passed is False
    assert len(result.evaluations) == 1
    assert result.evaluations[0].passed is False
    assert "Evaluator error" in result.evaluations[0].message
    assert len(result.failures) == 1


def test_latency_captured_accurately() -> None:
    """Test that runner captures positive latency for executed agents."""

    def slow_agent(x: int) -> int:
        time.sleep(0.02)  # sleep ~20ms
        return x * 2

    runner = ReliabilityRunner(agent=slow_agent)
    test = TestCase(name="latency_test", input=5)
    result = runner.run(test)

    assert result.trace.latency_ms is not None
    assert result.trace.latency_ms >= 15.0  # at least ~15ms


def test_trace_steps_supplied_by_caller_or_adapter() -> None:
    """Test that explicit trace steps can be supplied to runner."""
    step = TraceStep(
        name="get_order",
        type=StepType.TOOL,
        input={"order_id": "100"},
        output={"status": "confirmed"},
    )

    def simple_agent(x: str) -> str:
        return "order confirmed"

    runner = ReliabilityRunner(
        agent=simple_agent,
        evaluators=[ToolCalled("get_order")],
    )
    test = TestCase(name="steps_test", input="order_100")
    result = runner.run(test, steps=[step])

    assert result.passed is True
    assert len(result.trace.steps) == 1
    assert result.trace.steps[0].name == "get_order"
    assert result.evaluations[0].passed is True


def test_custom_execution_adapter_integration() -> None:
    """Test that custom ExecutionAdapter works smoothly with ReliabilityRunner."""

    class MockAdapter:
        def execute(self, agent: Any, test_case: TestCase) -> ExecutionTrace:
            out = agent(test_case.input)
            tool_step = TraceStep(
                name="adapter_tool",
                type=StepType.TOOL,
                input={"val": test_case.input},
            )
            return ExecutionTrace(
                test_id=test_case.id,
                input=test_case.input,
                output=out,
                status=ExecutionStatus.COMPLETED,
                steps=[tool_step],
            )

    runner = ReliabilityRunner(
        agent=lambda x: f"transformed_{x}",
        adapter=MockAdapter(),
        evaluators=[ToolCalled("adapter_tool")],
    )
    test = TestCase(name="adapter_test", input="val1")
    result = runner.run(test)

    assert result.passed is True
    assert result.trace.output == "transformed_val1"
    assert len(result.trace.steps) == 1
    assert result.trace.steps[0].name == "adapter_tool"
    assert result.evaluations[0].passed is True
