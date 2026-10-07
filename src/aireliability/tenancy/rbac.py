"""Role-Based Access Control (RBAC) mapping and permission enforcement (Phase 45)."""

from __future__ import annotations

from aireliability.tenancy.models import TenantContext, TenantPermission, TenantRole

# Canonical role-to-permission mapping
ROLE_PERMISSIONS: dict[TenantRole, set[TenantPermission]] = {
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


class RBACManager:
    """Evaluates security permissions against active tenant context."""

    def check_permission(
        self, context: TenantContext, permission: TenantPermission
    ) -> bool:
        """Verify whether context holds the required permission."""
        # 1. Direct permission override
        if permission in context.permissions:
            return True

        # 2. Derive through roles
        for role in context.roles:
            allowed = ROLE_PERMISSIONS.get(role, set())
            if permission in allowed or TenantPermission.ADMIN in allowed:
                return True

        return False
