"""Unit tests for Graph Impact Analysis (Phase 35)."""

import pytest

from aireliability.graph.graph import KnowledgeGraph
from aireliability.graph.impact import GraphImpactAnalyzer
from aireliability.graph.models import (
    GraphEdge,
    GraphNode,
    GraphNodeType,
    GraphRelationship,
)


def test_impact_analysis_nonexistent_node() -> None:
    graph = KnowledgeGraph()
    analyzer = GraphImpactAnalyzer(graph)

    with pytest.raises(KeyError, match="not found in knowledge graph"):
        analyzer.analyze("missing:node")


def test_impact_analysis_comprehensive() -> None:
    graph = KnowledgeGraph()
    analyzer = GraphImpactAnalyzer(graph)

    # Topology:
    # Model (m1)
    #   -> Evaluation (ev1)
    #        -> Failure (f1) [severity: HIGH, critical: true, tags: ["security"]]
    #             -> RootCause (rc1)
    #                  -> Incident (inc1) [severity: P0]
    #             -> Regression (reg1)
    #   -> Evaluation (ev2)
    #        -> Failure (f2) [severity: LOW]
    #   -> Recommendation (rec1) [title: "Rollback prompt to v1"]

    m1 = GraphNode.create(GraphNodeType.MODEL, "gpt-4-bad", name="Bad Model")
    ev1 = GraphNode.create(
        GraphNodeType.EVALUATION, "eval-1", metadata={"severity": "high"}
    )
    ev2 = GraphNode.create(
        GraphNodeType.EVALUATION, "eval-2", metadata={"severity": "low"}
    )
    f1 = GraphNode.create(
        GraphNodeType.FAILURE,
        "fail-1",
        tags=["security"],
        metadata={
            "severity": "HIGH",
            "critical": True,
            "evidence": "SQL injection bypass detected",
        },
    )
    f2 = GraphNode.create(GraphNodeType.FAILURE, "fail-2", metadata={"severity": "low"})
    rc1 = GraphNode.create(
        GraphNodeType.ROOT_CAUSE, "rc-1", name="Prompt Injection vulnerability"
    )
    inc1 = GraphNode.create(
        GraphNodeType.INCIDENT, "inc-1", metadata={"severity": "P0"}
    )
    reg1 = GraphNode.create(GraphNodeType.REGRESSION, "reg-1")
    rec1 = GraphNode.create(
        GraphNodeType.RECOMMENDATION, "rec-1", name="Rollback prompt to v1"
    )

    for node in [m1, ev1, ev2, f1, f2, rc1, inc1, reg1, rec1]:
        graph.add_node(node)

    graph.add_edge(
        GraphEdge.create(m1.node_id, ev1.node_id, GraphRelationship.EVALUATED)
    )
    graph.add_edge(
        GraphEdge.create(m1.node_id, ev2.node_id, GraphRelationship.EVALUATED)
    )
    graph.add_edge(GraphEdge.create(ev1.node_id, f1.node_id, GraphRelationship.FAILED))
    graph.add_edge(GraphEdge.create(ev2.node_id, f2.node_id, GraphRelationship.FAILED))
    graph.add_edge(
        GraphEdge.create(f1.node_id, rc1.node_id, GraphRelationship.HAS_ROOT_CAUSE)
    )
    graph.add_edge(
        GraphEdge.create(rc1.node_id, inc1.node_id, GraphRelationship.TRIGGERED)
    )
    graph.add_edge(
        GraphEdge.create(f1.node_id, reg1.node_id, GraphRelationship.CAUSED_REGRESSION)
    )
    graph.add_edge(
        GraphEdge.create(m1.node_id, rec1.node_id, GraphRelationship.RECOMMENDS)
    )

    report = analyzer.analyze(m1.node_id)

    assert report.root_node_id == m1.node_id
    assert report.root_node_type == GraphNodeType.MODEL
    assert report.affected_nodes_count == 8  # all other nodes are downstream
    assert report.failure_count == 2
    assert report.regression_count == 1
    assert report.incident_count == 1
    assert report.security_critical is True
    assert report.safety_critical is True  # Due to P0 incident
    assert report.impact_score > 0.5
    assert len(report.impact_paths) >= 3
    assert len(report.supporting_evidence) == 1
    assert "SQL injection" in report.supporting_evidence[0]["evidence"]
    assert "Rollback prompt to v1" in report.recommendations


def test_compute_blast_radius() -> None:
    graph = KnowledgeGraph()
    analyzer = GraphImpactAnalyzer(graph)

    # Empty / single node
    assert analyzer.compute_blast_radius("single") == 0.0

    n1 = GraphNode.create(GraphNodeType.MODEL, "m1")
    n2 = GraphNode.create(GraphNodeType.EVALUATION, "e1")
    n3 = GraphNode.create(GraphNodeType.FAILURE, "f1")
    n4 = GraphNode.create(GraphNodeType.TOOL, "t1")  # Unconnected

    graph.add_node(n1)
    graph.add_node(n2)
    graph.add_node(n3)
    graph.add_node(n4)

    graph.add_edge(
        GraphEdge.create(n1.node_id, n2.node_id, GraphRelationship.EVALUATED)
    )
    graph.add_edge(GraphEdge.create(n2.node_id, n3.node_id, GraphRelationship.FAILED))

    # Total nodes = 4. Reachable from n1 = [n2, n3] = 2.
    # Blast radius = 2 / (4 - 1) = 2/3 = 0.6667
    radius = analyzer.compute_blast_radius(n1.node_id)
    assert 0.66 <= radius <= 0.67

    # From n4 (no downstream connections)
    assert analyzer.compute_blast_radius(n4.node_id) == 0.0


def test_find_critical_paths() -> None:
    graph = KnowledgeGraph()
    analyzer = GraphImpactAnalyzer(graph)

    src = GraphNode.create(GraphNodeType.MODEL, "m1")
    mid = GraphNode.create(GraphNodeType.EVALUATION, "e1")
    crit_fail = GraphNode.create(
        GraphNodeType.FAILURE, "f_crit", metadata={"severity": "CRITICAL"}
    )
    normal_fail = GraphNode.create(
        GraphNodeType.FAILURE, "f_norm", metadata={"severity": "LOW"}
    )
    crit_inc = GraphNode.create(
        GraphNodeType.INCIDENT, "inc_crit", metadata={"severity": "P0"}
    )

    for n in [src, mid, crit_fail, normal_fail, crit_inc]:
        graph.add_node(n)

    graph.add_edge(
        GraphEdge.create(src.node_id, mid.node_id, GraphRelationship.EVALUATED)
    )
    graph.add_edge(
        GraphEdge.create(mid.node_id, crit_fail.node_id, GraphRelationship.FAILED)
    )
    graph.add_edge(
        GraphEdge.create(mid.node_id, normal_fail.node_id, GraphRelationship.FAILED)
    )
    graph.add_edge(
        GraphEdge.create(
            crit_fail.node_id, crit_inc.node_id, GraphRelationship.TRIGGERED
        )
    )

    crit_paths = analyzer.find_critical_paths(src.node_id)
    assert len(crit_paths) == 2  # One to crit_fail, one to crit_inc
    assert [src.node_id, mid.node_id, crit_fail.node_id] in crit_paths
    assert [src.node_id, mid.node_id, crit_fail.node_id, crit_inc.node_id] in crit_paths
