"""Unit tests for Graph Provenance and Lineage tracing (Phase 35)."""

from aireliability.graph.graph import KnowledgeGraph
from aireliability.graph.models import (
    GraphEdge,
    GraphNode,
    GraphNodeType,
    GraphRelationship,
)
from aireliability.graph.provenance import ProvenanceTracer


def test_node_provenance() -> None:
    graph = KnowledgeGraph()
    tracer = ProvenanceTracer(graph)

    # Missing node
    assert tracer.get_node_provenance("nonexistent") == {}

    # Existing node with provenance
    node = GraphNode(
        node_id="model:gpt-4o",
        node_type=GraphNodeType.MODEL,
        name="GPT-4o",
        version="2024-08-06",
        source_id="eval-run-99",
        environment="production",
        confidence=0.98,
        tags=["llm", "frontier"],
        provenance={"source_type": "EvaluationReport", "report_id": "eval-run-99"},
        metadata={"provider": "openai"},
    )
    graph.add_node(node)

    prov = tracer.get_node_provenance("model:gpt-4o")
    assert prov["node_id"] == "model:gpt-4o"
    assert prov["node_type"] == "MODEL"
    assert prov["name"] == "GPT-4o"
    assert prov["version"] == "2024-08-06"
    assert prov["confidence"] == 0.98
    assert prov["provenance"]["source_type"] == "EvaluationReport"
    assert prov["metadata"]["provider"] == "openai"


def test_edge_provenance() -> None:
    graph = KnowledgeGraph()
    tracer = ProvenanceTracer(graph)

    # Missing edge
    assert tracer.get_edge_provenance("nonexistent") == {}

    # Causal edge
    edge_causal = GraphEdge(
        edge_id="e1",
        source_node_id="eval:1",
        target_node_id="fail:1",
        relationship_type=GraphRelationship.FAILED,
        is_causal=True,
        confidence=1.0,
        evidence=["AssertionError: score 0.4 < threshold 0.8"],
        provenance={"source_id": "eval:1"},
        metadata={"status": "verified"},
    )
    graph.add_edge(edge_causal)

    prov = tracer.get_edge_provenance("e1")
    assert prov["edge_id"] == "e1"
    assert prov["is_causal"] is True
    assert prov["relationship_type"] == "FAILED"
    assert prov["confidence"] == 1.0
    assert "AssertionError" in prov["evidence"][0]

    # Non-causal correlated edge
    edge_corr = GraphEdge(
        edge_id="e2",
        source_node_id="model:v1",
        target_node_id="fail:1",
        relationship_type=GraphRelationship.CORRELATED_WITH,
        is_causal=False,
        confidence=0.74,
        evidence=["Co-occurrence frequency = 12"],
        temporal={"first_seen": "2026-10-01", "last_seen": "2026-10-05"},
    )
    graph.add_edge(edge_corr)

    prov_corr = tracer.get_edge_provenance("e2")
    assert prov_corr["is_causal"] is False
    assert prov_corr["relationship_type"] == "CORRELATED_WITH"
    assert prov_corr["confidence"] == 0.74
    assert prov_corr["temporal"]["first_seen"] == "2026-10-01"


def test_trace_origin() -> None:
    graph = KnowledgeGraph()
    tracer = ProvenanceTracer(graph)

    # Nonexistent node
    assert tracer.trace_origin("missing") == []

    # Build chain: dataset -> test_case -> execution -> trace -> evaluation -> failure
    nodes = [
        GraphNode(node_id="ds:1", node_type=GraphNodeType.DATASET, name="Gold Dataset"),
        GraphNode(node_id="tc:1", node_type=GraphNodeType.TEST_CASE, name="TestCase 1"),
        GraphNode(node_id="exec:1", node_type=GraphNodeType.EXECUTION, name="Exec 1"),
        GraphNode(node_id="eval:1", node_type=GraphNodeType.EVALUATION, name="Eval 1"),
        GraphNode(node_id="fail:1", node_type=GraphNodeType.FAILURE, name="Failure 1"),
    ]
    for n in nodes:
        graph.add_node(n)

    graph.add_edge(
        GraphEdge(
            edge_id="e_ds_tc",
            source_node_id="ds:1",
            target_node_id="tc:1",
            relationship_type=GraphRelationship.CONTAINS,
        )
    )
    graph.add_edge(
        GraphEdge(
            edge_id="e_tc_exec",
            source_node_id="tc:1",
            target_node_id="exec:1",
            relationship_type=GraphRelationship.EXECUTED,
        )
    )
    graph.add_edge(
        GraphEdge(
            edge_id="e_exec_eval",
            source_node_id="exec:1",
            target_node_id="eval:1",
            relationship_type=GraphRelationship.EVALUATED,
        )
    )
    graph.add_edge(
        GraphEdge(
            edge_id="e_eval_fail",
            source_node_id="eval:1",
            target_node_id="fail:1",
            relationship_type=GraphRelationship.FAILED,
        )
    )

    origins = tracer.trace_origin("fail:1", max_depth=10)
    assert len(origins) >= 1
    assert origins[0]["origin_node_id"] == "ds:1"
    assert origins[0]["origin_node_type"] == "DATASET"
    assert origins[0]["depth"] == 4
    assert origins[0]["path"] == ["ds:1", "tc:1", "exec:1", "eval:1", "fail:1"]


def test_explain_relationship() -> None:
    graph = KnowledgeGraph()
    tracer = ProvenanceTracer(graph)

    # Direct causal edge
    graph.add_node(GraphNode(node_id="eval:1", node_type=GraphNodeType.EVALUATION))
    graph.add_node(GraphNode(node_id="fail:1", node_type=GraphNodeType.FAILURE))
    graph.add_edge(
        GraphEdge(
            edge_id="e_direct",
            source_node_id="eval:1",
            target_node_id="fail:1",
            relationship_type=GraphRelationship.FAILED,
            is_causal=True,
            confidence=1.0,
            evidence=["Test failed on accuracy metric"],
        )
    )

    exp_direct = tracer.explain_relationship("eval:1", "fail:1")
    assert len(exp_direct) == 1
    assert exp_direct[0]["is_causal"] is True
    assert "Direct causal link" in exp_direct[0]["summary"]

    # Direct non-causal correlated edge
    graph.add_node(GraphNode(node_id="prompt:p1", node_type=GraphNodeType.PROMPT))
    graph.add_edge(
        GraphEdge(
            edge_id="e_corr",
            source_node_id="prompt:p1",
            target_node_id="fail:1",
            relationship_type=GraphRelationship.CORRELATED_WITH,
            is_causal=False,
            confidence=0.85,
        )
    )
    exp_corr = tracer.explain_relationship("prompt:p1", "fail:1")
    assert len(exp_corr) == 1
    assert exp_corr[0]["is_causal"] is False
    assert "Observed correlation (non-causal)" in exp_corr[0]["summary"]

    # Indirect multi-hop connection
    graph.add_node(GraphNode(node_id="incident:inc1", node_type=GraphNodeType.INCIDENT))
    graph.add_edge(
        GraphEdge(
            edge_id="e_fail_inc",
            source_node_id="fail:1",
            target_node_id="incident:inc1",
            relationship_type=GraphRelationship.TRIGGERED,
            is_causal=True,
        )
    )
    exp_indirect = tracer.explain_relationship("eval:1", "incident:inc1")
    assert len(exp_indirect) == 1
    assert exp_indirect[0]["hops"] == 2
    assert exp_indirect[0]["path"] == ["eval:1", "fail:1", "incident:inc1"]

    # No connection
    graph.add_node(GraphNode(node_id="orphan:1", node_type=GraphNodeType.TOOL))
    exp_none = tracer.explain_relationship("eval:1", "orphan:1")
    assert exp_none == []


def test_get_lineage() -> None:
    graph = KnowledgeGraph()
    tracer = ProvenanceTracer(graph)

    # Missing node
    assert tracer.get_lineage("missing") == {}

    # Node with upstream and downstream
    graph.add_node(
        GraphNode(node_id="up:1", node_type=GraphNodeType.DATASET, name="DS 1")
    )
    graph.add_node(
        GraphNode(
            node_id="curr:1", node_type=GraphNodeType.EVALUATION, name="Eval Current"
        )
    )
    graph.add_node(
        GraphNode(node_id="down:1", node_type=GraphNodeType.FAILURE, name="Failure A")
    )
    graph.add_node(
        GraphNode(node_id="down:2", node_type=GraphNodeType.METRIC, name="Metric B")
    )

    graph.add_edge(
        GraphEdge(
            edge_id="e1",
            source_node_id="up:1",
            target_node_id="curr:1",
            relationship_type=GraphRelationship.EVALUATED,
        )
    )
    graph.add_edge(
        GraphEdge(
            edge_id="e2",
            source_node_id="curr:1",
            target_node_id="down:1",
            relationship_type=GraphRelationship.FAILED,
        )
    )
    graph.add_edge(
        GraphEdge(
            edge_id="e3",
            source_node_id="curr:1",
            target_node_id="down:2",
            relationship_type=GraphRelationship.MEASURED_BY,
        )
    )

    lineage = tracer.get_lineage("curr:1")
    assert lineage["node_id"] == "curr:1"
    assert lineage["node_type"] == "EVALUATION"
    assert lineage["upstream_count"] == 1
    assert lineage["upstream_nodes"][0]["node_id"] == "up:1"
    assert lineage["downstream_count"] == 2
    downstream_ids = {d["node_id"] for d in lineage["downstream_nodes"]}
    assert downstream_ids == {"down:1", "down:2"}
