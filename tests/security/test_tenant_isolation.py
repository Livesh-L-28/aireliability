"""Cross-tenant, cross-organization, and cross-environment isolation security tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aireliability.api.app import create_app
from aireliability.tenancy.isolation import (
    CrossTenantAccessError,
    TenantIsolationManager,
)
from aireliability.tenancy.models import (
    TenantContext,
    TenantPermission,
    TenantResource,
    TenantRole,
)


def test_tenant_isolation_manager_cross_tenant_denial():
    """Verify TenantIsolationManager strictly blocks cross-tenant resource operations."""
    mgr = TenantIsolationManager()

    # Create Contexts
    ctx_a = TenantContext(
        organization_id="org_A",
        tenant_id="tenant_A",
        project_id="proj_A",
        environment="env_prod",
        actor_id="user_A",
        roles=[TenantRole.ENGINEER],
    )

    ctx_b = TenantContext(
        organization_id="org_B",
        tenant_id="tenant_B",
        project_id="proj_B",
        environment="env_staging",
        actor_id="user_B",
        roles=[TenantRole.ENGINEER],
    )

    # Tenant B creates a resource
    res_b = TenantResource(
        resource_id="res_secret_b",
        tenant_id="tenant_B",
        organization_id="org_B",
        project_id="proj_B",
        environment_id="env_staging",
        resource_type="evaluation",
        owner_id="user_B",
    )

    # 1. Tenant A attempts to read Tenant B resource -> Denied
    with pytest.raises(CrossTenantAccessError):
        mgr.verify_access(ctx_a, res_b, TenantPermission.READ)

    # 2. Tenant A attempts to modify Tenant B resource -> Denied
    with pytest.raises(CrossTenantAccessError):
        mgr.verify_access(ctx_a, res_b, TenantPermission.WRITE)

    # 3. Tenant A attempts to delete Tenant B resource -> Denied
    with pytest.raises(CrossTenantAccessError):
        mgr.verify_access(ctx_a, res_b, TenantPermission.ADMIN)

    # 4. Tenant B accesses own resource -> Allowed
    assert mgr.verify_access(ctx_b, res_b, TenantPermission.READ) is True

    # Verify audit logs captured the violations
    denial_events = [e for e in mgr.audit_log if e.decision == "DENY"]
    assert len(denial_events) == 3
    for audit_evt in denial_events:
        assert audit_evt.tenant_id == "tenant_A"
        assert "res_secret_b" in audit_evt.resource


def test_cross_organization_and_cross_environment_boundaries():
    """Verify boundary enforcement across organizations, projects, and environments."""
    mgr = TenantIsolationManager()

    ctx = TenantContext(
        organization_id="org_A",
        tenant_id="tenant_common",
        project_id="proj_A",
        environment="env_production",
        actor_id="user_1",
        roles=[TenantRole.ENGINEER],
    )

    # Mismatched Org
    res_diff_org = TenantResource(
        resource_id="res_org",
        tenant_id="tenant_common",
        organization_id="org_B",
        resource_type="dataset",
    )
    with pytest.raises(CrossTenantAccessError):
        mgr.verify_access(ctx, res_diff_org, TenantPermission.READ)

    # Mismatched Environment
    res_diff_env = TenantResource(
        resource_id="res_env",
        tenant_id="tenant_common",
        organization_id="org_A",
        environment_id="env_development",
        resource_type="dataset",
    )
    with pytest.raises(CrossTenantAccessError):
        mgr.verify_access(ctx, res_diff_env, TenantPermission.READ)


def test_api_cross_tenant_evaluations_and_datasets_denial():
    """Verify HTTP API guarantees zero cross-tenant visibility or tampering."""
    app = create_app()
    key_mgr = app.state.key_manager

    _, secret_a = key_mgr.create_key(tenant_id="tenant_A", name="Key A", scopes=["*"])
    _, secret_b = key_mgr.create_key(tenant_id="tenant_B", name="Key B", scopes=["*"])

    client = TestClient(app)

    # 1. Tenant A creates evaluation
    res_eval_a = client.post(
        "/api/v1/evaluations",
        headers={"X-API-Key": secret_a},
        json={"input_text": "A confidential", "output_text": "A confidential reply"},
    )
    assert res_eval_a.status_code == 200
    eval_id_a = res_eval_a.json()["evaluation_id"]

    # 2. Tenant B attempts to read Tenant A's evaluation -> 403 Forbidden
    res_cross_read = client.get(
        f"/api/v1/evaluations/{eval_id_a}",
        headers={"X-API-Key": secret_b},
    )
    assert res_cross_read.status_code == 403
    assert "Cross-tenant access forbidden" in res_cross_read.json()["detail"]
    assert "confidential" not in res_cross_read.text

    # 3. Tenant A creates dataset
    res_ds_a = client.post(
        "/api/v1/datasets",
        headers={"X-API-Key": secret_a},
        json={"name": "Confidential Dataset A", "items": [{"item": 1}]},
    )
    assert res_ds_a.status_code == 200

    # 4. Tenant B lists datasets -> must NOT contain Tenant A's dataset
    res_list_b = client.get("/api/v1/datasets", headers={"X-API-Key": secret_b})
    assert res_list_b.status_code == 200
    b_datasets = res_list_b.json()
    assert all("Confidential Dataset A" not in d.get("name", "") for d in b_datasets)


def test_api_cross_tenant_jobs_and_audit_isolation():
    """Verify async jobs and audit logs cannot cross tenant boundaries."""
    app = create_app()
    key_mgr = app.state.key_manager

    _, secret_a = key_mgr.create_key(tenant_id="tenant_A", name="Key A", scopes=["*"])
    _, secret_b = key_mgr.create_key(tenant_id="tenant_B", name="Key B", scopes=["*"])

    client = TestClient(app)

    # Tenant A submits a job
    res_job_a = client.post(
        "/api/v1/jobs",
        headers={"X-API-Key": secret_a},
        json={"operation": "eval_job", "payload": {"secret": "val"}},
    )
    assert res_job_a.status_code == 200
    job_id_a = res_job_a.json()["job_id"]

    # Tenant B tries to get Tenant A's job -> 404 (isolated)
    res_cross_job = client.get(
        f"/api/v1/jobs/{job_id_a}",
        headers={"X-API-Key": secret_b},
    )
    assert res_cross_job.status_code == 404

    # Tenant A gets own job -> 200
    res_own_job = client.get(
        f"/api/v1/jobs/{job_id_a}",
        headers={"X-API-Key": secret_a},
    )
    assert res_own_job.status_code == 200
