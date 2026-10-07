"""Unit tests for Phase 35 InMemoryGraphStore indexing, deduplication, and GraphStoreRegistry."""

import pytest

from aireliability.graph.models import (
    GraphEdge,
    GraphNode,
    GraphNodeType,
    GraphRelationship,
)
from aireliability.graph.registry import GraphStoreRegistry
from aireliability.graph.store import InMemoryGraphStore


def test_store_node_lifecycle() -> None:
    """Test adding, fetching, updating, and removing nodes."""
    store = InMemoryGraphStore()
    node = GraphNode.create(GraphNodeType.MODEL, "gpt-4o", name="GPT-4o")

    # Add node
    added = store.add_node(node)
    assert added.node_id == "model:gpt-4o"
    assert store.has_node("model:gpt-4o") is True
    assert store.node_count == 1

    # Get node
    fetched = store.get_node("model:gpt-4o")
    assert fetched is not None
    assert fetched.name == "GPT-4o"

    # Non-existent node
    assert store.get_node("model:non_existent") is None
    assert store.has_node("model:non_existent") is False

    # Remove node
    assert store.remove_node("model:gpt-4o") is True
    assert store.has_node("model:gpt-4o") is False
    assert store.node_count == 0
    assert store.remove_node("model:gpt-4o") is False


def test_store_edge_lifecycle_and_indexing() -> None:
    """Test adding, fetching, indexing, and removing directed edges."""
    store = InMemoryGraphStore()
    n1 = store.add_node(GraphNode.create(GraphNodeType.EVALUATION, "eval1"))
    n2 = store.add_node(GraphNode.create(GraphNodeType.MODEL, "model1"))

    edge = GraphEdge.create(
        source_node_id=n1.node_id,
        target_node_id=n2.node_id,
        relationship_type=GraphRelationship.USED_MODEL,
    )
    store.add_edge(edge)

    assert store.edge_count == 1
    assert store.has_edge(edge.edge_id) is True

    # Predecessors and successors
    succs = store.successors(n1.node_id)
    assert len(succs) == 1
    assert succs[0].node_id == n2.node_id

    preds = store.predecessors(n2.node_id)
    assert len(preds) == 1
    assert preds[0].node_id == n1.node_id

    # Filtered edges
    by_rel = store.list_edges(relationship_type=GraphRelationship.USED_MODEL)
    assert len(by_rel) == 1
    by_other = store.list_edges(relationship_type=GraphRelationship.CONTAINS)
    assert len(by_other) == 0

    # Neighbors
    both_nbrs = store.neighbors(n1.node_id, direction="both")
    assert len(both_nbrs) == 1


def test_store_deduplication() -> None:
    """Verify that re-adding identical nodes or edges updates rather than duplicating."""
    store = InMemoryGraphStore()
    n1 = GraphNode.create(GraphNodeType.PROMPT, "p1", name="Prompt V1")
    store.add_node(n1)
    assert store.node_count == 1

    # Re-add with updated metadata
    n1_updated = GraphNode.create(GraphNodeType.PROMPT, "p1", name="Prompt V1 Updated")
    store.add_node(n1_updated)
    assert store.node_count == 1
    assert store.get_node("prompt:p1").name == "Prompt V1 Updated"

    n2 = store.add_node(GraphNode.create(GraphNodeType.MODEL, "m1"))
    e1 = GraphEdge.create(
        n1.node_id, n2.node_id, GraphRelationship.USED_MODEL, confidence=0.8
    )
    store.add_edge(e1)
    assert store.edge_count == 1

    # Re-add edge with updated confidence
    e1_updated = GraphEdge.create(
        n1.node_id, n2.node_id, GraphRelationship.USED_MODEL, confidence=0.95
    )
    store.add_edge(e1_updated)
    assert store.edge_count == 1
    fetched_edge = store.get_edge(e1.edge_id)
    assert fetched_edge is not None
    assert fetched_edge.confidence == 0.95


def test_store_node_removal_cascades_edges() -> None:
    """Removing a node must clean up all incident incoming and outgoing edges."""
    store = InMemoryGraphStore()
    n1 = store.add_node(GraphNode.create(GraphNodeType.EVALUATION, "eval1"))
    n2 = store.add_node(GraphNode.create(GraphNodeType.FAILURE, "fail1"))
    n3 = store.add_node(GraphNode.create(GraphNodeType.ROOT_CAUSE, "rc1"))

    store.add_edge(GraphEdge.create(n1.node_id, n2.node_id, GraphRelationship.FAILED))
    store.add_edge(
        GraphEdge.create(n2.node_id, n3.node_id, GraphRelationship.HAS_ROOT_CAUSE)
    )
    assert store.node_count == 3
    assert store.edge_count == 2

    # Remove intermediate node n2 (failure)
    store.remove_node(n2.node_id)
    assert store.node_count == 2
    assert store.edge_count == 0  # Both incident edges removed


def test_store_list_filters() -> None:
    """Test listing nodes filtered by node_type and tags."""
    store = InMemoryGraphStore()
    store.add_node(GraphNode.create(GraphNodeType.MODEL, "m1", tags=["fast", "cheap"]))
    store.add_node(GraphNode.create(GraphNodeType.MODEL, "m2", tags=["frontier"]))
    store.add_node(GraphNode.create(GraphNodeType.PROMPT, "p1", tags=["fast"]))

    models = store.list_nodes(node_type=GraphNodeType.MODEL)
    assert len(models) == 2

    fast_nodes = store.list_nodes(tags=["fast"])
    assert len(fast_nodes) == 2


def test_graph_store_registry() -> None:
    """Test GraphStoreRegistry backend lookup and creation."""
    assert "memory" in GraphStoreRegistry.list_available()
    store = GraphStoreRegistry.create("memory")
    assert isinstance(store, InMemoryGraphStore)

    # Unknown backend
    with pytest.raises(KeyError):
        GraphStoreRegistry.create("unsupported_backend")
