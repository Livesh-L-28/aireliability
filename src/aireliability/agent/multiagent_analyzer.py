"""Multi-Agent Coordination and Communication Analyzer for Phase 40.

Evaluates collaboration traces between multiple cooperating agents.
Audits handoff boundaries, message delivery, role adherence, conflicting outputs,
and duplicate redundant operations across team members.
"""

from __future__ import annotations

from aireliability.agent.models import (
    AgentFailure,
    AgentFailureCategory,
    AgentHandoff,
    AgentMessage,
    AgentStage,
    AgentStageScore,
)
from aireliability.core.models import FailureSeverity


class MultiAgentAnalyzer:
    """Audits multi-agent handoffs, message envelopes, role boundaries, and team conflicts."""

    def __init__(self, agent_roles: dict[str, list[str]] | None = None) -> None:
        # Map of agent_id to permitted action keywords / tool namespaces
        self.agent_roles = agent_roles or {
            "planner": ["plan", "decompose", "coordinate"],
            "researcher": ["search", "query", "read", "fetch"],
            "coder": ["code", "write_file", "edit_file", "compile"],
            "reviewer": ["review", "test", "audit", "verify", "diff"],
        }

    def analyze_handoffs(
        self,
        handoffs: list[AgentHandoff],
    ) -> list[AgentFailure]:
        """Audit agent-to-agent task transfers and context integrity."""
        failures: list[AgentFailure] = []

        for h in handoffs:
            # 1. Handoff success check
            if not h.success:
                failures.append(
                    AgentFailure(
                        stage=AgentStage.MULTI_AGENT,
                        category=AgentFailureCategory.AGENT_HANDOFF_FAILURE,
                        severity=FailureSeverity.HIGH,
                        message=f"Handoff from '{h.from_agent_id}' to '{h.to_agent_id}' failed",
                        affected_component=h.to_agent_id,
                        confidence=0.95,
                    )
                )

            # 2. Context loss check
            if not h.task_context.strip():
                failures.append(
                    AgentFailure(
                        stage=AgentStage.MULTI_AGENT,
                        category=AgentFailureCategory.CONTEXT_LOSS,
                        severity=FailureSeverity.HIGH,
                        message=f"Handoff from '{h.from_agent_id}' to '{h.to_agent_id}' has empty task context",
                        affected_component=h.to_agent_id,
                        confidence=0.92,
                    )
                )

            # 3. Missing required fields in message
            if h.required_fields:
                for req in h.required_fields:
                    if (
                        req.lower() not in h.message.lower()
                        and req.lower() not in h.task_context.lower()
                    ):
                        failures.append(
                            AgentFailure(
                                stage=AgentStage.MULTI_AGENT,
                                category=AgentFailureCategory.MESSAGE_LOSS,
                                severity=FailureSeverity.MEDIUM,
                                message=f"Handoff from '{h.from_agent_id}' missing required field: '{req}'",
                                affected_component=h.to_agent_id,
                                confidence=0.88,
                            )
                        )

        return failures

    def analyze_messages(
        self,
        messages: list[AgentMessage],
    ) -> list[AgentFailure]:
        """Audit point-to-point agent communication messages."""
        failures: list[AgentFailure] = []
        known_agents = set()

        for m in messages:
            known_agents.add(m.sender)
            known_agents.add(m.recipient)

            if not m.recipient or m.recipient == "broadcast_unknown":
                failures.append(
                    AgentFailure(
                        stage=AgentStage.MULTI_AGENT,
                        category=AgentFailureCategory.WRONG_RECIPIENT,
                        severity=FailureSeverity.HIGH,
                        message=f"Message from '{m.sender}' has invalid/missing recipient: '{m.recipient}'",
                        affected_component=m.sender,
                        confidence=0.90,
                    )
                )

            if not m.content.strip():
                failures.append(
                    AgentFailure(
                        stage=AgentStage.MULTI_AGENT,
                        category=AgentFailureCategory.MESSAGE_CORRUPTION,
                        severity=FailureSeverity.MEDIUM,
                        message=f"Empty/corrupt message received from '{m.sender}'",
                        affected_component=m.recipient,
                        confidence=0.85,
                    )
                )

        return failures

    def evaluate_multiagent_system(
        self,
        handoffs: list[AgentHandoff],
        messages: list[AgentMessage] | None = None,
        agent_actions: dict[str, list[str]] | None = None,
    ) -> tuple[list[AgentFailure], AgentStageScore]:
        """Audit complete multi-agent coordination traces."""
        all_failures: list[AgentFailure] = []

        all_failures.extend(self.analyze_handoffs(handoffs))
        if messages:
            all_failures.extend(self.analyze_messages(messages))

        # Check role adherence if actions provided per agent
        if agent_actions:
            for agent_id, actions in agent_actions.items():
                agent_type = next(
                    (k for k in self.agent_roles if k in agent_id.lower()), None
                )
                if agent_type:
                    for action in actions:
                        act_lower = action.lower()
                        # If a researcher attempts to execute destructive/code actions
                        if agent_type == "researcher" and any(
                            k in act_lower for k in ["delete_db", "deploy", "merge"]
                        ):
                            all_failures.append(
                                AgentFailure(
                                    stage=AgentStage.MULTI_AGENT,
                                    category=AgentFailureCategory.AGENT_ROLE_FAILURE,
                                    severity=FailureSeverity.HIGH,
                                    message=f"Agent '{agent_id}' violated researcher role by performing action '{action}'",
                                    affected_component=agent_id,
                                    confidence=0.91,
                                )
                            )

        # Check duplicate work across agents
        if agent_actions and len(agent_actions) > 1:
            all_action_sets = list(agent_actions.values())
            for idx_a in range(len(all_action_sets)):
                for idx_b in range(idx_a + 1, len(all_action_sets)):
                    common = set(all_action_sets[idx_a]).intersection(
                        set(all_action_sets[idx_b])
                    )
                    # Filter out generic actions
                    common_substantive = [
                        c
                        for c in common
                        if len(c) > 10
                        and not any(w in c for w in ["init", "start", "stop"])
                    ]
                    if common_substantive:
                        agents = list(agent_actions.keys())
                        all_failures.append(
                            AgentFailure(
                                stage=AgentStage.MULTI_AGENT,
                                category=AgentFailureCategory.DUPLICATE_WORK,
                                severity=FailureSeverity.MEDIUM,
                                message=f"Duplicate work detected between '{agents[idx_a]}' and '{agents[idx_b]}': {common_substantive[0]}",
                                affected_component="multi_agent_orchestrator",
                                confidence=0.82,
                            )
                        )

        # Score calculation
        score = 1.0
        for f in all_failures:
            if f.severity == FailureSeverity.CRITICAL:
                score -= 0.50
            elif f.severity == FailureSeverity.HIGH:
                score -= 0.30
            elif f.severity == FailureSeverity.MEDIUM:
                score -= 0.15
            else:
                score -= 0.05
        score = max(0.0, min(1.0, score))

        stage_score = AgentStageScore(
            stage=AgentStage.MULTI_AGENT,
            score=score,
            confidence=0.90,
            metrics={
                "coordination_score": score,
                "handoff_count": float(len(handoffs)),
                "message_count": float(len(messages or [])),
                "failure_count": float(len(all_failures)),
            },
            failures=all_failures,
            explanation=(
                "Multi-agent coordination verified"
                if not all_failures
                else f"Detected {len(all_failures)} multi-agent coordination defects"
            ),
        )

        return all_failures, stage_score
