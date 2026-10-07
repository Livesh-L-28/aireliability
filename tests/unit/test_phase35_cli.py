"""Unit tests for Phase 35 Knowledge Graph CLI commands."""

import json
from pathlib import Path

import pytest

from aireliability.cli import main
from aireliability.graph.graph import KnowledgeGraph
from aireliability.graph.models import (
    GraphEdge,
    GraphNode,
    GraphNodeType,
    GraphRelationship,
)
from aireliability.graph.serialization import GraphSerializer


@pytest.fixture
def sample_graph_file(tmp_path: Path) -> Path:
    graph = KnowledgeGraph()
    m = GraphNode.create(GraphNodeType.MODEL, "gpt-4o", name="GPT-4o", tags=["openai"])
    ev = GraphNode.create(GraphNodeType.EVALUATION, "eval-1", name="Evaluation Run 1")
    f = GraphNode.create(
        GraphNodeType.FAILURE,
        "fail-1",
        name="Hallucination Bug",
        metadata={"severity": "HIGH"},
    )
    rc = GraphNode.create(
        GraphNodeType.ROOT_CAUSE,
        "rc-1",
        name="Outdated Context Window",
        metadata={"severity": "HIGH"},
    )
    reg = GraphNode.create(
        GraphNodeType.REGRESSION,
        "reg-1",
        name="Regression in QA",
        metadata={"dataset": "ds-v1"},
    )
    inc = GraphNode.create(
        GraphNodeType.INCIDENT,
        "inc-1",
        name="Prod Incident #101",
        metadata={"severity": "P1", "root_cause": "rc-1"},
    )

    for n in [m, ev, f, rc, reg, inc]:
        graph.add_node(n)

    graph.add_edge(GraphEdge.create(m.node_id, ev.node_id, GraphRelationship.EVALUATED))
    graph.add_edge(GraphEdge.create(ev.node_id, f.node_id, GraphRelationship.FAILED))
    graph.add_edge(
        GraphEdge.create(f.node_id, rc.node_id, GraphRelationship.HAS_ROOT_CAUSE)
    )
    graph.add_edge(
        GraphEdge.create(f.node_id, reg.node_id, GraphRelationship.CAUSED_REGRESSION)
    )
    graph.add_edge(
        GraphEdge.create(rc.node_id, inc.node_id, GraphRelationship.TRIGGERED)
    )

    file_path = tmp_path / "graph.json"
    GraphSerializer.export_json(graph, file_path)
    return file_path


def test_cli_graph_inspect(
    sample_graph_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["graph", "inspect", str(sample_graph_file)])
    captured = capsys.readouterr().out
    assert code == 0
    assert "Knowledge Graph Inspection:" in captured
    assert "Total Nodes: 6" in captured
    assert "Total Edges: 5" in captured


def test_cli_graph_inspect_json(
    sample_graph_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["graph", "inspect", str(sample_graph_file), "--json"])
    captured = capsys.readouterr().out
    assert code == 0
    data = json.loads(captured)
    assert data["node_count"] == 6
    assert data["edge_count"] == 5
    assert "MODEL" in data["node_types"]


def test_cli_graph_build(
    sample_graph_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_file = tmp_path / "rebuilt.json"
    code = main(["graph", "build", str(sample_graph_file), "-o", str(out_file)])
    captured = capsys.readouterr().out
    assert code == 0
    assert "Knowledge Graph built successfully" in captured
    assert out_file.exists()


def test_cli_graph_query(
    sample_graph_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["graph", "query", str(sample_graph_file), "--type", "MODEL"])
    captured = capsys.readouterr().out
    assert code == 0
    assert "Found 1 matching nodes:" in captured
    assert "model:gpt-4o" in captured


def test_cli_graph_query_json(
    sample_graph_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["graph", "query", str(sample_graph_file), "--type", "MODEL", "--json"])
    captured = capsys.readouterr().out
    assert code == 0
    nodes = json.loads(captured)
    assert len(nodes) == 1
    assert nodes[0]["node_id"] == "model:gpt-4o"


def test_cli_graph_neighbors(
    sample_graph_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "graph",
            "neighbors",
            str(sample_graph_file),
            "--node",
            "model:gpt-4o",
            "--direction",
            "outgoing",
        ]
    )
    captured = capsys.readouterr().out
    assert code == 0
    assert "evaluation:eval-1" in captured


def test_cli_graph_path(
    sample_graph_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "graph",
            "path",
            str(sample_graph_file),
            "--from",
            "model:gpt-4o",
            "--to",
            "incident:inc-1",
        ]
    )
    captured = capsys.readouterr().out
    assert code == 0
    assert "Path found (4 hops):" in captured
    assert (
        "model:gpt-4o -> evaluation:eval-1 -> failure:fail-1 -> root_cause:rc-1 -> incident:inc-1"
        in captured
    )


def test_cli_graph_impact(
    sample_graph_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "graph",
            "impact",
            str(sample_graph_file),
            "--node",
            "model:gpt-4o",
            "--json",
        ]
    )
    captured = capsys.readouterr().out
    assert code == 0
    report = json.loads(captured)
    assert report["root_node_id"] == "model:gpt-4o"
    assert report["failure_count"] == 1
    assert report["incident_count"] == 1
    assert report["impact_score"] > 0.0


def test_cli_graph_failures(
    sample_graph_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["graph", "failures", str(sample_graph_file), "--model", "gpt-4o"])
    captured = capsys.readouterr().out
    assert code == 0
    assert "failure:fail-1" in captured


def test_cli_graph_regressions(
    sample_graph_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["graph", "regressions", str(sample_graph_file), "--dataset", "ds-v1"])
    captured = capsys.readouterr().out
    assert code == 0
    assert "regression:reg-1" in captured


def test_cli_graph_incidents(
    sample_graph_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["graph", "incidents", str(sample_graph_file), "--root-cause", "rc-1"])
    captured = capsys.readouterr().out
    assert code == 0
    assert "incident:inc-1" in captured


def test_cli_graph_root_causes(
    sample_graph_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        ["graph", "root-causes", str(sample_graph_file), "--id", "root_cause:rc-1"]
    )
    captured = capsys.readouterr().out
    assert code == 0
    assert "Root Cause History for 'root_cause:rc-1':" in captured
    assert "failure:fail-1" in captured


def test_cli_graph_export(sample_graph_file: Path, tmp_path: Path) -> None:
    csv_out = tmp_path / "out_edges.csv"
    code = main(
        [
            "graph",
            "export",
            str(sample_graph_file),
            "-o",
            str(csv_out),
            "--format",
            "csv",
        ]
    )
    assert code == 0
    assert csv_out.exists()
    assert "source_node_id,target_node_id" in csv_out.read_text(encoding="utf-8")

    jsonl_out = tmp_path / "out.jsonl"
    code_jl = main(
        [
            "graph",
            "export",
            str(sample_graph_file),
            "-o",
            str(jsonl_out),
            "--format",
            "jsonl",
        ]
    )
    assert code_jl == 0
    assert jsonl_out.exists()


def test_cli_graph_diff(
    sample_graph_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Create second graph with an added node
    g2 = GraphSerializer.import_json(sample_graph_file)
    g2.add_node(GraphNode.create(GraphNodeType.TOOL, "calculator"))
    f2 = tmp_path / "graph2.json"
    GraphSerializer.export_json(g2, f2)

    code = main(["graph", "diff", str(sample_graph_file), str(f2)])
    captured = capsys.readouterr().out
    assert code == 0
    assert "Added nodes: 1" in captured
    assert "Removed nodes: 0" in captured


def test_cli_graph_error_handling(capsys: pytest.CaptureFixture[str]) -> None:
    # Missing file for inspect
    code = main(["graph", "inspect", "nonexistent_file_xyz.json"])
    assert code == 1
    err = capsys.readouterr().err
    assert "Error loading graph" in err
