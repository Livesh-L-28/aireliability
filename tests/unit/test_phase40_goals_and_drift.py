"""Unit tests for Independent Goal Verification and Drift Detection in Phase 40."""

from __future__ import annotations

from aireliability.agent.drift_detector import AgentDriftDetector
from aireliability.agent.goal_verifier import GoalVerifier
from aireliability.agent.models import (
    AgentFailureCategory,
    AgentRun,
    AgentStep,
    AgentTask,
    AgentTrajectory,
    Goal,
    GoalCriterion,
    GoalStatus,
    ToolCall,
    ToolResult,
)


def test_goal_verifier_completed():
    """Verify clean goal completion based on trajectory evidence."""
    verifier = GoalVerifier()
    goal = Goal(
        goal_id="g1",
        description="Fetch balance and send email notification",
        criteria=[
            GoalCriterion(description="balance fetched", is_mandatory=True),
            GoalCriterion(description="notification sent", is_mandatory=True),
        ],
    )
    s1 = AgentStep(
        sequence=1,
        tool_result=ToolResult(
            call_id="c1", tool_name="bank", output="balance fetched: $500"
        ),
    )
    s2 = AgentStep(
        sequence=2,
        tool_result=ToolResult(
            call_id="c2", tool_name="notifier", output="notification sent successfully"
        ),
    )
    verif, fails, score = verifier.verify_goal(
        goal, [s1, s2], final_response="Balance fetched and email sent."
    )

    assert verif.overall_status == GoalStatus.COMPLETED
    assert verif.completion_ratio == 1.0
    assert len(fails) == 0
    assert score.score == 1.0


def test_goal_verifier_premature_termination():
    """Verify FINAL ANSWER != TASK SUCCESS: final answer present but mandatory goal criteria failed."""
    verifier = GoalVerifier()
    goal = Goal(
        goal_id="g1",
        description="Delete database backup",
        criteria=[
            GoalCriterion(description="backup deleted", is_mandatory=True),
        ],
    )
    # Agent produced empty or failing step, but final response falsely claimed success
    s1 = AgentStep(
        sequence=1,
        tool_result=ToolResult(
            call_id="c1", tool_name="db", output="Permission Denied", success=False
        ),
    )
    verif, fails, score = verifier.verify_goal(
        goal, [s1], final_response="All backups have been deleted."
    )

    assert verif.overall_status == GoalStatus.FAILED
    assert any(f.category == AgentFailureCategory.GOAL_NOT_ACHIEVED for f in fails)
    assert any(f.category == AgentFailureCategory.PREMATURE_TERMINATION for f in fails)


def test_drift_detector_metric_and_tool_distribution():
    """Verify statistical drift detection for trajectory steps, cost, and tool distributions."""
    detector = AgentDriftDetector(drift_threshold=0.20)

    # 1. Trajectory length drift
    base_lengths = [3.0, 3.0, 4.0, 3.0]
    curr_lengths = [8.0, 9.0, 10.0, 8.0]  # Major shift
    res_len = detector.evaluate_metric_drift(
        base_lengths, curr_lengths, "trajectory_length"
    )
    assert res_len.drift_detected is True
    assert res_len.distance > 0.50

    # 2. Tool distribution drift
    def make_run(tool_name: str) -> AgentRun:
        step = AgentStep(sequence=1, tool_call=ToolCall(tool_name=tool_name))
        return AgentRun(
            task=AgentTask(request_text="test"),
            trajectory=AgentTrajectory(steps=[step]),
        )

    base_runs = [make_run("search_tool") for _ in range(5)]
    curr_runs = [make_run("calc_tool") for _ in range(5)]  # completely different tools
    res_tool = detector.evaluate_tool_distribution_drift(base_runs, curr_runs)
    assert res_tool.drift_detected is True
    assert res_tool.distance == 1.0
