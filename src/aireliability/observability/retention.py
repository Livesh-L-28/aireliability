"""Configurable in-memory retention and eviction manager."""

from __future__ import annotations

import time

from aireliability.observability.events import EventRecorder
from aireliability.observability.incidents import IncidentManager
from aireliability.observability.metrics import MetricsEngine
from aireliability.observability.traces import Tracer


class RetentionPolicyManager:
    """Enforces TTL retention policies on in-memory observability records."""

    def __init__(
        self,
        event_ttl_seconds: float = 3600.0,  # 1 hour default
        trace_ttl_seconds: float = 1800.0,  # 30 minutes default
        metric_ttl_seconds: float = 86400.0,  # 24 hours default
        incident_ttl_seconds: float = 2592000.0,  # 30 days default
    ) -> None:
        self.event_ttl_seconds = event_ttl_seconds
        self.trace_ttl_seconds = trace_ttl_seconds
        self.metric_ttl_seconds = metric_ttl_seconds
        self.incident_ttl_seconds = incident_ttl_seconds

    def prune_events(self, events: EventRecorder) -> int:
        """Prune events older than event_ttl_seconds."""
        now = time.time()
        cutoff = now - self.event_ttl_seconds
        initial = len(events._events)
        events._events = [
            ev for ev in events._events if ev.timestamp.timestamp() >= cutoff
        ]
        return initial - len(events._events)

    def prune_traces(self, tracer: Tracer) -> int:
        """Prune finished traces older than trace_ttl_seconds."""
        now = time.time()
        cutoff = now - self.trace_ttl_seconds
        to_delete = [
            tid
            for tid, tr in tracer._finished_records.items()
            if tr.start_time.timestamp() < cutoff
        ]
        for tid in to_delete:
            tracer._finished_records.pop(tid, None)
        return len(to_delete)

    def prune_metrics(self, metrics: MetricsEngine) -> int:
        """Prune raw metric samples older than metric_ttl_seconds."""
        now = time.time()
        cutoff = now - self.metric_ttl_seconds
        initial = len(metrics._raw_samples)
        metrics._raw_samples = [
            s for s in metrics._raw_samples if s.timestamp.timestamp() >= cutoff
        ]
        return initial - len(metrics._raw_samples)

    def prune_incidents(self, incidents: IncidentManager) -> int:
        """Prune resolved incidents older than incident_ttl_seconds."""
        now = time.time()
        cutoff = now - self.incident_ttl_seconds
        to_delete = [
            iid
            for iid, inc in incidents._incidents.items()
            if inc.resolved_at and inc.resolved_at.timestamp() < cutoff
        ]
        for iid in to_delete:
            incidents._incidents.pop(iid, None)
        return len(to_delete)

    def prune_all(
        self,
        events: EventRecorder | None = None,
        tracer: Tracer | None = None,
        metrics: MetricsEngine | None = None,
        incidents: IncidentManager | None = None,
    ) -> dict[str, int]:
        """Prune all stores based on their configured TTLs."""
        pruned: dict[str, int] = {}
        if events is not None:
            pruned["events"] = self.prune_events(events)
        if tracer is not None:
            pruned["traces"] = self.prune_traces(tracer)
        if metrics is not None:
            pruned["metrics"] = self.prune_metrics(metrics)
        if incidents is not None:
            pruned["incidents"] = self.prune_incidents(incidents)
        return pruned
