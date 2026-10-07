"""Unit tests for Phase 45 Enterprise Multi-Tenancy."""

from __future__ import annotations

import pytest

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
from aireliability.tenancy.usage import QuotaExceededError, UsageTracker


def test_tenant_context_and_rbac():
    rbac = RBACManager()
    ctx = TenantContext(
        organization_id="org_1",
        tenant_id="tenant_a",
        roles=[TenantRole.ENGINEER],
    )
    # Engineer has READ, WRITE, EVALUATE, RUN_SAFETY
    assert rbac.check_permission(ctx, TenantPermission.READ) is True
    assert rbac.check_permission(ctx, TenantPermission.RUN_SAFETY) is True
    # Engineer does not have MANAGE_USERS
    assert rbac.check_permission(ctx, TenantPermission.MANAGE_USERS) is False


def test_tenant_isolation_enforcement():
    mgr = TenantIsolationManager()
    res_a = TenantResource(
        resource_id="eval_100", tenant_id="tenant_a", resource_type="evaluation"
    )

    ctx_a = TenantContext(organization_id="org_1", tenant_id="tenant_a")
    ctx_b = TenantContext(organization_id="org_1", tenant_id="tenant_b")

    # Tenant A accesses own resource -> Allowed
    assert mgr.verify_access(res_a, context=ctx_a) is True

    # Tenant B tries to access Tenant A resource -> DENIED with CrossTenantAccessError
    with pytest.raises(CrossTenantAccessError) as exc:
        mgr.verify_access(res_a, context=ctx_b)
    assert "belongs to another tenant" in str(exc.value)

    # Verify audit event logged for DENY
    deny_events = [e for e in mgr.audit_log if e.decision == "DENY"]
    assert len(deny_events) == 1
    assert deny_events[0].tenant_id == "tenant_b"


def test_usage_tracker_and_quotas():
    tracker = UsageTracker()
    tracker.set_quota("tenant_x", TenantQuota(max_evaluations=10))

    # Record 5 evaluations
    tracker.record_usage("tenant_x", evaluations=5)
    usage = tracker.get_usage("tenant_x")
    assert usage.evaluations_count == 5

    # Try recording 6 more (exceeds max 10)
    with pytest.raises(QuotaExceededError):
        tracker.record_usage("tenant_x", evaluations=6)
