"""Serialization, deserialization, export, and graph diffing."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aireliability.graph.models import (
    GraphDiff,
    GraphEdge,
    GraphNode,
)

if TYPE_CHECKING:
    from aireliability.graph.graph import KnowledgeGraph


class GraphSerializer:
    """Handles serialization and deserialization of KnowledgeGraph state."""

    SCHEMA_VERSION = "1.0.0"

    @classmethod
    def to_dict(cls, graph: KnowledgeGraph) -> dict[str, Any]:
        """Convert KnowledgeGraph to a serializable dictionary."""
        return {
            "schema_version": cls.SCHEMA_VERSION,
            "node_count": graph.node_count,
            "edge_count": graph.edge_count,
            "nodes": [node.model_dump(mode="json") for node in graph.list_nodes()],
            "edges": [edge.model_dump(mode="json") for edge in graph.list_edges()],
        }

    @classmethod
    def to_json(cls, graph: KnowledgeGraph, indent: int = 2) -> str:
        """Convert KnowledgeGraph to JSON string."""
        return json.dumps(cls.to_dict(graph), indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KnowledgeGraph:
        """Construct KnowledgeGraph from a serialized dictionary."""
        from aireliability.graph.graph import KnowledgeGraph

        graph = KnowledgeGraph()

        raw_nodes = data.get("nodes", [])
        for node_data in raw_nodes:
            # Parse enum and create node
            node = GraphNode.model_validate(node_data)
            graph.add_node(node)

        raw_edges = data.get("edges", [])
        for edge_data in raw_edges:
            edge = GraphEdge.model_validate(edge_data)
            graph.add_edge(edge)

        return graph

    @classmethod
    def from_json(cls, json_str: str) -> KnowledgeGraph:
        """Construct KnowledgeGraph from a JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)

    @classmethod
    def export_json(cls, graph: KnowledgeGraph, path: str | Path) -> None:
        """Save KnowledgeGraph snapshot to a JSON file."""
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(cls.to_json(graph), encoding="utf-8")

    @classmethod
    def import_json(cls, path: str | Path) -> KnowledgeGraph:
        """Load KnowledgeGraph snapshot from a JSON file."""
        file_path = Path(path)
        if not file_path.is_file():
            raise FileNotFoundError(f"KnowledgeGraph file not found: {path}")
        content = file_path.read_text(encoding="utf-8")
        return cls.from_json(content)

    @classmethod
    def export_csv_edges(cls, graph: KnowledgeGraph, path: str | Path) -> None:
        """Export edge list to a CSV file."""
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "edge_id",
                    "source_node_id",
                    "target_node_id",
                    "relationship_type",
                    "is_causal",
                    "confidence",
                    "created_at",
                ]
            )
            for edge in graph.list_edges():
                writer.writerow(
                    [
                        edge.edge_id,
                        edge.source_node_id,
                        edge.target_node_id,
                        edge.relationship_type.value,
                        edge.is_causal,
                        edge.confidence,
                        edge.created_at.isoformat(),
                    ]
                )

    @classmethod
    def export_jsonl(cls, graph: KnowledgeGraph, path: str | Path) -> None:
        """Export graph entities line-by-line in JSON Lines format."""
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("w", encoding="utf-8") as f:
            # First line: metadata
            f.write(
                json.dumps(
                    {
                        "type": "GRAPH_METADATA",
                        "schema_version": cls.SCHEMA_VERSION,
                        "node_count": graph.node_count,
                        "edge_count": graph.edge_count,
                    }
                )
                + "\n"
            )
            for node in graph.list_nodes():
                f.write(
                    json.dumps({"type": "NODE", "data": node.model_dump(mode="json")})
                    + "\n"
                )
            for edge in graph.list_edges():
                f.write(
                    json.dumps({"type": "EDGE", "data": edge.model_dump(mode="json")})
                    + "\n"
                )


def _normalize_json_like(obj: Any) -> Any:
    if isinstance(obj, (list, tuple)):
        return [_normalize_json_like(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _normalize_json_like(v) for k, v in obj.items()}
    return obj


def diff_graphs(graph_a: KnowledgeGraph, graph_b: KnowledgeGraph) -> GraphDiff:
    """Compare two KnowledgeGraphs and compute added, removed, and modified nodes/edges."""
    nodes_a = {n.node_id: n for n in graph_a.list_nodes()}
    nodes_b = {n.node_id: n for n in graph_b.list_nodes()}

    # Nodes
    added_nodes = [n for nid, n in nodes_b.items() if nid not in nodes_a]
    removed_nodes = [n for nid, n in nodes_a.items() if nid not in nodes_b]
    changed_nodes: list[dict[str, Any]] = []

    for nid in set(nodes_a.keys()) & set(nodes_b.keys()):
        na = nodes_a[nid]
        nb = nodes_b[nid]
        diffs: dict[str, Any] = {}
        if na.confidence != nb.confidence:
            diffs["confidence"] = {"old": na.confidence, "new": nb.confidence}
        if na.version != nb.version:
            diffs["version"] = {"old": na.version, "new": nb.version}
        if _normalize_json_like(na.metadata) != _normalize_json_like(nb.metadata):
            diffs["metadata"] = {"old": na.metadata, "new": nb.metadata}
        if na.tags != nb.tags:
            diffs["tags"] = {"old": na.tags, "new": nb.tags}
        if diffs:
            changed_nodes.append({"node_id": nid, "changes": diffs})

    # Edges
    edges_a = {e.edge_id: e for e in graph_a.list_edges()}
    edges_b = {e.edge_id: e for e in graph_b.list_edges()}

    added_edges = [e for eid, e in edges_b.items() if eid not in edges_a]
    removed_edges = [e for eid, e in edges_a.items() if eid not in edges_b]
    changed_edges: list[dict[str, Any]] = []

    for eid in set(edges_a.keys()) & set(edges_b.keys()):
        ea = edges_a[eid]
        eb = edges_b[eid]
        diffs = {}
        if ea.confidence != eb.confidence:
            diffs["confidence"] = {"old": ea.confidence, "new": eb.confidence}
        if ea.is_causal != eb.is_causal:
            diffs["is_causal"] = {"old": ea.is_causal, "new": eb.is_causal}
        if _normalize_json_like(ea.evidence) != _normalize_json_like(eb.evidence):
            diffs["evidence"] = {"old": ea.evidence, "new": eb.evidence}
        if _normalize_json_like(ea.metadata) != _normalize_json_like(eb.metadata):
            diffs["metadata"] = {"old": ea.metadata, "new": eb.metadata}
        if diffs:
            changed_edges.append({"edge_id": eid, "changes": diffs})

    return GraphDiff(
        added_nodes=added_nodes,
        removed_nodes=removed_nodes,
        added_edges=added_edges,
        removed_edges=removed_edges,
        changed_nodes=changed_nodes,
        changed_edges=changed_edges,
    )
