"""Scenario B — Wrong Tool Benchmark Scenario.

Expected tool call:
  get_order

Faulty execution:
  delete_order

Framework must detect:
  FailureCategory.TOOL, FailureType.WRONG_TOOL
"""

from typing import Any

from aireliability.core.models import StepType, TestCase, TraceStep
from aireliability.evaluation import ToolCalled, ToolNotCalled


def get_scenario_b() -> tuple[TestCase, list[Any], list[TraceStep], list[TraceStep]]:
    """Return (test_case, evaluators, nominal_steps, faulty_steps)."""
    test_case = TestCase(
        id="scenario_b_wrong_tool",
        name="scenario_b_wrong_tool",
        input={"order_id": "ORD-2002", "query": "check status"},
        expected_output="Order details retrieved",
        expectations=["ToolCalled: get_order", "ToolNotCalled: delete_order"],
        tags=["benchmark", "wrong_tool"],
    )

    evaluators = [
        ToolCalled("get_order"),
        ToolNotCalled("delete_order"),
    ]

    nominal_steps = [
        TraceStep(type=StepType.TOOL, name="get_order", input={"order_id": "ORD-2002"}),
    ]

    faulty_steps = [
        TraceStep(
            type=StepType.TOOL, name="delete_order", input={"order_id": "ORD-2002"}
        ),
    ]

    return test_case, evaluators, nominal_steps, faulty_steps


def agent_b_nominal(payload: dict[str, Any]) -> str:
    """Agent version calling get_order."""
    return "Order details retrieved"


def agent_b_faulty(payload: dict[str, Any]) -> str:
    """Agent version mistakenly calling delete_order."""
    return "Order deleted"
