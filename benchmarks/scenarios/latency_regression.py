"""Scenario F — Latency Regression Benchmark Scenario.

Baseline execution:
  100 ms

Regressed execution:
  500 ms

Expectation:
  MaxLatency(250.0)

Framework must detect:
  Performance latency violation (FailureCategory.PERFORMANCE, FailureType.LATENCY)
"""

from typing import Any

from aireliability.core.models import TestCase, TraceStep
from aireliability.evaluation import MaxLatency


def get_scenario_f() -> tuple[TestCase, list[Any], list[TraceStep], list[TraceStep]]:
    """Return (test_case, evaluators, nominal_steps, faulty_steps)."""
    test_case = TestCase(
        id="scenario_f_latency_regression",
        name="scenario_f_latency_regression",
        input={"task": "fast_lookup"},
        expected_output="ok",
        expectations=["MaxLatency: 250.0"],
        tags=["benchmark", "latency_regression"],
    )

    evaluators = [
        MaxLatency(250.0),
    ]

    nominal_steps: list[TraceStep] = []
    faulty_steps: list[TraceStep] = []

    return test_case, evaluators, nominal_steps, faulty_steps


def agent_f_nominal(payload: dict[str, Any]) -> str:
    """Agent version within acceptable latency bounds."""
    return "ok"


def agent_f_faulty(payload: dict[str, Any]) -> str:
    """Agent version causing latency degradation."""
    return "ok"
