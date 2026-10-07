"""Tenant isolation enforcement and cross-tenant access protection (Phase 45)."""

from __future__ import annotations

import logging
from typing import Any

from aireliability.tenancy.context import TenantContextManager
from aireliability.tenancy.models import TenantAuditEvent, TenantContext, TenantResource
from aireliability.tenancy.rbac import RBACManager

logger = logging.getLogger(__name__)


class CrossTenantAccessError(PermissionError):
    """Raised when an operation attempts unauthorized access across tenant boundaries."""

    pass


class TenantIsolationManager:
    """Enforces strict tenant boundary checks and logs security audit records."""

    def __init__(self, rbac: RBACManager | None = None) -> None:
        self.rbac = rbac or RBACManager()
        self.audit_log: list[TenantAuditEvent] = []

    def verify_access(
        self,
        resource: Any,
        context: Any = None,
        action: Any = "read",
    ) -> bool:
        """Verify whether active tenant context owns the requested resource."""
        if isinstance(resource, TenantContext) and isinstance(context, TenantResource):
            resource, context = context, resource
        ctx: TenantContext = context or TenantContextManager.get_current_context()
        if hasattr(action, "value"):
            action = action.value

        # 1. Organization boundary verification
        if (
            resource.organization_id
            and ctx.organization_id
            and resource.organization_id != ctx.organization_id
        ):
            audit = TenantAuditEvent(
                tenant_id=ctx.tenant_id,
                actor_id=ctx.actor_id,
                action=action,
                resource=f"{resource.resource_type}:{resource.resource_id}",
                decision="DENY",
                details={
                    "target_organization_id": resource.organization_id,
                    "violation": "CROSS_ORGANIZATION_ACCESS",
                },
            )
            self.audit_log.append(audit)
            raise CrossTenantAccessError(
                f"Access denied: Resource '{resource.resource_id}' belongs to another organization. No data disclosed."
            )

        # 2. Strict tenant boundary verification
        if resource.tenant_id != ctx.tenant_id:
            # Audit DENIAL event immediately
            audit = TenantAuditEvent(
                tenant_id=ctx.tenant_id,
                actor_id=ctx.actor_id,
                action=action,
                resource=f"{resource.resource_type}:{resource.resource_id}",
                decision="DENY",
                details={
                    "target_tenant_id": resource.tenant_id,
                    "violation": "CROSS_TENANT_ACCESS",
                },
            )
            self.audit_log.append(audit)
            logger.warning(
                "Security Alert: Cross-tenant access denied for actor '%s' from tenant '%s' targeting resource '%s' in tenant '%s'.",
                ctx.actor_id,
                ctx.tenant_id,
                resource.resource_id,
                resource.tenant_id,
            )
            raise CrossTenantAccessError(
                f"Access denied: Resource '{resource.resource_id}' belongs to another tenant. No data disclosed."
            )

        # 3. Project boundary verification (when project context is specified)
        if (
            resource.project_id
            and ctx.project_id
            and ctx.project_id not in ("default", "default_project")
            and resource.project_id != ctx.project_id
        ):
            audit = TenantAuditEvent(
                tenant_id=ctx.tenant_id,
                actor_id=ctx.actor_id,
                action=action,
                resource=f"{resource.resource_type}:{resource.resource_id}",
                decision="DENY",
                details={
                    "target_project_id": resource.project_id,
                    "violation": "CROSS_PROJECT_ACCESS",
                },
            )
            self.audit_log.append(audit)
            raise CrossTenantAccessError(
                f"Access denied: Resource '{resource.resource_id}' belongs to another project. No data disclosed."
            )

        # 4. Environment boundary verification (when environment context is specified)
        if (
            resource.environment_id
            and ctx.environment_id
            and resource.environment_id != ctx.environment_id
        ):
            audit = TenantAuditEvent(
                tenant_id=ctx.tenant_id,
                actor_id=ctx.actor_id,
                action=action,
                resource=f"{resource.resource_type}:{resource.resource_id}",
                decision="DENY",
                details={
                    "target_environment_id": resource.environment_id,
                    "violation": "CROSS_ENVIRONMENT_ACCESS",
                },
            )
            self.audit_log.append(audit)
            raise CrossTenantAccessError(
                f"Access denied: Resource '{resource.resource_id}' belongs to another environment. No data disclosed."
            )

        # Audit ALLOW event
        audit = TenantAuditEvent(
            tenant_id=ctx.tenant_id,
            actor_id=ctx.actor_id,
            action=action,
            resource=f"{resource.resource_type}:{resource.resource_id}",
            decision="ALLOW",
        )
        self.audit_log.append(audit)
        return True
