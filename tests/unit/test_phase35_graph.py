"""Unit tests for Phase 35 KnowledgeGraph orchestration and topology metrics."""

from aireliability.graph.graph import KnowledgeGraph
from aireliability.graph.models import (
    GraphEdge,
    GraphNode,
    GraphNodeType,
    GraphRelationship,
)


def test_knowledge_graph_degrees_and_metrics() -> None:
    """Test degree, in_degree, and out_degree calculations."""
    kg = KnowledgeGraph()
    n1 = kg.add_node(GraphNode.create(GraphNodeType.DATASET, "ds1"))
    n2 = kg.add_node(GraphNode.create(GraphNodeType.TEST_CASE, "tc1"))
    n3 = kg.add_node(GraphNode.create(GraphNodeType.TEST_CASE, "tc2"))

    kg.add_edge(GraphEdge.create(n1.node_id, n2.node_id, GraphRelationship.CONTAINS))
    kg.add_edge(GraphEdge.create(n1.node_id, n3.node_id, GraphRelationship.CONTAINS))

    assert kg.node_count == 3
    assert kg.edge_count == 2

    assert kg.out_degree(n1.node_id) == 2
    assert kg.in_degree(n1.node_id) == 0
    assert kg.degree(n1.node_id) == 2

    assert kg.in_degree(n2.node_id) == 1
    assert kg.out_degree(n2.node_id) == 0
    assert kg.degree(n2.node_id) == 1


def test_knowledge_graph_subgraph_extraction() -> None:
    """Test extracting induced subgraph for a subset of nodes."""
    kg = KnowledgeGraph()
    n1 = kg.add_node(GraphNode.create(GraphNodeType.DATASET, "ds1"))
    n2 = kg.add_node(GraphNode.create(GraphNodeType.TEST_CASE, "tc1"))
    n3 = kg.add_node(GraphNode.create(GraphNodeType.TEST_CASE, "tc2"))
    n4 = kg.add_node(GraphNode.create(GraphNodeType.MODEL, "m1"))

    kg.add_edge(GraphEdge.create(n1.node_id, n2.node_id, GraphRelationship.CONTAINS))
    kg.add_edge(GraphEdge.create(n1.node_id, n3.node_id, GraphRelationship.CONTAINS))
    kg.add_edge(GraphEdge.create(n2.node_id, n4.node_id, GraphRelationship.USED_MODEL))

    # Extract subgraph with n1 and n2 only
    sub = kg.subgraph([n1.node_id, n2.node_id])
    assert sub.node_count == 2
    assert sub.edge_count == 1
    assert sub.has_node(n1.node_id) is True
    assert sub.has_node(n2.node_id) is True
    assert sub.has_node(n3.node_id) is False
    assert sub.has_node(n4.node_id) is False


def test_knowledge_graph_property_engines() -> None:
    """Test that query, traversal, impact_analyzer, and provenance properties initialize properly."""
    kg = KnowledgeGraph()
    assert kg.query is not None
    assert kg.traversal is not None
    assert kg.impact_analyzer is not None
    assert kg.provenance is not None


def test_knowledge_graph_clear() -> None:
    """Test clearing all nodes and edges."""
    kg = KnowledgeGraph()
    n = kg.add_node(GraphNode.create(GraphNodeType.MODEL, "m1"))
    kg.add_edge(GraphEdge.create(n.node_id, n.node_id, GraphRelationship.VERSION_OF))
    assert kg.node_count == 1
    assert kg.edge_count == 1

    kg.clear()
    assert kg.node_count == 0
    assert kg.edge_count == 0
