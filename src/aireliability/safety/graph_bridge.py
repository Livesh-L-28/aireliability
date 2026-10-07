"""Knowledge Graph synchronization bridge for Safety Validation (Phase 41 -> Phase 35)."""

from __future__ import annotations

from aireliability.graph.builder import KnowledgeGraphBuilder
from aireliability.graph.models import (
    GraphEdge,
    GraphNode,
    GraphNodeType,
    GraphRelationship,
)
from aireliability.safety.models import (
    SafetyCampaignResult,
    SafetyTest,
)


class SafetyGraphBridge:
    """Synchronizes safety validation entities and relationships into the Knowledge Graph."""

    def __init__(self, graph_builder: KnowledgeGraphBuilder | None = None) -> None:
        self.builder = graph_builder or KnowledgeGraphBuilder()

    def sync_campaign_result(
        self,
        result: SafetyCampaignResult,
        tests: list[SafetyTest] | None = None,
    ) -> int:
        """Sync a completed safety campaign result, findings, and tests into the graph."""
        nodes_added = 0

        # 1. Campaign node
        camp_node = GraphNode.create(
            node_type=GraphNodeType.SAFETY_CAMPAIGN,
            source_id=result.campaign_id,
            name=f"Campaign-{result.campaign_id[:8]}",
            metadata={
                "target_id": result.target.target_id,
                "total_tests": result.total_tests,
                "safety_score": result.score.safety_score,
                "hard_veto": result.score.hard_veto_applied,
            },
        )
        self.builder.graph.add_node(camp_node)
        nodes_added += 1

        # 2. Add findings
        for f in result.findings:
            find_node = GraphNode.create(
                node_type=GraphNodeType.SAFETY_FINDING,
                source_id=f.finding_id,
                name=f"Finding-{f.category.value}",
                metadata={
                    "severity": f.severity.value,
                    "verdict": f.verdict.value,
                    "message": f.message,
                },
            )
            self.builder.graph.add_node(find_node)
            nodes_added += 1

            # Edge: CAMPAIGN -> DETECTED -> FINDING
            edge = GraphEdge(
                source_id=camp_node.node_id,
                target_id=find_node.node_id,
                relationship=GraphRelationship.DETECTED,
            )
            self.builder.graph.add_edge(edge)

        # 3. Add tests if provided
        if tests:
            for t in tests:
                test_node = GraphNode.create(
                    node_type=GraphNodeType.SAFETY_TEST,
                    source_id=t.test_id,
                    name=f"Test-{t.category.value}",
                    metadata={
                        "category": t.category.value,
                        "strategy": t.strategy.value,
                    },
                )
                self.builder.graph.add_node(test_node)
                nodes_added += 1

                # Edge: CAMPAIGN -> CONTAINS -> TEST
                edge = GraphEdge(
                    source_id=camp_node.node_id,
                    target_id=test_node.node_id,
                    relationship=GraphRelationship.CONTAINS,
                )
                self.builder.graph.add_edge(edge)

        return nodes_added
