"""Unit tests for Phase 4 deterministic assertions."""

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from aireliability.core.models import (
    ExecutionStatus,
    ExecutionTrace,
    StepType,
    TestCase,
    TraceStep,
)
from aireliability.evaluation import (
    MaxCost,
    MaxLatency,
    OutputContains,
    OutputEquals,
    SchemaMatch,
    ToolArguments,
    ToolCalled,
    ToolNotCalled,
    ToolOrder,
)


class OrderModel(BaseModel):
    order_id: str
    status: str
    amount: float


# Helper functions to build test traces
def _create_trace(
    steps: list[TraceStep] | None = None,
    output: object = None,
    latency_ms: float | None = None,
    cost: float | None = None,
    status: ExecutionStatus = ExecutionStatus.COMPLETED,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> ExecutionTrace:
    return ExecutionTrace(
        steps=steps or [],
        output=output,
        latency_ms=latency_ms,
        cost=cost,
        status=status,
        started_at=started_at or datetime.now(UTC),
        completed_at=completed_at,
    )


def _tool_step(
    name: str, input_args: object = None, output: object = None
) -> TraceStep:
    return TraceStep(
        name=name,
        type=StepType.TOOL,
        input=input_args or {},
        output=output,
    )


# ==============================================================================
# 1. ToolCalled Tests
# ==============================================================================


def test_tool_called_passes_when_present() -> None:
    trace = _create_trace(
        steps=[_tool_step("get_order"), _tool_step("send_notification")]
    )
    assertion = ToolCalled("get_order")
    result = assertion.evaluate(trace)

    assert result.passed is True
    assert result.score == 1.0
    assert "Tool 'get_order' was called 1 time(s)" in result.message
    assert result.evidence["actual_calls"] == 1


def test_tool_called_fails_when_missing() -> None:
    trace = _create_trace(steps=[_tool_step("send_notification")])
    assertion = ToolCalled("get_order")
    result = assertion.evaluate(trace)

    assert result.passed is False
    assert result.score == 0.0
    assert "expected >= 1" in result.message
    assert result.evidence["actual_calls"] == 0


def test_tool_called_min_and_max_calls() -> None:
    trace = _create_trace(
        steps=[_tool_step("search"), _tool_step("search"), _tool_step("search")]
    )
    # Passed: exactly 3 calls with min=2, max=3
    assert ToolCalled("search", min_calls=2, max_calls=3).evaluate(trace).passed is True

    # Failed: 3 calls exceeds max 2
    res_max = ToolCalled("search", max_calls=2).evaluate(trace)
    assert res_max.passed is False
    assert res_max.score == 0.0

    # Failed: 3 calls below min 4
    res_min = ToolCalled("search", min_calls=4).evaluate(trace)
    assert res_min.passed is False


def test_tool_called_empty_trace() -> None:
    trace = _create_trace(steps=[])
    result = ToolCalled("any_tool").evaluate(trace)
    assert result.passed is False
    assert result.evidence["actual_calls"] == 0


# ==============================================================================
# 2. ToolNotCalled Tests
# ==============================================================================


def test_tool_not_called_passes_when_absent() -> None:
    trace = _create_trace(steps=[_tool_step("read_user")])
    assertion = ToolNotCalled("delete_database")
    result = assertion.evaluate(trace)

    assert result.passed is True
    assert result.score == 1.0
    assert result.evidence["actual_calls"] == 0


def test_tool_not_called_fails_when_called() -> None:
    trace = _create_trace(
        steps=[_tool_step("read_user"), _tool_step("delete_database")]
    )
    assertion = ToolNotCalled("delete_database")
    result = assertion.evaluate(trace)

    assert result.passed is False
    assert result.score == 0.0
    assert "was called 1 time(s)" in result.message
    assert result.evidence["actual_calls"] == 1


def test_tool_not_called_empty_trace() -> None:
    trace = _create_trace(steps=[])
    result = ToolNotCalled("delete_database").evaluate(trace)
    assert result.passed is True


# ==============================================================================
# 3. ToolOrder Tests
# ==============================================================================


def test_tool_order_subsequence_passing() -> None:
    # Subsequence passes with extra intermediate tools
    trace = _create_trace(
        steps=[
            _tool_step("get_order"),
            _tool_step("log_event"),  # extra tool
            _tool_step("cancel_order"),
            _tool_step("refund_order"),
        ]
    )
    assertion = ToolOrder(["get_order", "cancel_order", "refund_order"])
    result = assertion.evaluate(trace)

    assert result.passed is True
    assert result.score == 1.0


def test_tool_order_incorrect_ordering_evidence() -> None:
    trace = _create_trace(
        steps=[
            _tool_step("get_order"),
            _tool_step("refund_order"),
            _tool_step("cancel_order"),
        ]
    )
    assertion = ToolOrder(["get_order", "cancel_order", "refund_order"])
    result = assertion.evaluate(trace)

    assert result.passed is False
    assert result.score == 0.0
    # Useful evidence formatting as required in prompt
    assert "Expected tool order:" in result.evidence["formatted_comparison"]
    assert (
        "get_order → cancel_order → refund_order"
        in result.evidence["formatted_comparison"]
    )
    assert "Actual:" in result.evidence["formatted_comparison"]
    assert (
        "get_order → refund_order → cancel_order"
        in result.evidence["formatted_comparison"]
    )


def test_tool_order_exact_match_flag() -> None:
    trace_with_extra = _create_trace(
        steps=[
            _tool_step("get_order"),
            _tool_step("extra_log"),
            _tool_step("refund_order"),
        ]
    )
    exact_assertion = ToolOrder(
        ["get_order", "refund_order"],
        exact_match=True,
    )
    res = exact_assertion.evaluate(trace_with_extra)
    assert res.passed is False
    assert "did not match exactly" in res.message


def test_tool_order_missing_tool() -> None:
    trace = _create_trace(steps=[_tool_step("get_order"), _tool_step("cancel_order")])
    assertion = ToolOrder(["get_order", "cancel_order", "refund_order"])
    result = assertion.evaluate(trace)
    assert result.passed is False


def test_tool_order_empty_trace() -> None:
    trace = _create_trace(steps=[])
    assertion = ToolOrder(["get_order"])
    result = assertion.evaluate(trace)
    assert result.passed is False
    assert result.evidence["actual_order"] == []


# ==============================================================================
# 4. ToolArguments Tests
# ==============================================================================


def test_tool_arguments_subset_match_passes() -> None:
    args = {"order_id": "123", "amount": 50, "reason": "damaged"}
    trace = _create_trace(steps=[_tool_step("refund_order", args)])
    assertion = ToolArguments("refund_order", {"order_id": "123", "amount": 50})
    result = assertion.evaluate(trace)

    assert result.passed is True
    assert result.score == 1.0


def test_tool_arguments_mismatch_fails() -> None:
    trace = _create_trace(
        steps=[_tool_step("refund_order", {"order_id": "123", "amount": 25})]
    )
    assertion = ToolArguments("refund_order", {"order_id": "123", "amount": 50})
    result = assertion.evaluate(trace)

    assert result.passed is False
    assert result.score == 0.0
    assert "amount" in result.message


def test_tool_arguments_exact_match_mode() -> None:
    trace = _create_trace(
        steps=[
            _tool_step(
                "refund_order",
                {"order_id": "123", "amount": 50, "extra": "bonus"},
            )
        ]
    )
    exact_assertion = ToolArguments(
        "refund_order",
        {"order_id": "123", "amount": 50},
        match_subset=False,
    )
    result = exact_assertion.evaluate(trace)
    assert result.passed is False


def test_tool_arguments_match_modes() -> None:
    # 2 calls: first has wrong args, second has correct args
    trace = _create_trace(
        steps=[
            _tool_step("call_api", {"attempt": 1}),
            _tool_step("call_api", {"attempt": 2}),
        ]
    )
    # match_mode='any': should pass because attempt 2 matches
    any_check = ToolArguments("call_api", {"attempt": 2}, match_mode="any")
    assert any_check.evaluate(trace).passed is True

    # match_mode='first': should fail because attempt 1 != 2
    first_check = ToolArguments("call_api", {"attempt": 2}, match_mode="first")
    assert first_check.evaluate(trace).passed is False

    # match_mode='all': should fail
    all_check = ToolArguments("call_api", {"attempt": 2}, match_mode="all")
    assert all_check.evaluate(trace).passed is False


def test_tool_arguments_tool_not_called() -> None:
    trace = _create_trace(steps=[])
    result = ToolArguments("missing_tool", {"k": "v"}).evaluate(trace)
    assert result.passed is False
    assert "never called" in result.message


# ==============================================================================
# 5. OutputEquals Tests
# ==============================================================================


def test_output_equals_direct_value() -> None:
    trace = _create_trace(output={"status": "success", "id": 10})
    assertion = OutputEquals({"status": "success", "id": 10})
    assert assertion.evaluate(trace).passed is True

    fail_assertion = OutputEquals({"status": "failed"})
    res = fail_assertion.evaluate(trace)
    assert res.passed is False
    assert res.score == 0.0
    assert "Output mismatch" in res.message


def test_output_equals_using_test_case_expected() -> None:
    tc = TestCase(name="test", input="in", expected_output="expected output")
    matching_trace = _create_trace(output="expected output")
    mismatched_trace = _create_trace(output="other output")

    assertion = OutputEquals(use_test_case_expected=True)
    assert assertion.evaluate(matching_trace, tc).passed is True
    assert assertion.evaluate(mismatched_trace, tc).passed is False


# ==============================================================================
# 6. OutputContains Tests
# ==============================================================================


def test_output_contains_string() -> None:
    trace = _create_trace(output="Your order has been cancelled and refund completed.")
    assert OutputContains("refund completed").evaluate(trace).passed is True
    assert OutputContains("not found").evaluate(trace).passed is False


def test_output_contains_case_insensitive() -> None:
    trace = _create_trace(output="REFUND COMPLETED")
    assert (
        OutputContains("refund completed", case_sensitive=False).evaluate(trace).passed
        is True
    )
    assert (
        OutputContains("refund completed", case_sensitive=True).evaluate(trace).passed
        is False
    )


def test_output_contains_non_string_output() -> None:
    trace = _create_trace(output={"message": "refund completed", "code": 200})
    assert OutputContains("refund completed").evaluate(trace).passed is True


def test_output_contains_none_output() -> None:
    trace = _create_trace(output=None)
    result = OutputContains("anything").evaluate(trace)
    assert result.passed is False
    assert "output is None" in result.message


# ==============================================================================
# 7. SchemaMatch Tests
# ==============================================================================


def test_schema_match_pydantic_dict() -> None:
    trace = _create_trace(
        output={"order_id": "ORD-1", "status": "shipped", "amount": 99.9}
    )
    assertion = SchemaMatch(OrderModel)
    assert assertion.evaluate(trace).passed is True


def test_schema_match_pydantic_json_string() -> None:
    json_str = '{"order_id": "ORD-1", "status": "shipped", "amount": 99.9}'
    trace = _create_trace(output=json_str)
    assert SchemaMatch(OrderModel).evaluate(trace).passed is True


def test_schema_match_pydantic_invalid_data() -> None:
    # Missing order_id and invalid amount
    trace = _create_trace(output={"status": "shipped", "amount": "not_a_number"})
    result = SchemaMatch(OrderModel).evaluate(trace)
    assert result.passed is False
    assert result.score == 0.0
    assert "Schema validation failed" in result.message


def test_schema_match_dict_type_schema() -> None:
    schema = {"id": int, "name": str}
    valid_trace = _create_trace(output={"id": 1, "name": "alice"})
    invalid_trace = _create_trace(output={"id": "one", "name": "alice"})

    assert SchemaMatch(schema).evaluate(valid_trace).passed is True
    assert SchemaMatch(schema).evaluate(invalid_trace).passed is False


# ==============================================================================
# 8. MaxLatency Tests
# ==============================================================================


def test_max_latency_within_limit() -> None:
    trace = _create_trace(latency_ms=120.0)
    assertion = MaxLatency(max_latency_ms=200.0)
    res = assertion.evaluate(trace)
    assert res.passed is True
    assert res.score == 1.0


def test_max_latency_violation() -> None:
    trace = _create_trace(latency_ms=350.5)
    assertion = MaxLatency(max_latency_ms=200.0)
    res = assertion.evaluate(trace)
    assert res.passed is False
    assert res.score == 0.0
    assert "exceeded maximum allowed 200.00ms (by 150.50ms)" in res.message


def test_max_latency_computed_from_timestamps() -> None:
    start = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    end = start + timedelta(milliseconds=150)
    trace = ExecutionTrace(
        started_at=start,
        completed_at=end,
    )
    assert MaxLatency(200.0).evaluate(trace).passed is True
    assert MaxLatency(100.0).evaluate(trace).passed is False


def test_max_latency_missing_data() -> None:
    trace = ExecutionTrace()
    # If completed_at is None and latency_ms is None
    res = MaxLatency(100.0).evaluate(trace)
    assert res.passed is False
    assert "does not contain latency_ms" in res.message


# ==============================================================================
# 9. MaxCost Tests
# ==============================================================================


def test_max_cost_within_limit() -> None:
    trace = _create_trace(cost=0.0045)
    assertion = MaxCost(max_cost=0.01)
    res = assertion.evaluate(trace)
    assert res.passed is True
    assert res.score == 1.0


def test_max_cost_violation() -> None:
    trace = _create_trace(cost=0.025)
    assertion = MaxCost(max_cost=0.01)
    res = assertion.evaluate(trace)
    assert res.passed is False
    assert res.score == 0.0
    assert "Cost $0.0250 exceeded maximum allowed $0.0100" in res.message


def test_max_cost_missing_data() -> None:
    trace = _create_trace(cost=None)
    res = MaxCost(0.01).evaluate(trace)
    assert res.passed is False
    assert "does not contain cost data" in res.message


# ==============================================================================
# 10. Malformed and Edge-case Traces
# ==============================================================================


def test_malformed_trace_steps_with_non_tool_steps() -> None:
    trace = _create_trace(
        steps=[
            TraceStep(name="llm_call", type=StepType.LLM),
            TraceStep(name="memory_lookup", type=StepType.MEMORY),
            TraceStep(name="get_order", type=StepType.TOOL),
        ]
    )
    # Only TOOL steps are counted for ToolCalled and ToolOrder
    assert ToolCalled("llm_call").evaluate(trace).passed is False
    assert ToolCalled("get_order").evaluate(trace).passed is True
    assert ToolOrder(["get_order"]).evaluate(trace).passed is True


def test_trace_with_non_dict_step_input() -> None:
    step = TraceStep(
        name="bad_tool",
        type=StepType.TOOL,
        input="non_dict_string_input",
    )
    trace = _create_trace(steps=[step])
    res = ToolArguments("bad_tool", {"key": "val"}).evaluate(trace)
    assert res.passed is False
    assert "Actual input is not a dict" in res.message
