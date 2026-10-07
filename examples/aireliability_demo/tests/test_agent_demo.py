"""Tests for Autonomous Agent, tools, state, and Phase 40 evaluation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from aireliability_demo.app.agent.agent import ControlledAgent
from aireliability_demo.app.agent.tools import (
    tool_calculator,
    tool_document_lookup,
    tool_knowledge_search,
    tool_status_lookup,
)
from aireliability_demo.app.reliability.evaluator import DemoReliabilityEvaluator

from aireliability.agent.models import GoalStatus


def test_agent_safe_tools() -> None:
    # Calculator
    assert tool_calculator("2 + 2") == "4.0"
    assert tool_calculator("0.80 * 1.15") == "0.92"
    assert "CALCULATION_ERROR" in tool_calculator("1 / 0")

    # Knowledge search
    res = tool_knowledge_search("evaluation")
    assert "evaluation" in res.lower()

    # Document lookup
    doc_text = tool_document_lookup("evaluation.md")
    assert "# AI Reliability Evaluation Framework" in doc_text

    # Status lookup
    status = tool_status_lookup("evaluation")
    assert "HEALTHY" in status


def test_normal_agent_execution_and_phase40_eval() -> None:
    agent = ControlledAgent("TestAuditAgent")
    evaluator = DemoReliabilityEvaluator()

    run = agent.execute_task(
        "Calculate the projected reliability score after a 15% improvement from 0.80.",
        scenario="NORMAL_AGENT",
    )
    assert run.trajectory.total_steps >= 1
    assert "calculator" in run.tools

    evaluated = evaluator.evaluate_agent(run)
    assert evaluated.run_id == run.run_id
    assert evaluated.reliability_score.overall_score > 0.0


def test_agent_runaway_loop_and_retry_scenarios() -> None:
    agent = ControlledAgent("LoopTestAgent")

    run_runaway = agent.execute_task("Run runaway check", scenario="RUNAWAY_LOOP")
    assert run_runaway.trajectory.total_steps == 4
    assert run_runaway.goal_verification.overall_status == GoalStatus.FAILED

    run_retry = agent.execute_task("Run retry check", scenario="RETRY_LOOP")
    assert run_retry.trajectory.total_steps == 2
    assert run_retry.goal_verification.overall_status == GoalStatus.FAILED


def test_agent_wrong_tool_and_goal_failure() -> None:
    agent = ControlledAgent("WrongToolAgent")

    run_wrong = agent.execute_task("Calculate 5 + 5", scenario="WRONG_TOOL")
    assert len(run_wrong.failures) >= 1
    assert run_wrong.goal_verification.overall_status == GoalStatus.FAILED

    run_goal = agent.execute_task("Do task", scenario="GOAL_FAILURE")
    assert run_goal.goal_verification.overall_status == GoalStatus.FAILED
