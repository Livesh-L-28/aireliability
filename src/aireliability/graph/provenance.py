"""Provenance tracing, lineage inspection, and explainability for graph relationships."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aireliability.graph.graph import KnowledgeGraph


class ProvenanceTracer:
    """Traces upstream origin, causality, and evidence supporting reliability graph entities."""

    def __init__(self, graph: KnowledgeGraph) -> None:
        self.graph = graph

    def get_node_provenance(self, node_id: str) -> dict[str, Any]:
        """Retrieve recorded provenance, source attributes, and metadata for a node."""
        node = self.graph.get_node(node_id)
        if not node:
            return {}

        return {
            "node_id": node.node_id,
            "node_type": node.node_type.value,
            "name": node.name,
            "source_id": node.source_id,
            "version": node.version,
            "environment": node.environment,
            "confidence": node.confidence,
            "created_at": node.created_at.isoformat(),
            "tags": node.tags,
            "provenance": node.provenance,
            "metadata": node.metadata,
        }

    def get_edge_provenance(self, edge_id: str) -> dict[str, Any]:
        """Retrieve recorded causality, confidence, evidence, and temporal tags for an edge."""
        edge = self.graph.get_edge(edge_id)
        if not edge:
            return {}

        return {
            "edge_id": edge.edge_id,
            "source_node_id": edge.source_node_id,
            "target_node_id": edge.target_node_id,
            "relationship_type": edge.relationship_type.value,
            "is_causal": edge.is_causal,
            "confidence": edge.confidence,
            "evidence": edge.evidence,
            "provenance": edge.provenance,
            "temporal": edge.temporal,
            "created_at": edge.created_at.isoformat(),
            "metadata": edge.metadata,
        }

    def trace_origin(self, node_id: str, max_depth: int = 8) -> list[dict[str, Any]]:
        """Trace upstream incoming paths to uncover root origins (datasets, models, executions)."""
        if not self.graph.has_node(node_id):
            return []

        origins: list[dict[str, Any]] = []
        visited: set[str] = set()

        def _traverse_upstream(
            curr_id: str, depth: int, current_path: list[str]
        ) -> None:
            if depth >= max_depth or curr_id in visited:
                return

            visited.add(curr_id)
            in_edges = self.graph.list_edges(target_node_id=curr_id)

            if not in_edges and len(current_path) > 1:
                # Leaf origin found
                origin_node = self.graph.get_node(curr_id)
                if origin_node:
                    origins.append(
                        {
                            "origin_node_id": origin_node.node_id,
                            "origin_node_type": origin_node.node_type.value,
                            "name": origin_node.name,
                            "path": list(reversed(current_path)),
                            "depth": len(current_path) - 1,
                        }
                    )
                return

            for edge in in_edges:
                src_id = edge.source_node_id
                _traverse_upstream(src_id, depth + 1, current_path + [src_id])

        _traverse_upstream(node_id, 0, [node_id])
        return origins

    def explain_relationship(
        self, source_node_id: str, target_node_id: str
    ) -> list[dict[str, Any]]:
        """Provide detailed human-readable and structured explanation between two nodes."""
        direct_edges = self.graph.list_edges(
            source_node_id=source_node_id, target_node_id=target_node_id
        )

        explanations: list[dict[str, Any]] = []

        for edge in direct_edges:
            explanation = {
                "source": source_node_id,
                "target": target_node_id,
                "relationship": edge.relationship_type.value,
                "is_causal": edge.is_causal,
                "confidence": edge.confidence,
                "evidence": edge.evidence,
                "summary": (
                    f"Direct causal link: {source_node_id} {edge.relationship_type.value} {target_node_id}"
                    if edge.is_causal
                    else f"Observed correlation (non-causal): {source_node_id} {edge.relationship_type.value} "
                    f"{target_node_id} with confidence {edge.confidence:.2f}"
                ),
            }
            explanations.append(explanation)

        # If no direct edge, attempt path search
        if not explanations:
            path = self.graph.traversal.find_path(
                source_node_id, target_node_id, max_depth=6
            )
            if path:
                explanations.append(
                    {
                        "source": source_node_id,
                        "target": target_node_id,
                        "path": path,
                        "hops": len(path) - 1,
                        "summary": f"Indirect connection over {len(path) - 1} hops: {' -> '.join(path)}",
                    }
                )

        return explanations

    def get_lineage(self, node_id: str) -> dict[str, Any]:
        """Aggregate upstream dependencies and downstream dependents for a comprehensive lineage."""
        node = self.graph.get_node(node_id)
        if not node:
            return {}

        upstream = self.graph.traversal.bfs(node_id, max_depth=5, direction="incoming")
        downstream = self.graph.traversal.bfs(
            node_id, max_depth=5, direction="outgoing"
        )

        return {
            "node_id": node_id,
            "node_type": node.node_type.value,
            "upstream_count": len(upstream),
            "upstream_nodes": [
                {"node_id": u.node_id, "node_type": u.node_type.value, "name": u.name}
                for u in upstream
            ],
            "downstream_count": len(downstream),
            "downstream_nodes": [
                {"node_id": d.node_id, "node_type": d.node_type.value, "name": d.name}
                for d in downstream
            ],
        }
