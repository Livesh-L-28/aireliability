"""Phase 30 Final End-to-End Integration, Resilience & Security Test Suite.

Validates complete real-world workflows:
- Workflow A: Normal Job end-to-end processing
- Workflow B: Unauthorized Request (Gateway rejection, zero quota consumed)
- Workflow C: Cross-Tenant Request Isolation
- Workflow D: Rate-Limited Tenant burst handling
- Workflow E: Quota Exhaustion
- Workflow F: Worker Failure & Resilience Recovery
- Workflow G: Cancellation Boundaries
- Workflow H: End-to-End Observability Correlation (tenant, execution, trace, span)
- Persistence parity between InMemoryDistributedStorage and SQLiteDistributedStorage
"""

import asyncio
import os
import tempfile
from typing import Any

import pytest

from aireliability.control_plane.controller import ControlPlane
from aireliability.control_plane.models import ControlPlaneConfig
from aireliability.core.models import TestCase
from aireliability.distributed.models import JobStatus
from aireliability.distributed.sqlite_storage import SQLiteDistributedStorage
from aireliability.distributed.storage import InMemoryDistributedStorage
from aireliability.observability.context import (
    clear_current_context,
    observability_context,
)
from aireliability.observability.models import HealthStatus
from aireliability.security.models import GatewayRequest, Principal
from aireliability.tenancy.models import RateLimitPolicy, ResourceQuota


def dummy_agent(inputs: dict[str, Any]) -> dict[str, Any]:
    text = inputs.get("text", "")
    if "fail_me" in text:
        raise RuntimeError("Controlled synthetic failure for test")
    return {"result": f"processed: {text}"}


class TestPhase30Workflows:
    """Complete workflow validations across all package subsystems."""

    def test_workflow_a_normal_job_e2e(self):
        async def run_test():
            clear_current_context()
            cp = ControlPlane(
                agent=dummy_agent,
                config=ControlPlaneConfig(max_concurrency=2),
            )
            # Register tenant and API key
            await cp.governance.register_tenant(
                "tenant_alpha",
                name="Alpha Corp",
                quota=ResourceQuota(max_queued_jobs=100, max_concurrent_jobs=10),
            )
            created_key = cp.gateway.api_keys.create_key(
                tenant_id="tenant_alpha",
                name="Alpha Agent Key",
                roles=["DEVELOPER"],
            )

            tc = TestCase(id="tc_wf_a", name="Workflow A Test", input={"text": "hello"})
            with observability_context(tenant_id="tenant_alpha", trace_id="trace_wf_a"):
                job = await cp.submit_job(
                    test_case=tc,
                    metadata={
                        "api_key": created_key.raw_key,
                        "tenant_id": "tenant_alpha",
                    },
                )
                assert job.job_id is not None

                # Process job through scheduler
                await cp.scheduler.tick()

                # Verify outcome persisted
                outcome = cp.storage.get_outcome(job.job_id)
                assert outcome is not None
                assert outcome.status == JobStatus.COMPLETED

                # Verify telemetry event emitted
                events = cp.observability.events.get_events(tenant_id="tenant_alpha")
                assert any(
                    e.event_type == "job.submitted" and e.job_id == job.job_id
                    for e in events
                )
                assert any(
                    e.event_type == "job.completed" and e.job_id == job.job_id
                    for e in events
                )

                # Verify snapshot status
                snap = cp.observability.snapshot(tenant_id="tenant_alpha")
                assert snap.system_status == HealthStatus.HEALTHY
                assert snap.success_rate >= 0.99

            await cp.stop()

        asyncio.run(run_test())

    def test_workflow_b_unauthorized_request_rejection(self):
        async def run_test():
            clear_current_context()
            cp = ControlPlane(agent=dummy_agent)
            await cp.governance.register_tenant("tenant_sec")

            tc = TestCase(id="tc_wf_b", name="Unauthorized", input={"text": "x"})

            # Attempt submission with forged invalid key
            from aireliability.security.errors import SecurityError

            with pytest.raises(SecurityError) as exc_info:
                await cp.submit_job(
                    test_case=tc,
                    metadata={
                        "api_key": "airel_forged_invalid_key_1234567890",
                        "tenant_id": "tenant_sec",
                    },
                )

            assert (
                "invalid" in str(exc_info.value).lower()
                or "reject" in str(exc_info.value).lower()
            )

            # Verify no job was queued
            from aireliability.control_plane.models import QueueState

            queued = await cp.queue.list_jobs(queue_state=QueueState.QUEUED)
            assert len(queued) == 0

            # Verify security audit event logged
            audits = cp.gateway.audit.list_events(tenant_id="tenant_sec")
            assert len(audits) >= 1
            assert any(a.result in ("rejected", "auth_failed") for a in audits)

            await cp.stop()

        asyncio.run(run_test())

    def test_workflow_c_cross_tenant_request_isolation(self):
        async def run_test():
            clear_current_context()
            cp = ControlPlane(agent=dummy_agent)
            await cp.governance.register_tenant("tenant_1")
            await cp.governance.register_tenant("tenant_2")

            # Tenant 1 API key
            key1 = cp.gateway.api_keys.create_key(
                tenant_id="tenant_1",
                name="Key 1",
                roles=["DEVELOPER"],
            )

            # Attempt to submit job for Tenant 2 using Tenant 1 key
            req = GatewayRequest(
                action="jobs.submit",
                tenant_id="tenant_2",
                api_key=key1.raw_key,
            )
            resp = cp.gateway.handle_request(req)
            assert not resp.allowed
            assert (
                "boundary" in str(resp.reason).lower()
                or "unauthorized" in str(resp.reason).lower()
                or "rejected" in str(resp.reason).lower()
            )

            await cp.stop()

        asyncio.run(run_test())

    def test_workflow_d_rate_limited_tenant(self):
        async def run_test():
            clear_current_context()
            cp = ControlPlane(agent=dummy_agent)
            await cp.governance.register_tenant("tenant_burst")

            # Configure strict rate limit
            strict_policy = RateLimitPolicy(rate=1.0, burst_capacity=1.0)
            cp.governance.rate_limiter.set_policy(
                "tenant_burst:default:default", strict_policy
            )
            cp.gateway.rate_limiter.set_policy(
                "sec:tenant_burst:user_burst", strict_policy
            )

            principal = Principal(
                principal_id="user_burst",
                tenant_id="tenant_burst",
                roles=["DEVELOPER"],
                permissions=["jobs.submit"],
            )

            req = GatewayRequest(
                action="jobs.submit",
                tenant_id="tenant_burst",
            )

            # First request allowed
            r1 = cp.gateway.handle_request(req, principal=principal)
            assert r1.allowed

            # Rapid second request rejected by rate limiter
            r2 = cp.gateway.handle_request(req, principal=principal)
            assert not r2.allowed
            assert "rate limit" in str(r2.reason).lower()

            await cp.stop()

        asyncio.run(run_test())

    def test_workflow_e_quota_exhaustion(self):
        async def run_test():
            clear_current_context()
            cp = ControlPlane(agent=dummy_agent)
            # Register tenant with max_queued_jobs = 1
            await cp.governance.register_tenant(
                "tenant_q",
                quota=ResourceQuota(max_queued_jobs=1, max_concurrent_jobs=10),
            )
            tc1 = TestCase(id="tc1", name="tc1", input={"text": "1"})
            tc2 = TestCase(id="tc2", name="tc2", input={"text": "2"})

            # First job enqueued successfully
            j1 = await cp.submit_job(tc1, metadata={"tenant_id": "tenant_q"})
            assert j1.job_id is not None

            # Second job triggers quota error
            from aireliability.tenancy import QuotaExceededError

            with pytest.raises(QuotaExceededError):
                await cp.submit_job(tc2, metadata={"tenant_id": "tenant_q"})

            await cp.stop()

        asyncio.run(run_test())

    def test_workflow_f_worker_failure_and_resilience_recovery(self):
        async def run_test():
            clear_current_context()
            cp = ControlPlane(
                agent=dummy_agent,
                config=ControlPlaneConfig(max_concurrency=1),
            )
            await cp.governance.register_tenant("tenant_fail")

            tc = TestCase(id="tc_fail", name="Fail Test", input={"text": "fail_me"})
            job = await cp.submit_job(
                tc,
                max_retries=1,
                metadata={"tenant_id": "tenant_fail"},
            )

            # Process job
            await cp.scheduler.tick()

            # Verify failure recorded
            outcome = cp.storage.get_outcome(job.job_id)
            assert outcome is not None
            assert outcome.status == JobStatus.FAILED

            # Verify resilience failure event
            failures = cp.resilience.get_failure_records(execution_id=job.execution_id)
            assert len(failures) >= 1

            # Observability captures failure event
            events = cp.observability.events.get_events(
                tenant_id="tenant_fail", event_type="job.failed"
            )
            assert len(events) >= 1

            await cp.stop()

        asyncio.run(run_test())

    def test_workflow_g_cancellation_boundaries(self):
        async def run_test():
            clear_current_context()
            cp = ControlPlane(agent=dummy_agent)
            await cp.governance.register_tenant("tenant_canc")

            tc = TestCase(id="tc_c", name="Cancel Test", input={"text": "hold"})
            job = await cp.submit_job(
                tc,
                delay_seconds=60.0,  # Scheduled in future
                metadata={"tenant_id": "tenant_canc"},
            )

            # Cancel job
            cancelled = await cp.cancel_job(job.job_id)
            assert cancelled.job_status == JobStatus.CANCELLED
            assert cp.cancellation.is_cancelled(job.job_id)

            await cp.stop()

        asyncio.run(run_test())

    def test_workflow_h_observability_correlation(self):
        async def run_test():
            clear_current_context()
            cp = ControlPlane(agent=dummy_agent)
            trace_id = "tr-corr-99"

            with observability_context(
                tenant_id="acme",
                project_id="proj_1",
                namespace="prod",
                trace_id=trace_id,
            ):
                tc = TestCase(id="tc_corr", name="tc_corr", input={"text": "ok"})
                job = await cp.submit_job(tc)
                await cp.scheduler.tick()

                # Fetch events and verify exact correlation
                events = cp.observability.events.get_events(trace_id=trace_id)
                assert len(events) >= 2
                for ev in events:
                    assert ev.trace_id == trace_id
                    assert ev.tenant_id == "acme"
                    assert ev.project_id == "proj_1"
                    assert ev.namespace == "prod"
                    assert ev.job_id == job.job_id

            await cp.stop()

        asyncio.run(run_test())


class TestPersistenceParity:
    """Validate InMemoryDistributedStorage and SQLiteDistributedStorage parity."""

    def test_sqlite_and_in_memory_parity(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            sqlite_path = tf.name

        try:
            in_mem = InMemoryDistributedStorage()
            sq_store = SQLiteDistributedStorage(db_path=sqlite_path)

            for store in (in_mem, sq_store):
                # 1. API key persistence
                class MockKey:
                    key_id = "k_1"
                    key_prefix = "airel_test"
                    hashed_secret = "hash"
                    salt = "salt"
                    tenant_id = "tenant_p"
                    project_id = "default"
                    namespace = "default"
                    name = "Key 1"
                    roles = ["DEVELOPER"]
                    permissions = ["jobs.submit"]
                    created_at = "2026-09-27T00:00:00"
                    expires_at = None
                    revoked = False
                    revoked_at = None
                    last_used_at = None
                    metadata = {}
                    is_active = True

                store.save_api_key(MockKey())
                keys = store.list_api_keys(tenant_id="tenant_p")
                assert len(keys) == 1

                # 2. Observability incident persistence
                from aireliability.observability.incidents import IncidentRecord
                from aireliability.observability.models import IncidentStatus

                inc = IncidentRecord(
                    incident_id="inc_parity_1",
                    severity="HIGH",
                    title="Parity Check",
                    description="Validating storage",
                    tenant_id="tenant_p",
                    status=IncidentStatus.DETECTED,
                )
                store.save_incident(inc)
                fetched_inc = store.get_incident("inc_parity_1")
                assert fetched_inc is not None
                assert fetched_inc.title == "Parity Check"

                # 3. Isolation
                assert len(store.list_api_keys(tenant_id="other")) == 0
                assert len(store.list_incidents(tenant_id="other")) == 0

                store.clear()
                assert len(store.list_api_keys()) == 0
                assert len(store.list_incidents()) == 0
        finally:
            if os.path.exists(sqlite_path):
                os.remove(sqlite_path)


class TestFailureAndRecovery:
    """Validate system fail-closed security/tenancy and fail-safe observability."""

    def test_observability_failure_does_not_break_core_execution(self):
        """Observability telemetry failures must NOT bring down core job execution."""

        async def run_test():
            clear_current_context()
            cp = ControlPlane(agent=dummy_agent)

            # Intentionally cause an error in an observability subscriber
            def broken_listener(evt):
                raise RuntimeError("Synthetic observability exporter crash!")

            cp.observability.events.subscribe(broken_listener)

            tc = TestCase(id="tc_obs_safe", name="Safe Test", input={"text": "hello"})
            # Job submission and completion must succeed even if subscriber crashed
            job = await cp.submit_job(tc)
            assert job.job_id is not None

            await cp.scheduler.tick()
            outcome = cp.storage.get_outcome(job.job_id)
            assert outcome is not None
            assert outcome.status == JobStatus.COMPLETED

            await cp.stop()

        asyncio.run(run_test())

    def test_tenant_suspension_blocks_admission(self):
        """Suspended tenants must fail closed immediately on admission."""

        async def run_test():
            clear_current_context()
            from aireliability.tenancy.models import TenantStatus

            cp = ControlPlane(agent=dummy_agent)
            await cp.governance.register_tenant("tenant_sus")
            await cp.governance.set_tenant_status("tenant_sus", TenantStatus.SUSPENDED)

            tc = TestCase(id="tc_sus", name="Suspended Test", input={"text": "x"})
            with pytest.raises(ValueError) as exc_info:
                await cp.submit_job(tc, metadata={"tenant_id": "tenant_sus"})

            assert "suspended" in str(exc_info.value).lower()
            await cp.stop()

        asyncio.run(run_test())

    def test_replay_attack_rejection(self):
        """Duplicate request_id or nonce within replay window must fail closed."""

        async def run_test():
            clear_current_context()
            cp = ControlPlane(agent=dummy_agent)
            req = GatewayRequest(
                request_id="req_unique_999",
                nonce="nonce_unique_111",
                action="jobs.submit",
            )
            # First request allowed
            r1 = cp.gateway.handle_request(req)
            assert r1.allowed

            # Replayed request rejected
            r2 = cp.gateway.handle_request(req)
            assert not r2.allowed
            assert "replay" in str(r2.reason).lower()

            await cp.stop()

        asyncio.run(run_test())

    def test_credential_sanitization_in_persisted_audit_and_exceptions(self):
        """Raw secrets, tokens, and keys must NEVER appear in audit records."""

        async def run_test():
            clear_current_context()
            secret_value = "super_secret_raw_token_xyz123"
            cp = ControlPlane(agent=dummy_agent)

            req = GatewayRequest(
                action="jobs.submit",
                api_key=f"airel_{secret_value}",
                bearer_token=secret_value,
                payload={"api_key": secret_value, "safe_data": 42},
            )
            resp = cp.gateway.handle_request(req)
            # Inspect audit records
            audits = cp.gateway.audit.list_events()
            for rec in audits:
                assert secret_value not in str(rec.reason or "")
                assert secret_value not in str(rec.metadata or {})

            # Verify response does not leak secret
            assert secret_value not in str(resp.reason or "")
            await cp.stop()

        asyncio.run(run_test())


class TestConcurrencySafety:
    """Validate concurrency behavior across queues, workers, and rate limiters."""

    def test_concurrent_quota_reservations(self):
        async def run_test():
            clear_current_context()
            from aireliability.tenancy.quota import QuotaManager

            qm = QuotaManager()
            qm.set_quota("t_conc", ResourceQuota(max_queued_jobs=10))

            # Simulate concurrent admissions
            async def try_admit():
                allowed, _ = await qm.check_job_admission("t_conc", requested_jobs=1)
                if allowed:
                    await qm.record_job_enqueued("t_conc", count=1)
                return allowed

            results = await asyncio.gather(*(try_admit() for _ in range(20)))
            admitted = [r for r in results if r]
            rejected = [r for r in results if not r]
            assert len(admitted) == 10
            assert len(rejected) == 10

        asyncio.run(run_test())
