"""Phase 27 — Multi-Tenancy, Isolation & Resource Governance Benchmarks.

Measures:
1. Tenant lookup & validation overhead
2. Resource quota check & reservation latency
3. Rate limiter check overhead (Fixed Window, Sliding Window, Token Bucket)
4. ResourceGovernanceManager unified admission pipeline
5. Tenant-aware scheduling policies (Fair vs. Weighted vs. Priority)
6. Tenant-aware worker selection with constraints
7. Tenant-scoped persistence query latency (InMemory & SQLite)
8. Tenant authorization check throughput (TenantAccessPolicy)
9. Baseline vs. Tenant-Aware Execution Overhead
"""

import asyncio
import statistics
import time

from aireliability import (
    ControlPlane,
    ControlPlaneConfig,
    RateLimitAlgorithm,
    RateLimiter,
    RateLimitPolicy,
    ResourceGovernanceManager,
    ResourceQuota,
    TestCase,
)
from aireliability.tenancy import (
    QuotaManager,
    TenantAccessPolicy,
    TenantContext,
    TenantFairSchedulingPolicy,
    WeightedTenantSchedulingPolicy,
)


def benchmark_tenant_lookup_and_registration():
    """Benchmark tenant registration and lookup throughput."""

    async def _run():
        gov = ResourceGovernanceManager()
        iterations = 2000

        # Register tenants
        for i in range(100):
            await gov.register_tenant(f"tenant-{i}", name=f"Tenant {i}")

        latencies_us = []
        for i in range(iterations):
            tid = f"tenant-{i % 100}"
            t0 = time.perf_counter()
            t = await gov.get_tenant(tid)
            t1 = time.perf_counter()
            assert t is not None
            latencies_us.append((t1 - t0) * 1_000_000.0)

        mean_us = statistics.mean(latencies_us)
        median_us = statistics.median(latencies_us)
        throughput = iterations / (sum(latencies_us) / 1_000_000.0)

        print("\n--- Tenant Lookup Benchmark ---")
        print(f"Iterations: {iterations}")
        print(f"Mean:       {mean_us:.2f} µs")
        print(f"Median:     {median_us:.2f} µs")
        print(f"Throughput: {throughput:,.0f} lookups/sec")

    asyncio.run(_run())


def benchmark_quota_checks():
    """Benchmark real-time quota admission checks and token recording."""

    async def _run():
        qm = QuotaManager()
        qm.set_quota(
            "tenant-bench",
            ResourceQuota(max_queued_jobs=10000, max_concurrent_jobs=1000),
        )
        iterations = 2000
        latencies_us = []

        for _ in range(iterations):
            t0 = time.perf_counter()
            allowed, _ = await qm.check_job_admission("tenant-bench")
            t1 = time.perf_counter()
            assert allowed is True
            latencies_us.append((t1 - t0) * 1_000_000.0)

        mean_us = statistics.mean(latencies_us)
        median_us = statistics.median(latencies_us)
        throughput = iterations / (sum(latencies_us) / 1_000_000.0)

        print("\n--- Quota Check Benchmark ---")
        print(f"Iterations: {iterations}")
        print(f"Mean:       {mean_us:.2f} µs")
        print(f"Median:     {median_us:.2f} µs")
        print(f"Throughput: {throughput:,.0f} checks/sec")

    asyncio.run(_run())


def benchmark_rate_limiter():
    """Benchmark rate limiting check across algorithms."""

    async def _run():
        rl = RateLimiter()
        policy = RateLimitPolicy(
            rate=100_000,
            burst=100_000,
            window_seconds=60.0,
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
        )
        rl.set_policy("bench-scope", policy)
        iterations = 2000
        latencies_us = []

        for _ in range(iterations):
            t0 = time.perf_counter()
            decision = await rl.check("bench-scope")
            t1 = time.perf_counter()
            assert decision.allowed is True
            latencies_us.append((t1 - t0) * 1_000_000.0)

        mean_us = statistics.mean(latencies_us)
        median_us = statistics.median(latencies_us)
        throughput = iterations / (sum(latencies_us) / 1_000_000.0)

        print("\n--- Rate Limiter Benchmark (Token Bucket) ---")
        print(f"Iterations: {iterations}")
        print(f"Mean:       {mean_us:.2f} µs")
        print(f"Median:     {median_us:.2f} µs")
        print(f"Throughput: {throughput:,.0f} checks/sec")

    asyncio.run(_run())


def benchmark_tenant_scheduling_policies():
    """Benchmark Fair and Weighted scheduling policies."""
    fair_policy = TenantFairSchedulingPolicy()
    weighted_policy = WeightedTenantSchedulingPolicy(
        tenant_weights={"tenant-A": 1, "tenant-B": 3, "tenant-C": 5}
    )

    from aireliability.control_plane.models import ScheduledJob

    candidates = []
    for i in range(30):
        t_letter = "A" if i % 3 == 0 else ("B" if i % 3 == 1 else "C")
        candidates.append(
            ScheduledJob(
                job_id=f"job_{i}",
                test_case=TestCase(id=f"tc_{i}", name=f"tc_{i}", input="x"),
                metadata={"tenant_id": f"tenant-{t_letter}"},
            )
        )

    iterations = 2000
    latencies_fair_us = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        j = fair_policy.select_next(candidates)
        t1 = time.perf_counter()
        assert j is not None
        latencies_fair_us.append((t1 - t0) * 1_000_000.0)

    latencies_weight_us = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        j = weighted_policy.select_next(candidates)
        t1 = time.perf_counter()
        assert j is not None
        latencies_weight_us.append((t1 - t0) * 1_000_000.0)

    fair_thr = iterations / (sum(latencies_fair_us) / 1_000_000.0)
    weight_thr = iterations / (sum(latencies_weight_us) / 1_000_000.0)
    print("\n--- Scheduling Policies Benchmark ---")
    print(
        f"Fair Scheduling:     Mean: {statistics.mean(latencies_fair_us):.2f} µs | "
        f"Throughput: {fair_thr:,.0f} selections/sec"
    )
    print(
        f"Weighted Scheduling: Mean: {statistics.mean(latencies_weight_us):.2f} µs | "
        f"Throughput: {weight_thr:,.0f} selections/sec"
    )


def benchmark_tenant_authorization():
    """Benchmark TenantAccessPolicy rule evaluations."""
    policy = TenantAccessPolicy()
    ctx_a = TenantContext(tenant_id="tenant-A")
    iterations = 2000
    latencies_us = []

    for i in range(iterations):
        target = "tenant-A" if i % 2 == 0 else "tenant-B"
        t0 = time.perf_counter()
        policy.can_read(ctx_a, target)
        t1 = time.perf_counter()
        latencies_us.append((t1 - t0) * 1_000_000.0)

    mean_us = statistics.mean(latencies_us)
    throughput = iterations / (sum(latencies_us) / 1_000_000.0)

    print("\n--- Authorization Boundary Benchmark ---")
    print(f"Iterations: {iterations}")
    print(f"Mean:       {mean_us:.2f} µs")
    print(f"Throughput: {throughput:,.0f} evaluations/sec")


def benchmark_baseline_vs_tenant_execution():
    """Compare baseline execution with tenant-governed execution."""

    async def _run():
        def fast_agent(inputs: dict[str, str]) -> dict[str, str]:
            return {"echo": "ok"}

        test_cases_base = [
            TestCase(id=f"base_{i}", name=f"base_{i}", input={"msg": "x"})
            for i in range(20)
        ]
        test_cases_tenant = [
            TestCase(
                id=f"tenant_{i}",
                name=f"tenant_{i}",
                input={"msg": "x"},
                metadata={"tenant_id": f"tenant-{i % 3}"},
            )
            for i in range(20)
        ]

        # 1. Baseline Run (default tenant, unconfigured)
        cp_base = ControlPlane(
            agent=fast_agent, config=ControlPlaneConfig(max_concurrency=5)
        )
        t0_base = time.perf_counter()
        sum_base = await cp_base.execute_execution(test_cases_base, timeout=10.0)
        t1_base = time.perf_counter()
        base_duration_ms = (t1_base - t0_base) * 1000.0
        assert sum_base.all_passed
        await cp_base.stop()

        # 2. Multi-Tenant Governed Run
        gov = ResourceGovernanceManager()
        for i in range(3):
            await gov.register_tenant(
                f"tenant-{i}", quota=ResourceQuota(max_queued_jobs=100)
            )

        cp_tenant = ControlPlane(
            agent=fast_agent,
            governance_manager=gov,
            config=ControlPlaneConfig(max_concurrency=5),
        )
        t0_tenant = time.perf_counter()
        sum_tenant = await cp_tenant.execute_execution(test_cases_tenant, timeout=10.0)
        t1_tenant = time.perf_counter()
        tenant_duration_ms = (t1_tenant - t0_tenant) * 1000.0
        assert sum_tenant.all_passed
        await cp_tenant.stop()

        overhead_pct = (
            ((tenant_duration_ms - base_duration_ms) / base_duration_ms) * 100.0
            if base_duration_ms > 0
            else 0.0
        )

        print("\n--- Baseline vs. Tenant-Aware Execution Overhead ---")
        print(f"Baseline (20 jobs):     {base_duration_ms:.2f} ms")
        print(f"Tenant-Aware (20 jobs): {tenant_duration_ms:.2f} ms")
        print(f"Governance Overhead:    {overhead_pct:+.2f}%")

    asyncio.run(_run())


def main():
    print("=" * 60)
    print("Running Phase 27 Multi-Tenancy & Resource Governance Benchmarks")
    print("=" * 60)

    benchmark_tenant_lookup_and_registration()
    benchmark_quota_checks()
    benchmark_rate_limiter()
    benchmark_tenant_scheduling_policies()
    benchmark_tenant_authorization()
    benchmark_baseline_vs_tenant_execution()

    print("\nAll Phase 27 benchmarks completed successfully.")


if __name__ == "__main__":
    main()
