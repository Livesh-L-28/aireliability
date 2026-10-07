"""Unit tests for Graph Serialization, Export, and Diffing (Phase 35)."""

from pathlib import Path

import pytest

from aireliability.graph.graph import KnowledgeGraph
from aireliability.graph.models import (
    GraphEdge,
    GraphNode,
    GraphNodeType,
    GraphRelationship,
)
from aireliability.graph.serialization import GraphSerializer, diff_graphs


def _sample_graph() -> KnowledgeGraph:
    graph = KnowledgeGraph()
    n1 = GraphNode.create(
        GraphNodeType.MODEL,
        "gpt-4o",
        name="GPT-4o",
        version="v1.0",
        tags=["openai"],
        confidence=0.95,
        metadata={"temp": 0.7},
    )
    n2 = GraphNode.create(
        GraphNodeType.FAILURE,
        "f-001",
        name="Hallucination Failure",
        tags=["output"],
        metadata={"severity": "HIGH"},
    )
    graph.add_node(n1)
    graph.add_node(n2)

    edge = GraphEdge.create(
        n1.node_id,
        n2.node_id,
        GraphRelationship.FAILED,
        is_causal=True,
        confidence=0.88,
        evidence=["Evaluated factuality score 0.3"],
        metadata={"batch": 1},
    )
    graph.add_edge(edge)
    return graph


def test_dict_roundtrip() -> None:
    original = _sample_graph()
    d = GraphSerializer.to_dict(original)

    assert d["schema_version"] == "1.0.0"
    assert d["node_count"] == 2
    assert d["edge_count"] == 1

    restored = GraphSerializer.from_dict(d)
    assert restored.node_count == 2
    assert restored.edge_count == 1
    assert restored.has_node("model:gpt-4o")
    assert restored.has_node("failure:f-001")

    node = restored.get_node("model:gpt-4o")
    assert node is not None
    assert node.version == "v1.0"
    assert node.tags == ["openai"]


def test_json_roundtrip() -> None:
    original = _sample_graph()
    json_str = GraphSerializer.to_json(original)
    assert isinstance(json_str, str)
    assert "model:gpt-4o" in json_str

    restored = GraphSerializer.from_json(json_str)
    assert restored.node_count == 2
    assert restored.edge_count == 1
    edge = restored.list_edges()[0]
    assert edge.relationship_type == GraphRelationship.FAILED
    assert edge.is_causal is True
    assert edge.confidence == 0.88


def test_file_export_import(tmp_path: Path) -> None:
    original = _sample_graph()
    export_path = tmp_path / "sub" / "graph.json"

    GraphSerializer.export_json(original, export_path)
    assert export_path.exists()

    restored = GraphSerializer.import_json(export_path)
    assert restored.node_count == original.node_count
    assert restored.edge_count == original.edge_count

    # Nonexistent file import error
    with pytest.raises(FileNotFoundError):
        GraphSerializer.import_json(tmp_path / "nonexistent.json")


def test_export_csv_edges(tmp_path: Path) -> None:
    graph = _sample_graph()
    csv_path = tmp_path / "edges.csv"

    GraphSerializer.export_csv_edges(graph, csv_path)
    assert csv_path.exists()

    content = csv_path.read_text(encoding="utf-8")
    lines = content.strip().splitlines()
    assert len(lines) == 2  # header + 1 edge
    assert "edge_id,source_node_id,target_node_id,relationship_type" in lines[0]
    assert "model:gpt-4o,failure:f-001,FAILED,True,0.88" in lines[1]


def test_export_jsonl(tmp_path: Path) -> None:
    graph = _sample_graph()
    jsonl_path = tmp_path / "graph.jsonl"

    GraphSerializer.export_jsonl(graph, jsonl_path)
    assert jsonl_path.exists()

    content = jsonl_path.read_text(encoding="utf-8")
    lines = content.strip().splitlines()
    assert len(lines) == 4  # 1 metadata + 2 nodes + 1 edge
    assert '"type": "GRAPH_METADATA"' in lines[0]
    assert '"type": "NODE"' in lines[1]
    assert '"type": "NODE"' in lines[2]
    assert '"type": "EDGE"' in lines[3]


def test_graph_diff_identical() -> None:
    g1 = _sample_graph()
    diff_self = diff_graphs(g1, g1)
    assert diff_self.has_changes is False
    assert len(diff_self.added_nodes) == 0
    assert len(diff_self.removed_nodes) == 0
    assert len(diff_self.changed_nodes) == 0


def test_graph_diff_changes() -> None:
    g1 = KnowledgeGraph()
    n1 = GraphNode.create(
        GraphNodeType.MODEL, "m1", version="v1", confidence=0.8, tags=["tag1"]
    )
    n2 = GraphNode.create(GraphNodeType.PROMPT, "p1")
    g1.add_node(n1)
    g1.add_node(n2)
    e1 = GraphEdge(
        edge_id="e1",
        source_node_id=n1.node_id,
        target_node_id=n2.node_id,
        relationship_type=GraphRelationship.USED_PROMPT,
        confidence=0.7,
        is_causal=False,
        evidence=["evidence 1"],
    )
    g1.add_edge(e1)

    g2 = KnowledgeGraph()
    # n1 modified: version v2, confidence 0.95, tags changed, metadata added
    n1_mod = GraphNode(
        node_id=n1.node_id,
        node_type=n1.node_type,
        version="v2",
        confidence=0.95,
        tags=["tag1", "tag2"],
        metadata={"updated": True},
    )
    # n2 removed in g2
    # n3 added in g2
    n3 = GraphNode.create(GraphNodeType.TOOL, "t1")
    g2.add_node(n1_mod)
    g2.add_node(n3)

    # e1 modified in g2
    e1_mod = GraphEdge(
        edge_id="e1",
        source_node_id=n1.node_id,
        target_node_id=n2.node_id,
        relationship_type=GraphRelationship.USED_PROMPT,
        confidence=0.99,
        is_causal=True,
        evidence=["new evidence"],
        metadata={"flag": 1},
    )
    # e2 added in g2
    e2 = GraphEdge(
        edge_id="e2",
        source_node_id=n1.node_id,
        target_node_id=n3.node_id,
        relationship_type=GraphRelationship.USED_TOOL,
    )
    g2.add_edge(e1_mod)
    g2.add_edge(e2)

    diff = diff_graphs(g1, g2)
    assert diff.has_changes is True

    # Added & removed nodes
    added_node_ids = {n.node_id for n in diff.added_nodes}
    assert added_node_ids == {n3.node_id}
    removed_node_ids = {n.node_id for n in diff.removed_nodes}
    assert removed_node_ids == {n2.node_id}

    # Changed node
    assert len(diff.changed_nodes) == 1
    ch_node = diff.changed_nodes[0]
    assert ch_node["node_id"] == n1.node_id
    assert ch_node["changes"]["version"]["new"] == "v2"
    assert ch_node["changes"]["confidence"]["new"] == 0.95

    # Added & removed edges
    added_edge_ids = {e.edge_id for e in diff.added_edges}
    assert added_edge_ids == {"e2"}
    assert len(diff.removed_edges) == 0

    # Changed edge
    assert len(diff.changed_edges) == 1
    ch_edge = diff.changed_edges[0]
    assert ch_edge["edge_id"] == "e1"
    assert ch_edge["changes"]["is_causal"]["new"] is True
    assert ch_edge["changes"]["confidence"]["new"] == 0.99
    assert ch_edge["changes"]["evidence"]["new"] == ["new evidence"]
