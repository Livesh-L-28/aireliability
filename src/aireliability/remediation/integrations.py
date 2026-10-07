"""Integrations linking Remediation Engine with KnowledgeGraph and Observability."""

from __future__ import annotations

import logging

from aireliability.graph.graph import KnowledgeGraph
from aireliability.graph.models import (
    GraphEdge,
    GraphNode,
    GraphNodeType,
    GraphRelationship,
)
from aireliability.observability.manager import ObservabilityManager
from aireliability.remediation.models import RemediationProposal

logger = logging.getLogger(__name__)


class RemediationGraphBridge:
    """Synchronizes self-healing remediation proposals and causal edges into KnowledgeGraph."""

    def record_remediation(
        self,
        graph: KnowledgeGraph,
        proposal: RemediationProposal,
    ) -> GraphNode:
        """Add a remediation proposal node and its causal edges to the Knowledge Graph."""
        node = GraphNode.create(
            node_type=GraphNodeType.RECOMMENDATION,
            source_id=proposal.proposal_id,
            name=proposal.title,
            tags=list(proposal.tags)
            + [
                f"state:{proposal.state.value}",
                f"risk:{proposal.risk_tier.value}",
                "type:remediation",
            ],
            confidence=proposal.confidence,
            provenance=proposal.provenance.model_dump(),
            metadata={
                "repair_type": proposal.repair_type.value,
                "patch_count": len(proposal.patches),
                "generated_tests_count": len(proposal.generated_test_ids),
                "simulation_passed": proposal.simulation.passed
                if proposal.simulation
                else None,
                "gates_passed": proposal.gate_evaluation.gates_passed
                if proposal.gate_evaluation
                else None,
            },
        )
        graph.add_node(node)
        node_id = node.node_id

        # 1. Connect to source failure if present
        if proposal.provenance.source_failure_id:
            fail_id = proposal.provenance.source_failure_id
            fail_node_id = (
                fail_id if fail_id.startswith("failure:") else f"failure:{fail_id}"
            )
            if graph.has_node(fail_node_id):
                graph.add_edge(
                    GraphEdge.create(
                        relationship_type=GraphRelationship.RECOMMENDS,
                        source_node_id=fail_node_id,
                        target_node_id=node_id,
                    )
                )

        # 2. Connect to source incident if present
        if proposal.provenance.source_incident_id:
            inc_id = proposal.provenance.source_incident_id
            inc_node_id = (
                inc_id if inc_id.startswith("incident:") else f"incident:{inc_id}"
            )
            if graph.has_node(inc_node_id):
                graph.add_edge(
                    GraphEdge.create(
                        relationship_type=GraphRelationship.TRIGGERED,
                        source_node_id=inc_node_id,
                        target_node_id=node_id,
                    )
                )

        # 3. Connect to generated test cases
        for test_id in proposal.generated_test_ids:
            test_node_id = (
                test_id if test_id.startswith("test_case:") else f"test_case:{test_id}"
            )
            if graph.has_node(test_node_id):
                graph.add_edge(
                    GraphEdge.create(
                        relationship_type=GraphRelationship.SUPPORTED_BY,
                        source_node_id=node_id,
                        target_node_id=test_node_id,
                    )
                )

        # 4. Connect to target components
        for patch in proposal.patches:
            comp_type = patch.target_component_type
            comp_id = patch.target_component_id
            comp_node_id = f"{comp_type}:{comp_id}"
            if graph.has_node(comp_node_id):
                graph.add_edge(
                    GraphEdge.create(
                        relationship_type=GraphRelationship.AFFECTS,
                        source_node_id=node_id,
                        target_node_id=comp_node_id,
                    )
                )

        return node


class RemediationObservabilityBridge:
    """Emits telemetry metrics and events for self-healing lifecycle actions."""

    def __init__(self, obs_manager: ObservabilityManager | None = None) -> None:
        self.obs_manager = obs_manager
        self.metrics: dict[str, int] = {
            "proposals_total": 0,
            "simulations_passed": 0,
            "simulations_failed": 0,
            "approvals_total": 0,
            "rollouts_total": 0,
            "verifications_total": 0,
            "promotions_total": 0,
            "rollbacks_total": 0,
        }

    def record_proposal_created(self, proposal: RemediationProposal) -> None:
        """Record proposal creation event."""
        self.metrics["proposals_total"] += 1

    def record_simulation(self, proposal: RemediationProposal) -> None:
        """Record simulation outcome event."""
        if proposal.simulation and proposal.simulation.passed:
            self.metrics["simulations_passed"] += 1
        else:
            self.metrics["simulations_failed"] += 1

    def record_approval(self, proposal: RemediationProposal) -> None:
        """Record approval event."""
        self.metrics["approvals_total"] += 1

    def record_rollout(self, proposal: RemediationProposal) -> None:
        """Record rollout activation event."""
        self.metrics["rollouts_total"] += 1

    def record_verification(self, proposal: RemediationProposal) -> None:
        """Record successful verification event."""
        self.metrics["verifications_total"] += 1

    def record_promotion(self, proposal: RemediationProposal) -> None:
        """Record promotion event."""
        self.metrics["promotions_total"] += 1

    def record_rollback(self, proposal: RemediationProposal) -> None:
        """Record rollback event."""
        self.metrics["rollbacks_total"] += 1
