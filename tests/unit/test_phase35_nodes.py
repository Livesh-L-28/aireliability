"""Unit tests for Phase 35 Graph Node factory functions and security sanitization."""

from aireliability.graph.models import GraphNodeType
from aireliability.graph.nodes import (
    node_from_cluster,
    node_from_dataset,
    node_from_evaluation,
    node_from_execution,
    node_from_failure,
    node_from_incident,
    node_from_metric,
    node_from_model,
    node_from_pattern,
    node_from_prompt,
    node_from_recommendation,
    node_from_regression,
    node_from_retriever,
    node_from_root_cause,
    node_from_test_case,
    node_from_tool,
    node_from_trace,
    node_from_trace_step,
    node_from_trend,
)


def test_node_from_dataset_and_sanitization() -> None:
    """Test node_from_dataset sanitizes API keys and sensitive tokens in metadata."""
    node = node_from_dataset(
        dataset_id="ds_eval_1",
        name="Medical QA Dataset",
        version="2.1.0",
        metadata={
            "api_key": "sk-1234567890abcdef1234567890",
            "bearer_token": "secret_jwt_token_here",
            "samples": 500,
        },
    )
    assert node.node_id == "dataset:ds_eval_1"
    assert node.node_type == GraphNodeType.DATASET
    assert node.name == "Medical QA Dataset"
    assert node.version == "2.1.0"
    # Ensure secrets are sanitized
    assert node.metadata["api_key"] == "[REDACTED]"
    assert node.metadata["bearer_token"] == "[REDACTED]"
    assert node.metadata["samples"] == 500


def test_node_from_test_case() -> None:
    """Test node_from_test_case."""
    node = node_from_test_case(
        "tc_42", name="Query TestCase", metadata={"dataset_id": "ds_eval_1"}
    )
    assert node.node_id == "test_case:tc_42"
    assert node.node_type == GraphNodeType.TEST_CASE
    assert node.source_id == "tc_42"
    assert node.metadata["dataset_id"] == "ds_eval_1"


def test_node_from_execution_and_trace() -> None:
    """Test execution and trace nodes."""
    exec_node = node_from_execution("exec_99", metadata={"target": "agent:app"})
    assert exec_node.node_id == "execution:exec_99"
    assert exec_node.node_type == GraphNodeType.EXECUTION
    assert exec_node.metadata["target"] == "agent:app"

    tr_node = node_from_trace("tr_500", metadata={"execution_id": "exec_99"})
    assert tr_node.node_id == "trace:tr_500"
    assert tr_node.node_type == GraphNodeType.TRACE

    step_node = node_from_trace_step(
        "step_1", name="call_tool", metadata={"trace_id": "tr_500"}
    )
    assert step_node.node_id == "trace_step:step_1"
    assert step_node.node_type == GraphNodeType.TRACE_STEP


def test_node_from_components() -> None:
    """Test model, prompt, tool, retriever nodes."""
    m_node = node_from_model("claude-3-opus", version="20240229")
    assert m_node.node_id == "model:claude-3-opus:20240229"
    assert m_node.node_type == GraphNodeType.MODEL
    assert m_node.name == "claude-3-opus"
    assert m_node.version == "20240229"

    p_node = node_from_prompt("system_rag_prompt", version="v3")
    assert p_node.node_id == "prompt:system_rag_prompt:v3"
    assert p_node.node_type == GraphNodeType.PROMPT

    t_node = node_from_tool("search_web")
    assert t_node.node_id == "tool:search_web"
    assert t_node.node_type == GraphNodeType.TOOL

    r_node = node_from_retriever("hybrid_bm25_vector")
    assert r_node.node_id == "retriever:hybrid_bm25_vector"
    assert r_node.node_type == GraphNodeType.RETRIEVER


def test_node_from_evaluation_and_metric() -> None:
    """Test evaluation and metric nodes."""
    eval_node = node_from_evaluation("report_123", target_name="agent_v2")
    assert eval_node.node_id == "evaluation:report_123"
    assert eval_node.node_type == GraphNodeType.EVALUATION

    metric_node = node_from_metric("exact_match", value=0.92)
    assert metric_node.node_id == "metric:exact_match"
    assert metric_node.node_type == GraphNodeType.METRIC
    assert metric_node.metadata["value"] == 0.92


def test_node_from_failure_and_root_cause() -> None:
    """Test failure and root cause nodes."""
    f_node = node_from_failure(
        failure_id="fail_01",
        category="HALLUCINATION",
        failure_type="UNGROUNDED_CLAIM",
        message="Model hallucinated entity",
        severity="HIGH",
    )
    assert f_node.node_id == "failure:fail_01"
    assert f_node.node_type == GraphNodeType.FAILURE
    assert f_node.metadata["severity"] == "HIGH"

    rc_node = node_from_root_cause(
        root_cause_id="rc_01",
        category="RETRIEVAL_FAILURE",
        root_cause_type="EMPTY_CONTEXT",
        description="Retriever returned empty context",
        confidence=0.88,
    )
    assert rc_node.node_id == "root_cause:rc_01"
    assert rc_node.node_type == GraphNodeType.ROOT_CAUSE
    assert rc_node.confidence == 0.88


def test_node_from_regression_and_incident() -> None:
    """Test regression and incident nodes."""
    reg_node = node_from_regression(
        regression_id="reg_01",
        name="Regression test_accuracy",
        metadata={"metric": "accuracy", "delta": -0.15},
    )
    assert reg_node.node_id == "regression:reg_01"
    assert reg_node.node_type == GraphNodeType.REGRESSION

    inc_node = node_from_incident(
        incident_id="inc_01",
        title="Production Latency Spike",
        severity="P1",
    )
    assert inc_node.node_id == "incident:inc_01"
    assert inc_node.node_type == GraphNodeType.INCIDENT


def test_node_from_intelligence_entities() -> None:
    """Test failure cluster, pattern, trend, and recommendation nodes."""
    c_node = node_from_cluster(
        "cluster_42", name="SyntaxError Cluster", fingerprint="fp_abc123"
    )
    assert c_node.node_id == "failure_cluster:cluster_42"
    assert c_node.node_type == GraphNodeType.FAILURE_CLUSTER
    assert c_node.metadata["fingerprint"] == "fp_abc123"

    pat_node = node_from_pattern(
        "pat_01", pattern_type="SYSTEMIC", title="Prompt Drift Failure"
    )
    assert pat_node.node_id == "pattern:pat_01"
    assert pat_node.node_type == GraphNodeType.PATTERN

    tr_node = node_from_trend(
        "trend_01", metric="hallucination_rate", direction="DEGRADING"
    )
    assert tr_node.node_id == "trend:trend_01"
    assert tr_node.node_type == GraphNodeType.TREND

    rec_node = node_from_recommendation(
        "rec_01", title="Upgrade prompt to v4", priority="HIGH"
    )
    assert rec_node.node_id == "recommendation:rec_01"
    assert rec_node.node_type == GraphNodeType.RECOMMENDATION
