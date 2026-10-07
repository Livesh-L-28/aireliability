"""Unit tests for Phase 35 Graph Models and Enums."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from aireliability.graph.models import (
    GraphDiff,
    GraphEdge,
    GraphImpactReport,
    GraphNode,
    GraphNodeType,
    GraphRelationship,
)


def test_graph_node_types_taxonomy() -> None:
    """Verify standard node types are present in taxonomy."""
    assert GraphNodeType.DATASET == "DATASET"
    assert GraphNodeType.TEST_CASE == "TEST_CASE"
    assert GraphNodeType.MODEL == "MODEL"
    assert GraphNodeType.PROMPT == "PROMPT"
    assert GraphNodeType.TOOL == "TOOL"
    assert GraphNodeType.RETRIEVER == "RETRIEVER"
    assert GraphNodeType.EVALUATION == "EVALUATION"
    assert GraphNodeType.FAILURE == "FAILURE"
    assert GraphNodeType.ROOT_CAUSE == "ROOT_CAUSE"
    assert GraphNodeType.REGRESSION == "REGRESSION"
    assert GraphNodeType.INCIDENT == "INCIDENT"
    assert GraphNodeType.FAILURE_CLUSTER == "FAILURE_CLUSTER"
    assert len(GraphNodeType) >= 30


def test_graph_relationship_taxonomy() -> None:
    """Verify standard relationship types are defined."""
    assert GraphRelationship.CONTAINS == "CONTAINS"
    assert GraphRelationship.USED_MODEL == "USED_MODEL"
    assert GraphRelationship.USED_PROMPT == "USED_PROMPT"
    assert GraphRelationship.FAILED == "FAILED"
    assert GraphRelationship.HAS_ROOT_CAUSE == "HAS_ROOT_CAUSE"
    assert GraphRelationship.CAUSED_REGRESSION == "CAUSED_REGRESSION"
    assert GraphRelationship.CORRELATED_WITH == "CORRELATED_WITH"
    assert GraphRelationship.SUPPORTED_BY == "SUPPORTED_BY"
    assert len(GraphRelationship) >= 30


def test_graph_node_creation_valid() -> None:
    """Test valid GraphNode instantiation and convenience factory."""
    node = GraphNode.create(
        node_type=GraphNodeType.MODEL,
        source_id="gpt-4o",
        name="GPT-4 Omni",
        version="2024-05-13",
        environment="production",
        tags=["llm", "frontier"],
        confidence=0.95,
        metadata={"provider": "openai"},
    )
    assert node.node_id == "model:gpt-4o"
    assert node.node_type == GraphNodeType.MODEL
    assert node.name == "GPT-4 Omni"
    assert node.version == "2024-05-13"
    assert node.environment == "production"
    assert node.tags == ["llm", "frontier"]
    assert node.confidence == 0.95
    assert node.metadata == {"provider": "openai"}
    assert isinstance(node.created_at, datetime)


def test_graph_node_immutability() -> None:
    """Verify GraphNode is frozen and immutable."""
    node = GraphNode.create(
        node_type=GraphNodeType.PROMPT,
        source_id="sys_prompt_1",
    )
    with pytest.raises(ValidationError):
        node.name = "new_name"  # type: ignore[misc]


def test_graph_node_confidence_bounds() -> None:
    """Verify confidence values are clamped or validated."""
    node_low = GraphNode.create(
        node_type=GraphNodeType.MODEL,
        source_id="m1",
        confidence=-0.5,
    )
    assert node_low.confidence == 0.0

    node_high = GraphNode.create(
        node_type=GraphNodeType.MODEL,
        source_id="m2",
        confidence=1.5,
    )
    assert node_high.confidence == 1.0


def test_graph_edge_creation_valid() -> None:
    """Test valid GraphEdge instantiation with deterministic ID."""
    edge = GraphEdge.create(
        source_node_id="evaluation:eval_101",
        target_node_id="model:gpt-4o",
        relationship_type=GraphRelationship.USED_MODEL,
        confidence=0.99,
        evidence=["Report metadata indicates model:gpt-4o was evaluated"],
        metadata={"eval_run": "run_1"},
    )
    assert edge.edge_id == "edge:evaluation:eval_101->USED_MODEL->model:gpt-4o"
    assert edge.source_node_id == "evaluation:eval_101"
    assert edge.target_node_id == "model:gpt-4o"
    assert edge.relationship_type == GraphRelationship.USED_MODEL
    assert edge.is_causal is False
    assert edge.confidence == 0.99
    assert len(edge.evidence) == 1


def test_graph_diff_model() -> None:
    """Verify GraphDiff correctly detects whether changes exist."""
    diff_empty = GraphDiff()
    assert diff_empty.has_changes is False

    n = GraphNode.create(GraphNodeType.DATASET, "ds_1")
    diff_with_nodes = GraphDiff(added_nodes=[n])
    assert diff_with_nodes.has_changes is True


def test_graph_impact_report_model() -> None:
    """Verify GraphImpactReport data fields."""
    report = GraphImpactReport(
        root_node_id="model:gpt-4o",
        root_node_type=GraphNodeType.MODEL,
        affected_nodes_count=5,
        failure_count=2,
        regression_count=1,
        incident_count=0,
        safety_critical=False,
        security_critical=True,
        impact_score=0.45,
    )
    assert report.root_node_id == "model:gpt-4o"
    assert report.failure_count == 2
    assert report.security_critical is True
    assert report.impact_score == 0.45
