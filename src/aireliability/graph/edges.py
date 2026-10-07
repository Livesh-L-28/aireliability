"""Edge creation and relationship factories for the AI Reliability Knowledge Graph."""

from __future__ import annotations

from typing import Any

from aireliability.graph.models import GraphEdge, GraphRelationship


def edge_contains(
    source_id: str,
    target_id: str,
    metadata: dict[str, Any] | None = None,
) -> GraphEdge:
    """Create a CONTAINS edge."""
    return GraphEdge.create(
        source_node_id=source_id,
        target_node_id=target_id,
        relationship_type=GraphRelationship.CONTAINS,
        metadata=metadata,
    )


def edge_executed(
    source_id: str,
    target_id: str,
    metadata: dict[str, Any] | None = None,
) -> GraphEdge:
    """Create an EXECUTED edge."""
    return GraphEdge.create(
        source_node_id=source_id,
        target_node_id=target_id,
        relationship_type=GraphRelationship.EXECUTED,
        metadata=metadata,
    )


def edge_used_model(
    source_id: str,
    model_node_id: str,
    metadata: dict[str, Any] | None = None,
) -> GraphEdge:
    """Create a USED_MODEL edge."""
    return GraphEdge.create(
        source_node_id=source_id,
        target_node_id=model_node_id,
        relationship_type=GraphRelationship.USED_MODEL,
        metadata=metadata,
    )


def edge_used_prompt(
    source_id: str,
    prompt_node_id: str,
    metadata: dict[str, Any] | None = None,
) -> GraphEdge:
    """Create a USED_PROMPT edge."""
    return GraphEdge.create(
        source_node_id=source_id,
        target_node_id=prompt_node_id,
        relationship_type=GraphRelationship.USED_PROMPT,
        metadata=metadata,
    )


def edge_used_tool(
    source_id: str,
    tool_node_id: str,
    metadata: dict[str, Any] | None = None,
) -> GraphEdge:
    """Create a USED_TOOL edge."""
    return GraphEdge.create(
        source_node_id=source_id,
        target_node_id=tool_node_id,
        relationship_type=GraphRelationship.USED_TOOL,
        metadata=metadata,
    )


def edge_used_retriever(
    source_id: str,
    retriever_node_id: str,
    metadata: dict[str, Any] | None = None,
) -> GraphEdge:
    """Create a USED_RETRIEVER edge."""
    return GraphEdge.create(
        source_node_id=source_id,
        target_node_id=retriever_node_id,
        relationship_type=GraphRelationship.USED_RETRIEVER,
        metadata=metadata,
    )


def edge_evaluated(
    source_id: str,
    eval_id: str,
    metadata: dict[str, Any] | None = None,
) -> GraphEdge:
    """Create an EVALUATED edge."""
    return GraphEdge.create(
        source_node_id=source_id,
        target_node_id=eval_id,
        relationship_type=GraphRelationship.EVALUATED,
        metadata=metadata,
    )


def edge_measured_by(
    eval_id: str,
    metric_id: str,
    metadata: dict[str, Any] | None = None,
) -> GraphEdge:
    """Create a MEASURED_BY edge."""
    return GraphEdge.create(
        source_node_id=eval_id,
        target_node_id=metric_id,
        relationship_type=GraphRelationship.MEASURED_BY,
        metadata=metadata,
    )


def edge_failed(
    source_id: str,
    failure_id: str,
    metadata: dict[str, Any] | None = None,
) -> GraphEdge:
    """Create a FAILED edge."""
    return GraphEdge.create(
        source_node_id=source_id,
        target_node_id=failure_id,
        relationship_type=GraphRelationship.FAILED,
        metadata=metadata,
    )


def edge_has_root_cause(
    failure_id: str,
    root_cause_id: str,
    confidence: float = 1.0,
    metadata: dict[str, Any] | None = None,
) -> GraphEdge:
    """Create a HAS_ROOT_CAUSE edge."""
    return GraphEdge.create(
        source_node_id=failure_id,
        target_node_id=root_cause_id,
        relationship_type=GraphRelationship.HAS_ROOT_CAUSE,
        confidence=confidence,
        metadata=metadata,
    )


def edge_caused_regression(
    source_id: str,
    regression_id: str,
    is_causal: bool = True,
    metadata: dict[str, Any] | None = None,
) -> GraphEdge:
    """Create a CAUSED_REGRESSION edge."""
    return GraphEdge.create(
        source_node_id=source_id,
        target_node_id=regression_id,
        relationship_type=GraphRelationship.CAUSED_REGRESSION,
        is_causal=is_causal,
        metadata=metadata,
    )


def edge_triggered(
    source_id: str,
    incident_id: str,
    metadata: dict[str, Any] | None = None,
) -> GraphEdge:
    """Create a TRIGGERED edge."""
    return GraphEdge.create(
        source_node_id=source_id,
        target_node_id=incident_id,
        relationship_type=GraphRelationship.TRIGGERED,
        metadata=metadata,
    )


def edge_linked_to(
    source_id: str,
    target_id: str,
    metadata: dict[str, Any] | None = None,
) -> GraphEdge:
    """Create a LINKED_TO edge."""
    return GraphEdge.create(
        source_node_id=source_id,
        target_node_id=target_id,
        relationship_type=GraphRelationship.LINKED_TO,
        metadata=metadata,
    )


def edge_correlated_with(
    source_id: str,
    target_id: str,
    strength: float = 0.5,
    is_causal: bool = False,
    evidence: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> GraphEdge:
    """Create a CORRELATED_WITH edge, explicitly guaranteeing non-causality by default."""
    meta = dict(metadata or {})
    meta["strength"] = strength
    return GraphEdge.create(
        source_node_id=source_id,
        target_node_id=target_id,
        relationship_type=GraphRelationship.CORRELATED_WITH,
        is_causal=is_causal,
        confidence=strength,
        evidence=evidence,
        metadata=meta,
    )


def edge_affects(
    source_id: str,
    target_id: str,
    metadata: dict[str, Any] | None = None,
) -> GraphEdge:
    """Create an AFFECTS edge."""
    return GraphEdge.create(
        source_node_id=source_id,
        target_node_id=target_id,
        relationship_type=GraphRelationship.AFFECTS,
        metadata=metadata,
    )


def edge_supported_by(
    source_id: str,
    target_id: str,
    confidence: float = 1.0,
    metadata: dict[str, Any] | None = None,
) -> GraphEdge:
    """Create a SUPPORTED_BY edge linking intelligence claims or recommendations to underlying evidence."""
    return GraphEdge.create(
        source_node_id=source_id,
        target_node_id=target_id,
        relationship_type=GraphRelationship.SUPPORTED_BY,
        confidence=confidence,
        metadata=metadata,
    )


def edge_recommends(
    rec_id: str,
    target_id: str,
    metadata: dict[str, Any] | None = None,
) -> GraphEdge:
    """Create a RECOMMENDS edge."""
    return GraphEdge.create(
        source_node_id=rec_id,
        target_node_id=target_id,
        relationship_type=GraphRelationship.RECOMMENDS,
        metadata=metadata,
    )


def edge_depends_on(
    dependent_id: str,
    dependency_id: str,
    metadata: dict[str, Any] | None = None,
) -> GraphEdge:
    """Create a DEPENDS_ON edge."""
    return GraphEdge.create(
        source_node_id=dependent_id,
        target_node_id=dependency_id,
        relationship_type=GraphRelationship.DEPENDS_ON,
        metadata=metadata,
    )
