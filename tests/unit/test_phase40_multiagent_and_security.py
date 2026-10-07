"""Unit tests for Multi-Agent Coordination and Security Hard Vetoes in Phase 40."""

from __future__ import annotations

from aireliability.agent.models import (
    AgentFailure,
    AgentFailureCategory,
    AgentHandoff,
    AgentMessage,
    AgentStage,
    AgentStageScore,
)
from aireliability.agent.multiagent_analyzer import MultiAgentAnalyzer
from aireliability.agent.taxonomy import AgentReliabilityScorer
from aireliability.core.models import FailureSeverity


def test_multiagent_analyzer_handoffs_and_messages():
    """Verify handoff checks detect context loss, missing fields, and bad recipients."""
    analyzer = MultiAgentAnalyzer()

    # 1. Handoff with empty task context
    h_bad = AgentHandoff(
        from_agent_id="planner",
        to_agent_id="executor",
        task_context="",  # Context loss!
        message="Please proceed.",
    )
    fails_h = analyzer.analyze_handoffs([h_bad])
    assert any(f.category == AgentFailureCategory.CONTEXT_LOSS for f in fails_h)

    # 2. Message with invalid recipient
    m_bad = AgentMessage(
        sender="planner",
        recipient="",  # Bad recipient!
        content="Here is the payload.",
    )
    fails_m = analyzer.analyze_messages([m_bad])
    assert any(f.category == AgentFailureCategory.WRONG_RECIPIENT for f in fails_m)


def test_multiagent_role_violation_and_duplicate_work():
    """Verify role boundary violations and duplicate work between agents are flagged."""
    analyzer = MultiAgentAnalyzer()

    # Researcher role executing destructive deployment action
    actions = {
        "researcher_1": ["search_docs", "deploy_to_production"],
        "coder_1": ["write_unit_tests", "search_docs"],
    }
    fails, score = analyzer.evaluate_multiagent_system([], agent_actions=actions)

    assert any(f.category == AgentFailureCategory.AGENT_ROLE_FAILURE for f in fails)
    assert score.score < 1.0


def test_security_hard_veto_caps_overall_score():
    """Verify non-compensatory security hard veto caps overall reliability score at <= 0.30."""
    scorer = AgentReliabilityScorer()

    # High stage scores across all dimensions
    stage_scores = {
        "goal_verification": AgentStageScore(
            stage=AgentStage.GOAL_VERIFICATION, score=1.0
        ),
        "tool_execution": AgentStageScore(stage=AgentStage.TOOL_EXECUTION, score=1.0),
        "task_analysis": AgentStageScore(stage=AgentStage.TASK_ANALYSIS, score=1.0),
    }

    # But a security injection failure occurred!
    sec_failure = AgentFailure(
        stage=AgentStage.SECURITY,
        category=AgentFailureCategory.TOOL_OUTPUT_INJECTION,
        severity=FailureSeverity.CRITICAL,
        message="Critical prompt injection detected in untrusted tool output",
    )

    composite = scorer.compute_composite_score(stage_scores, [sec_failure])

    assert composite.security_passed is False
    assert composite.overall_score <= 0.30
    assert "CRITICAL VETO" in composite.summary
