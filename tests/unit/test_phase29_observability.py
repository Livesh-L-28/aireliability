"""Comprehensive unit tests for Phase 29: Production Observability,
Tracing & Operations.
"""

import asyncio
import os
import tempfile
import time

from aireliability.control_plane.controller import ControlPlane
from aireliability.core.models import TestCase
from aireliability.distributed.sqlite_storage import SQLiteDistributedStorage
from aireliability.observability.aggregation import TelemetryAggregator
from aireliability.observability.anomaly import (
    AnomalySeverity,
    StatisticalAnomalyDetector,
)
from aireliability.observability.context import (
    clear_current_context,
    get_current_context,
    observability_context,
)
from aireliability.observability.events import EventRecorder
from aireliability.observability.exporter import (
    CsvMetricExporter,
    JsonExporter,
    JsonlExporter,
)
from aireliability.observability.health import (
    HealthStatus,
    OperationalHealthManager,
)
from aireliability.observability.incidents import (
    IncidentManager,
    IncidentStatus,
)
from aireliability.observability.metrics import (
    MetricsEngine,
)
from aireliability.observability.models import (
    SpanKind,
    TelemetryEvent,
)
from aireliability.observability.retention import RetentionPolicyManager
from aireliability.observability.sanitization import TelemetrySanitizer
from aireliability.observability.slo import (
    SLOManager,
)
from aireliability.observability.traces import Tracer


class TestObservabilityContext:
    def test_trace_creation_and_defaults(self):
        clear_current_context()
        ctx = get_current_context()
        assert ctx.trace_id is not None
        assert ctx.tenant_id == "default"
        assert ctx.project_id == "default"
        assert ctx.namespace == "default"

    def test_nested_contexts_and_scoping(self):
        clear_current_context()
        with observability_context(tenant_id="tenant_a", trace_id="trace_123"):
            ctx1 = get_current_context()
            assert ctx1.tenant_id == "tenant_a"
            assert ctx1.trace_id == "trace_123"

            with observability_context(span_id="span_inner", tenant_id="tenant_b"):
                ctx2 = get_current_context()
                assert ctx2.tenant_id == "tenant_b"
                assert ctx2.trace_id == "trace_123"
                assert ctx2.span_id == "span_inner"

            ctx3 = get_current_context()
            assert ctx3.tenant_id == "tenant_a"
            assert ctx3.span_id is None

    def test_async_context_propagation(self):
        async def run_async_test():
            clear_current_context()

            async def worker_task(tenant: str):
                with observability_context(tenant_id=tenant):
                    await asyncio.sleep(0.01)
                    return get_current_context().tenant_id

            results = await asyncio.gather(
                worker_task("tenant_1"),
                worker_task("tenant_2"),
            )
            assert results == ["tenant_1", "tenant_2"]

        asyncio.run(run_async_test())


class TestTelemetrySanitization:
    def test_sensitive_field_redaction(self):
        sanitizer = TelemetrySanitizer()
        raw = {
            "api_key": "sk-secret12345",
            "password": "supersecretpassword",
            "normal_field": "hello world",
            "nested": {
                "token": "bearer xyz",
                "safe": 123,
            },
        }
        sanitized = sanitizer.sanitize(raw)
        assert sanitized["api_key"] == "[REDACTED]"
        assert sanitized["password"] == "[REDACTED]"
        assert sanitized["normal_field"] == "hello world"
        assert sanitized["nested"]["token"] == "[REDACTED]"
        assert sanitized["nested"]["safe"] == 123


class TestStructuredEvents:
    def test_event_recording_and_correlation(self):
        recorder = EventRecorder()
        with observability_context(tenant_id="acme", trace_id="tr-999"):
            ev = recorder.record_event(
                event_type="job.submitted",
                attributes={"api_key": "secret", "job_name": "eval_1"},
            )
            assert ev.tenant_id == "acme"
            assert ev.trace_id == "tr-999"
            assert ev.attributes["api_key"] == "[REDACTED]"
            assert ev.attributes["job_name"] == "eval_1"

    def test_tenant_filtered_event_queries(self):
        recorder = EventRecorder()
        recorder.record_event(event_type="job.submitted", tenant_id="tenant_1")
        recorder.record_event(event_type="job.completed", tenant_id="tenant_2")

        t1_events = recorder.get_events(tenant_id="tenant_1")
        t2_events = recorder.get_events(tenant_id="tenant_2")
        assert len(t1_events) == 1
        assert t1_events[0].tenant_id == "tenant_1"
        assert len(t2_events) == 1
        assert t2_events[0].tenant_id == "tenant_2"


class TestDistributedTracing:
    def test_trace_lifecycle_and_nested_spans(self):
        tracer = Tracer()
        root_span = tracer.start_trace(
            name="request_root",
            tenant_id="tenant_corp",
        )
        assert root_span.trace_id is not None

        with root_span:
            child1 = tracer.span("security.authenticate", kind=SpanKind.SERVER)
            with child1:
                child1.set_attribute("user", "alice")
                child1.add_event("auth_ok")

            child2 = tracer.span("worker.execute", kind=SpanKind.WORKER)
            with child2:
                try:
                    raise ValueError("simulation error")
                except ValueError as err:
                    child2.record_exception(err)

        trace_rec = tracer.finish_trace(root_span.trace_id)
        assert trace_rec is not None
        assert trace_rec.tenant_id == "tenant_corp"
        assert trace_rec.status == "error"
        assert len(trace_rec.spans) == 3

        names = [s.name for s in trace_rec.spans]
        assert "request_root" in names
        assert "security.authenticate" in names
        assert "worker.execute" in names


class TestMetricsEngine:
    def test_counter_gauge_histogram_and_percentiles(self):
        metrics = MetricsEngine()
        c = metrics.counter("test_counter")
        c.increment(2.0, tenant_id="t1")
        assert c.get(tenant_id="t1") == 2.0

        g = metrics.gauge("test_gauge")
        g.set(42.0)
        assert g.get() == 42.0
        g.decrement(2.0)
        assert g.get() == 40.0

        h = metrics.histogram("test_latency")
        for val in [0.01, 0.02, 0.05, 0.1, 0.5, 1.0]:
            h.observe(val, env="prod")

        pcts = h.get_percentiles(env="prod")
        assert pcts["count"] == 6.0
        assert pcts["min"] == 0.01
        assert pcts["max"] == 1.0
        assert pcts["p50"] > 0.0
        assert pcts["p95"] > pcts["p50"]

    def test_prometheus_exposition_rendering(self):
        metrics = MetricsEngine()
        metrics.counter("aireliability_jobs_submitted_total").increment(
            tenant_id="acme"
        )
        metrics.gauge("aireliability_queue_depth").set(5.0)
        metrics.histogram("aireliability_job_latency_seconds").observe(
            0.12, tenant_id="acme"
        )

        prom_text = metrics.render_prometheus()
        assert "# TYPE aireliability_jobs_submitted_total counter" in prom_text
        assert 'aireliability_jobs_submitted_total{tenant_id="acme"} 1.0' in prom_text
        assert "# TYPE aireliability_queue_depth gauge" in prom_text
        assert "aireliability_queue_depth 5.0" in prom_text
        assert "# TYPE aireliability_job_latency_seconds summary" in prom_text


class TestOperationalHealth:
    def test_healthy_and_degraded_evaluations(self):
        class MockResilience:
            def __init__(self, open_cb=False):
                self.circuit_breakers = {}
                if open_cb:

                    class OpenCB:
                        def is_open(self):
                            return True

                    self.circuit_breakers["cb_1"] = OpenCB()

        health_mgr_ok = OperationalHealthManager(
            resilience_manager=MockResilience(open_cb=False)
        )
        snap_ok = health_mgr_ok.evaluate_health()
        assert snap_ok.overall_status == HealthStatus.HEALTHY

        health_mgr_degraded = OperationalHealthManager(
            resilience_manager=MockResilience(open_cb=True)
        )
        snap_degraded = health_mgr_degraded.evaluate_health()
        assert snap_degraded.overall_status == HealthStatus.DEGRADED
        assert snap_degraded.resilience_status == HealthStatus.DEGRADED


class TestSLOAndErrorBudget:
    def test_compliant_and_violated_slo_evaluations(self):
        metrics = MetricsEngine()
        events = EventRecorder()
        tracer = Tracer()
        aggregator = TelemetryAggregator(metrics, events, tracer)
        slo_mgr = SLOManager(aggregator)

        slo = slo_mgr.register_slo(
            name="job_success_rate",
            sli_name="success_rate",
            target=0.95,
            window_seconds=60.0,
        )

        # 9 successes, 1 failure -> 90% (< 95% target)
        for _ in range(9):
            events.record_event(event_type="job.completed", tenant_id="t1")
        events.record_event(event_type="job.failed", tenant_id="t1")

        evaluation = slo_mgr.evaluate_slo(slo.slo_id, tenant_id="t1")
        assert evaluation is not None
        assert not evaluation.compliant
        assert evaluation.actual_value == 0.90
        assert evaluation.burn_rate > 1.0
        assert evaluation.remaining_error_budget < 0.001


class TestStatisticalAnomalyDetection:
    def test_normal_and_anomalous_observations(self):
        detector = StatisticalAnomalyDetector(
            z_threshold_warning=2.0,
            z_threshold_anomaly=3.0,
            min_samples=5,
        )
        # Establish stable baseline around 10.0
        for _ in range(20):
            detector.record_observation("latency", 10.0)

        # Normal small deviation
        rep_normal = detector.detect("latency", 10.0)
        assert rep_normal.severity == AnomalySeverity.NORMAL

        # Extreme anomaly
        rep_anomaly = detector.detect("latency", 500.0)
        assert rep_anomaly.severity == AnomalySeverity.ANOMALY
        assert rep_anomaly.deviation > 100.0


class TestIncidentLifecycle:
    def test_incident_flow(self):
        mgr = IncidentManager()
        inc = mgr.create_incident(
            title="Spike in provider errors",
            description="500 errors observed",
            severity="CRITICAL",
            tenant_id="tenant_alpha",
            trace_ids=["trace_abc"],
        )
        assert inc.status == IncidentStatus.DETECTED
        assert inc.tenant_id == "tenant_alpha"

        mgr.acknowledge_incident(inc.incident_id)
        assert mgr.get_incident(inc.incident_id).status == IncidentStatus.ACKNOWLEDGED

        mgr.mitigate_incident(inc.incident_id)
        assert mgr.get_incident(inc.incident_id).status == IncidentStatus.MITIGATING

        mgr.resolve_incident(inc.incident_id)
        assert mgr.get_incident(inc.incident_id).status == IncidentStatus.RESOLVED


class TestRetentionPolicies:
    def test_retention_pruning(self):
        retention = RetentionPolicyManager(
            event_ttl_seconds=0.01,
            trace_ttl_seconds=0.01,
        )
        events = EventRecorder()
        tracer = Tracer()

        events.record_event("job.submitted")
        root = tracer.start_trace()
        root.finish()
        tracer.finish_trace(root.trace_id)

        assert len(events.get_events()) == 1
        assert len(tracer.list_traces()) == 1

        time.sleep(0.02)
        pruned = retention.prune_all(events=events, tracer=tracer)
        assert pruned["events"] >= 1
        assert pruned["traces"] >= 1
        assert len(events.get_events()) == 0
        assert len(tracer.list_traces()) == 0


class TestExporters:
    def test_json_jsonl_csv_exporters(self):
        ev = TelemetryEvent(
            event_type="job.submitted",
            tenant_id="tenant_test",
        )
        jsonl = JsonlExporter().export_events([ev])
        assert "job.submitted" in jsonl
        assert "tenant_test" in jsonl

        json_out = JsonExporter().export_events([ev])
        assert json_out.startswith("[")

        metrics = MetricsEngine()
        sample = metrics.record_sample("test_metric", 123.45, tenant_id="tenant_test")
        csv_out = CsvMetricExporter().export([sample])
        assert "test_metric" in csv_out
        assert "123.45" in csv_out


class TestPersistenceBackend:
    def test_sqlite_observability_persistence(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            db_path = tf.name

        try:
            store = SQLiteDistributedStorage(db_path=db_path)

            # 1. Event
            ev = TelemetryEvent(
                event_type="job.submitted",
                tenant_id="acme",
                attributes={"foo": "bar"},
            )
            store.save_telemetry_event(ev)
            queried_evs = store.list_telemetry_events(tenant_id="acme")
            assert len(queried_evs) == 1
            assert queried_evs[0].event_type == "job.submitted"
            assert queried_evs[0].attributes["foo"] == "bar"

            # 2. Trace
            tracer = Tracer()
            root = tracer.start_trace(tenant_id="acme")
            with root:
                sp = tracer.span("sub_op")
                with sp:
                    pass
            trace_rec = tracer.finish_trace(root.trace_id)
            store.save_trace_record(trace_rec)

            fetched_trace = store.get_trace_record(root.trace_id)
            assert fetched_trace is not None
            assert fetched_trace.trace_id == root.trace_id
            assert len(fetched_trace.spans) == 2

            # 3. Incident
            inc_mgr = IncidentManager()
            inc = inc_mgr.create_incident(
                title="Storage latency high",
                description="Disk full warning",
                tenant_id="acme",
            )
            store.save_incident(inc)
            fetched_inc = store.get_incident(inc.incident_id)
            assert fetched_inc is not None
            assert fetched_inc.title == "Storage latency high"

            # Tenant isolation
            assert len(store.list_telemetry_events(tenant_id="other")) == 0
            assert len(store.list_trace_records(tenant_id="other")) == 0
            assert len(store.list_incidents(tenant_id="other")) == 0

            # Clear
            store.clear()
            assert len(store.list_telemetry_events()) == 0
            assert len(store.list_trace_records()) == 0
            assert len(store.list_incidents()) == 0
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)


class TestControlPlaneIntegration:
    def test_control_plane_observability_pipeline(self):
        async def run_integration():
            cp = ControlPlane()
            tc = TestCase(id="tc-obs-1", name="Test Obs", input={"text": "ping"})

            # Submit job
            job = await cp.submit_job(
                test_case=tc,
                metadata={"tenant_id": "tenant_flow"},
            )
            assert job.job_id is not None

            # Verify event recorded
            events = cp.observability.events.get_events(tenant_id="tenant_flow")
            assert len(events) >= 1
            assert any(e.event_type == "job.submitted" for e in events)

            # Operational snapshot check
            snap = cp.observability.snapshot(tenant_id="tenant_flow")
            assert snap.system_status == HealthStatus.HEALTHY
            assert snap.active_jobs >= 1

        asyncio.run(run_integration())
