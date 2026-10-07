"""Top-level KnowledgeGraph orchestrator and container."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from aireliability.graph.models import (
    GraphDiff,
    GraphEdge,
    GraphNode,
    GraphNodeType,
    GraphRelationship,
)
from aireliability.graph.store import GraphStore, InMemoryGraphStore

if TYPE_CHECKING:
    from aireliability.graph.impact import GraphImpactAnalyzer
    from aireliability.graph.provenance import ProvenanceTracer
    from aireliability.graph.query import GraphQuery
    from aireliability.graph.traversal import GraphTraversal


class KnowledgeGraph:
    """Core AI Reliability Knowledge Graph representing entities, failures, and dependencies."""

    def __init__(self, store: GraphStore | None = None) -> None:
        self.store: GraphStore = store if store is not None else InMemoryGraphStore()

    # -------------------------------------------------------------------------
    # Node Operations
    # -------------------------------------------------------------------------

    def add_node(self, node: GraphNode) -> GraphNode:
        """Add or update a node."""
        return self.store.add_node(node)

    def get_node(self, node_id: str, tenant_id: str | None = None) -> GraphNode | None:
        """Fetch node by identifier, with optional tenant boundary verification."""
        node = self.store.get_node(node_id)
        if not node:
            return None
        if tenant_id:
            node_tenant = getattr(node, "tenant_id", None) or node.metadata.get(
                "tenant_id"
            )
            if node_tenant and node_tenant != tenant_id:
                return None
        return node

    def has_node(self, node_id: str, tenant_id: str | None = None) -> bool:
        """Check if node exists within tenant scope."""
        return self.get_node(node_id, tenant_id=tenant_id) is not None

    def remove_node(self, node_id: str) -> bool:
        """Remove node and incident edges."""
        return self.store.remove_node(node_id)

    def list_nodes(
        self,
        node_type: GraphNodeType | None = None,
        tags: Sequence[str] | None = None,
        tenant_id: str | None = None,
    ) -> list[GraphNode]:
        """List stored nodes filtered by type, tags, and tenant boundary."""
        nodes = self.store.list_nodes(node_type=node_type, tags=tags)
        if tenant_id:
            nodes = [
                n
                for n in nodes
                if (getattr(n, "tenant_id", None) or n.metadata.get("tenant_id"))
                == tenant_id
            ]
        return nodes

    # -------------------------------------------------------------------------
    # Edge Operations
    # -------------------------------------------------------------------------

    def add_edge(self, edge: GraphEdge) -> GraphEdge:
        """Add or update a directed edge."""
        return self.store.add_edge(edge)

    def get_edge(self, edge_id: str) -> GraphEdge | None:
        """Fetch edge by edge_id."""
        return self.store.get_edge(edge_id)

    def has_edge(self, edge_id: str) -> bool:
        """Check if edge exists."""
        return self.store.has_edge(edge_id)

    def remove_edge(self, edge_id: str) -> bool:
        """Remove an edge by identifier."""
        return self.store.remove_edge(edge_id)

    def list_edges(
        self,
        relationship_type: GraphRelationship | None = None,
        source_node_id: str | None = None,
        target_node_id: str | None = None,
    ) -> list[GraphEdge]:
        """List edges matching criteria."""
        return self.store.list_edges(
            relationship_type=relationship_type,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
        )

    # -------------------------------------------------------------------------
    # Topology and Neighborhood
    # -------------------------------------------------------------------------

    def neighbors(
        self,
        node_id: str,
        direction: str = "both",
        relationship_type: GraphRelationship | None = None,
        tenant_id: str | None = None,
    ) -> list[GraphNode]:
        """Return adjacent nodes within tenant boundaries."""
        if tenant_id and not self.has_node(node_id, tenant_id=tenant_id):
            return []
        adj = self.store.neighbors(
            node_id=node_id, direction=direction, relationship_type=relationship_type
        )
        if tenant_id:
            adj = [
                n
                for n in adj
                if (getattr(n, "tenant_id", None) or n.metadata.get("tenant_id"))
                == tenant_id
            ]
        return adj

    def predecessors(
        self,
        node_id: str,
        relationship_type: GraphRelationship | None = None,
        tenant_id: str | None = None,
    ) -> list[GraphNode]:
        """Return upstream incoming neighbors."""
        if tenant_id and not self.has_node(node_id, tenant_id=tenant_id):
            return []
        preds = self.store.predecessors(
            node_id=node_id, relationship_type=relationship_type
        )
        if tenant_id:
            preds = [
                n
                for n in preds
                if (getattr(n, "tenant_id", None) or n.metadata.get("tenant_id"))
                == tenant_id
            ]
        return preds

    def successors(
        self,
        node_id: str,
        relationship_type: GraphRelationship | None = None,
        tenant_id: str | None = None,
    ) -> list[GraphNode]:
        """Return downstream outgoing neighbors."""
        if tenant_id and not self.has_node(node_id, tenant_id=tenant_id):
            return []
        succs = self.store.successors(
            node_id=node_id, relationship_type=relationship_type
        )
        if tenant_id:
            succs = [
                n
                for n in succs
                if (getattr(n, "tenant_id", None) or n.metadata.get("tenant_id"))
                == tenant_id
            ]
        return succs

    def in_degree(self, node_id: str) -> int:
        """Count incoming edges pointing into node_id."""
        return len(self.store.list_edges(target_node_id=node_id))

    def out_degree(self, node_id: str) -> int:
        """Count outgoing edges originating from node_id."""
        return len(self.store.list_edges(source_node_id=node_id))

    def degree(self, node_id: str) -> int:
        """Total degree of node_id (in_degree + out_degree)."""
        return self.in_degree(node_id) + self.out_degree(node_id)

    def subgraph(
        self, node_ids: Sequence[str], tenant_id: str | None = None
    ) -> KnowledgeGraph:
        """Extract induced subgraph containing only specified node_ids within tenant scope."""
        sub = KnowledgeGraph()
        id_set = set(node_ids)

        for nid in id_set:
            node = self.get_node(nid, tenant_id=tenant_id)
            if node:
                sub.add_node(node)

        allowed_ids = {n.node_id for n in sub.list_nodes()}
        for edge in self.list_edges():
            if (
                edge.source_node_id in allowed_ids
                and edge.target_node_id in allowed_ids
            ):
                if tenant_id:
                    edge_tenant = getattr(edge, "tenant_id", None)
                    if edge_tenant and edge_tenant != tenant_id:
                        continue
                sub.add_edge(edge)

        return sub

        return sub

    def clear(self) -> None:
        """Clear all contents."""
        self.store.clear()

    @property
    def node_count(self) -> int:
        """Total node count."""
        return self.store.node_count

    @property
    def edge_count(self) -> int:
        """Total edge count."""
        return self.store.edge_count

    # -------------------------------------------------------------------------
    # High-Level Interfaces (Lazy-loaded to avoid circular dependencies)
    # -------------------------------------------------------------------------

    @property
    def query(self) -> GraphQuery:
        """Return a GraphQuery interface over this graph."""
        from aireliability.graph.query import GraphQuery

        return GraphQuery(self)

    @property
    def traversal(self) -> GraphTraversal:
        """Return a GraphTraversal engine over this graph."""
        from aireliability.graph.traversal import GraphTraversal

        return GraphTraversal(self)

    @property
    def impact_analyzer(self) -> GraphImpactAnalyzer:
        """Return a GraphImpactAnalyzer engine over this graph."""
        from aireliability.graph.impact import GraphImpactAnalyzer

        return GraphImpactAnalyzer(self)

    @property
    def provenance(self) -> ProvenanceTracer:
        """Return a ProvenanceTracer engine over this graph."""
        from aireliability.graph.provenance import ProvenanceTracer

        return ProvenanceTracer(self)

    # -------------------------------------------------------------------------
    # Serialization and Diff
    # -------------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize entire graph to JSON-compatible dictionary."""
        from aireliability.graph.serialization import GraphSerializer

        return GraphSerializer.to_dict(self)

    def to_json(self, indent: int = 2) -> str:
        """Serialize entire graph to formatted JSON string."""
        from aireliability.graph.serialization import GraphSerializer

        return GraphSerializer.to_json(self, indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KnowledgeGraph:
        """Instantiate a KnowledgeGraph from a serialized dictionary."""
        from aireliability.graph.serialization import GraphSerializer

        return GraphSerializer.from_dict(data)

    @classmethod
    def from_json(cls, json_str: str) -> KnowledgeGraph:
        """Instantiate a KnowledgeGraph from a JSON string."""
        from aireliability.graph.serialization import GraphSerializer

        return GraphSerializer.from_json(json_str)

    def diff(self, other: KnowledgeGraph) -> GraphDiff:
        """Compute structural difference between this graph and another KnowledgeGraph."""
        from aireliability.graph.serialization import diff_graphs

        return diff_graphs(self, other)
