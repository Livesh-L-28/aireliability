"""Unit tests for Phase 40 Models and Task Understanding Analyzer."""

from __future__ import annotations

import pytest

from aireliability.agent.models import (
    ActionType,
    AgentFailureCategory,
    AgentStep,
    Observation,
    ToolCall,
    ToolRiskLevel,
)
from aireliability.agent.task_analyzer import TaskAnalyzer


def test_agent_models_creation_and_immutability():
    """Verify strongly typed models instantiate and enforce immutability."""
    tool_call = ToolCall(tool_name="database_query", arguments={"query": "SELECT *"})
    assert tool_call.tool_name == "database_query"
    assert tool_call.risk_level == ToolRiskLevel.LOW

    with pytest.raises((TypeError, ValueError)):
        tool_call.tool_name = "modified"  # frozen model

    obs = Observation(
        source="tool",
        raw_data={"status": "ok"},
        interpreted_content="Query returned OK",
    )
    assert obs.is_safe is True
    assert obs.confidence == 1.0

    step = AgentStep(
        sequence=1,
        action="query_db",
        action_type=ActionType.TOOL_CALL,
        tool_call=tool_call,
        observation=obs,
    )
    assert step.sequence == 1
    assert step.tool_call.tool_name == "database_query"


def test_agent_task_analyzer_normal_extraction():
    """Verify task understanding extracts objectives and explicit constraints."""
    analyzer = TaskAnalyzer()
    req = "Process customer refund for user 42. You must never expose the raw credit card number."
    task, failures, score = analyzer.analyze_task(
        request_text=req,
        expected_constraints=["never expose raw credit card"],
    )

    assert task.request_text == req
    assert score.score > 0.70
    assert task.ambiguity_score < 0.50
    assert len(task.extracted_objectives) >= 1
    # Check that constraint keyword 'never' was recognized
    assert len(task.constraints) >= 1


def test_agent_task_analyzer_ambiguous_request():
    """Verify task analyzer detects ambiguous language and flags comprehension risks."""
    analyzer = TaskAnalyzer()
    ambiguous_req = "Maybe clean up some files somehow and make the code nice and better whenever you want."
    task, failures, score = analyzer.analyze_task(request_text=ambiguous_req)

    assert task.ambiguity_score > 0.40
    # Ambiguous language should be flagged in task completeness or failure list
    assert task.completeness_score < 1.0


def test_agent_task_analyzer_missing_expected_constraint():
    """Verify missing expected benchmark constraint emits failure."""
    analyzer = TaskAnalyzer()
    req = "Deploy the web service to cluster us-east."
    task, failures, score = analyzer.analyze_task(
        request_text=req,
        expected_constraints=[
            "read-only permission only",
            "require approval before write",
        ],
    )

    missing_fails = [
        f for f in failures if f.category == AgentFailureCategory.MISSING_CONSTRAINT
    ]
    assert len(missing_fails) >= 1
    assert any("read-only" in f.message for f in missing_fails)


def test_agent_task_edge_cases():
    """Verify edge cases: Unicode text, empty text, whitespace."""
    analyzer = TaskAnalyzer()
    task, failures, score = analyzer.analyze_task(request_text="   ")
    assert len(failures) >= 1

    unicode_req = "查询客户 42 的账户余额，必须在 5 秒内完成 🚀"
    task_u, fails_u, score_u = analyzer.analyze_task(request_text=unicode_req)
    assert "查询客户" in task_u.request_text
