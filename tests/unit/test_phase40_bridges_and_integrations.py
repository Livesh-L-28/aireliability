"""Unit tests for Phase 34-39 Subsystem Bridges and Observability in Phase 40."""

from __future__ import annotations

from aireliability.agent.graph_bridge import AgentGraphBridge
from aireliability.agent.healing_bridge import AgentHealingBridge
from aireliability.agent.intelligence_bridge import AgentIntelligenceBridge
from aireliability.agent.models import (
    ActionType,
    AgentFailure,
    AgentFailureCategory,
    AgentRun,
    AgentStage,
    AgentStep,
    AgentTask,
    AgentTrajectory,
    GoalVerification,
    ToolCall,
    ToolResult,
)
from aireliability.agent.observability_bridge import AgentObservabilityBridge
from aireliability.agent.optimization_bridge import AgentOptimizationBridge
from aireliability.agent.rag_bridge import AgentRAGBridge
from aireliability.agent.test_bridge import AgentTestBridge
from aireliability.core.models import FailureSeverity
from aireliability.graph.graph import KnowledgeGraph
from aireliability.rag.models import RAGFailure, RAGFailureCategory, RAGStage


def test_phase34_intelligence_bridge():
    """Verify agent failures flow into Phase 34 normalized failures, clusters, and recommendations."""
    bridge = AgentIntelligenceBridge()
    f1 = AgentFailure(
        stage=AgentStage.TOOL_SELECTION,
        category=AgentFailureCategory.WRONG_TOOL,
        severity=FailureSeverity.HIGH,
        message="Wrong tool selected",
        affected_component="sql_tool",
    )
    norm = bridge.normalize_agent_failure(f1, run_id="r1", agent_id="agent_1")
    assert norm.category == "agent_tool_selection"
    assert norm.component == "sql_tool"

    clusters = bridge.cluster_agent_failures([f1], run_id="r1", agent_id="agent_1")
    assert len(clusters) == 1
    assert clusters[0].frequency == 1


def test_phase35_graph_bridge():
    """Verify knowledge graph synchronization and traversals."""
    kg = KnowledgeGraph()
    bridge = AgentGraphBridge(kg)

    step = AgentStep(
        sequence=1,
        action="search",
        action_type=ActionType.TOOL_CALL,
        tool_call=ToolCall(tool_name="web_search"),
    )
    fail = AgentFailure(
        stage=AgentStage.TOOL_EXECUTION,
        category=AgentFailureCategory.TOOL_ERROR,
        severity=FailureSeverity.HIGH,
        message="Failed search",
    )
    run = AgentRun(
        run_id="run_graph_test",
        agent_id="test_agent",
        task=AgentTask(task_id="t1", request_text="search query"),
        trajectory=AgentTrajectory(steps=[step]),
        failures=[fail],
        goal_verification=GoalVerification(goal_id="g1"),
    )

    bridge.sync_agent_run(run)
    assert kg.has_node("agent:test_agent")
    assert kg.has_node("task:t1")
    assert kg.has_node("execution:run_graph_test")

    # Traverse
    fails_found = bridge.find_failures_for_agent("test_agent")
    assert len(fails_found) >= 1
    tool_fails = bridge.find_failures_for_tool("web_search")
    assert len(tool_fails) >= 1


def test_phase36_test_bridge():
    """Verify test generation engine synthesizes candidate tests from agent failures."""
    bridge = AgentTestBridge()
    fail = AgentFailure(
        stage=AgentStage.LOOP,
        category=AgentFailureCategory.RUNAWAY_LOOP,
        severity=FailureSeverity.CRITICAL,
        message="Runaway loop detected on api tool",
        affected_component="api_tool",
    )
    run = AgentRun(
        task=AgentTask(request_text="query account"),
        failures=[fail],
    )
    result = bridge.generate_agent_tests(run, max_tests=3)
    assert len(result.test_cases) >= 1


def test_phase37_healing_bridge():
    """Verify self-healing remediation proposals are created from agent failures."""
    bridge = AgentHealingBridge()
    fail = AgentFailure(
        stage=AgentStage.TOOL_ARGUMENTS,
        category=AgentFailureCategory.INVALID_ARGUMENTS,
        severity=FailureSeverity.HIGH,
        message="Invalid parameter types",
        affected_component="calculator",
    )
    proposals = bridge.propose_agent_remediations([fail])
    assert len(proposals) >= 1
    assert proposals[0].proposal_id.startswith("rem_")


def test_phase38_optimization_bridge():
    """Verify optimization problem configuration for agent hyperparameters."""
    bridge = AgentOptimizationBridge()
    problem = bridge.create_agent_optimization_problem(agent_id="finance_bot")
    assert problem.name == "Agent Trajectory Optimization"
    assert len(problem.objectives) >= 2
    assert len(problem.variables) == 3
    assert any(v.variable_id == "max_steps" for v in problem.variables)


def test_phase39_rag_bridge():
    """Verify cross-system attribution distinguishes Agent tool failure from RAG internal retrieval failure."""
    bridge = AgentRAGBridge()

    # Step calling RAG tool with empty query -> Agent Argument Failure
    step_bad_arg = AgentStep(
        sequence=1,
        tool_call=ToolCall(tool_name="rag_tool", arguments={"query": ""}),
    )
    fails_arg = bridge.attribute_rag_tool_failure(step_bad_arg)
    assert any(f.stage == AgentStage.TOOL_ARGUMENTS for f in fails_arg)

    # Step with valid query but internal RAG retrieval failure -> RAG retrieval failure
    step_valid = AgentStep(
        sequence=2,
        tool_call=ToolCall(
            tool_name="rag_tool", arguments={"query": "reliable systems"}
        ),
    )
    rag_fail = RAGFailure(
        stage=RAGStage.RETRIEVAL,
        category=RAGFailureCategory.RETRIEVAL_FAILURE,
        severity=FailureSeverity.HIGH,
        message="Index returned zero documents",
    )
    fails_rag = bridge.attribute_rag_tool_failure(step_valid, rag_failures=[rag_fail])
    assert any(f.stage == AgentStage.TOOL_EXECUTION for f in fails_rag)
    assert any("RAG Subsystem Retrieval Failure" in f.message for f in fails_rag)


def test_observability_bridge():
    """Verify prometheus metric counters and gauges are incremented on run record."""
    bridge = AgentObservabilityBridge()
    step = AgentStep(
        sequence=1,
        tool_call=ToolCall(tool_name="api"),
        tool_result=ToolResult(call_id="c1", tool_name="api", success=True),
    )
    run = AgentRun(
        task=AgentTask(request_text="test"),
        trajectory=AgentTrajectory(
            steps=[step], total_cost=0.01, total_latency_seconds=1.2
        ),
    )
    bridge.record_run(run)
    assert bridge.c_runs.get() >= 1
    assert bridge.c_tool_calls.get() >= 1
