"""Scenario A — Tool Ordering Benchmark Scenario.

Expected tool invocation sequence:
  get_order -> cancel_order -> refund_order

Faulty execution sequence:
  get_order -> refund_order -> cancel_order

Framework must detect:
  FailureCategory.TOOL, FailureType.WRONG_ORDER
"""

from typing import Any

from aireliability.core.models import StepType, TestCase, TraceStep
from aireliability.evaluation import ToolOrder


def get_scenario_a() -> tuple[
    TestCase, list[ToolOrder], list[TraceStep], list[TraceStep]
]:
    """Return (test_case, evaluators, nominal_steps, faulty_steps)."""
    test_case = TestCase(
        id="scenario_a_tool_order",
        name="scenario_a_tool_order",
        input={"order_id": "ORD-1001", "action": "cancel_and_refund"},
        expected_output="Refund processed successfully",
        expectations=["ToolOrder: [get_order, cancel_order, refund_order]"],
        tags=["benchmark", "tool_order"],
    )

    evaluators = [
        ToolOrder(["get_order", "cancel_order", "refund_order"]),
    ]

    nominal_steps = [
        TraceStep(type=StepType.TOOL, name="get_order", input={"order_id": "ORD-1001"}),
        TraceStep(
            type=StepType.TOOL, name="cancel_order", input={"order_id": "ORD-1001"}
        ),
        TraceStep(
            type=StepType.TOOL, name="refund_order", input={"order_id": "ORD-1001"}
        ),
    ]

    # Inverted: refund_order before cancel_order
    faulty_steps = [
        TraceStep(type=StepType.TOOL, name="get_order", input={"order_id": "ORD-1001"}),
        TraceStep(
            type=StepType.TOOL, name="refund_order", input={"order_id": "ORD-1001"}
        ),
        TraceStep(
            type=StepType.TOOL, name="cancel_order", input={"order_id": "ORD-1001"}
        ),
    ]

    return test_case, evaluators, nominal_steps, faulty_steps


def agent_a_nominal(payload: dict[str, Any]) -> str:
    """Agent version with correct sequence."""
    return "Refund processed successfully"


def agent_a_faulty(payload: dict[str, Any]) -> str:
    """Agent version with wrong tool execution order."""
    return "Refund processed successfully"
