"""Unit tests for Phase 15 Real Agent Integration Layer.

Covers:
1. CallableAdapter:
   - Successful execution with plain Python functions
   - Callable exceptions (propagation & suppression)
   - Input/output capture
   - Start / end timestamps & latency computation
   - Custom metadata handling
2. Tool events & representation:
   - ToolCallRecord serialization & to_trace_step()
   - Tool name, arguments, result, duration, status
   - ExecutionEvent handling
3. Adapter conversion:
   - Agent execution -> Adapter -> ExecutionTrace -> TraceStep
   - Direct functions, objects with .run() or .invoke()
   - Object history / events extraction
   - Custom step extractor hook
4. End-to-end workflow:
   - agent -> adapter -> trace -> evaluator -> failure -> regression
"""

from datetime import UTC, datetime
from typing import Any

import pytest

from aireliability.core.models import (
    ExecutionStatus,
    ExecutionTrace,
    StepType,
    TestCase,
    TraceStep,
)
from aireliability.evaluation.expectations import ToolOrder
from aireliability.execution.adapters import (
    AgentEventType,
    CallableAdapter,
    ExecutionEvent,
    ToolCallRecord,
)
from aireliability.execution.runner import ReliabilityRunner
from aireliability.regression import (
    BaselineManager,
    ComparisonStatus,
    RegressionGenerator,
)
from examples.local_agent import LocalSupportAgent

# ---------------------------------------------------------------------------
# 1. CallableAdapter Core Tests
# ---------------------------------------------------------------------------


def test_callable_adapter_successful_function():
    """Verify CallableAdapter executes a simple Python function."""

    def simple_agent(prompt: str) -> str:
        return f"Echo: {prompt}"

    adapter = CallableAdapter(agent=simple_agent)
    test_case = TestCase(name="echo_test", input="hello world")

    trace = adapter.execute(test_case=test_case)

    assert isinstance(trace, ExecutionTrace)
    assert trace.test_id == test_case.id
    assert trace.input == "hello world"
    assert trace.output == "Echo: hello world"
    assert trace.status == ExecutionStatus.COMPLETED
    assert trace.started_at is not None
    assert trace.completed_at is not None
    assert trace.completed_at >= trace.started_at
    assert trace.latency_ms is not None
    assert trace.latency_ms >= 0.0


def test_callable_adapter_positional_signature():
    """Verify CallableAdapter executes with adapter.execute(agent, test_case)."""

    def square_agent(val: int) -> int:
        return val * val

    adapter = CallableAdapter()
    test_case = TestCase(name="square_test", input=6)

    trace = adapter.execute(square_agent, test_case)

    assert trace.output == 36
    assert trace.status == ExecutionStatus.COMPLETED


def test_callable_adapter_exception_reraised_by_default():
    """Verify exceptions in agent are re-raised when suppress_exceptions=False."""

    def failing_agent(val: Any) -> Any:
        raise ValueError("Simulated agent runtime error")

    adapter = CallableAdapter(agent=failing_agent, suppress_exceptions=False)
    test_case = TestCase(name="fail_test", input="test")

    with pytest.raises(ValueError, match="Simulated agent runtime error") as exc_info:
        adapter.execute(test_case=test_case)

    # Execution trace is attached to the exception
    attached_trace = getattr(exc_info.value, "execution_trace", None)
    assert attached_trace is not None
    assert attached_trace.status == ExecutionStatus.FAILED
    assert attached_trace.output["error"] == "Simulated agent runtime error"


def test_callable_adapter_exception_suppressed():
    """Verify exceptions are captured in trace when suppress_exceptions=True."""

    def failing_agent(val: Any) -> Any:
        raise ZeroDivisionError("division by zero")

    adapter = CallableAdapter(agent=failing_agent, suppress_exceptions=True)
    test_case = TestCase(name="suppressed_fail_test", input=0)

    trace = adapter.execute(test_case=test_case)

    assert trace.status == ExecutionStatus.FAILED
    assert trace.output["error_type"] == "ZeroDivisionError"
    assert "division by zero" in trace.output["error"]


def test_callable_adapter_no_agent_provided_error():
    """Verify TypeError when no agent is provided."""
    adapter = CallableAdapter()
    test_case = TestCase(name="no_agent", input="x")

    with pytest.raises(TypeError, match="No agent or callable provided"):
        adapter.execute(test_case=test_case)


# ---------------------------------------------------------------------------
# 2. Tool Events and Representation Tests
# ---------------------------------------------------------------------------


def test_tool_call_record_to_trace_step():
    """Verify ToolCallRecord accurately translates to TraceStep."""
    start = datetime(2026, 9, 26, 10, 0, 0, tzinfo=UTC)
    end = datetime(2026, 9, 26, 10, 0, 0, 150000, tzinfo=UTC)

    record = ToolCallRecord(
        name="lookup_user",
        arguments={"user_id": 42},
        result={"name": "Alice", "role": "admin"},
        started_at=start,
        completed_at=end,
        duration_ms=150.0,
        status="completed",
        metadata={"cache_hit": True},
    )

    step = record.to_trace_step()

    assert isinstance(step, TraceStep)
    assert step.type == StepType.TOOL
    assert step.name == "lookup_user"
    assert step.input == {"user_id": 42}
    assert step.output == {"name": "Alice", "role": "admin"}
    assert step.started_at == start
    assert step.completed_at == end
    assert step.duration_ms == 150.0
    assert step.metadata["cache_hit"] is True
    assert step.metadata["status"] == "completed"


def test_execution_event_representation():
    """Verify ExecutionEvent captures agent transitions."""
    event = ExecutionEvent(
        type=AgentEventType.TOOL_CALL,
        name="execute_sql",
        payload={"arguments": {"query": "SELECT 1"}},
        metadata={"db": "postgres"},
    )

    assert event.type == AgentEventType.TOOL_CALL
    assert event.name == "execute_sql"
    assert event.payload["arguments"]["query"] == "SELECT 1"
    assert event.metadata["db"] == "postgres"


# ---------------------------------------------------------------------------
# 3. Adapter Conversion & Tool Extraction Tests
# ---------------------------------------------------------------------------


class MockAgentWithHistory:
    """Agent class maintaining tool history."""

    def __init__(self) -> None:
        self.tool_calls: list[ToolCallRecord] = []

    def run(self, query: str) -> str:
        self.tool_calls.append(
            ToolCallRecord(
                name="query_db",
                arguments={"query": query},
                result=["row1", "row2"],
                duration_ms=12.5,
            )
        )
        return "Query processed"


def test_adapter_extracts_tool_history_from_agent():
    """Verify CallableAdapter inspects agent attributes to populate trace steps."""
    agent = MockAgentWithHistory()
    adapter = CallableAdapter(agent=agent)
    test_case = TestCase(name="history_test", input="SELECT *")

    trace = adapter.execute(test_case=test_case)

    assert trace.status == ExecutionStatus.COMPLETED
    assert trace.output == "Query processed"
    assert len(trace.steps) == 1
    assert trace.steps[0].type == StepType.TOOL
    assert trace.steps[0].name == "query_db"
    assert trace.steps[0].input == {"query": "SELECT *"}
    assert trace.steps[0].output == ["row1", "row2"]


def test_adapter_extracts_steps_from_dict_return():
    """Verify CallableAdapter parses tool_calls dictionary envelopes."""

    def dict_agent(prompt: str) -> dict[str, Any]:
        return {
            "output": "Task completed successfully",
            "tool_calls": [
                {
                    "name": "fetch_doc",
                    "arguments": {"doc_id": "abc"},
                    "result": "content",
                }
            ],
        }

    adapter = CallableAdapter(agent=dict_agent)
    test_case = TestCase(name="envelope_test", input="get doc abc")

    trace = adapter.execute(test_case=test_case)

    assert trace.output == "Task completed successfully"
    assert len(trace.steps) == 1
    assert trace.steps[0].name == "fetch_doc"
    assert trace.steps[0].input == {"doc_id": "abc"}
    assert trace.steps[0].output == "content"


def test_adapter_custom_extract_hook():
    """Verify custom extract_steps_hook extracts arbitrary traces."""

    def custom_hook(agent: Any, result: Any) -> list[TraceStep]:
        return [
            TraceStep(
                name="custom_step",
                type=StepType.AGENT,
                input={"raw": result},
            )
        ]

    def agent(prompt: str) -> str:
        return f"result_for_{prompt}"

    adapter = CallableAdapter(agent=agent, extract_steps_hook=custom_hook)
    test_case = TestCase(name="hook_test", input="ping")

    trace = adapter.execute(test_case=test_case)

    assert len(trace.steps) == 1
    assert trace.steps[0].name == "custom_step"
    assert trace.steps[0].type == StepType.AGENT


# ---------------------------------------------------------------------------
# 4. End-to-End ReliabilityRunner and Regression Lifecycle
# ---------------------------------------------------------------------------


def test_real_agent_integration_e2e_lifecycle():
    """Verify the full workflow:
    agent -> adapter -> trace -> evaluator -> failure -> regression.
    """
    test = TestCase(
        id="support_e2e_tc",
        name="support_e2e",
        input="I need a refund for order 123.",
    )

    evaluators = [
        ToolOrder(
            expected_order=["get_order", "cancel_order", "refund_order"],
            exact_match=True,
        )
    ]

    # Step 1: Run Faulty Agent
    faulty_agent = LocalSupportAgent(mode="faulty")
    adapter = CallableAdapter(agent=faulty_agent)
    runner = ReliabilityRunner(
        agent=faulty_agent,
        adapter=adapter,
        evaluators=evaluators,
    )

    res_faulty = runner.run(test)
    assert not res_faulty.passed
    assert len(res_faulty.failures) == 1
    failure = res_faulty.failures[0]
    assert failure.category == "tool"
    assert failure.type == "wrong_order"
    assert failure.confidence == 1.0

    # Step 2: Generate Regression Test
    generator = RegressionGenerator()
    reg_test = generator.generate(failure=failure, test_case=test)
    assert reg_test.source_failure_id == failure.failure_id
    assert "type:wrong_order" in reg_test.test_case.tags

    # Baseline: initial faulty run
    baseline_mgr = BaselineManager()
    baseline_mgr.create_baseline([res_faulty], name="default")

    # Step 3: Run Fixed Agent
    fixed_agent = LocalSupportAgent(mode="nominal")
    fixed_adapter = CallableAdapter(agent=fixed_agent)
    fixed_runner = ReliabilityRunner(
        agent=fixed_agent,
        adapter=fixed_adapter,
        evaluators=evaluators,
    )

    res_fixed = fixed_runner.run(test)
    assert res_fixed.passed
    assert len(res_fixed.failures) == 0

    comp_fixed = baseline_mgr.compare_single(res_fixed, baseline_name="default")
    assert comp_fixed.status == ComparisonStatus.FIXED

    # Update baseline with passing run
    baseline_mgr.create_baseline([res_fixed], name="default")

    # Step 4: Re-introduce Faulty Agent
    res_reintroduced = runner.run(test)
    assert not res_reintroduced.passed

    comp_reintroduced = baseline_mgr.compare_single(
        res_reintroduced, baseline_name="default"
    )
    assert comp_reintroduced.status == ComparisonStatus.REGRESSION
