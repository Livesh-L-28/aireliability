"""Unit tests for Loops, Retries, and Runaway Execution in Phase 40."""

from __future__ import annotations

from aireliability.agent.loop_detector import LoopDetector
from aireliability.agent.models import (
    ActionType,
    AgentFailureCategory,
    AgentStep,
    LoopClassification,
    ToolCall,
    ToolResult,
)
from aireliability.agent.retry_analyzer import RetryAnalyzer
from aireliability.agent.runaway_detector import RunawayDetector


def test_loop_detector_no_loop_and_finite_retry():
    """Verify clean trajectory and 2-step finite retry classification."""
    detector = LoopDetector()

    # Clean
    s1 = AgentStep(
        sequence=1,
        action="search",
        action_type=ActionType.TOOL_CALL,
        tool_call=ToolCall(tool_name="search"),
    )
    s2 = AgentStep(
        sequence=2,
        action="calc",
        action_type=ActionType.TOOL_CALL,
        tool_call=ToolCall(tool_name="calc"),
    )
    c_clean, fails_c, _ = detector.detect_loops([s1, s2])
    assert c_clean == LoopClassification.NO_LOOP

    # 2 consecutive identical -> finite retry
    s3 = AgentStep(
        sequence=3,
        action="calc",
        action_type=ActionType.TOOL_CALL,
        tool_call=ToolCall(tool_name="calc"),
    )
    c_retry, fails_r, _ = detector.detect_loops([s2, s3])
    assert c_retry == LoopClassification.FINITE_RETRY


def test_loop_detector_runaway_and_oscillating():
    """Verify 4+ identical calls trigger RUNAWAY_LOOP and A->B->A->B triggers loop risks."""
    detector = LoopDetector(runaway_loop_threshold=4)

    # 4 consecutive identical calls
    steps_runaway = [
        AgentStep(
            sequence=i,
            action="call_api",
            action_type=ActionType.TOOL_CALL,
            tool_call=ToolCall(tool_name="api"),
        )
        for i in range(1, 6)
    ]
    c_runaway, fails_rw, score_rw = detector.detect_loops(steps_runaway)
    assert c_runaway == LoopClassification.RUNAWAY_LOOP
    assert score_rw.score == 0.0

    # Oscillating: A -> B -> A -> B -> A -> B
    step_a = AgentStep(
        sequence=1,
        action="tool_a",
        action_type=ActionType.TOOL_CALL,
        tool_call=ToolCall(tool_name="a"),
    )
    step_b = AgentStep(
        sequence=2,
        action="tool_b",
        action_type=ActionType.TOOL_CALL,
        tool_call=ToolCall(tool_name="b"),
    )
    steps_osc = [step_a, step_b, step_a, step_b, step_a, step_b]
    c_osc, fails_osc, _ = detector.detect_loops(steps_osc)
    assert c_osc in (
        LoopClassification.INFINITE_LOOP_RISK,
        LoopClassification.RUNAWAY_LOOP,
    )


def test_retry_analyzer_productive_vs_redundant():
    """Verify retry analyzer differentiates productive recovered retries from redundant storms."""
    analyzer = RetryAnalyzer(storm_threshold=3)

    # 1. Productive retry: fail -> retry with different/recovered outcome
    s1 = AgentStep(
        sequence=1,
        tool_call=ToolCall(tool_name="api", arguments={"timeout": 5}),
        tool_result=ToolResult(
            call_id="c1", tool_name="api", success=False, error_message="timeout"
        ),
    )
    s2 = AgentStep(
        sequence=2,
        tool_call=ToolCall(tool_name="api", arguments={"timeout": 15}),
        tool_result=ToolResult(call_id="c2", tool_name="api", success=True),
    )
    fails_prod, score_prod = analyzer.analyze_retries([s1, s2])
    assert score_prod.metrics["recovery_rate"] == 1.0
    assert len(fails_prod) == 0

    # 2. Redundant retry: fail -> retry with identical failing arguments
    s3 = AgentStep(
        sequence=2,
        tool_call=ToolCall(tool_name="api", arguments={"timeout": 5}),
        tool_result=ToolResult(call_id="c3", tool_name="api", success=False),
    )
    fails_red, score_red = analyzer.analyze_retries([s1, s3])
    assert any(f.category == AgentFailureCategory.REDUNDANT_RETRY for f in fails_red)


def test_runaway_detector_budgets():
    """Verify limit checks for max_steps, max_cost, max_runtime."""
    detector = RunawayDetector(max_steps=5, max_cost=1.0, max_runtime_seconds=10.0)

    # Over step budget
    steps = [AgentStep(sequence=i, action=f"step_{i}") for i in range(7)]
    fails_steps, score_steps = detector.evaluate_trajectory_limits(steps)
    assert any(f.category == AgentFailureCategory.LIMIT_EXCEEDED for f in fails_steps)
    assert score_steps.score < 0.60

    # Over cost and runtime
    fails_cost, _ = detector.evaluate_trajectory_limits(
        [], total_cost=2.5, total_latency_seconds=15.0
    )
    assert any(f.category == AgentFailureCategory.COST_FAILURE for f in fails_cost)
    assert any(f.category == AgentFailureCategory.LATENCY_FAILURE for f in fails_cost)
