"""Node creation and normalization factories for the AI Reliability Knowledge Graph."""

from __future__ import annotations

from typing import Any

from aireliability.graph.models import GraphNode, GraphNodeType
from aireliability.telemetry.sanitizer import SanitizationPolicy

_DEFAULT_SANITIZER = SanitizationPolicy()


def _sanitize_dict(data: dict[str, Any] | None) -> dict[str, Any]:
    """Sanitize metadata values using the platform SanitizationPolicy."""
    if not data:
        return {}
    sanitized: dict[str, Any] = {}
    for k, v in data.items():
        if _DEFAULT_SANITIZER.is_sensitive_key(k):
            sanitized[k] = _DEFAULT_SANITIZER.redaction_text
        elif isinstance(v, str):
            sanitized[k] = _DEFAULT_SANITIZER.sanitize(v, key_context=k)
        elif isinstance(v, dict):
            sanitized[k] = _sanitize_dict(v)
        else:
            sanitized[k] = v
    return sanitized


def node_from_dataset(
    dataset_id: str,
    name: str = "",
    version: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> GraphNode:
    """Create a DATASET graph node."""
    return GraphNode.create(
        node_type=GraphNodeType.DATASET,
        source_id=dataset_id,
        name=name or dataset_id,
        version=version,
        metadata=_sanitize_dict(metadata),
    )


def node_from_test_case(
    test_id: str,
    name: str = "",
    dataset_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> GraphNode:
    """Create a TEST_CASE graph node."""
    meta = dict(metadata or {})
    if dataset_id:
        meta["dataset_id"] = dataset_id
    return GraphNode.create(
        node_type=GraphNodeType.TEST_CASE,
        source_id=test_id,
        name=name or test_id,
        metadata=_sanitize_dict(meta),
    )


def node_from_execution(
    execution_id: str, metadata: dict[str, Any] | None = None
) -> GraphNode:
    """Create an EXECUTION graph node."""
    return GraphNode.create(
        node_type=GraphNodeType.EXECUTION,
        source_id=execution_id,
        name=f"Execution {execution_id}",
        metadata=_sanitize_dict(metadata),
    )


def node_from_trace(trace_id: str, metadata: dict[str, Any] | None = None) -> GraphNode:
    """Create a TRACE graph node."""
    return GraphNode.create(
        node_type=GraphNodeType.TRACE,
        source_id=trace_id,
        name=f"Trace {trace_id}",
        metadata=_sanitize_dict(metadata),
    )


def node_from_trace_step(
    step_id: str, name: str = "", metadata: dict[str, Any] | None = None
) -> GraphNode:
    """Create a TRACE_STEP graph node."""
    return GraphNode.create(
        node_type=GraphNodeType.TRACE_STEP,
        source_id=step_id,
        name=name or step_id,
        metadata=_sanitize_dict(metadata),
    )


def node_from_model(
    model_name: str,
    version: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> GraphNode:
    """Create a MODEL graph node."""
    return GraphNode.create(
        node_type=GraphNodeType.MODEL,
        source_id=f"{model_name}:{version}" if version else model_name,
        name=model_name,
        version=version,
        metadata=_sanitize_dict(metadata),
    )


def node_from_prompt(
    prompt_name: str,
    version: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> GraphNode:
    """Create a PROMPT graph node."""
    return GraphNode.create(
        node_type=GraphNodeType.PROMPT,
        source_id=f"{prompt_name}:{version}" if version else prompt_name,
        name=prompt_name,
        version=version,
        metadata=_sanitize_dict(metadata),
    )


def node_from_tool(
    tool_name: str,
    version: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> GraphNode:
    """Create a TOOL graph node."""
    return GraphNode.create(
        node_type=GraphNodeType.TOOL,
        source_id=f"{tool_name}:{version}" if version else tool_name,
        name=tool_name,
        version=version,
        metadata=_sanitize_dict(metadata),
    )


def node_from_retriever(
    retriever_name: str, metadata: dict[str, Any] | None = None
) -> GraphNode:
    """Create a RETRIEVER graph node."""
    return GraphNode.create(
        node_type=GraphNodeType.RETRIEVER,
        source_id=retriever_name,
        name=retriever_name,
        metadata=_sanitize_dict(metadata),
    )


def node_from_evaluation(
    report_id: str, target_name: str = "", metadata: dict[str, Any] | None = None
) -> GraphNode:
    """Create an EVALUATION graph node."""
    return GraphNode.create(
        node_type=GraphNodeType.EVALUATION,
        source_id=report_id,
        name=f"Evaluation on {target_name}"
        if target_name
        else f"Evaluation {report_id}",
        metadata=_sanitize_dict(metadata),
    )


def node_from_metric(
    metric_name: str,
    value: float,
    evaluation_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> GraphNode:
    """Create a METRIC graph node."""
    meta = dict(metadata or {})
    meta["value"] = value
    if evaluation_id:
        meta["evaluation_id"] = evaluation_id
    return GraphNode.create(
        node_type=GraphNodeType.METRIC,
        source_id=metric_name,
        name=f"Metric: {metric_name} ({value:.3f})",
        metadata=_sanitize_dict(meta),
    )


def node_from_failure(
    failure_id: str,
    category: str,
    failure_type: str = "",
    message: str = "",
    severity: str = "MEDIUM",
    metadata: dict[str, Any] | None = None,
) -> GraphNode:
    """Create a FAILURE graph node."""
    meta = dict(metadata or {})
    meta["category"] = category
    meta["failure_type"] = failure_type
    meta["severity"] = severity
    if message:
        meta["sanitized_message"] = _DEFAULT_SANITIZER.sanitize(message)

    name = f"Failure: [{category.upper()}] {failure_type or failure_id}"
    return GraphNode.create(
        node_type=GraphNodeType.FAILURE,
        source_id=failure_id,
        name=name,
        tags=[category, severity.lower()],
        metadata=_sanitize_dict(meta),
    )


def node_from_root_cause(
    root_cause_id: str,
    category: str,
    root_cause_type: str = "",
    description: str = "",
    confidence: float = 1.0,
    metadata: dict[str, Any] | None = None,
) -> GraphNode:
    """Create a ROOT_CAUSE graph node."""
    meta = dict(metadata or {})
    meta["category"] = category
    meta["root_cause_type"] = root_cause_type
    if description:
        meta["description"] = _DEFAULT_SANITIZER.sanitize(description)

    name = f"RootCause: {category}.{root_cause_type or 'general'}"
    return GraphNode.create(
        node_type=GraphNodeType.ROOT_CAUSE,
        source_id=root_cause_id,
        name=name,
        confidence=confidence,
        tags=[category],
        metadata=_sanitize_dict(meta),
    )


def node_from_regression(
    regression_id: str,
    name: str = "",
    test_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> GraphNode:
    """Create a REGRESSION graph node."""
    meta = dict(metadata or {})
    if test_id:
        meta["test_id"] = test_id
    return GraphNode.create(
        node_type=GraphNodeType.REGRESSION,
        source_id=regression_id,
        name=name or f"Regression {regression_id}",
        metadata=_sanitize_dict(meta),
    )


def node_from_incident(
    incident_id: str,
    title: str = "",
    severity: str = "HIGH",
    metadata: dict[str, Any] | None = None,
) -> GraphNode:
    """Create an INCIDENT graph node."""
    meta = dict(metadata or {})
    meta["severity"] = severity
    name = f"Incident [{severity}]: {title or incident_id}"
    return GraphNode.create(
        node_type=GraphNodeType.INCIDENT,
        source_id=incident_id,
        name=_DEFAULT_SANITIZER.sanitize(name),
        tags=[severity.lower(), "incident"],
        metadata=_sanitize_dict(meta),
    )


def node_from_cluster(
    cluster_id: str,
    name: str = "",
    fingerprint: str = "",
    metadata: dict[str, Any] | None = None,
) -> GraphNode:
    """Create a FAILURE_CLUSTER graph node."""
    meta = dict(metadata or {})
    if fingerprint:
        meta["fingerprint"] = fingerprint
    return GraphNode.create(
        node_type=GraphNodeType.FAILURE_CLUSTER,
        source_id=cluster_id,
        name=name or f"Cluster {cluster_id}",
        metadata=_sanitize_dict(meta),
    )


def node_from_pattern(
    pattern_id: str,
    pattern_type: str,
    title: str = "",
    metadata: dict[str, Any] | None = None,
) -> GraphNode:
    """Create a PATTERN graph node."""
    meta = dict(metadata or {})
    meta["pattern_type"] = pattern_type
    name = f"Pattern [{pattern_type}]: {title or pattern_id}"
    return GraphNode.create(
        node_type=GraphNodeType.PATTERN,
        source_id=pattern_id,
        name=name,
        tags=[pattern_type],
        metadata=_sanitize_dict(meta),
    )


def node_from_trend(
    trend_id: str,
    metric: str,
    direction: str,
    metadata: dict[str, Any] | None = None,
) -> GraphNode:
    """Create a TREND graph node."""
    meta = dict(metadata or {})
    meta["metric"] = metric
    meta["direction"] = direction
    name = f"Trend: {metric} ({direction})"
    return GraphNode.create(
        node_type=GraphNodeType.TREND,
        source_id=trend_id,
        name=name,
        tags=[direction.lower()],
        metadata=_sanitize_dict(meta),
    )


def node_from_recommendation(
    rec_id: str,
    title: str = "",
    priority: str = "HIGH",
    metadata: dict[str, Any] | None = None,
) -> GraphNode:
    """Create a RECOMMENDATION graph node."""
    meta = dict(metadata or {})
    meta["priority"] = priority
    name = f"Recommendation [{priority}]: {title or rec_id}"
    return GraphNode.create(
        node_type=GraphNodeType.RECOMMENDATION,
        source_id=rec_id,
        name=name,
        tags=[priority.lower()],
        metadata=_sanitize_dict(meta),
    )
