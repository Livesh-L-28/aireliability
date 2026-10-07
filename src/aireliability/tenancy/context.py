"""Thread-safe context management for active tenant execution context (Phase 45)."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from aireliability.tenancy.models import TenantContext, TenantRole

_CURRENT_TENANT_CONTEXT: ContextVar[TenantContext | None] = ContextVar(
    "current_tenant_context", default=None
)


class TenantContextManager:
    """Manages thread-safe and async-safe tenant context state."""

    @staticmethod
    def get_current_context() -> TenantContext:
        """Return the active tenant context or fallback to default sandbox."""
        ctx = _CURRENT_TENANT_CONTEXT.get()
        if ctx is None:
            ctx = TenantContext(
                organization_id="org_default",
                tenant_id="tenant_default",
                actor_id="system",
                roles=[TenantRole.OWNER],
            )
        return ctx

    @staticmethod
    def set_current_context(context: TenantContext) -> Any:
        """Set the active tenant context and return token for resetting."""
        return _CURRENT_TENANT_CONTEXT.set(context)

    @staticmethod
    def reset_context(token: Any) -> None:
        """Reset the tenant context back to previous state."""
        _CURRENT_TENANT_CONTEXT.reset(token)
