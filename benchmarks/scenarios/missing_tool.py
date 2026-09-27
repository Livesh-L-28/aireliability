"""Scenario D — Missing Required Tool Benchmark Scenario.

Expected tool sequence:
  get_order
  cancel_order
  refund_order

Faulty execution:
  get_order
  cancel_order  (refund_order is missing)

Framework must detect:
  Missing required tool operation (FailureCategory.TOOL, FailureType.WRONG_TOOL)
"""

from typing import Any

from aireliability.core.models import StepType, TestCase, TraceStep
from aireliability.evaluation import ToolCalled


def get_scenario_d() -> tuple[TestCase, list[Any], list[TraceStep], list[TraceStep]]:
    """Return (test_case, evaluators, nominal_steps, faulty_steps)."""
    test_case = TestCase(
        id="scenario_d_missing_tool",
        name="scenario_d_missing_tool",
        input={"order_id": "ORD-4004"},
        expected_output="Refund processed",
        expectations=[
            "ToolCalled: get_order",
            "ToolCalled: cancel_order",
            "ToolCalled: refund_order",
        ],
        tags=["benchmark", "missing_tool"],
    )

    evaluators = [
        ToolCalled("get_order"),
        ToolCalled("cancel_order"),
        ToolCalled("refund_order"),
    ]

    nominal_steps = [
        TraceStep(type=StepType.TOOL, name="get_order", input={"order_id": "ORD-4004"}),
        TraceStep(
            type=StepType.TOOL, name="cancel_order", input={"order_id": "ORD-4004"}
        ),
        TraceStep(
            type=StepType.TOOL, name="refund_order", input={"order_id": "ORD-4004"}
        ),
    ]

    # Missing refund_order
    faulty_steps = [
        TraceStep(type=StepType.TOOL, name="get_order", input={"order_id": "ORD-4004"}),
        TraceStep(
            type=StepType.TOOL, name="cancel_order", input={"order_id": "ORD-4004"}
        ),
    ]

    return test_case, evaluators, nominal_steps, faulty_steps


def agent_d_nominal(payload: dict[str, Any]) -> str:
    """Agent version calling all three operations."""
    return "Refund processed"


def agent_d_faulty(payload: dict[str, Any]) -> str:
    """Agent version omitting refund_order."""
    return "Cancellation only completed"
