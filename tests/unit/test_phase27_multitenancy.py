"""Unit and integration tests for Phase 27 — Multi-Tenancy, Isolation &
Resource Governance.

Covers:
- Tenant model & lifecycle (ACTIVE, SUSPENDED, DISABLED)
- Tenant, project, and namespace boundaries
- Resource quotas (max_queued_jobs, max_concurrent_jobs, tokens, violation tracking)
- Rate limiting (FIXED_WINDOW, SLIDING_WINDOW, TOKEN_BUCKET)
- Fair and weighted tenant scheduling policies
- Tenant-aware worker allocation & selection constraints
- Tenant-aware cancellation (job, tenant, project, namespace)
- Tenant-aware persistence queries (InMemory & SQLite)
- Authorization boundaries (TenantAccessPolicy)
- ResourceGovernanceManager admission pipeline
- ControlPlane tenant-aware execution & metrics
- Complete backward compatibility with Phases 1-26
"""

import asyncio
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from aireliability.control_plane import (
    ControlPlane,
    JobPriority,
    ScheduledJob,
    WorkerCapacityInfo,
    WorkerManager,
)
from aireliability.core.models import TestCase
from aireliability.distributed.models import ReliabilityJob
from aireliability.distributed.sqlite_storage import SQLiteDistributedStorage
from aireliability.distributed.storage import InMemoryDistributedStorage
from aireliability.tenancy import (
    ProjectContext,
    QuotaExceededError,
    QuotaManager,
    RateLimitAlgorithm,
    RateLimiter,
    RateLimitPolicy,
    ResourceGovernanceManager,
    ResourceNamespace,
    ResourceQuota,
    Tenant,
    TenantAccessPolicy,
    TenantContext,
    TenantFairSchedulingPolicy,
    TenantPriorityPolicy,
    TenantStatus,
    WeightedTenantSchedulingPolicy,
)


def test_tenant_lifecycle():
    """Verify tenant creation, properties, and lifecycle transitions."""
    t = Tenant(
        tenant_id="tenant-alpha",
        name="Alpha Corp",
        status=TenantStatus.ACTIVE,
        quota=ResourceQuota(max_concurrent_jobs=5, max_queued_jobs=20),
    )
    assert t.tenant_id == "tenant-alpha"
    assert t.is_active is True
    assert t.quota.max_concurrent_jobs == 5

    # Suspend
    suspended = t.model_copy(update={"status": TenantStatus.SUSPENDED})
    assert suspended.is_active is False
    assert suspended.status == TenantStatus.SUSPENDED

    # Disabled
    disabled = t.model_copy(update={"status": TenantStatus.DISABLED})
    assert disabled.is_active is False
    assert disabled.status == TenantStatus.DISABLED


def test_tenant_and_project_contexts():
    """Verify TenantContext, ProjectContext, and ResourceNamespace hierarchy."""
    ctx = TenantContext(
        tenant_id="tenant-1",
        project_id="proj-finance",
        namespace="eval-staging",
    )
    assert ctx.tenant_id == "tenant-1"
    assert ctx.project_id == "proj-finance"
    assert ctx.namespace == "eval-staging"
    assert ctx.scope_key == "tenant-1:proj-finance:eval-staging"

    p_ctx = ProjectContext(tenant_id="tenant-1", project_id="proj-finance")
    assert p_ctx.scope_key == "tenant-1:proj-finance"

    r_ns = ResourceNamespace(tenant_id="tenant-1", namespace="eval-staging")
    assert r_ns.scope_key == "tenant-1:eval-staging"

    # Default context fallback
    def_ctx = TenantContext()
    assert def_ctx.tenant_id == "default"
    assert def_ctx.project_id == "default"
    assert def_ctx.namespace == "default"


def test_quota_manager_enforcement():
    """Verify QuotaManager limits for queued and concurrent jobs."""

    async def run_test():
        qm = QuotaManager()
        quota = ResourceQuota(max_queued_jobs=2, max_concurrent_jobs=1)
        qm.set_quota("tenant-q", quota)

        # Queue check: 2 allowed, 3rd fails
        can_queue, _ = await qm.check_job_admission("tenant-q", requested_jobs=1)
        assert can_queue is True
        await qm.record_job_enqueued("tenant-q", count=2)

        can_queue2, reason = await qm.check_job_admission("tenant-q", requested_jobs=1)
        assert can_queue2 is False
        assert "quota exceeded" in reason

        # Concurrency check
        can_exec, _ = await qm.check_job_execution("tenant-q", requested_concurrency=1)
        assert can_exec is True
        await qm.acquire_concurrency("tenant-q", count=1)

        can_exec2, reason2 = await qm.check_job_execution(
            "tenant-q", requested_concurrency=1
        )
        assert can_exec2 is False
        assert "concurrent jobs quota exceeded" in reason2

        # Releasing concurrency restores execution capacity
        await qm.release_concurrency("tenant-q", count=1)
        can_exec3, _ = await qm.check_job_execution("tenant-q", requested_concurrency=1)
        assert can_exec3 is True

        # Token usage tracking
        await qm.record_token_usage("tenant-q", tokens=150)
        usage = await qm.get_usage("tenant-q")
        assert usage.total_tokens_consumed == 150
        assert usage.queued_jobs == 2

        # Violation tracking
        violations = qm.list_violations("tenant-q")
        assert len(violations) >= 2

    asyncio.run(run_test())


def test_rate_limiter_algorithms():
    """Verify Token Bucket, Fixed Window, and Sliding Window algorithms."""

    async def run_test():
        rl = RateLimiter()

        # 1. Token Bucket
        tb_policy = RateLimitPolicy(
            rate=2,
            burst=2,
            window_seconds=10.0,
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
        )
        rl.set_policy("tenant:tb", tb_policy)

        d1 = await rl.check("tenant:tb", cost=1)
        assert d1.allowed is True
        d2 = await rl.check("tenant:tb", cost=1)
        assert d2.allowed is True
        d3 = await rl.check("tenant:tb", cost=1)
        assert d3.allowed is False
        assert "exhausted" in d3.reason or "exceeded" in d3.reason

        # 2. Fixed Window
        fw_policy = RateLimitPolicy(
            rate=2,
            window_seconds=60.0,
            algorithm=RateLimitAlgorithm.FIXED_WINDOW,
        )
        rl.set_policy("tenant:fw", fw_policy)

        assert (await rl.check("tenant:fw")).allowed is True
        assert (await rl.check("tenant:fw")).allowed is True
        assert (await rl.check("tenant:fw")).allowed is False

        # 3. Sliding Window
        sw_policy = RateLimitPolicy(
            rate=2,
            window_seconds=60.0,
            algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
        )
        rl.set_policy("tenant:sw", sw_policy)

        assert (await rl.check("tenant:sw")).allowed is True
        assert (await rl.check("tenant:sw")).allowed is True
        assert (await rl.check("tenant:sw")).allowed is False

    asyncio.run(run_test())


def test_tenant_fair_and_weighted_scheduling():
    """Verify round-robin fair and proportional weighted scheduling."""

    def make_job(job_id: str, tenant_id: str) -> ScheduledJob:
        return ScheduledJob(
            job_id=job_id,
            test_case=TestCase(id=job_id, name=job_id, input="x"),
            metadata={"tenant_id": tenant_id},
        )

    # 1. Fair round-robin across tenants
    fair_policy = TenantFairSchedulingPolicy()
    jobs = [
        make_job("j1", "tenant-A"),
        make_job("j2", "tenant-A"),
        make_job("j3", "tenant-B"),
        make_job("j4", "tenant-B"),
    ]

    selected1 = fair_policy.select_next(jobs)
    assert selected1 is not None and selected1.job_id == "j1"

    # Next round should pick tenant-B
    remaining1 = [j for j in jobs if j.job_id != selected1.job_id]
    selected2 = fair_policy.select_next(remaining1)
    assert selected2 is not None and selected2.job_id == "j3"

    # 2. Weighted tenant scheduling
    weighted_policy = WeightedTenantSchedulingPolicy(
        tenant_weights={"tenant-A": 1, "tenant-B": 3}
    )
    w_jobs = [
        make_job("wa1", "tenant-A"),
        make_job("wb1", "tenant-B"),
        make_job("wb2", "tenant-B"),
    ]
    w_selected = weighted_policy.select_next(w_jobs)
    assert w_selected is not None
    assert w_selected.metadata["tenant_id"] == "tenant-B"

    # 3. TenantPriorityPolicy
    pri_policy = TenantPriorityPolicy(tenant_weights={"tenant-High": 10})
    p_jobs = [
        ScheduledJob(
            job_id="p1",
            priority=JobPriority.NORMAL,
            test_case=TestCase(id="tc1", name="tc1", input="x"),
            metadata={"tenant_id": "tenant-Normal"},
        ),
        ScheduledJob(
            job_id="p2",
            priority=JobPriority.CRITICAL,
            test_case=TestCase(id="tc2", name="tc2", input="x"),
            metadata={"tenant_id": "tenant-Normal"},
        ),
    ]
    p_sel = pri_policy.select_next(p_jobs)
    assert p_sel is not None and p_sel.job_id == "p2"


def test_tenant_aware_worker_allocation():
    """Verify WorkerCapacityInfo constraint matching and select_best_worker."""

    async def run_test():
        storage = InMemoryDistributedStorage()
        wm = WorkerManager(storage=storage)

        # Worker 1: General worker (no restrictions)
        await wm.register_worker("worker-general", capacity=2)

        # Worker 2: Dedicated worker for tenant-A
        w2_info = WorkerCapacityInfo(
            worker_id="worker-dedicated-a",
            capacity=2,
            active_jobs=0,
            last_heartbeat=datetime.now(UTC),
            is_active=True,
            metadata={"supported_tenants": ["tenant-A"]},
        )
        await wm.register_worker(
            w2_info.worker_id, capacity=w2_info.capacity, metadata=w2_info.metadata
        )

        # Worker 2 should not match tenant-B
        w_b = await wm.select_best_worker(tenant_id="tenant-B")
        assert w_b is not None
        assert w_b.worker_id == "worker-general"

        # Worker 2 should be eligible for tenant-A
        w_a = await wm.select_best_worker(tenant_id="tenant-A")
        assert w_a is not None
        assert w_a.worker_id in ("worker-general", "worker-dedicated-a")

    asyncio.run(run_test())


def test_tenant_aware_cancellation():
    """Verify tenant, project, and namespace cooperative cancellation."""
    from aireliability.control_plane.cancellation import CancellationCoordinator

    coord = CancellationCoordinator()

    jobs = [
        ScheduledJob(
            job_id="j_a1",
            test_case=TestCase(id="1", name="1", input="x"),
            metadata={"tenant_id": "tenant-A", "project_id": "proj-1"},
        ),
        ScheduledJob(
            job_id="j_a2",
            test_case=TestCase(id="2", name="2", input="x"),
            metadata={"tenant_id": "tenant-A", "project_id": "proj-2"},
        ),
        ScheduledJob(
            job_id="j_b1",
            test_case=TestCase(id="3", name="3", input="x"),
            metadata={"tenant_id": "tenant-B", "project_id": "proj-1"},
        ),
    ]

    # Cancel only tenant-A
    cancelled_a = coord.cancel_tenant("tenant-A", jobs)
    assert len(cancelled_a) == 2
    assert all(getattr(j, "tenant_id", "default") == "tenant-A" for j in cancelled_a)
    assert coord.is_cancelled("j_a1") is True
    assert coord.is_cancelled("j_a2") is True
    assert coord.is_cancelled("j_b1") is False

    # Cancel by project
    coord2 = CancellationCoordinator()
    cancelled_proj = coord2.cancel_project("proj-1", jobs)
    assert len(cancelled_proj) == 2
    assert {j.job_id for j in cancelled_proj} == {"j_a1", "j_b1"}


def test_tenant_aware_persistence_queries():
    """Verify tenant filtering in InMemoryDistributedStorage and SQLite."""
    # Test InMemory
    in_mem = InMemoryDistributedStorage()
    rel_a = ReliabilityJob(
        job_id="job_a",
        execution_id="exec_1",
        test_case=TestCase(id="tc_a", name="tc_a", input="a"),
        metadata={"tenant_id": "tenant-A", "project_id": "p1"},
    )
    rel_b = ReliabilityJob(
        job_id="job_b",
        execution_id="exec_1",
        test_case=TestCase(id="tc_b", name="tc_b", input="b"),
        metadata={"tenant_id": "tenant-B", "project_id": "p2"},
    )
    in_mem.save_job(rel_a)
    in_mem.save_job(rel_b)

    all_jobs = in_mem.list_jobs()
    assert len(all_jobs) == 2
    tenant_a_jobs = in_mem.list_jobs(tenant_id="tenant-A")
    assert len(tenant_a_jobs) == 1
    assert tenant_a_jobs[0].job_id == "job_a"

    # Test SQLite
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_tenancy.db"
        sqlite_storage = SQLiteDistributedStorage(db_path)
        sqlite_storage.save_job(rel_a)
        sqlite_storage.save_job(rel_b)

        sq_all = sqlite_storage.list_jobs()
        assert len(sq_all) == 2
        sq_a = sqlite_storage.list_jobs(tenant_id="tenant-A")
        assert len(sq_a) == 1
        assert sq_a[0].job_id == "job_a"
        sq_b = sqlite_storage.list_jobs(tenant_id="tenant-B")
        assert len(sq_b) == 1
        assert sq_b[0].job_id == "job_b"


def test_authorization_boundaries():
    """Verify TenantAccessPolicy rules for cross-tenant isolation."""
    policy = TenantAccessPolicy()

    actor_a = TenantContext(tenant_id="tenant-A")

    # Tenant-A can access Tenant-A resources
    assert policy.can_access(actor_a, target_tenant_id="tenant-A") is True
    assert policy.can_read(actor_a, "tenant-A") is True
    assert policy.can_submit(actor_a, "tenant-A") is True
    assert policy.can_cancel(actor_a, "tenant-A") is True
    assert policy.can_administer(actor_a, "tenant-A") is True

    # Tenant-A CANNOT access Tenant-B resources
    assert policy.can_access(actor_a, target_tenant_id="tenant-B") is False
    assert policy.can_read(actor_a, "tenant-B") is False
    assert policy.can_submit(actor_a, "tenant-B") is False
    assert policy.can_cancel(actor_a, "tenant-B") is False
    assert policy.can_administer(actor_a, "tenant-B") is False

    # System/admin bypass
    admin_ctx = TenantContext(
        tenant_id="tenant-A",
        metadata={"role": "system_admin"},
    )
    assert policy.can_access(admin_ctx, "tenant-B") is True
    assert policy.can_cancel(admin_ctx, "tenant-B") is True


def test_resource_governance_admission_pipeline():
    """Verify full admission flow:
    Tenant Status -> Quota -> Rate Limit -> Resilience.
    """

    async def run_test():
        gov = ResourceGovernanceManager()

        # 1. Register active tenant
        await gov.register_tenant(
            "tenant-active", quota=ResourceQuota(max_queued_jobs=1)
        )
        ctx_active = TenantContext(tenant_id="tenant-active")
        allowed, _ = await gov.check_admission(ctx_active)
        assert allowed is True

        # 2. Suspended tenant is rejected
        await gov.register_tenant("tenant-susp")
        await gov.set_tenant_status("tenant-susp", TenantStatus.SUSPENDED)
        ctx_susp = TenantContext(tenant_id="tenant-susp")
        with pytest.raises(ValueError, match="SUSPENDED"):
            await gov.check_admission(ctx_susp)

        # 3. Quota exceeded rejection
        await gov.quota_manager.record_job_enqueued("tenant-active", count=1)
        with pytest.raises(QuotaExceededError):
            await gov.check_admission(ctx_active)

    asyncio.run(run_test())


def test_control_plane_multi_tenant_execution():
    """Verify end-to-end execution with tenant metadata and metrics in ControlPlane."""

    async def run_test():
        def simple_agent(inputs: dict[str, str]) -> dict[str, str]:
            return {"echo": inputs.get("msg", "ok")}

        storage = InMemoryDistributedStorage()
        cp = ControlPlane(agent=simple_agent, storage=storage)

        tc_a = TestCase(id="tc_t_a", name="tc_t_a", input={"msg": "hello-A"})
        tc_b = TestCase(id="tc_t_b", name="tc_t_b", input={"msg": "hello-B"})

        j_a = await cp.submit_job(
            tc_a,
            metadata={"tenant_id": "tenant-A", "project_id": "proj-X"},
        )
        j_b = await cp.submit_job(
            tc_b,
            metadata={"tenant_id": "tenant-B", "project_id": "proj-Y"},
        )

        assert j_a.tenant_id == "tenant-A"
        assert j_b.tenant_id == "tenant-B"

        # List jobs filtered by tenant in storage
        jobs_a = storage.list_jobs(tenant_id="tenant-A")
        assert len(jobs_a) == 1
        assert jobs_a[0].job_id == j_a.job_id

        jobs_b = storage.list_jobs(tenant_id="tenant-B")
        assert len(jobs_b) == 1
        assert jobs_b[0].job_id == j_b.job_id

        await cp.stop()

    asyncio.run(run_test())


def test_backward_compatibility_defaults():
    """Verify that omitting tenant configuration defaults gracefully to 'default'."""
    job = ScheduledJob(
        test_case=TestCase(id="tc_default", name="tc_default", input="test"),
    )
    assert job.tenant_id == "default"
    assert job.project_id == "default"
    assert job.namespace == "default"

    rel_job = ReliabilityJob(
        execution_id="exec_def",
        test_case=TestCase(id="tc_def", name="tc_def", input="test"),
    )
    assert rel_job.tenant_id == "default"
    assert rel_job.project_id == "default"
    assert rel_job.namespace == "default"
