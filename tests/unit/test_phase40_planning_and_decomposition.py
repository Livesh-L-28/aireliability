"""Unit tests for Task Decomposition and Planning Evaluator in Phase 40."""

from __future__ import annotations

from aireliability.agent.decomposition_analyzer import TaskDecompositionAnalyzer
from aireliability.agent.models import (
    ActionType,
    AgentFailureCategory,
    AgentPlan,
    AgentStep,
    AgentTrajectory,
    ToolCall,
    TrajectoryDeviationType,
)
from aireliability.agent.plan_evaluator import PlanEvaluator


def test_decomposition_valid_dag():
    """Verify clean subtask decomposition without cyclic dependencies."""
    analyzer = TaskDecompositionAnalyzer()
    subtasks = ["fetch_data", "process_data", "train_model", "deploy"]
    dependencies = {
        "process_data": ["fetch_data"],
        "train_model": ["process_data"],
        "deploy": ["train_model"],
    }
    is_valid, failures, score = analyzer.analyze_decomposition(subtasks, dependencies)
    assert is_valid is True
    assert len(failures) == 0
    assert score.score == 1.0


def test_decomposition_circular_dependency():
    """Verify circular dependency is detected and reported."""
    analyzer = TaskDecompositionAnalyzer()
    subtasks = ["task_a", "task_b", "task_c"]
    dependencies = {
        "task_b": ["task_a"],
        "task_c": ["task_b"],
        "task_a": ["task_c"],  # Cycle: A -> B -> C -> A
    }
    is_valid, failures, score = analyzer.analyze_decomposition(subtasks, dependencies)
    assert is_valid is False
    circ_fails = [
        f for f in failures if f.category == AgentFailureCategory.CIRCULAR_DEPENDENCY
    ]
    assert len(circ_fails) >= 1
    assert score.score < 0.50


def test_decomposition_duplicate_and_missing_dependencies():
    """Verify duplicate subtask and nonexistent dependency detection."""
    analyzer = TaskDecompositionAnalyzer()
    subtasks = ["fetch", "fetch", "analyze"]
    dependencies = {
        "analyze": ["unknown_task"],
    }
    is_valid, failures, score = analyzer.analyze_decomposition(subtasks, dependencies)
    dup_fails = [
        f for f in failures if f.category == AgentFailureCategory.DUPLICATE_SUBTASK
    ]
    dep_fails = [
        f for f in failures if f.category == AgentFailureCategory.DEPENDENCY_VIOLATION
    ]
    assert len(dup_fails) >= 1
    assert len(dep_fails) >= 1


def test_plan_evaluator_tool_availability():
    """Verify plan feasibility checks available tools."""
    evaluator = PlanEvaluator()
    plan = AgentPlan(
        steps=["query_database", "run_computation", "send_email_tool"],
        dependencies={},
    )
    # Available tools missing 'email_tool'
    available_tools = ["query_database", "calculator"]
    _plan, failures, score = evaluator.evaluate_plan(
        plan, available_tools=available_tools
    )
    missing_fails = [
        f for f in failures if f.category == AgentFailureCategory.PLAN_UNFEASIBLE
    ]
    assert len(missing_fails) >= 1
    assert score.score < 1.0


def test_plan_vs_trajectory_expected_adaptation():
    """Verify deviation after earlier tool failure is classified as benign/expected adaptation."""
    evaluator = PlanEvaluator()
    plan = AgentPlan(
        steps=["query_primary_db", "format_output"],
        dependencies={},
    )
    # Trajectory had a failure on primary db, then adapted to fallback_db
    step1 = AgentStep(
        sequence=1,
        action="query_primary_db",
        action_type=ActionType.TOOL_CALL,
        tool_call=ToolCall(tool_name="primary_db"),
        tool_result=None,  # failed
    )
    step1 = step1.model_copy(update={"status": "failed"})
    step2 = AgentStep(
        sequence=2,
        action="query_fallback_db",  # unexpected step, but response to failure
        action_type=ActionType.TOOL_CALL,
        tool_call=ToolCall(tool_name="fallback_db"),
    )
    trajectory = AgentTrajectory(steps=[step1, step2])

    dev_type, failures, details = evaluator.compare_plan_vs_trajectory(plan, trajectory)
    assert dev_type in (
        TrajectoryDeviationType.EXPECTED_ADAPTATION,
        TrajectoryDeviationType.BENIGN_DEVIATION,
        TrajectoryDeviationType.FAILURE,
    )


def test_plan_vs_trajectory_omitted_step():
    """Verify skipped critical steps are flagged as failure."""
    evaluator = PlanEvaluator()
    plan = AgentPlan(
        steps=["clean_data", "run_safety_check", "deploy"],
        dependencies={},
    )
    # Agent skipped safety check
    step1 = AgentStep(sequence=1, action="clean_data")
    step2 = AgentStep(sequence=2, action="deploy")
    trajectory = AgentTrajectory(steps=[step1, step2])

    dev_type, failures, details = evaluator.compare_plan_vs_trajectory(plan, trajectory)
    assert dev_type == TrajectoryDeviationType.FAILURE
    assert any(f.category == AgentFailureCategory.PLAN_INCONSISTENT for f in failures)
