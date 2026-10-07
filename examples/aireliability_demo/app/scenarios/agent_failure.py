"""Agent failure scenarios (runaway loops, wrong tool selection, tool failure)."""

from __future__ import annotations

from typing import Any

from aireliability.core.models import FailureReport, FailureSeverity
from aireliability_demo.app.agent.agent import ControlledAgent


def run_agent_failure_scenario(scenario: str = "RUNAWAY_LOOP") -> dict[str, Any]:
    """Execute controlled autonomous agent failure trajectory."""
    agent = ControlledAgent("FailingDemoAgent")
    agent_run = agent.execute_task(
        "Execute automated status inspection and calculation.",
        scenario=scenario,
    )

    failures: list[FailureReport] = []
    sc_upper = scenario.upper()

    if sc_upper == "RUNAWAY_LOOP":
        failures.append(
            FailureReport(
                failure_id="fail_agent_runaway_01",
                trace_id="tr_agent_runaway",
                category="agent",
                type="runaway_loop",
                message="Trajectory exceeded identical step repetition limit (4 identical calls)",
                severity=FailureSeverity.CRITICAL,
                metadata={"component": "agent:loop_detector"},
            )
        )
    elif sc_upper == "WRONG_TOOL":
        failures.append(
            FailureReport(
                failure_id="fail_agent_tool_01",
                trace_id="tr_agent_tool",
                category="agent",
                type="tool_selection_error",
                message="Agent selected information search tool instead of arithmetic calculator",
                severity=FailureSeverity.HIGH,
                metadata={"component": "agent:tool_evaluator"},
            )
        )
    elif sc_upper == "TOOL_FAILURE":
        failures.append(
            FailureReport(
                failure_id="fail_agent_exec_01",
                trace_id="tr_agent_exec",
                category="agent",
                type="tool_execution_error",
                message="Tool raised error when attempting to lookup non-existent resource",
                severity=FailureSeverity.HIGH,
                metadata={"component": "agent:tool_executor"},
            )
        )
    elif sc_upper == "GOAL_FAILURE":
        failures.append(
            FailureReport(
                failure_id="fail_agent_goal_01",
                trace_id="tr_agent_goal",
                category="agent",
                type="goal_criteria_unmet",
                message="Final response terminated prematurely without satisfying mandatory goals",
                severity=FailureSeverity.CRITICAL,
                metadata={"component": "agent:goal_verifier"},
            )
        )

    return {
        "scenario": sc_upper,
        "agent_run": agent_run,
        "failures": failures,
    }
