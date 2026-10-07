"""Integration and telemetry bridge connecting the Knowledge Graph to platform observability."""

from __future__ import annotations

import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aireliability.observability.manager import ObservabilityManager


class GraphTelemetry:
    """Telemetry instrumentation for graph build, query, traversal, and export operations."""

    def __init__(self, observability: ObservabilityManager | None = None) -> None:
        self.observability = observability
        self._metrics = observability.metrics if observability else None
        self._tracer = observability.tracer if observability else None

    @contextmanager
    def track_build(self, source_type: str) -> Generator[dict[str, Any], None, None]:
        """Track graph build lifecycle, duration, and errors."""
        start_time = time.perf_counter()
        context_data: dict[str, Any] = {"source_type": source_type, "success": True}

        if self._metrics:
            self._metrics.counter("aireliability_graph_build_started_total").increment(
                1.0, source_type=source_type
            )

        span_cm = (
            self._tracer.span(f"graph.build.{source_type}") if self._tracer else None
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
                self._metrics.counter("aireliability_graph_errors_total").increment(
                    1.0, operation="build", error_type=exc.__class__.__name__
                )
            raise
        finally:
            duration = time.perf_counter() - start_time
            context_data["duration_seconds"] = duration
            if self._metrics:
                self._metrics.counter(
                    "aireliability_graph_build_completed_total"
                ).increment(1.0, source_type=source_type)
                self._metrics.histogram(
                    "aireliability_graph_build_duration_seconds"
                ).observe(duration, source_type=source_type)

    @contextmanager
    def track_query(self, query_type: str) -> Generator[dict[str, Any], None, None]:
        """Track query execution duration and latency."""
        start_time = time.perf_counter()
        context_data: dict[str, Any] = {"query_type": query_type, "success": True}

        span_cm = (
            self._tracer.span(f"graph.query.{query_type}") if self._tracer else None
        )

        try:
            if span_cm:
                with span_cm:
                    yield context_data
            else:
                yield context_data
        except Exception as exc:
            context_data["success"] = False
            if self._metrics:
                self._metrics.counter("aireliability_graph_errors_total").increment(
                    1.0, operation="query", error_type=exc.__class__.__name__
                )
            raise
        finally:
            duration = time.perf_counter() - start_time
            if self._metrics:
                self._metrics.histogram(
                    "aireliability_graph_query_duration_seconds"
                ).observe(duration, query_type=query_type)

    @contextmanager
    def track_traversal(
        self, traversal_type: str
    ) -> Generator[dict[str, Any], None, None]:
        """Track traversal execution latency."""
        start_time = time.perf_counter()
        context_data: dict[str, Any] = {
            "traversal_type": traversal_type,
            "success": True,
        }

        try:
            yield context_data
        finally:
            duration = time.perf_counter() - start_time
            if self._metrics:
                self._metrics.histogram(
                    "aireliability_graph_traversal_duration_seconds"
                ).observe(duration, traversal_type=traversal_type)

    @contextmanager
    def track_serialization(
        self, format_type: str = "json"
    ) -> Generator[dict[str, Any], None, None]:
        """Track graph serialization latency."""
        start_time = time.perf_counter()
        context_data: dict[str, Any] = {"format": format_type, "success": True}

        try:
            yield context_data
        finally:
            duration = time.perf_counter() - start_time
            if self._metrics:
                self._metrics.histogram(
                    "aireliability_graph_serialization_duration_seconds"
                ).observe(duration, format=format_type)

    def record_nodes_created(self, count: int) -> None:
        """Record count of newly created nodes in the graph."""
        if self._metrics and count > 0:
            self._metrics.counter("aireliability_graph_nodes_created_total").increment(
                count
            )

    def record_edges_created(self, count: int) -> None:
        """Record count of newly created edges in the graph."""
        if self._metrics and count > 0:
            self._metrics.counter("aireliability_graph_edges_created_total").increment(
                count
            )

    def record_duplicates_avoided(self, count: int) -> None:
        """Record count of duplicate nodes or edges avoided."""
        if self._metrics and count > 0:
            self._metrics.counter(
                "aireliability_graph_duplicates_avoided_total"
            ).increment(count)
