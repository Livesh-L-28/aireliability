"""Benchmark suite for Multi-Tenancy Architecture (Phase 45) across tenant scales."""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

# Path setup for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aireliability.tenancy.context import TenantContextManager
from aireliability.tenancy.isolation import (
    CrossTenantAccessError,
    TenantIsolationManager,
)
from aireliability.tenancy.models import (
    TenantContext,
    TenantPermission,
    TenantQuota,
    TenantResource,
    TenantRole,
)
from aireliability.tenancy.rbac import RBACManager
from aireliability.tenancy.usage import UsageTracker
from benchmarks.benchmark_config import BenchmarkConfig
from benchmarks.benchmark_utils import BenchmarkMetric, measure_benchmark


def make_tenant_context(tenant_idx: int) -> TenantContext:
    """Create a synthetic TenantContext."""
    return TenantContext(
        organization_id=f"org_{tenant_idx // 10}",
        tenant_id=f"tenant_{tenant_idx:04d}",
        actor_id=f"user_{tenant_idx}",
        roles=[TenantRole.ENGINEER],
    )


def run_multitenancy_benchmarks(config: BenchmarkConfig) -> list[BenchmarkMetric]:
    metrics: list[BenchmarkMetric] = []
    isolation_mgr = TenantIsolationManager()
    rbac_mgr = RBACManager()
    usage_tracker = UsageTracker()

    # Pre-populate 1,000 tenants in usage tracker
    for i in range(min(1000, config.sizes.LARGE)):
        t_id = f"tenant_{i:04d}"
        usage_tracker.set_quota(
            t_id,
            TenantQuota(max_evaluations=100000, max_api_requests=500000),
        )

    # 1. Tenant Context Creation
    def bench_context_creation() -> None:
        _ = TenantContext(
            organization_id="org_benchmark",
            tenant_id="tenant_0001",
            actor_id="user_bench",
            roles=[TenantRole.ENGINEER, TenantRole.ANALYST],
        )

    metrics.append(
        measure_benchmark(
            operation="tenancy_context_creation",
            target_func=bench_context_creation,
            input_size="Single TenantContext instantiation",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("tenant_isolation_check"),
            seed=config.seed,
        )
    )

    ctx_sample = make_tenant_context(1)
    resource_same = TenantResource(
        resource_id="res_001",
        resource_type="dataset",
        tenant_id=ctx_sample.tenant_id,
        organization_id=ctx_sample.organization_id,
    )
    resource_diff = TenantResource(
        resource_id="res_999",
        resource_type="dataset",
        tenant_id="tenant_foreign",
        organization_id="org_foreign",
    )

    # 2. Isolation Verification - Authorized Access (Within-tenant boundary)
    def bench_isolation_verify_authorized() -> None:
        _ = isolation_mgr.verify_access(
            resource=resource_same, context=ctx_sample, action="read"
        )

    metrics.append(
        measure_benchmark(
            operation="tenancy_isolation_verify_authorized",
            target_func=bench_isolation_verify_authorized,
            input_size="Authorized tenant resource boundary check",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("tenant_isolation_check"),
            seed=config.seed,
        )
    )

    # 3. Isolation Verification - Cross-Tenant Leakage Rejection (Veto check)
    def bench_isolation_rejection() -> None:
        with contextlib.suppress(CrossTenantAccessError):
            isolation_mgr.verify_access(
                resource=resource_diff, context=ctx_sample, action="read"
            )

    metrics.append(
        measure_benchmark(
            operation="tenancy_isolation_cross_tenant_rejection",
            target_func=bench_isolation_rejection,
            input_size="Cross-tenant access denial check",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("tenant_isolation_check"),
            seed=config.seed,
        )
    )

    # 4. RBAC Authorization Decision
    def bench_rbac_authorization() -> None:
        _ = rbac_mgr.check_permission(ctx_sample, TenantPermission.EVALUATE)

    metrics.append(
        measure_benchmark(
            operation="tenancy_rbac_permission_check",
            target_func=bench_rbac_authorization,
            input_size="RBAC permission resolution",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("tenant_isolation_check"),
            seed=config.seed,
        )
    )

    # 5. Quota Lookup (Across 1,000 tenants)
    def bench_quota_lookup_1000() -> None:
        for i in range(100):
            _ = usage_tracker.get_quota(f"tenant_{(i * 7) % 1000:04d}")

    metrics.append(
        measure_benchmark(
            operation="tenancy_quota_lookup_100",
            target_func=bench_quota_lookup_1000,
            input_size="100 quota lookups across 1,000 tenants",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("tenant_isolation_check"),
            seed=config.seed,
        )
    )

    # 6. Usage Tracking (Recording evaluations within quota)
    def bench_record_usage() -> None:
        usage_tracker.record_usage(
            tenant_id="tenant_0001",
            evaluations=1,
            tokens=120,
            requests=1,
        )

    metrics.append(
        measure_benchmark(
            operation="tenancy_record_usage_enforcement",
            target_func=bench_record_usage,
            input_size="Record resource usage and check quota",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("tenant_isolation_check"),
            seed=config.seed,
        )
    )

    # 7. Thread-Local Context Switch & Reset
    def bench_context_switch() -> None:
        tok = TenantContextManager.set_current_context(ctx_sample)
        _ = TenantContextManager.get_current_context()
        TenantContextManager.reset_context(tok)

    metrics.append(
        measure_benchmark(
            operation="tenancy_contextvar_switch_and_reset",
            target_func=bench_context_switch,
            input_size="ContextVar state switch and reset",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("tenant_isolation_check"),
            seed=config.seed,
        )
    )

    return metrics


if __name__ == "__main__":
    cfg = BenchmarkConfig.from_mode("quick")
    res = run_multitenancy_benchmarks(cfg)
    for m in res:
        print(
            f"[{m.status}] {m.operation}: p50={m.median_latency_ms}ms, p95={m.p95_latency_ms}ms, throughput={m.throughput_ops} ops/s"
        )
