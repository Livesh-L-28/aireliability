"""Unit tests for Phase 28 — Secure API Gateway, Authentication & Authorization."""

import time
from datetime import UTC, datetime, timedelta

import pytest

from aireliability.control_plane.controller import ControlPlane
from aireliability.core.models import TestCase
from aireliability.distributed.metrics import DistributedMetrics
from aireliability.distributed.sqlite_storage import SQLiteDistributedStorage
from aireliability.distributed.storage import InMemoryDistributedStorage
from aireliability.security.api_keys import APIKeyManager
from aireliability.security.audit import AuditLogger
from aireliability.security.authorization import AuthorizationEngine
from aireliability.security.errors import (
    ExpiredCredentialError,
    InvalidAPIKeyError,
    SecurityError,
)
from aireliability.security.gateway import SecurityGateway
from aireliability.security.models import (
    AuthorizationDecision,
    GatewayRequest,
    Principal,
)
from aireliability.security.replay_protection import ReplayProtection
from aireliability.security.request_validator import RequestValidator
from aireliability.security.roles import RoleManager
from aireliability.security.tokens import SimpleSignedTokenValidator
from aireliability.tenancy.rate_limiter import RateLimiter, RateLimitPolicy

# --- 1. API Key Authentication Tests ---


def test_api_key_creation_and_verification() -> None:
    mgr = APIKeyManager()
    created = mgr.create_key(tenant_id="tenant-a", name="Test Key")
    assert created.raw_key.startswith("airel_")
    assert created.key.tenant_id == "tenant-a"
    assert created.key.is_active

    # Verification success
    verified = mgr.verify_key(created.raw_key)
    assert verified.key_id == created.key.key_id
    assert verified.last_used_at is not None


def test_invalid_and_malformed_api_key() -> None:
    mgr = APIKeyManager()
    mgr.create_key(tenant_id="tenant-a")

    with pytest.raises(InvalidAPIKeyError):
        mgr.verify_key("invalid_format_key")

    with pytest.raises(InvalidAPIKeyError):
        mgr.verify_key("airel_nonexistentsecretkey1234567890")


def test_revoked_api_key() -> None:
    mgr = APIKeyManager()
    created = mgr.create_key(tenant_id="tenant-a")
    mgr.revoke_key(created.key.key_id)

    with pytest.raises(ExpiredCredentialError, match="revoked"):
        mgr.verify_key(created.raw_key)


def test_expired_api_key() -> None:
    mgr = APIKeyManager()
    past_expiry = datetime.now(UTC) - timedelta(seconds=10)
    created = mgr.create_key(tenant_id="tenant-a", expires_at=past_expiry)

    with pytest.raises(ExpiredCredentialError, match="expired"):
        mgr.verify_key(created.raw_key)


def test_api_key_rotation() -> None:
    mgr = APIKeyManager()
    created = mgr.create_key(tenant_id="tenant-a", name="Rotation Key")
    rotated = mgr.rotate_key(created.key.key_id)

    # Old key revoked
    with pytest.raises(ExpiredCredentialError):
        mgr.verify_key(created.raw_key)

    # New key functional
    verified = mgr.verify_key(rotated.raw_key)
    assert verified.key_id == rotated.key.key_id
    assert verified.tenant_id == "tenant-a"


# --- 2. Token Authentication Tests ---


def test_signed_token_creation_and_validation() -> None:
    validator = SimpleSignedTokenValidator(secret="test-token-secret")
    token = validator.create_token(
        sub="user-123",
        tenant_id="tenant-token",
        roles=["DEVELOPER"],
        permissions=["jobs.submit"],
        expires_in_seconds=60.0,
    )
    res = validator.validate_token(token)
    assert res.valid
    assert res.claims is not None
    assert res.claims.sub == "user-123"
    assert res.claims.tenant_id == "tenant-token"
    assert "jobs.submit" in res.claims.permissions


def test_expired_and_tampered_token() -> None:
    validator = SimpleSignedTokenValidator(secret="test-token-secret")
    expired_token = validator.create_token(sub="user-1", expires_in_seconds=-10.0)
    res = validator.validate_token(expired_token)
    assert not res.valid
    assert "expired" in (res.reason or "").lower()

    # Tampered signature
    valid_token = validator.create_token(sub="user-2", expires_in_seconds=60.0)
    tampered = valid_token[:-4] + "dead"
    res_tampered = validator.validate_token(tampered)
    assert not res_tampered.valid


# --- 3. Authorization & RBAC Tests ---


def test_authorization_allowed_permissions() -> None:
    engine = AuthorizationEngine()
    principal = Principal(
        principal_id="dev-1",
        tenant_id="tenant-a",
        roles=["DEVELOPER"],
        permissions=["jobs.read", "jobs.submit"],
        authenticated=True,
    )
    decision, reason = engine.authorize(
        principal=principal,
        action="jobs.submit",
        tenant_id="tenant-a",
    )
    assert decision == AuthorizationDecision.ALLOW
    assert reason is None


def test_authorization_denied_permissions() -> None:
    engine = AuthorizationEngine()
    principal = Principal(
        principal_id="viewer-1",
        tenant_id="tenant-a",
        roles=["VIEWER"],
        permissions=["jobs.read"],
        authenticated=True,
    )
    decision, reason = engine.authorize(
        principal=principal,
        action="jobs.submit",
        tenant_id="tenant-a",
    )
    assert decision == AuthorizationDecision.DENY
    assert "Permission denied" in (reason or "")


def test_role_manager_permission_expansion() -> None:
    role_mgr = RoleManager()
    perms = role_mgr.get_permissions_for_roles(["DEVELOPER"])
    assert "jobs.submit" in perms
    assert "jobs.read" in perms
    assert "tenants.manage" not in perms

    admin_perms = role_mgr.get_permissions_for_roles(["ADMIN"])
    assert "tenants.manage" in admin_perms
    assert "security.manage" in admin_perms


# --- 4. Tenant, Project, and Namespace Isolation Tests ---


def test_cross_tenant_isolation_boundary() -> None:
    engine = AuthorizationEngine()
    principal = Principal(
        principal_id="dev-tenant-a",
        tenant_id="tenant-a",
        roles=["DEVELOPER"],
        permissions=["jobs.submit"],
        authenticated=True,
    )
    # Attempt to act on tenant-b
    decision, reason = engine.authorize(
        principal=principal,
        action="jobs.submit",
        tenant_id="tenant-b",
    )
    assert decision == AuthorizationDecision.DENY
    assert "Tenant boundary violation" in (reason or "")


def test_global_admin_cross_tenant_allowed() -> None:
    engine = AuthorizationEngine()
    admin = Principal(
        principal_id="global-admin",
        tenant_id="system",
        roles=["ADMIN"],
        permissions=["*"],
        authenticated=True,
    )
    decision, reason = engine.authorize(
        principal=admin,
        action="jobs.submit",
        tenant_id="tenant-any",
    )
    assert decision == AuthorizationDecision.ALLOW


def test_project_and_namespace_isolation() -> None:
    engine = AuthorizationEngine()
    scoped_user = Principal(
        principal_id="scoped-dev",
        tenant_id="tenant-a",
        project_id="project-1",
        namespace="prod",
        roles=["DEVELOPER"],
        permissions=["jobs.submit"],
        authenticated=True,
    )
    # Different project
    dec, reason = engine.authorize(
        scoped_user, action="jobs.submit", tenant_id="tenant-a", project_id="project-2"
    )
    assert dec == AuthorizationDecision.DENY
    assert "Project boundary violation" in (reason or "")

    # Different namespace
    dec, reason = engine.authorize(
        scoped_user,
        action="jobs.submit",
        tenant_id="tenant-a",
        project_id="project-1",
        namespace="staging",
    )
    assert dec == AuthorizationDecision.DENY
    assert "Namespace boundary violation" in (reason or "")


# --- 5. Request Validation Tests ---


def test_request_validation_success_and_failure() -> None:
    validator = RequestValidator(max_payload_bytes=100)
    valid_req = GatewayRequest(
        request_id="req-123",
        action="jobs.submit",
        tenant_id="tenant-a",
        payload={"k": "v"},
    )
    res = validator.validate(valid_req)
    assert res.valid

    # Invalid tenant ID format
    bad_req = GatewayRequest(
        request_id="req-124",
        action="jobs.submit",
        tenant_id="invalid/tenant!@#",
    )
    res_bad = validator.validate(bad_req)
    assert not res_bad.valid
    assert "Invalid tenant_id format" in (res_bad.reason or "")

    # Exceeded payload size
    oversized_req = GatewayRequest(
        request_id="req-125",
        action="jobs.submit",
        tenant_id="tenant-a",
        payload={"data": "x" * 200},
    )
    res_over = validator.validate(oversized_req)
    assert not res_over.valid
    assert "Payload size exceeds" in (res_over.reason or "")


# --- 6. Replay Protection Tests ---


def test_replay_protection_duplicate_request_and_nonce() -> None:
    replay = ReplayProtection(window_seconds=60.0)
    ok, _ = replay.check_and_record(request_id="req-unique-1", nonce="nonce-1")
    assert ok

    # Duplicate request ID
    ok_dup_req, reason_req = replay.check_and_record(
        request_id="req-unique-1", nonce="nonce-2"
    )
    assert not ok_dup_req
    assert "duplicate request_id" in (reason_req or "")

    # Duplicate nonce
    ok_dup_nonce, reason_nonce = replay.check_and_record(
        request_id="req-unique-2", nonce="nonce-1"
    )
    assert not ok_dup_nonce
    assert "duplicate nonce" in (reason_nonce or "")


def test_replay_protection_expired_timestamp() -> None:
    replay = ReplayProtection(window_seconds=30.0)
    stale_time = time.time() - 100.0  # 100 seconds ago
    ok, reason = replay.check_and_record(
        request_id="req-stale", request_timestamp=stale_time
    )
    assert not ok
    assert "Request timestamp expired" in (reason or "")


# --- 7. Gateway Pipeline & Rate Limiting Tests ---


def test_gateway_full_successful_request() -> None:
    gw = SecurityGateway()
    key_res = gw.api_keys.create_key(
        tenant_id="acme",
        roles=["DEVELOPER"],
    )
    req = GatewayRequest(
        action="jobs.submit",
        tenant_id="acme",
        api_key=key_res.raw_key,
        payload={"task": "reliability_eval"},
    )
    resp = gw.handle_request(
        req, handler=lambda r, p: {"status": "enqueued", "owner": p.principal_id}
    )
    assert resp.allowed
    assert resp.status == "success"
    assert resp.data.get("status") == "enqueued"
    assert resp.principal is not None
    assert resp.principal.tenant_id == "acme"


def test_gateway_rejection_on_auth_failure() -> None:
    gw = SecurityGateway()
    req = GatewayRequest(
        action="jobs.submit",
        tenant_id="acme",
        api_key="airel_boguskeyvalue99999",
    )
    resp = gw.handle_request(req)
    assert not resp.allowed
    assert resp.status == "rejected"
    assert "not recognized" in (resp.reason or "")


def test_gateway_rejection_on_security_rate_limit() -> None:
    limiter = RateLimiter(default_policy=RateLimitPolicy(rate=2.0, burst_capacity=2.0))
    gw = SecurityGateway(rate_limiter=limiter)
    key_res = gw.api_keys.create_key(tenant_id="rate-test", roles=["DEVELOPER"])

    # 1st request
    req1 = GatewayRequest(
        request_id="r1",
        action="jobs.read",
        tenant_id="rate-test",
        api_key=key_res.raw_key,
    )
    assert gw.handle_request(req1).allowed

    # 2nd request
    req2 = GatewayRequest(
        request_id="r2",
        action="jobs.read",
        tenant_id="rate-test",
        api_key=key_res.raw_key,
    )
    assert gw.handle_request(req2).allowed

    # 3rd request should hit rate limit
    req3 = GatewayRequest(
        request_id="r3",
        action="jobs.read",
        tenant_id="rate-test",
        api_key=key_res.raw_key,
    )
    resp3 = gw.handle_request(req3)
    assert not resp3.allowed
    assert "rate limit" in (resp3.reason or "").lower()


# --- 8. Audit Logging & Sanitization Tests ---


def test_audit_logging_and_credential_sanitization() -> None:
    audit = AuditLogger()
    event = audit.record(
        action="api_keys.create",
        result="success",
        principal_id="admin-1",
        tenant_id="acme",
        metadata={
            "key_name": "Prod Key",
            "api_key": "airel_secretvalue_should_be_stripped",
            "secret": "top-secret-password",
        },
    )
    # Ensure sensitive credentials were completely redacted
    assert "api_key" not in event.metadata
    assert "secret" not in event.metadata
    assert event.metadata.get("key_name") == "Prod Key"

    events = audit.list_events(tenant_id="acme")
    assert len(events) == 1
    assert events[0].action == "api_keys.create"


# --- 9. Persistence (SQLite) Tests ---


def test_sqlite_security_persistence() -> None:
    storage = SQLiteDistributedStorage(":memory:")
    mgr = APIKeyManager(storage=storage)
    created = mgr.create_key(tenant_id="sql-tenant", name="SQLite Key")

    # Verify retrieval from sqlite
    fetched = storage.get_api_key(created.key.key_id)
    assert fetched is not None
    assert fetched.key_id == created.key.key_id
    assert fetched.tenant_id == "sql-tenant"

    # List keys
    keys = storage.list_api_keys(tenant_id="sql-tenant")
    assert len(keys) == 1

    # Audit events
    audit = AuditLogger(storage=storage)
    audit.record(
        action="jobs.submit",
        result="allowed",
        principal_id="sql-user",
        tenant_id="sql-tenant",
    )
    aud_events = storage.list_audit_events(tenant_id="sql-tenant")
    assert len(aud_events) == 1
    assert aud_events[0].action == "jobs.submit"


# --- 10. Control Plane Integration Tests ---


def test_control_plane_gateway_rejection_prevents_resource_consumption() -> None:
    async def run_test() -> None:
        storage = InMemoryDistributedStorage()
        metrics = DistributedMetrics()
        cp = ControlPlane(storage=storage, metrics=metrics)

        # Submit job with mismatched tenant identity
        test_case = TestCase(id="sec_test_1", name="Security Test Case", input="hello")

        # Attaching non-admin API key belonging to another tenant
        bad_key = cp.gateway.api_keys.create_key(tenant_id="tenant-x")

        with pytest.raises(SecurityError, match="Tenant boundary violation"):
            await cp.submit_job(
                test_case,
                metadata={
                    "tenant_id": "tenant-target",
                    "api_key": bad_key.raw_key,
                },
            )

        # Verify no job or quota was consumed in the queue
        assert await cp.queue.size() == 0
        assert len(storage.list_jobs()) == 0

    import asyncio

    asyncio.run(run_test())
