"""Evidence extraction, linking, and provenance management for intelligence findings."""

from __future__ import annotations

from aireliability.core.models import ExecutionTrace, FailureReport, RegressionTest
from aireliability.diagnosis.models import RootCause
from aireliability.evaluation.governance.baselines import EvaluationBaseline
from aireliability.evaluation.models import EvaluationReport, MetricResult
from aireliability.intelligence.models import EvidenceReference
from aireliability.observability.incidents import IncidentRecord


def from_evaluation_report(
    report: EvaluationReport, description: str = ""
) -> EvidenceReference:
    """Create an EvidenceReference from an EvaluationReport."""
    desc = (
        description
        or f"Evaluation run on target '{report.target_name}' across {report.total_test_cases} test cases."
    )
    return EvidenceReference(
        source_type="evaluation_report",
        source_id=report.report_id,
        description=desc,
        timestamp=report.timestamp,
        metadata={
            "target_name": report.target_name,
            "dataset_id": report.dataset_id,
            "passed": report.passed,
            "total_test_cases": report.total_test_cases,
            "failed_test_cases": report.failed_test_cases,
        },
    )


def from_failure_report(
    failure: FailureReport, description: str = ""
) -> EvidenceReference:
    """Create an EvidenceReference from a FailureReport."""
    cat = getattr(failure.category, "value", str(failure.category))
    f_type = getattr(failure.type, "value", str(failure.type))
    desc = description or f"Failure [{cat}.{f_type}]: {failure.message[:120]}"
    return EvidenceReference(
        source_type="failure_report",
        source_id=failure.failure_id,
        description=desc,
        metadata={
            "trace_id": failure.trace_id,
            "test_id": failure.test_id,
            "category": cat,
            "type": f_type,
            "severity": str(getattr(failure.severity, "value", failure.severity)),
        },
    )


def from_root_cause(
    root_cause: RootCause, report_id: str | None = None
) -> EvidenceReference:
    """Create an EvidenceReference from a diagnosed RootCause."""
    cat = getattr(root_cause.category, "value", str(root_cause.category))
    r_type = getattr(root_cause.type, "value", str(root_cause.type))
    desc = f"Root cause diagnosis [{cat}.{r_type}]: {root_cause.description}"
    return EvidenceReference(
        source_type="root_cause",
        source_id=root_cause.id,
        description=desc,
        metadata={
            "diagnosis_report_id": report_id,
            "category": cat,
            "type": r_type,
            "confidence": root_cause.confidence,
            "affected_step": root_cause.affected_step,
        },
    )


def from_execution_trace(
    trace: ExecutionTrace, description: str = ""
) -> EvidenceReference:
    """Create an EvidenceReference from an ExecutionTrace."""
    desc = (
        description
        or f"Execution trace {trace.trace_id} with {len(trace.steps)} steps."
    )
    return EvidenceReference(
        source_type="execution_trace",
        source_id=trace.trace_id,
        description=desc,
        timestamp=trace.started_at,
        metadata={
            "test_id": trace.test_id,
            "status": str(getattr(trace.status, "value", trace.status)),
            "latency_ms": trace.latency_ms,
            "cost": trace.cost,
        },
    )


def from_metric_result(
    metric: MetricResult, report_id: str | None = None
) -> EvidenceReference:
    """Create an EvidenceReference from a computed MetricResult."""
    return EvidenceReference(
        source_type="metric_result",
        source_id=f"metric_{metric.name}_{report_id or 'unknown'}",
        description=f"Observed value for metric '{metric.name}': {metric.value:.4f}",
        metric_name=metric.name,
        observed_value=metric.value,
        metadata={
            "sample_count": metric.sample_count,
            "dimension": metric.dimension,
            "confidence_interval": metric.confidence_interval,
            "report_id": report_id,
        },
    )


def from_regression_test(regression_test: RegressionTest) -> EvidenceReference:
    """Create an EvidenceReference from a synthesized RegressionTest."""
    return EvidenceReference(
        source_type="regression_test",
        source_id=regression_test.id,
        description=f"Synthesized regression test: {regression_test.name}",
        metadata={
            "source_failure_id": regression_test.source_failure_id,
            "tags": regression_test.tags,
        },
    )


def from_incident(incident: IncidentRecord) -> EvidenceReference:
    """Create an EvidenceReference from an operational IncidentRecord."""
    return EvidenceReference(
        source_type="incident",
        source_id=incident.incident_id,
        description=f"Operational incident [{incident.severity}]: {incident.title}",
        timestamp=incident.detected_at,
        metadata={
            "severity": incident.severity,
            "status": str(getattr(incident.status, "value", incident.status)),
            "trace_ids": incident.trace_ids,
        },
    )


def from_baseline(baseline: EvaluationBaseline) -> EvidenceReference:
    """Create an EvidenceReference from a versioned EvaluationBaseline."""
    return EvidenceReference(
        source_type="baseline",
        source_id=baseline.id,
        description=f"Reference baseline '{baseline.name}' (v{baseline.version}, composite: {baseline.composite_score:.4f})",
        timestamp=baseline.timestamp,
        metadata={
            "name": baseline.name,
            "version": baseline.version,
            "dataset_version": baseline.dataset_version,
            "composite_score": baseline.composite_score,
        },
    )
