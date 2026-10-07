"""Unit tests for Phase 35 GraphTraversal engine."""

import pytest

from aireliability.graph.graph import KnowledgeGraph
from aireliability.graph.models import (
    GraphEdge,
    GraphNode,
    GraphNodeType,
    GraphRelationship,
)
from aireliability.graph.traversal import GraphTraversal


@pytest.fixture
def sample_traversal_graph() -> KnowledgeGraph:
    """Build a sample DAG with a diamond pattern and attached branches.

    n1 (DATASET) -> n2 (TEST_CASE) -> n3 (EXECUTION) -> n4 (EVALUATION) -> n5 (FAILURE)
                                                      -> n6 (METRIC)
    n4 -> n7 (ROOT_CAUSE)
    """
    kg = KnowledgeGraph()
    n1 = kg.add_node(GraphNode.create(GraphNodeType.DATASET, "ds1"))
    n2 = kg.add_node(GraphNode.create(GraphNodeType.TEST_CASE, "tc1"))
    n3 = kg.add_node(GraphNode.create(GraphNodeType.EXECUTION, "ex1"))
    n4 = kg.add_node(GraphNode.create(GraphNodeType.EVALUATION, "eval1"))
    n5 = kg.add_node(GraphNode.create(GraphNodeType.FAILURE, "f1"))
    n6 = kg.add_node(GraphNode.create(GraphNodeType.METRIC, "acc"))
    n7 = kg.add_node(GraphNode.create(GraphNodeType.ROOT_CAUSE, "rc1"))

    kg.add_edge(GraphEdge.create(n1.node_id, n2.node_id, GraphRelationship.CONTAINS))
    kg.add_edge(GraphEdge.create(n2.node_id, n3.node_id, GraphRelationship.EXECUTED))
    kg.add_edge(GraphEdge.create(n3.node_id, n4.node_id, GraphRelationship.EVALUATED))
    kg.add_edge(GraphEdge.create(n4.node_id, n5.node_id, GraphRelationship.FAILED))
    kg.add_edge(GraphEdge.create(n4.node_id, n6.node_id, GraphRelationship.MEASURED_BY))
    kg.add_edge(
        GraphEdge.create(n4.node_id, n7.node_id, GraphRelationship.HAS_ROOT_CAUSE)
    )

    return kg


def test_bfs_traversal(sample_traversal_graph: KnowledgeGraph) -> None:
    """Test breadth-first traversal respects depth and node limits."""
    t = GraphTraversal(sample_traversal_graph)
    # Depth 1 from ds1 -> tc1 only
    res_d1 = t.bfs("dataset:ds1", max_depth=1)
    assert len(res_d1) == 1
    assert res_d1[0].node_id == "test_case:tc1"

    # Depth 2 -> tc1, ex1
    res_d2 = t.bfs("dataset:ds1", max_depth=2)
    assert len(res_d2) == 2
    assert [n.node_id for n in res_d2] == ["test_case:tc1", "execution:ex1"]

    # Max nodes limit
    res_limited = t.bfs("dataset:ds1", max_depth=5, max_nodes=2)
    assert len(res_limited) == 2


def test_dfs_traversal(sample_traversal_graph: KnowledgeGraph) -> None:
    """Test depth-first traversal."""
    t = GraphTraversal(sample_traversal_graph)
    res = t.dfs("dataset:ds1", max_depth=5)
    assert len(res) == 6  # all descendants reachable


def test_traversal_filters(sample_traversal_graph: KnowledgeGraph) -> None:
    """Test filtering by relationship type and node type."""
    t = GraphTraversal(sample_traversal_graph)

    # Filter by node type: METRIC only
    metrics = t.bfs("evaluation:eval1", max_depth=2, node_types=[GraphNodeType.METRIC])
    assert len(metrics) == 1
    assert metrics[0].node_id == "metric:acc"

    # Filter by relationship type: FAILED only
    failures = t.bfs(
        "evaluation:eval1", max_depth=2, relationship_types=[GraphRelationship.FAILED]
    )
    assert len(failures) == 1
    assert failures[0].node_id == "failure:f1"


def test_traversal_direction(sample_traversal_graph: KnowledgeGraph) -> None:
    """Test incoming, outgoing, and both direction traversal."""
    t = GraphTraversal(sample_traversal_graph)

    # Incoming from evaluation:eval1 -> ex1
    incoming = t.bfs("evaluation:eval1", max_depth=1, direction="incoming")
    assert len(incoming) == 1
    assert incoming[0].node_id == "execution:ex1"

    # Outgoing from evaluation:eval1 -> f1, acc, rc1
    outgoing = t.bfs("evaluation:eval1", max_depth=1, direction="outgoing")
    assert len(outgoing) == 3


def test_find_path(sample_traversal_graph: KnowledgeGraph) -> None:
    """Test shortest path computation."""
    t = GraphTraversal(sample_traversal_graph)
    path = t.find_path("dataset:ds1", "failure:f1")
    assert path == [
        "dataset:ds1",
        "test_case:tc1",
        "execution:ex1",
        "evaluation:eval1",
        "failure:f1",
    ]

    # Non-existent path
    assert t.find_path("failure:f1", "dataset:ds1", direction="outgoing") is None


def test_cycle_detection() -> None:
    """Test cycle detection in cyclic graphs."""
    kg = KnowledgeGraph()
    n1 = kg.add_node(
        GraphNode.create(
            GraphNodeType.SERVICE
            if hasattr(GraphNodeType, "SERVICE")
            else GraphNodeType.MODEL,
            "a",
        )
    )
    n2 = kg.add_node(
        GraphNode.create(
            GraphNodeType.SERVICE
            if hasattr(GraphNodeType, "SERVICE")
            else GraphNodeType.MODEL,
            "b",
        )
    )
    n3 = kg.add_node(
        GraphNode.create(
            GraphNodeType.SERVICE
            if hasattr(GraphNodeType, "SERVICE")
            else GraphNodeType.MODEL,
            "c",
        )
    )

    kg.add_edge(GraphEdge.create(n1.node_id, n2.node_id, GraphRelationship.DEPENDS_ON))
    kg.add_edge(GraphEdge.create(n2.node_id, n3.node_id, GraphRelationship.DEPENDS_ON))
    kg.add_edge(GraphEdge.create(n3.node_id, n1.node_id, GraphRelationship.DEPENDS_ON))

    t = GraphTraversal(kg)
    cycles = t.find_cycles()
    assert len(cycles) >= 1
    assert set(cycles[0]) == {n1.node_id, n2.node_id, n3.node_id}


def test_get_reachable_subgraph(sample_traversal_graph: KnowledgeGraph) -> None:
    """Test extracting reachable subgraph."""
    t = GraphTraversal(sample_traversal_graph)
    sub = t.get_reachable_subgraph("evaluation:eval1", max_depth=2)
    assert sub.node_count == 4  # eval1 + f1 + acc + rc1
    assert sub.has_node("evaluation:eval1") is True
    assert sub.has_node("failure:f1") is True
    assert sub.has_node("dataset:ds1") is False
