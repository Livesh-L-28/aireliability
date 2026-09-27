"""Scenario E — Output Regression Benchmark Scenario.

Expected output:
  "Your refund has been completed."

Faulty output:
  "Your order has been cancelled."

Framework must detect:
  Output regression (FailureCategory.TASK, FailureType.TASK_INCORRECT)
"""

from typing import Any

from aireliability.core.models import TestCase, TraceStep
from aireliability.evaluation import OutputContains, OutputEquals


def get_scenario_e() -> tuple[TestCase, list[Any], list[TraceStep], list[TraceStep]]:
    """Return (test_case, evaluators, nominal_steps, faulty_steps)."""
    test_case = TestCase(
        id="scenario_e_output_regression",
        name="scenario_e_output_regression",
        input={"prompt": "finalize refund for customer"},
        expected_output="Your refund has been completed.",
        expectations=["OutputEquals: Your refund has been completed."],
        tags=["benchmark", "output_regression"],
    )

    evaluators = [
        OutputEquals("Your refund has been completed."),
        OutputContains("refund has been completed"),
    ]

    nominal_steps: list[TraceStep] = []
    faulty_steps: list[TraceStep] = []

    return test_case, evaluators, nominal_steps, faulty_steps


def agent_e_nominal(payload: dict[str, Any]) -> str:
    """Agent version producing expected response."""
    return "Your refund has been completed."


def agent_e_faulty(payload: dict[str, Any]) -> str:
    """Agent version producing regressed response."""
    return "Your order has been cancelled."
