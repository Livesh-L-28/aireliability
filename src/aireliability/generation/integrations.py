"""Integration bridges connecting Test Generation with KnowledgeGraph, Observability, and Security."""

from __future__ import annotations

from aireliability.generation.models import (
    GeneratedTest,
    TestGenerationResult,
)
from aireliability.graph.graph import KnowledgeGraph
from aireliability.graph.models import (
    GraphEdge,
    GraphNode,
    GraphNodeType,
    GraphRelationship,
)
from aireliability.observability.manager import ObservabilityManager


class GraphIntegrationBridge:
    """Synchronizes generated tests and provenance relationships into the Knowledge Graph."""

    def record_generated_test(
        self,
        graph: KnowledgeGraph,
        test: GeneratedTest,
        dataset_id: str | None = None,
    ) -> GraphNode:
        """Add a generated test node and its evidential provenance edges to KnowledgeGraph."""
        node_id = f"test_case:{test.test_id}"
        node = GraphNode.create(
            node_type=GraphNodeType.TEST_CASE,
            source_id=test.test_id,
            name=test.name,
            tags=list(test.tags)
            + [f"status:{test.status.value}", f"risk:{test.risk_level.value}"],
            confidence=test.confidence,
            provenance=test.provenance.model_dump(),
            metadata={
                "strategy": str(test.strategy),
                "test_type": str(test.test_type),
                "fingerprint": test.fingerprint,
                "has_ground_truth": test.has_ground_truth,
                "quality_score": test.quality_score.total_score
                if test.quality_score
                else None,
            },
        )
        graph.add_node(node)

        # 1. Failure provenance edge
        if test.provenance.source_failure_id:
            fail_id = test.provenance.source_failure_id
            fail_node_id = (
                fail_id if fail_id.startswith("failure:") else f"failure:{fail_id}"
            )
            if graph.has_node(fail_node_id):
                graph.add_edge(
                    GraphEdge.create(
                        relationship_type=GraphRelationship.GENERATED,
                        source_node_id=fail_node_id,
                        target_node_id=node_id,
                    )
                )

        # 2. Incident provenance edge
        if test.provenance.source_incident_id:
            inc_id = test.provenance.source_incident_id
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

        # 3. Trace provenance edge
        if test.provenance.source_trace_id:
            tr_id = test.provenance.source_trace_id
            tr_node_id = tr_id if tr_id.startswith("trace:") else f"trace:{tr_id}"
            if graph.has_node(tr_node_id):
                graph.add_edge(
                    GraphEdge.create(
                        relationship_type=GraphRelationship.GENERATED,
                        source_node_id=tr_node_id,
                        target_node_id=node_id,
                    )
                )

        # 4. Pattern provenance edge
        if test.provenance.source_pattern_id:
            pat_id = test.provenance.source_pattern_id
            pat_node_id = (
                pat_id if pat_id.startswith("pattern:") else f"pattern:{pat_id}"
            )
            if graph.has_node(pat_node_id):
                graph.add_edge(
                    GraphEdge.create(
                        relationship_type=GraphRelationship.SUPPORTED_BY,
                        source_node_id=pat_node_id,
                        target_node_id=node_id,
                    )
                )

        # 5. Parent test derivation edge
        if test.provenance.parent_test_id:
            p_id = test.provenance.parent_test_id
            parent_node_id = (
                p_id if p_id.startswith("test_case:") else f"test_case:{p_id}"
            )
            if graph.has_node(parent_node_id):
                graph.add_edge(
                    GraphEdge.create(
                        relationship_type=GraphRelationship.DERIVED_FROM,
                        source_node_id=parent_node_id,
                        target_node_id=node_id,
                    )
                )

        # 6. Dataset membership edge
        if dataset_id:
            ds_node_id = (
                dataset_id
                if dataset_id.startswith("dataset:")
                else f"dataset:{dataset_id}"
            )
            if graph.has_node(ds_node_id):
                graph.add_edge(
                    GraphEdge.create(
                        relationship_type=GraphRelationship.BELONGS_TO,
                        source_node_id=node_id,
                        target_node_id=ds_node_id,
                    )
                )

        return node

    def query_tests_for_failure(
        self, graph: KnowledgeGraph, failure_id: str
    ) -> list[GraphNode]:
        """Find generated tests linked to a failure."""
        fail_node_id = (
            failure_id if failure_id.startswith("failure:") else f"failure:{failure_id}"
        )
        edges = graph.list_edges(
            relationship_type=GraphRelationship.GENERATED,
            source_node_id=fail_node_id,
        )
        return [
            graph.get_node(e.target_node_id)
            for e in edges
            if graph.get_node(e.target_node_id) is not None
        ]

    def query_failures_without_tests(self, graph: KnowledgeGraph) -> list[GraphNode]:
        """Identify failure nodes that have zero generated test cases protecting them."""
        failure_nodes = graph.list_nodes(node_type=GraphNodeType.FAILURE)
        unprotected: list[GraphNode] = []
        for fn in failure_nodes:
            edges = graph.list_edges(
                relationship_type=GraphRelationship.GENERATED,
                source_node_id=fn.node_id,
            )
            test_edges = [
                e
                for e in edges
                if (node := graph.get_node(e.target_node_id))
                and node.node_type == GraphNodeType.TEST_CASE
            ]
            if not test_edges:
                unprotected.append(fn)
        return unprotected


class ObservabilityIntegrationBridge:
    """Emits test generation telemetry, latency metrics, and run status to ObservabilityManager."""

    def record_run(
        self,
        obs: ObservabilityManager,
        result: TestGenerationResult,
    ) -> None:
        """Record generation metrics to existing metrics engine."""
        try:
            obs.metrics.counter("test_generation_candidates_total").increment(
                float(result.total_generated)
            )
            obs.metrics.counter("test_generation_validated_total").increment(
                float(result.total_validated)
            )
            obs.metrics.counter("test_generation_rejected_total").increment(
                float(result.total_rejected)
            )
            obs.metrics.counter("test_generation_promoted_total").increment(
                float(result.total_promoted)
            )
            obs.metrics.histogram("test_generation_duration_seconds").observe(
                result.duration_ms / 1000.0
            )
        except Exception:
            # Observability metrics should never crash pipeline execution
            pass
