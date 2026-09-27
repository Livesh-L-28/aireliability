"""Scenario C — Wrong Tool Arguments Benchmark Scenario.

Expected tool arguments:
  refund_order(order_id="123")

Faulty execution:
  refund_order(order_id="456")

Framework must detect:
  FailureCategory.TOOL, FailureType.WRONG_ARGUMENT
"""

from typing import Any

from aireliability.core.models import StepType, TestCase, TraceStep
from aireliability.evaluation import ToolArguments


def get_scenario_c() -> tuple[TestCase, list[Any], list[TraceStep], list[TraceStep]]:
    """Return (test_case, evaluators, nominal_steps, faulty_steps)."""
    test_case = TestCase(
        id="scenario_c_wrong_arguments",
        name="scenario_c_wrong_arguments",
        input={"order_id": "123"},
        expected_output="Refund submitted",
        expectations=["ToolArguments: refund_order with order_id=123"],
        tags=["benchmark", "wrong_argument"],
    )

    evaluators = [
        ToolArguments("refund_order", {"order_id": "123"}),
    ]

    nominal_steps = [
        TraceStep(
            type=StepType.TOOL,
            name="refund_order",
            input={"order_id": "123"},
            output={"status": "queued"},
        ),
    ]

    faulty_steps = [
        TraceStep(
            type=StepType.TOOL,
            name="refund_order",
            input={"order_id": "456"},  # Wrong argument!
            output={"status": "queued"},
        ),
    ]

    return test_case, evaluators, nominal_steps, faulty_steps


def agent_c_nominal(payload: dict[str, Any]) -> str:
    """Agent version using correct order_id."""
    return "Refund submitted"


def agent_c_faulty(payload: dict[str, Any]) -> str:
    """Agent version passing incorrect order_id."""
    return "Refund submitted"
