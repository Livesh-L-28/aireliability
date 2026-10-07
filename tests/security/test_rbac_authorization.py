"""Role-Based Access Control (RBAC) comprehensive authorization matrix test suite."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aireliability.api.app import create_app
from aireliability.tenancy.models import TenantContext, TenantPermission, TenantRole
from aireliability.tenancy.rbac import RBACManager

# Canonical Authorization Matrix: Role -> Set of Permitted Operations
EXPECTED_MATRIX: dict[TenantRole, set[TenantPermission]] = {
    TenantRole.OWNER: {
        TenantPermission.READ,
        TenantPermission.WRITE,
        TenantPermission.EXECUTE,
        TenantPermission.EVALUATE,
        TenantPermission.MANAGE_POLICIES,
        TenantPermission.MANAGE_USERS,
        TenantPermission.MANAGE_TENANTS,
        TenantPermission.RUN_SAFETY,
        TenantPermission.RUN_OPTIMIZATION,
        TenantPermission.RUN_HEALING,
        TenantPermission.MANAGE_API_KEYS,
        TenantPermission.READ_AUDIT,
        TenantPermission.ADMIN,
    },
    TenantRole.ADMIN: {
        TenantPermission.READ,
        TenantPermission.WRITE,
        TenantPermission.EXECUTE,
        TenantPermission.EVALUATE,
        TenantPermission.MANAGE_POLICIES,
        TenantPermission.MANAGE_USERS,
        TenantPermission.RUN_SAFETY,
        TenantPermission.RUN_OPTIMIZATION,
        TenantPermission.RUN_HEALING,
        TenantPermission.MANAGE_API_KEYS,
        TenantPermission.READ_AUDIT,
    },
    TenantRole.ENGINEER: {
        TenantPermission.READ,
        TenantPermission.WRITE,
        TenantPermission.EXECUTE,
        TenantPermission.EVALUATE,
        TenantPermission.RUN_SAFETY,
        TenantPermission.RUN_OPTIMIZATION,
        TenantPermission.RUN_HEALING,
    },
    TenantRole.ANALYST: {
        TenantPermission.READ,
        TenantPermission.EVALUATE,
        TenantPermission.READ_AUDIT,
    },
    TenantRole.VIEWER: {
        TenantPermission.READ,
    },
    TenantRole.AUDITOR: {
        TenantPermission.READ,
        TenantPermission.READ_AUDIT,
    },
    TenantRole.SERVICE_ACCOUNT: {
        TenantPermission.READ,
        TenantPermission.WRITE,
        TenantPermission.EXECUTE,
        TenantPermission.EVALUATE,
    },
}

ALL_PERMISSIONS = [
    TenantPermission.READ,
    TenantPermission.WRITE,
    TenantPermission.EXECUTE,
    TenantPermission.EVALUATE,
    TenantPermission.MANAGE_POLICIES,
    TenantPermission.MANAGE_USERS,
    TenantPermission.MANAGE_TENANTS,
    TenantPermission.RUN_SAFETY,
    TenantPermission.RUN_OPTIMIZATION,
    TenantPermission.RUN_HEALING,
    TenantPermission.MANAGE_API_KEYS,
    TenantPermission.READ_AUDIT,
    TenantPermission.ADMIN,
]

ALL_ROLES = [
    TenantRole.OWNER,
    TenantRole.ADMIN,
    TenantRole.ENGINEER,
    TenantRole.ANALYST,
    TenantRole.VIEWER,
    TenantRole.AUDITOR,
    TenantRole.SERVICE_ACCOUNT,
]


@pytest.mark.parametrize("role", ALL_ROLES)
@pytest.mark.parametrize("permission", ALL_PERMISSIONS)
def test_rbac_authorization_matrix(role: TenantRole, permission: TenantPermission):
    """Test every single (Role × Operation) combination against RBACManager."""
    rbac = RBACManager()
    ctx = TenantContext(
        organization_id="org_test",
        tenant_id="tenant_test",
        actor_id=f"actor_{role.value}",
        roles=[role],
    )

    expected_allowed = permission in EXPECTED_MATRIX[role]
    actual_allowed = rbac.check_permission(ctx, permission)
    assert actual_allowed == expected_allowed, (
        f"RBAC check failed for Role '{role.value}' and Permission '{permission.value}'. "
        f"Expected {expected_allowed}, got {actual_allowed}."
    )


def test_api_endpoint_rbac_enforcement():
    """Verify RBAC is enforced across FastAPI endpoints."""
    app = create_app()
    client = TestClient(app)

    # 1. VIEWER can read datasets, but cannot create evaluations or manage tenants
    viewer_headers = {"Authorization": "Bearer bearer_token_tenant_rbac_user1_viewer"}
    resp_read = client.get("/api/v1/datasets", headers=viewer_headers)
    assert resp_read.status_code == 200

    resp_eval = client.post(
        "/api/v1/evaluations",
        headers=viewer_headers,
        json={"input_text": "hi", "output_text": "there"},
    )
    assert resp_eval.status_code == 403

    resp_tenant = client.post(
        "/api/v1/tenants",
        headers=viewer_headers,
        json={"tenant_id": "new_t"},
    )
    assert resp_tenant.status_code == 403

    # 2. AUDITOR can read audit logs, but cannot run healing or optimization
    auditor_headers = {"Authorization": "Bearer bearer_token_tenant_rbac_user2_auditor"}
    resp_audit = client.get("/api/v1/audit", headers=auditor_headers)
    assert resp_audit.status_code == 200

    resp_healing = client.post(
        "/api/v1/healing/plan",
        headers=auditor_headers,
        json={},
    )
    assert resp_healing.status_code == 403

    # 3. ENGINEER can evaluate and run safety, but cannot read audit logs
    engineer_headers = {
        "Authorization": "Bearer bearer_token_tenant_rbac_user3_engineer"
    }
    resp_eng_eval = client.post(
        "/api/v1/evaluations",
        headers=engineer_headers,
        json={"input_text": "eng", "output_text": "response"},
    )
    assert resp_eng_eval.status_code == 200

    resp_eng_audit = client.get("/api/v1/audit", headers=engineer_headers)
    assert resp_eng_audit.status_code == 403

    # 4. OWNER can perform all operations
    owner_headers = {"Authorization": "Bearer bearer_token_tenant_rbac_user4_owner"}
    assert client.get("/api/v1/audit", headers=owner_headers).status_code == 200
    assert (
        client.post("/api/v1/healing/plan", headers=owner_headers, json={}).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/tenants", headers=owner_headers, json={"name": "Owner T"}
        ).status_code
        == 200
    )
