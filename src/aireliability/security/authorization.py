"""Authorization engine with explicit RBAC, tenant, and namespace boundaries."""

from aireliability.security.models import (
    AuthorizationDecision,
    Principal,
)
from aireliability.security.permissions import PermissionManager
from aireliability.tenancy.models import (
    DEFAULT_NAMESPACE,
    DEFAULT_PROJECT_ID,
    DEFAULT_TENANT_ID,
)


class AuthorizationEngine:
    """Evaluates granular permissions and tenant boundaries for incoming actions."""

    def __init__(
        self,
        permission_manager: PermissionManager | None = None,
        allow_cross_tenant_admin: bool = True,
    ) -> None:
        self.permission_manager = permission_manager or PermissionManager()
        self.allow_cross_tenant_admin = allow_cross_tenant_admin

    def authorize(
        self,
        principal: Principal,
        action: str,
        tenant_id: str | None = None,
        project_id: str | None = None,
        namespace: str | None = None,
        resource: str | None = None,
    ) -> tuple[AuthorizationDecision, str | None]:
        """Evaluate if principal has permission to perform action on resource scope.

        Returns (AuthorizationDecision, reason_if_denied).
        """
        target_tenant = tenant_id or DEFAULT_TENANT_ID
        target_project = project_id or DEFAULT_PROJECT_ID
        target_namespace = namespace or DEFAULT_NAMESPACE

        # 1. System / Global Admin Check
        is_global_admin = (
            "ADMIN" in principal.roles or "security.manage" in principal.permissions
        )
        if is_global_admin:
            return AuthorizationDecision.ALLOW, None

        # 2. Tenant Boundary Isolation Check
        # Principal cannot cross tenant boundaries unless they are global admin
        if principal.tenant_id != target_tenant:
            return (
                AuthorizationDecision.DENY,
                f"Tenant boundary violation: Principal tenant '{principal.tenant_id}' "
                f"cannot access resource tenant '{target_tenant}'.",
            )

        # 3. Project Boundary Check (if not TENANT_ADMIN)
        is_tenant_admin = "TENANT_ADMIN" in principal.roles
        if (
            not is_tenant_admin
            and principal.project_id != DEFAULT_PROJECT_ID
            and target_project != DEFAULT_PROJECT_ID
            and principal.project_id != target_project
        ):
            return (
                AuthorizationDecision.DENY,
                f"Project boundary violation: Principal project "
                f"'{principal.project_id}' cannot access resource "
                f"project '{target_project}'.",
            )

        # 4. Namespace Boundary Check (if not TENANT_ADMIN or PROJECT_ADMIN)
        is_project_admin = is_tenant_admin or ("PROJECT_ADMIN" in principal.roles)
        if (
            not is_project_admin
            and principal.namespace != DEFAULT_NAMESPACE
            and target_namespace != DEFAULT_NAMESPACE
            and principal.namespace != target_namespace
        ):
            return (
                AuthorizationDecision.DENY,
                f"Namespace boundary violation: Principal namespace "
                f"'{principal.namespace}' cannot access resource "
                f"namespace '{target_namespace}'.",
            )

        # 5. Granular Action Permission Check
        has_permission = False
        for granted_perm in principal.permissions:
            if self.permission_manager.implies(granted_perm, action):
                has_permission = True
                break

        if not has_permission:
            return (
                AuthorizationDecision.DENY,
                f"Permission denied: Principal lacks required permission '{action}'.",
            )

        return AuthorizationDecision.ALLOW, None
