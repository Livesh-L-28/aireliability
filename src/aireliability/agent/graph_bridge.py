"""Phase 35 Knowledge Graph Bridge for Phase 40 Advanced Agent Reliability.

Ingests agent lifecycle runs, tasks, steps, tools, and failures into the Phase 35
KnowledgeGraph, establishing explicit semantic relationships:
- AGENT -> EXECUTED -> RUN
- TASK -> EXECUTED -> RUN
- RUN -> CONTAINS -> STEP
- STEP -> USED_TOOL -> TOOL
- STEP -> PRODUCED -> OBSERVATION
- RUN -> FAILED -> FAILURE
- FAILURE -> HAS_ROOT_CAUSE -> ROOT_CAUSE
- RUN -> VERIFIED_BY -> GOAL_CHECK

Provides graph traversals for querying failures by agent, tool, and root causes.
"""

from __future__ import annotations

import logging

from aireliability.agent.models import AgentRun
from aireliability.graph.graph import KnowledgeGraph
from aireliability.graph.models import (
    GraphEdge,
    GraphNode,
    GraphNodeType,
    GraphRelationship,
)

logger = logging.getLogger(__name__)


class AgentGraphBridge:
    """Synchronizes agent execution trajectories with the Phase 35 Knowledge Graph."""

    def __init__(self, graph: KnowledgeGraph | None = None) -> None:
        self.graph = graph or KnowledgeGraph()

    def sync_agent_run(self, run: AgentRun) -> None:
        """Populate the knowledge graph with complete provenance for an AgentRun."""
        # 1. Agent Node
        agent_node = GraphNode.create(
            node_type=GraphNodeType.AGENT,
            source_id=run.agent_id,
            name=f"Agent {run.agent_id}",
            version=run.agent_version,
            environment=run.environment,
            tags=["agent", run.agent_id],
        )
        self.graph.add_node(agent_node)
        agent_node_id = agent_node.node_id

        # 2. Task Node
        task_node = GraphNode.create(
            node_type=GraphNodeType.TASK,
            source_id=run.task.task_id,
            name=f"Task {run.task.task_id[:8]}",
            tags=["task"],
        )
        self.graph.add_node(task_node)
        task_node_id = task_node.node_id

        # 3. Execution / Run Node
        run_node = GraphNode.create(
            node_type=GraphNodeType.EXECUTION,
            source_id=run.run_id,
            name=f"Agent Run {run.run_id[:8]}",
            environment=run.environment,
            tags=["agent_run", run.agent_id],
            provenance=dict(run.provenance),
        )
        self.graph.add_node(run_node)
        run_node_id = run_node.node_id

        # Link AGENT -> EXECUTED -> RUN
        self.graph.add_edge(
            GraphEdge.create(
                source_node_id=agent_node_id,
                target_node_id=run_node_id,
                relationship_type=GraphRelationship.EXECUTED,
            )
        )

        # Link TASK -> EXECUTED -> RUN
        self.graph.add_edge(
            GraphEdge.create(
                source_node_id=task_node_id,
                target_node_id=run_node_id,
                relationship_type=GraphRelationship.EXECUTED,
            )
        )

        # 4. Trajectory Steps & Tools & Observations
        for step in run.trajectory.steps:
            step_node = GraphNode.create(
                node_type=GraphNodeType.TRACE_STEP,
                source_id=f"{run.run_id}_{step.sequence}",
                name=f"Step {step.sequence}: {step.action_type.value}",
                tags=["step", step.action_type.value],
            )
            self.graph.add_node(step_node)
            step_node_id = step_node.node_id

            # RUN -> CONTAINS -> STEP
            self.graph.add_edge(
                GraphEdge.create(
                    source_node_id=run_node_id,
                    target_node_id=step_node_id,
                    relationship_type=GraphRelationship.CONTAINS,
                )
            )

            # STEP -> USED_TOOL -> TOOL
            if step.tool_call is not None:
                tool_name = step.tool_call.tool_name
                tool_node = GraphNode.create(
                    node_type=GraphNodeType.TOOL,
                    source_id=tool_name,
                    name=f"Tool {tool_name}",
                    tags=["tool", tool_name],
                )
                self.graph.add_node(tool_node)
                self.graph.add_edge(
                    GraphEdge.create(
                        source_node_id=step_node_id,
                        target_node_id=tool_node.node_id,
                        relationship_type=GraphRelationship.USED_TOOL,
                    )
                )

            # STEP -> PRODUCED -> OBSERVATION
            if step.observation is not None:
                obs_node = GraphNode.create(
                    node_type=GraphNodeType.OBSERVATION,
                    source_id=step.observation.observation_id,
                    name=f"Obs {step.observation.observation_id[:8]}",
                    tags=["observation"],
                )
                self.graph.add_node(obs_node)
                self.graph.add_edge(
                    GraphEdge.create(
                        source_node_id=step_node_id,
                        target_node_id=obs_node.node_id,
                        relationship_type=GraphRelationship.PRODUCED,
                    )
                )

        # 5. Failures & Root Causes
        for f in run.failures:
            fail_node = GraphNode.create(
                node_type=GraphNodeType.FAILURE,
                source_id=f.failure_id,
                name=f.category.value,
                tags=["failure", f.stage.value, f.category.value],
            )
            self.graph.add_node(fail_node)
            fail_node_id = fail_node.node_id

            # RUN -> FAILED -> FAILURE
            self.graph.add_edge(
                GraphEdge.create(
                    source_node_id=run_node_id,
                    target_node_id=fail_node_id,
                    relationship_type=GraphRelationship.FAILED,
                )
            )

            # Root cause
            rc_node = GraphNode.create(
                node_type=GraphNodeType.ROOT_CAUSE,
                source_id=f.stage.value,
                name=f"Root Cause: {f.stage.value}",
                tags=["root_cause", f.stage.value],
            )
            self.graph.add_node(rc_node)

            # FAILURE -> HAS_ROOT_CAUSE -> ROOT_CAUSE
            self.graph.add_edge(
                GraphEdge.create(
                    source_node_id=fail_node_id,
                    target_node_id=rc_node.node_id,
                    relationship_type=GraphRelationship.HAS_ROOT_CAUSE,
                )
            )

        # 6. Goal Verification
        goal_check_node = GraphNode.create(
            node_type=GraphNodeType.GOAL_CHECK,
            source_id=run.goal_verification.goal_id,
            name=f"Goal Status: {run.goal_verification.overall_status.value}",
            tags=["goal_check", run.goal_verification.overall_status.value],
        )
        self.graph.add_node(goal_check_node)
        self.graph.add_edge(
            GraphEdge.create(
                source_node_id=run_node_id,
                target_node_id=goal_check_node.node_id,
                relationship_type=GraphRelationship.VERIFIED_BY,
            )
        )

    def find_failures_for_agent(self, agent_id: str) -> list[GraphNode]:
        """Find all failure nodes associated with a specific agent ID."""
        agent_node_id = f"agent:{agent_id}"
        if not self.graph.has_node(agent_node_id):
            return []
        edges = self.graph.list_edges(
            source_node_id=agent_node_id, relationship_type=GraphRelationship.EXECUTED
        )
        failures: list[GraphNode] = []
        for e in edges:
            run_fail_edges = self.graph.list_edges(
                source_node_id=e.target_node_id,
                relationship_type=GraphRelationship.FAILED,
            )
            for fe in run_fail_edges:
                node = self.graph.get_node(fe.target_node_id)
                if node:
                    failures.append(node)
        return failures

    def find_failures_for_tool(self, tool_name: str) -> list[GraphNode]:
        """Find failures associated with executions that used a given tool."""
        tool_node_id = f"tool:{tool_name}"
        if not self.graph.has_node(tool_node_id):
            return []
        edges = self.graph.list_edges(
            target_node_id=tool_node_id, relationship_type=GraphRelationship.USED_TOOL
        )
        affected_runs = set()
        for e in edges:
            step_edges = self.graph.list_edges(
                target_node_id=e.source_node_id,
                relationship_type=GraphRelationship.CONTAINS,
            )
            for se in step_edges:
                affected_runs.add(se.source_node_id)

        failures: list[GraphNode] = []
        for run_id in affected_runs:
            fail_edges = self.graph.list_edges(
                source_node_id=run_id, relationship_type=GraphRelationship.FAILED
            )
            for fe in fail_edges:
                node = self.graph.get_node(fe.target_node_id)
                if node:
                    failures.append(node)
        return failures
