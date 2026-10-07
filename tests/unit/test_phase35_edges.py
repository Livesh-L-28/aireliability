"""Unit tests for Phase 35 Graph Edge factory functions and correlation vs causation semantics."""

from aireliability.graph.edges import (
    edge_affects,
    edge_caused_regression,
    edge_contains,
    edge_correlated_with,
    edge_depends_on,
    edge_evaluated,
    edge_executed,
    edge_failed,
    edge_has_root_cause,
    edge_measured_by,
    edge_recommends,
    edge_supported_by,
    edge_triggered,
    edge_used_model,
    edge_used_prompt,
    edge_used_retriever,
    edge_used_tool,
)
from aireliability.graph.models import GraphRelationship


def test_edge_contains_and_executed() -> None:
    """Test standard compositional edges."""
    e1 = edge_contains("dataset:ds1", "test_case:tc1")
    assert e1.source_node_id == "dataset:ds1"
    assert e1.target_node_id == "test_case:tc1"
    assert e1.relationship_type == GraphRelationship.CONTAINS

    e2 = edge_executed("execution:ex1", "trace:tr1")
    assert e2.relationship_type == GraphRelationship.EXECUTED


def test_edge_component_usage() -> None:
    """Test model, prompt, tool, and retriever usage edges."""
    e_model = edge_used_model("evaluation:eval1", "model:gpt-4o")
    assert e_model.relationship_type == GraphRelationship.USED_MODEL

    e_prompt = edge_used_prompt("evaluation:eval1", "prompt:sys_v1")
    assert e_prompt.relationship_type == GraphRelationship.USED_PROMPT

    e_tool = edge_used_tool("execution:ex1", "tool:calculator")
    assert e_tool.relationship_type == GraphRelationship.USED_TOOL

    e_ret = edge_used_retriever("evaluation:eval1", "retriever:hybrid")
    assert e_ret.relationship_type == GraphRelationship.USED_RETRIEVER


def test_edge_evaluation_and_metrics() -> None:
    """Test evaluated and measured_by edges."""
    e_ev = edge_evaluated("test_case:tc1", "evaluation:eval1")
    assert e_ev.relationship_type == GraphRelationship.EVALUATED

    e_mb = edge_measured_by("evaluation:eval1", "metric:accuracy")
    assert e_mb.relationship_type == GraphRelationship.MEASURED_BY


def test_edge_failures_and_root_causes() -> None:
    """Test failure, root-cause, regression, and incident edges."""
    e_fail = edge_failed("evaluation:eval1", "failure:f1")
    assert e_fail.relationship_type == GraphRelationship.FAILED

    e_rc = edge_has_root_cause("failure:f1", "root_cause:rc1", confidence=0.85)
    assert e_rc.relationship_type == GraphRelationship.HAS_ROOT_CAUSE
    assert e_rc.confidence == 0.85

    e_reg = edge_caused_regression(
        "evaluation:eval1", "regression:reg1", is_causal=True
    )
    assert e_reg.relationship_type == GraphRelationship.CAUSED_REGRESSION
    assert e_reg.is_causal is True

    e_trig = edge_triggered("root_cause:rc1", "incident:inc1")
    assert e_trig.relationship_type == GraphRelationship.TRIGGERED


def test_correlation_vs_causation_separation() -> None:
    """MANDATORY: Verify that edge_correlated_with is non-causal by default."""
    e_corr = edge_correlated_with(
        source_id="model:gpt-4o",
        target_id="metric:hallucination_rate",
        strength=0.78,
        evidence=["Observed 0.78 correlation across 5 evaluation runs"],
    )
    assert e_corr.relationship_type == GraphRelationship.CORRELATED_WITH
    assert e_corr.is_causal is False
    assert e_corr.confidence == 0.78
    assert len(e_corr.evidence) == 1
    assert e_corr.metadata["strength"] == 0.78

    # Explicit causal override requires explicit flag
    e_causal = edge_correlated_with(
        source_id="model:gpt-4o",
        target_id="metric:hallucination_rate",
        strength=0.99,
        is_causal=True,
    )
    assert e_causal.is_causal is True


def test_intelligence_edges() -> None:
    """Test supported_by, recommends, affects, and depends_on edges."""
    e_sup = edge_supported_by(
        "recommendation:rec1", "failure_cluster:fc1", confidence=0.92
    )
    assert e_sup.relationship_type == GraphRelationship.SUPPORTED_BY
    assert e_sup.confidence == 0.92

    e_rec = edge_recommends("recommendation:rec1", "model:gpt-4o")
    assert e_rec.relationship_type == GraphRelationship.RECOMMENDS

    e_aff = edge_affects("failure_cluster:fc1", "model:gpt-4o")
    assert e_aff.relationship_type == GraphRelationship.AFFECTS

    e_dep = edge_depends_on("service:auth", "model:embedding")
    assert e_dep.relationship_type == GraphRelationship.DEPENDS_ON
