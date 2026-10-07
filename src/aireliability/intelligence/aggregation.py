"""Telemetry instrumentation, metrics aggregation, and incident linking for intelligence workflows."""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from aireliability.intelligence.models import (
    CrossRunCorrelation,
    FailureCluster,
    FailurePattern,
    ImpactAssessment,
    ImpactSeverity,
    IntelligenceSummary,
    NormalizedFailure,
    RecommendationPriority,
    ReliabilityRecommendation,
    ReliabilityTrend,
)
from aireliability.observability.incidents import IncidentManager, IncidentRecord
from aireliability.observability.manager import ObservabilityManager


class IntelligenceTelemetry:
    """Instrumentation layer for AI reliability intelligence operations."""

    def __init__(
        self,
        observability: ObservabilityManager | None = None,
        incident_manager: IncidentManager | None = None,
    ) -> None:
        self.observability = observability
        self.incident_manager = incident_manager or (
            observability.incidents if observability else None
        )
        self._metrics = observability.metrics if observability else None
        self._tracer = observability.tracer if observability else None

    @contextmanager
    def track_analysis(self, target_name: str) -> Generator[dict[str, Any], None, None]:
        """Track analysis lifecycle, duration, and error reporting via tracing and metrics."""
        start_time = time.perf_counter()
        context_data: dict[str, Any] = {"target": target_name, "success": True}

        if self._metrics:
            self._metrics.counter(
                "aireliability_intelligence_analyses_started_total"
            ).increment()

        span_cm = (
            self._tracer.span(f"intelligence.analysis.{target_name}")
            if self._tracer
            else None
        )

        try:
            if span_cm:
                with span_cm:
                    yield context_data
            else:
                yield context_data
        except Exception as exc:
            context_data["success"] = False
            context_data["error"] = str(exc)
            if self._metrics:
                self._metrics.counter(
                    "aireliability_intelligence_errors_total",
                    labels={"error_type": exc.__class__.__name__},
                ).increment()
            raise
        finally:
            duration = time.perf_counter() - start_time
            context_data["duration_seconds"] = duration
            if self._metrics:
                self._metrics.counter(
                    "aireliability_intelligence_analyses_completed_total"
                ).increment()
                self._metrics.histogram(
                    "aireliability_intelligence_duration_seconds"
                ).observe(duration)

    def record_failures_analyzed(self, count: int) -> None:
        """Record the number of normalized failures processed."""
        if self._metrics and count > 0:
            self._metrics.counter(
                "aireliability_intelligence_failures_analyzed_total"
            ).increment(count)

    def record_clusters_generated(self, count: int) -> None:
        """Record the number of failure clusters identified."""
        if self._metrics and count > 0:
            self._metrics.counter(
                "aireliability_intelligence_clusters_total"
            ).increment(count)

    def record_patterns_detected(self, count: int) -> None:
        """Record the number of failure patterns detected."""
        if self._metrics and count > 0:
            self._metrics.counter(
                "aireliability_intelligence_patterns_total"
            ).increment(count)

    def record_correlations_detected(self, count: int) -> None:
        """Record the number of cross-run correlations detected."""
        if self._metrics and count > 0:
            self._metrics.counter(
                "aireliability_intelligence_correlations_total"
            ).increment(count)

    def record_recommendations_generated(self, count: int) -> None:
        """Record the number of remediation recommendations created."""
        if self._metrics and count > 0:
            self._metrics.counter(
                "aireliability_intelligence_recommendations_total"
            ).increment(count)

    def maybe_create_incident(
        self,
        impact: ImpactAssessment,
        recommendation: ReliabilityRecommendation | None = None,
        tenant_id: str = "default",
    ) -> IncidentRecord | None:
        """Create an incident if impact assessment is critical or safety/security breach."""
        if not self.incident_manager:
            return None

        is_critical = (
            impact.observed_impact == ImpactSeverity.CRITICAL
            or impact.safety_critical
            or impact.security_critical
        )
        if not is_critical:
            return None

        severity = "CRITICAL"
        title = (
            recommendation.title
            if recommendation
            else f"Reliability Intelligence Critical Finding: {impact.target_id}"
        )
        description = (
            f"{impact.explanation}\n\nSuggested Action: "
            f"{recommendation.suggested_action if recommendation else 'Review affected components'}"
        )

        trace_ids = [
            ev.metadata.get("trace_id")
            for ev in impact.evidence
            if ev.metadata and "trace_id" in ev.metadata and ev.metadata["trace_id"]
        ]

        incident = self.incident_manager.create_incident(
            title=title,
            description=description,
            severity=severity,
            tenant_id=tenant_id,
            trace_ids=trace_ids,
            metadata={
                "target_id": impact.target_id,
                "safety_critical": impact.safety_critical,
                "security_critical": impact.security_critical,
                "impact_score": impact.impact_score,
                "affected_components": impact.affected_components,
            },
        )
        return incident


def aggregate_summary(
    failures: list[NormalizedFailure],
    clusters: list[FailureCluster],
    patterns: list[FailurePattern],
    correlations: list[CrossRunCorrelation],
    trends: list[ReliabilityTrend],
    impacts: list[ImpactAssessment],
    recommendations: list[ReliabilityRecommendation],
) -> IntelligenceSummary:
    """Compile aggregated metrics and dominant signatures into an IntelligenceSummary."""
    category_counts = Counter(f.category for f in failures)
    root_cause_counts = Counter(
        f"{f.root_cause_category or 'unknown'}.{f.root_cause_type or 'unknown'}"
        for f in failures
        if f.root_cause_category or f.root_cause_type
    )

    critical_count = sum(
        1
        for imp in impacts
        if imp.observed_impact == ImpactSeverity.CRITICAL
        or imp.safety_critical
        or imp.security_critical
    )

    highest_priority_recs = [
        r.title
        for r in recommendations
        if r.priority in (RecommendationPriority.CRITICAL, RecommendationPriority.HIGH)
    ][:5]

    return IntelligenceSummary(
        total_failures_analyzed=len(failures),
        total_clusters=len(clusters),
        total_patterns=len(patterns),
        total_correlations=len(correlations),
        total_trends=len(trends),
        total_recommendations=len(recommendations),
        critical_issues_count=critical_count,
        dominant_failure_categories=dict(category_counts.most_common(5)),
        dominant_root_causes=dict(root_cause_counts.most_common(5)),
        highest_priority_recommendations=highest_priority_recs,
    )
