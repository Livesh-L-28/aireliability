"""Graph store abstractions and high-performance in-memory indexed graph store."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from aireliability.graph.models import (
    GraphEdge,
    GraphNode,
    GraphNodeType,
    GraphRelationship,
)


class GraphStore(ABC):
    """Abstract interface defining required graph storage capabilities."""

    @abstractmethod
    def add_node(self, node: GraphNode) -> GraphNode:
        """Add or update a node in the graph."""
        ...

    @abstractmethod
    def get_node(self, node_id: str) -> GraphNode | None:
        """Retrieve a node by its unique node_id."""
        ...

    @abstractmethod
    def update_node(self, node: GraphNode) -> GraphNode:
        """Update an existing node's metadata or attributes."""
        ...

    @abstractmethod
    def remove_node(self, node_id: str) -> bool:
        """Remove a node and all incident edges."""
        ...

    @abstractmethod
    def has_node(self, node_id: str) -> bool:
        """Check if a node exists."""
        ...

    @abstractmethod
    def add_edge(self, edge: GraphEdge) -> GraphEdge:
        """Add or update a directed edge."""
        ...

    @abstractmethod
    def get_edge(self, edge_id: str) -> GraphEdge | None:
        """Retrieve an edge by its unique edge_id."""
        ...

    @abstractmethod
    def remove_edge(self, edge_id: str) -> bool:
        """Remove an edge by edge_id."""
        ...

    @abstractmethod
    def has_edge(self, edge_id: str) -> bool:
        """Check if an edge exists."""
        ...

    @abstractmethod
    def list_nodes(
        self,
        node_type: GraphNodeType | None = None,
        tags: Sequence[str] | None = None,
    ) -> list[GraphNode]:
        """Query nodes filtered by type or tags."""
        ...

    @abstractmethod
    def list_edges(
        self,
        relationship_type: GraphRelationship | None = None,
        source_node_id: str | None = None,
        target_node_id: str | None = None,
    ) -> list[GraphEdge]:
        """Query edges filtered by relationship or endpoint IDs."""
        ...

    @abstractmethod
    def neighbors(
        self,
        node_id: str,
        direction: str = "both",
        relationship_type: GraphRelationship | None = None,
    ) -> list[GraphNode]:
        """Find adjacent nodes along directed edges."""
        ...

    @abstractmethod
    def predecessors(
        self,
        node_id: str,
        relationship_type: GraphRelationship | None = None,
    ) -> list[GraphNode]:
        """Retrieve incoming adjacent nodes (sources of incoming edges)."""
        ...

    @abstractmethod
    def successors(
        self,
        node_id: str,
        relationship_type: GraphRelationship | None = None,
    ) -> list[GraphNode]:
        """Retrieve outgoing adjacent nodes (targets of outgoing edges)."""
        ...

    @abstractmethod
    def clear(self) -> None:
        """Clear all nodes and edges from storage."""
        ...

    @property
    @abstractmethod
    def node_count(self) -> int:
        """Total number of nodes currently stored."""
        ...

    @property
    @abstractmethod
    def edge_count(self) -> int:
        """Total number of edges currently stored."""
        ...


class InMemoryGraphStore(GraphStore):
    """High-performance in-memory graph store with multi-index acceleration."""

    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[str, GraphEdge] = {}

        # Secondary indexes for O(1) / O(degree) queries
        self._nodes_by_type: dict[GraphNodeType, set[str]] = {}
        self._edges_by_type: dict[GraphRelationship, set[str]] = {}
        self._out_edges: dict[str, set[str]] = {}  # source_id -> {edge_ids}
        self._in_edges: dict[str, set[str]] = {}  # target_id -> {edge_ids}
        self._edge_by_pair: dict[tuple[str, str, GraphRelationship], str] = {}

    def add_node(self, node: GraphNode) -> GraphNode:
        """Idempotently add or update a node."""
        old = self._nodes.get(node.node_id)
        if old is not None and old.node_type != node.node_type:
            # Clean old type index if type changed
            self._nodes_by_type.get(old.node_type, set()).discard(old.node_id)

        self._nodes[node.node_id] = node
        self._nodes_by_type.setdefault(node.node_type, set()).add(node.node_id)
        self._out_edges.setdefault(node.node_id, set())
        self._in_edges.setdefault(node.node_id, set())
        return node

    def get_node(self, node_id: str) -> GraphNode | None:
        """Fetch node by node_id."""
        return self._nodes.get(node_id)

    def update_node(self, node: GraphNode) -> GraphNode:
        """Update node attributes."""
        return self.add_node(node)

    def remove_node(self, node_id: str) -> bool:
        """Remove a node and all incident incoming and outgoing edges."""
        if node_id not in self._nodes:
            return False

        # Remove outgoing edges
        out_ids = list(self._out_edges.get(node_id, set()))
        for eid in out_ids:
            self.remove_edge(eid)

        # Remove incoming edges
        in_ids = list(self._in_edges.get(node_id, set()))
        for eid in in_ids:
            self.remove_edge(eid)

        node = self._nodes.pop(node_id)
        self._nodes_by_type.get(node.node_type, set()).discard(node_id)
        self._out_edges.pop(node_id, None)
        self._in_edges.pop(node_id, None)
        return True

    def has_node(self, node_id: str) -> bool:
        """Check if node_id exists."""
        return node_id in self._nodes

    def add_edge(self, edge: GraphEdge) -> GraphEdge:
        """Idempotently add an edge. Auto-creates placeholder nodes if missing."""
        # Ensure source and target node containers exist
        self._out_edges.setdefault(edge.source_node_id, set())
        self._in_edges.setdefault(edge.target_node_id, set())

        # Check for existing duplicate edge with same source, target, relationship
        pair_key = (edge.source_node_id, edge.target_node_id, edge.relationship_type)
        existing_edge_id = self._edge_by_pair.get(pair_key)
        if existing_edge_id:
            # Replace existing edge with updated representation
            self.remove_edge(existing_edge_id)

        self._edges[edge.edge_id] = edge
        self._edge_by_pair[pair_key] = edge.edge_id
        self._edges_by_type.setdefault(edge.relationship_type, set()).add(edge.edge_id)
        self._out_edges[edge.source_node_id].add(edge.edge_id)
        self._in_edges[edge.target_node_id].add(edge.edge_id)
        return edge

    def get_edge(self, edge_id: str) -> GraphEdge | None:
        """Fetch edge by edge_id."""
        return self._edges.get(edge_id)

    def remove_edge(self, edge_id: str) -> bool:
        """Remove edge by edge_id."""
        edge = self._edges.pop(edge_id, None)
        if edge is None:
            return False

        pair_key = (edge.source_node_id, edge.target_node_id, edge.relationship_type)
        self._edge_by_pair.pop(pair_key, None)
        self._edges_by_type.get(edge.relationship_type, set()).discard(edge_id)

        if edge.source_node_id in self._out_edges:
            self._out_edges[edge.source_node_id].discard(edge_id)
        if edge.target_node_id in self._in_edges:
            self._in_edges[edge.target_node_id].discard(edge_id)
        return True

    def has_edge(self, edge_id: str) -> bool:
        """Check if edge exists."""
        return edge_id in self._edges

    def list_nodes(
        self,
        node_type: GraphNodeType | None = None,
        tags: Sequence[str] | None = None,
    ) -> list[GraphNode]:
        """List nodes matching type and tags."""
        if node_type is not None:
            node_ids = self._nodes_by_type.get(node_type, set())
            candidates = [self._nodes[nid] for nid in node_ids if nid in self._nodes]
        else:
            candidates = list(self._nodes.values())

        if tags:
            tag_set = set(tags)
            candidates = [c for c in candidates if tag_set.issubset(set(c.tags))]

        return candidates

    def list_edges(
        self,
        relationship_type: GraphRelationship | None = None,
        source_node_id: str | None = None,
        target_node_id: str | None = None,
    ) -> list[GraphEdge]:
        """Query edges with index-backed intersection."""
        if source_node_id is not None:
            edge_ids = self._out_edges.get(source_node_id, set())
        elif target_node_id is not None:
            edge_ids = self._in_edges.get(target_node_id, set())
        elif relationship_type is not None:
            edge_ids = self._edges_by_type.get(relationship_type, set())
        else:
            return list(self._edges.values())

        result: list[GraphEdge] = []
        for eid in edge_ids:
            edge = self._edges.get(eid)
            if edge is None:
                continue
            if (
                relationship_type is not None
                and edge.relationship_type != relationship_type
            ):
                continue
            if source_node_id is not None and edge.source_node_id != source_node_id:
                continue
            if target_node_id is not None and edge.target_node_id != target_node_id:
                continue
            result.append(edge)
        return result

    def neighbors(
        self,
        node_id: str,
        direction: str = "both",
        relationship_type: GraphRelationship | None = None,
    ) -> list[GraphNode]:
        """Return adjacent nodes in specified direction."""
        res_nodes: dict[str, GraphNode] = {}

        if direction in ("out", "outgoing", "both"):
            for e in self.list_edges(
                relationship_type=relationship_type, source_node_id=node_id
            ):
                target = self.get_node(e.target_node_id)
                if target:
                    res_nodes[target.node_id] = target

        if direction in ("in", "incoming", "both"):
            for e in self.list_edges(
                relationship_type=relationship_type, target_node_id=node_id
            ):
                source = self.get_node(e.source_node_id)
                if source:
                    res_nodes[source.node_id] = source

        return list(res_nodes.values())

    def predecessors(
        self,
        node_id: str,
        relationship_type: GraphRelationship | None = None,
    ) -> list[GraphNode]:
        """Return nodes with directed edges pointing into node_id."""
        return self.neighbors(
            node_id, direction="in", relationship_type=relationship_type
        )

    def successors(
        self,
        node_id: str,
        relationship_type: GraphRelationship | None = None,
    ) -> list[GraphNode]:
        """Return nodes with directed edges originating from node_id."""
        return self.neighbors(
            node_id, direction="out", relationship_type=relationship_type
        )

    def get_edges_between(
        self, source_node_id: str, target_node_id: str
    ) -> list[GraphEdge]:
        """Find all edges directly connecting source_node_id to target_node_id."""
        out_eids = self._out_edges.get(source_node_id, set())
        in_eids = self._in_edges.get(target_node_id, set())
        common = out_eids.intersection(in_eids)
        return [self._edges[eid] for eid in common if eid in self._edges]

    def clear(self) -> None:
        """Clear all nodes, edges, and indexes."""
        self._nodes.clear()
        self._edges.clear()
        self._nodes_by_type.clear()
        self._edges_by_type.clear()
        self._out_edges.clear()
        self._in_edges.clear()
        self._edge_by_pair.clear()

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)
