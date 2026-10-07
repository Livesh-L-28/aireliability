"""Observability Bridge recording RAG metrics and distributed trace spans."""

from __future__ import annotations

import logging

from aireliability.observability.manager import ObservabilityManager
from aireliability.rag.models import RAGRun

logger = logging.getLogger(__name__)


class RAGObservabilityBridge:
    """Emits Prometheus metrics and distributed traces for RAG pipeline stages."""

    def __init__(self, manager: ObservabilityManager | None = None) -> None:
        self.manager = manager or ObservabilityManager()
        self._init_metrics()

    def _init_metrics(self) -> None:
        """Initialize standard RAG observability counters."""
        metrics = self.manager.metrics
        self.c_runs = metrics.register_counter(
            "rag_runs_total", "Total RAG executions evaluated"
        )
        self.c_failures = metrics.register_counter(
            "rag_failures_total", "Total RAG failure events"
        )
        self.c_retrieval_fail = metrics.register_counter(
            "rag_retrieval_failures_total", "Retrieval stage failures"
        )
        self.c_grounding_fail = metrics.register_counter(
            "rag_grounding_failures_total", "Grounding stage failures"
        )
        self.c_citation_fail = metrics.register_counter(
            "rag_citation_failures_total", "Citation validation failures"
        )
        self.c_hallucinations = metrics.register_counter(
            "rag_hallucination_events_total", "Hallucination events detected"
        )
        self.c_stale_evidence = metrics.register_counter(
            "rag_stale_evidence_total", "Stale evidence encounters"
        )
        self.c_conflicts = metrics.register_counter(
            "rag_conflicts_total", "Evidence conflict occurrences"
        )
        self.c_drift = metrics.register_counter(
            "rag_drift_events_total", "RAG statistical drift events"
        )

    def record_run(self, run: RAGRun) -> None:
        """Record completed RAG run metrics and trace spans."""
        self.c_runs.increment()

        # Record failures
        for f in run.failures:
            self.c_failures.increment()
            stage_str = f.stage.value
            if stage_str == "retrieval":
                self.c_retrieval_fail.increment()
            elif stage_str == "grounding":
                self.c_grounding_fail.increment()
            elif stage_str == "citation":
                self.c_citation_fail.increment()
            elif stage_str == "freshness":
                self.c_stale_evidence.increment()

        if run.conflicts:
            self.c_conflicts.increment(amount=float(len(run.conflicts)))

        # Trace span
        tracer = self.manager.tracer
        span = tracer.start_span(f"rag_run_{run.run_id}")
        span.set_attribute("rag.query", run.query.text)
        span.set_attribute("rag.overall_score", run.reliability_score.overall_score)
        span.set_attribute("rag.failures_count", len(run.failures))
        span.finish()
