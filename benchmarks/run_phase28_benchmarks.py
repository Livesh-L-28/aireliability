"""Performance and latency benchmarks for Phase 28 — Secure API Gateway."""

import asyncio
import time

from aireliability.control_plane.controller import ControlPlane
from aireliability.core.models import TestCase
from aireliability.distributed.storage import InMemoryDistributedStorage
from aireliability.security.api_keys import APIKeyManager
from aireliability.security.audit import AuditLogger
from aireliability.security.authorization import AuthorizationEngine
from aireliability.security.gateway import SecurityGateway
from aireliability.security.models import (
    GatewayRequest,
    Principal,
)
from aireliability.security.replay_protection import ReplayProtection
from aireliability.security.tokens import SimpleSignedTokenValidator


def benchmark_api_key_verification(iterations: int = 5_000) -> float:
    mgr = APIKeyManager()
    created = mgr.create_key(tenant_id="bench-tenant")
    raw_key = created.raw_key

    # Warmup
    for _ in range(50):
        mgr.verify_key(raw_key)

    start = time.perf_counter()
    for _ in range(iterations):
        mgr.verify_key(raw_key)
    elapsed = time.perf_counter() - start
    return (elapsed / iterations) * 1_000_000  # microseconds


def benchmark_token_validation(iterations: int = 5_000) -> float:
    validator = SimpleSignedTokenValidator(secret="benchmark-secret-key-1234567890")
    token = validator.create_token(
        sub="bench-user", tenant_id="bench-tenant", roles=["DEVELOPER"]
    )

    # Warmup
    for _ in range(50):
        validator.validate_token(token)

    start = time.perf_counter()
    for _ in range(iterations):
        validator.validate_token(token)
    elapsed = time.perf_counter() - start
    return (elapsed / iterations) * 1_000_000  # microseconds


def benchmark_authorization_decision(iterations: int = 10_000) -> float:
    engine = AuthorizationEngine()
    principal = Principal(
        principal_id="bench-user",
        tenant_id="bench-tenant",
        roles=["DEVELOPER"],
        permissions=["jobs.read", "jobs.submit"],
        authenticated=True,
    )

    # Warmup
    for _ in range(100):
        engine.authorize(principal, "jobs.submit", tenant_id="bench-tenant")

    start = time.perf_counter()
    for _ in range(iterations):
        engine.authorize(principal, "jobs.submit", tenant_id="bench-tenant")
    elapsed = time.perf_counter() - start
    return (elapsed / iterations) * 1_000_000  # microseconds


def benchmark_tenant_boundary_check(iterations: int = 10_000) -> float:
    engine = AuthorizationEngine()
    principal = Principal(
        principal_id="bench-user",
        tenant_id="tenant-alpha",
        roles=["DEVELOPER"],
        permissions=["jobs.submit"],
        authenticated=True,
    )

    # Warmup
    for _ in range(100):
        engine.authorize(principal, "jobs.submit", tenant_id="tenant-beta")

    start = time.perf_counter()
    for _ in range(iterations):
        engine.authorize(principal, "jobs.submit", tenant_id="tenant-beta")
    elapsed = time.perf_counter() - start
    return (elapsed / iterations) * 1_000_000  # microseconds


def benchmark_replay_check(iterations: int = 10_000) -> float:
    replay = ReplayProtection(window_seconds=300.0)

    # Warmup
    for i in range(100):
        replay.check_and_record(f"warm_{i}")

    start = time.perf_counter()
    for i in range(iterations):
        replay.check_and_record(f"req_{i}")
    elapsed = time.perf_counter() - start
    return (elapsed / iterations) * 1_000_000  # microseconds


def benchmark_audit_event_creation(iterations: int = 5_000) -> float:
    audit = AuditLogger()

    # Warmup
    for _ in range(50):
        audit.record(action="jobs.submit", result="allowed", tenant_id="bench-tenant")

    start = time.perf_counter()
    for _ in range(iterations):
        audit.record(action="jobs.submit", result="allowed", tenant_id="bench-tenant")
    elapsed = time.perf_counter() - start
    return (elapsed / iterations) * 1_000_000  # microseconds


def benchmark_gateway_handle_request(iterations: int = 5_000) -> float:
    gw = SecurityGateway()
    key_res = gw.api_keys.create_key(tenant_id="bench-tenant", roles=["DEVELOPER"])
    raw_key = key_res.raw_key

    # Warmup
    for _ in range(50):
        req = GatewayRequest(
            action="jobs.read",
            tenant_id="bench-tenant",
            api_key=raw_key,
        )
        gw.handle_request(req)

    start = time.perf_counter()
    for i in range(iterations):
        req = GatewayRequest(
            request_id=f"gw_{i}",
            action="jobs.read",
            tenant_id="bench-tenant",
            api_key=raw_key,
        )
        gw.handle_request(req)
    elapsed = time.perf_counter() - start
    return (elapsed / iterations) * 1_000_000  # microseconds


def benchmark_control_plane_gateway_overhead(iterations: int = 500) -> float:
    async def run_comparison() -> float:
        tc = TestCase(id="tc_bench", name="tc_bench", input="payload")

        # 1. Baseline submission (direct without gateway overhead)
        from aireliability.security.models import GatewayResponse
        from aireliability.tenancy.models import RateLimitPolicy, ResourceQuota

        storage_base = InMemoryDistributedStorage()
        cp_base = ControlPlane(storage=storage_base)
        await cp_base.governance.register_tenant(
            "default",
            quota=ResourceQuota(max_queued_jobs=100_000, max_concurrent_jobs=100_000),
        )
        unlimited_policy = RateLimitPolicy(rate=100_000.0, burst_capacity=100_000.0)
        cp_base.governance.rate_limiter.default_policy = unlimited_policy
        cp_base.governance.rate_limiter.set_policy(
            "default:default:default", unlimited_policy
        )

        orig_handle = cp_base.gateway.handle_request
        cp_base.gateway.handle_request = lambda r, h=None: GatewayResponse(
            status="success", request_id=r.request_id, allowed=True
        )

        # Warmup
        for _ in range(10):
            await cp_base.submit_job(tc)

        start_base = time.perf_counter()
        for _ in range(iterations):
            await cp_base.submit_job(tc)
        time_base = time.perf_counter() - start_base
        await cp_base.stop()

        # Restore
        cp_base.gateway.handle_request = orig_handle

        # 2. Gateway-enabled submission
        storage_gw = InMemoryDistributedStorage()
        cp_gw = ControlPlane(storage=storage_gw)
        await cp_gw.governance.register_tenant(
            "default",
            quota=ResourceQuota(max_queued_jobs=100_000, max_concurrent_jobs=100_000),
        )
        cp_gw.governance.rate_limiter.default_policy = unlimited_policy
        cp_gw.governance.rate_limiter.set_policy(
            "default:default:default", unlimited_policy
        )
        cp_gw.gateway.rate_limiter.default_policy = unlimited_policy
        key_res = cp_gw.gateway.api_keys.create_key(
            tenant_id="default", roles=["ADMIN"]
        )

        for _ in range(10):
            await cp_gw.submit_job(tc, metadata={"api_key": key_res.raw_key})

        start_gw = time.perf_counter()
        for _ in range(iterations):
            await cp_gw.submit_job(tc, metadata={"api_key": key_res.raw_key})
        time_gw = time.perf_counter() - start_gw
        await cp_gw.stop()

        overhead_pct = ((time_gw - time_base) / time_base) * 100.0
        return overhead_pct

    return asyncio.run(run_comparison())


def main() -> None:
    print("=" * 70)
    print("AI Reliability Engine — Phase 28 Security Benchmarks")
    print("=" * 70)

    t_key = benchmark_api_key_verification()
    print(f"API Key Verification:        {t_key:6.2f} µs / op")

    t_tok = benchmark_token_validation()
    print(f"Token Validation:            {t_tok:6.2f} µs / op")

    t_authz = benchmark_authorization_decision()
    print(f"Authorization Decision:      {t_authz:6.2f} µs / op")

    t_bnd = benchmark_tenant_boundary_check()
    print(f"Tenant Boundary Check:       {t_bnd:6.2f} µs / op")

    t_rep = benchmark_replay_check()
    print(f"Replay Protection Check:     {t_rep:6.2f} µs / op")

    t_aud = benchmark_audit_event_creation()
    print(f"Audit Event Creation:        {t_aud:6.2f} µs / op")

    t_gw = benchmark_gateway_handle_request()
    print(f"Gateway Full Request:        {t_gw:6.2f} µs / op")

    overhead = benchmark_control_plane_gateway_overhead()
    print(f"ControlPlane Gateway Overhead: {overhead:+.2f} %")
    print("=" * 70)


if __name__ == "__main__":
    main()
