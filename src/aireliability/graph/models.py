"""Strongly typed data models for the AI Reliability Knowledge Graph (Phase 35)."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def _generate_id(prefix: str = "node") -> str:
    """Generate a unique identifier with a given prefix."""
    return f"{prefix}_{uuid4().hex[:12]}"


def _utc_now() -> datetime:
    """Return current datetime in UTC timezone."""
    return datetime.now(UTC)


class GraphNodeType(StrEnum):
    """Taxonomy of node types supported in the AI Reliability Knowledge Graph."""

    DATASET = "DATASET"
    DATASET_VERSION = "DATASET_VERSION"
    TEST_CASE = "TEST_CASE"
    EXECUTION = "EXECUTION"
    TRACE = "TRACE"
    TRACE_STEP = "TRACE_STEP"
    MODEL = "MODEL"
    MODEL_VERSION = "MODEL_VERSION"
    PROMPT = "PROMPT"
    PROMPT_VERSION = "PROMPT_VERSION"
    TOOL = "TOOL"
    TOOL_VERSION = "TOOL_VERSION"
    RETRIEVER = "RETRIEVER"
    RERANKER = "RERANKER"
    EMBEDDING_MODEL = "EMBEDDING_MODEL"
    EVALUATION = "EVALUATION"
    METRIC = "METRIC"
    FAILURE = "FAILURE"
    ROOT_CAUSE = "ROOT_CAUSE"
    REGRESSION = "REGRESSION"
    INCIDENT = "INCIDENT"
    EXPERIMENT = "EXPERIMENT"
    BASELINE = "BASELINE"
    DEPLOYMENT = "DEPLOYMENT"
    ENVIRONMENT = "ENVIRONMENT"
    PRODUCTION_EVENT = "PRODUCTION_EVENT"
    PATTERN = "PATTERN"
    FAILURE_CLUSTER = "FAILURE_CLUSTER"
    TREND = "TREND"
    RECOMMENDATION = "RECOMMENDATION"
    AGENT = "AGENT"
    AGENT_VERSION = "AGENT_VERSION"
    TASK = "TASK"
    GOAL_CHECK = "GOAL_CHECK"
    OBSERVATION = "OBSERVATION"
    # Phase 41: Safety Validation
    SAFETY_TEST = "SAFETY_TEST"
    ATTACK = "ATTACK"
    SAFETY_FINDING = "SAFETY_FINDING"
    SAFETY_CAMPAIGN = "SAFETY_CAMPAIGN"
    SAFETY_BASELINE = "SAFETY_BASELINE"
    SAFETY_REGRESSION = "SAFETY_REGRESSION"
    SAFETY_REMEDIATION = "SAFETY_REMEDIATION"
    # Phase 42: Prediction
    PREDICTION = "PREDICTION"
    FORECAST = "FORECAST"
    PREDICTION_BASELINE = "PREDICTION_BASELINE"
    # Phase 43: Dashboard
    DASHBOARD = "DASHBOARD"
    ALERT = "ALERT"
    # Phase 44: Policy Engine
    POLICY = "POLICY"
    POLICY_RULE = "POLICY_RULE"
    POLICY_DECISION = "POLICY_DECISION"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    # Phase 45 & 46: Multi-Tenancy & Platform
    ORGANIZATION = "ORGANIZATION"
    TENANT = "TENANT"
    PROJECT = "PROJECT"
    API_KEY = "API_KEY"
    JOB = "JOB"
    WEBHOOK = "WEBHOOK"


class GraphRelationship(StrEnum):
    """Taxonomy of relationship edge types in the AI Reliability Knowledge Graph."""

    CONTAINS = "CONTAINS"
    VERSION_OF = "VERSION_OF"
    DERIVED_FROM = "DERIVED_FROM"
    EXECUTED = "EXECUTED"
    PRODUCED = "PRODUCED"
    USED_MODEL = "USED_MODEL"
    USED_PROMPT = "USED_PROMPT"
    USED_TOOL = "USED_TOOL"
    USED_RETRIEVER = "USED_RETRIEVER"
    USED_RERANKER = "USED_RERANKER"
    USED_EMBEDDING = "USED_EMBEDDING"
    GENERATED = "GENERATED"
    EVALUATED = "EVALUATED"
    MEASURED_BY = "MEASURED_BY"
    FAILED = "FAILED"
    HAS_ROOT_CAUSE = "HAS_ROOT_CAUSE"
    CAUSED_REGRESSION = "CAUSED_REGRESSION"
    LINKED_TO = "LINKED_TO"
    TRIGGERED = "TRIGGERED"
    OCCURRED_IN = "OCCURRED_IN"
    BELONGS_TO = "BELONGS_TO"
    PART_OF = "PART_OF"
    CORRELATED_WITH = "CORRELATED_WITH"
    AFFECTS = "AFFECTS"
    RECOMMENDS = "RECOMMENDS"
    SUPPORTED_BY = "SUPPORTED_BY"
    PRECEDED = "PRECEDED"
    PRECEDES = "PRECEDES"
    FOLLOWED_BY = "FOLLOWED_BY"
    DEPENDS_ON = "DEPENDS_ON"
    RELATED_TO = "RELATED_TO"
    VERIFIED_BY = "VERIFIED_BY"
    TARGETS = "TARGETS"
    DETECTED = "DETECTED"
    VIOLATES = "VIOLATES"
    GENERATED_FROM = "GENERATED_FROM"
    MUTATED_FROM = "MUTATED_FROM"
    CAUSED = "CAUSED"
    REMEDIATED_BY = "REMEDIATED_BY"
    REGRESSED_TO = "REGRESSED_TO"
    PREDICTS = "PREDICTS"


class GraphNode(BaseModel):
    """Represents a discrete entity in the AI Reliability Knowledge Graph."""

    model_config = ConfigDict(frozen=True)

    node_id: str
    node_type: GraphNodeType
    name: str = ""
    version: str | None = None
    source_id: str | None = None
    environment: str | None = None
    tags: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=_utc_now)
    provenance: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str | None = None

    @classmethod
    def create(
        cls,
        node_type: GraphNodeType,
        source_id: str,
        name: str = "",
        version: str | None = None,
        environment: str | None = None,
        tags: list[str] | None = None,
        confidence: float = 1.0,
        provenance: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        tenant_id: str | None = None,
    ) -> GraphNode:
        """Create a GraphNode with a canonical formatted node_id."""
        canon_id = f"{node_type.value.lower()}:{source_id}"
        return cls(
            node_id=canon_id,
            node_type=node_type,
            name=name or source_id,
            version=version,
            source_id=source_id,
            environment=environment,
            tags=list(tags or []),
            confidence=max(0.0, min(1.0, confidence)),
            provenance=dict(provenance or {}),
            metadata=dict(metadata or {}),
            tenant_id=tenant_id,
        )


class GraphEdge(BaseModel):
    """Represents a directed relationship between two nodes in the graph."""

    model_config = ConfigDict(frozen=True)

    edge_id: str = Field(default_factory=lambda: _generate_id("edge"))
    source_node_id: str
    target_node_id: str
    relationship_type: GraphRelationship
    is_causal: bool = False
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=_utc_now)
    evidence: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str | None = None
    temporal: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def create(
        cls,
        source_node_id: str,
        target_node_id: str,
        relationship_type: GraphRelationship,
        is_causal: bool = False,
        confidence: float = 1.0,
        evidence: list[str] | None = None,
        provenance: dict[str, Any] | None = None,
        temporal: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> GraphEdge:
        """Generate a deterministic edge representation."""
        edge_id = f"edge:{source_node_id}->{relationship_type.value}->{target_node_id}"
        return cls(
            edge_id=edge_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            relationship_type=relationship_type,
            is_causal=is_causal,
            confidence=max(0.0, min(1.0, confidence)),
            evidence=list(evidence or []),
            provenance=dict(provenance or {}),
            temporal=dict(temporal or {}),
            metadata=dict(metadata or {}),
        )


class GraphDiff(BaseModel):
    """Structural difference between two KnowledgeGraph snapshots."""

    model_config = ConfigDict(frozen=True)

    added_nodes: list[GraphNode] = Field(default_factory=list)
    removed_nodes: list[GraphNode] = Field(default_factory=list)
    added_edges: list[GraphEdge] = Field(default_factory=list)
    removed_edges: list[GraphEdge] = Field(default_factory=list)
    changed_nodes: list[dict[str, Any]] = Field(default_factory=list)
    changed_edges: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """True if any structural or metadata diff exists."""
        return bool(
            self.added_nodes
            or self.removed_nodes
            or self.added_edges
            or self.removed_edges
            or self.changed_nodes
            or self.changed_edges
        )


class GraphImpactReport(BaseModel):
    """Quantitative and topological impact assessment originating from a root node."""

    model_config = ConfigDict(frozen=True)

    root_node_id: str
    root_node_type: GraphNodeType
    affected_nodes_count: int = 0
    affected_node_types: dict[str, int] = Field(default_factory=dict)
    severity_distribution: dict[str, int] = Field(default_factory=dict)
    failure_count: int = 0
    regression_count: int = 0
    incident_count: int = 0
    safety_critical: bool = False
    security_critical: bool = False
    impact_score: float = Field(default=0.0, ge=0.0, le=1.0)
    impact_paths: list[list[str]] = Field(default_factory=list)
    supporting_evidence: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
