"""Central resource governance orchestrator coordinating admission, quotas,
rate limits, and resilience.
"""

import asyncio
from typing import Any

from aireliability.control_plane.models import JobPriority
from aireliability.resilience.manager import ResilienceManager
from aireliability.telemetry.sanitizer import SanitizationPolicy
from aireliability.tenancy.models import (
    DEFAULT_NAMESPACE,
    DEFAULT_PROJECT_ID,
    DEFAULT_TENANT_ID,
    ResourceQuota,
    Tenant,
    TenantContext,
    TenantStatus,
)
from aireliability.tenancy.quota import QuotaManager
from aireliability.tenancy.rate_limiter import RateLimiter


class ResourceGovernanceManager:
    """Coordinates multi-tenant registration, quotas, rate limits, and admission."""

    def __init__(
        self,
        *,
        quota_manager: QuotaManager | None = None,
        rate_limiter: RateLimiter | None = None,
        resilience_manager: ResilienceManager | None = None,
        sanitizer: SanitizationPolicy | None = None,
        storage: Any | None = None,
    ) -> None:
        self.quota_manager = quota_manager or QuotaManager()
        self.rate_limiter = rate_limiter or RateLimiter()
        self.resilience_manager = resilience_manager or ResilienceManager()
        self.sanitizer = sanitizer or SanitizationPolicy()
        self.storage = storage

        self._tenants: dict[str, Tenant] = {
            DEFAULT_TENANT_ID: Tenant(
                tenant_id=DEFAULT_TENANT_ID,
                name="Default Tenant",
                status=TenantStatus.ACTIVE,
            )
        }
        self._lock = asyncio.Lock()

    async def create_tenant(
        self,
        tenant_id: str,
        name: str | None = None,
        quota: ResourceQuota | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Tenant:
        """Alias for register_tenant."""
        return await self.register_tenant(
            tenant_id=tenant_id, name=name, quota=quota, metadata=metadata
        )

    async def register_tenant(
        self,
        tenant_id: str,
        name: str | None = None,
        quota: ResourceQuota | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Tenant:
        """Register or update a tenant profile with sanitized metadata."""
        async with self._lock:
            sanitized_meta = self.sanitizer.sanitize(metadata or {})
            t = Tenant(
                tenant_id=tenant_id,
                name=name or f"Tenant {tenant_id}",
                status=TenantStatus.ACTIVE,
                quota=quota or ResourceQuota(),
                metadata=sanitized_meta,
            )
            self._tenants[tenant_id] = t
            if quota:
                self.quota_manager.set_quota(tenant_id, quota)
            return t

    async def get_tenant(self, tenant_id: str) -> Tenant | None:
        """Retrieve tenant profile by ID."""
        async with self._lock:
            return self._tenants.get(tenant_id)

    async def list_tenants(self) -> list[Tenant]:
        """List all registered tenants."""
        async with self._lock:
            return list(self._tenants.values())

    async def set_tenant_status(
        self, tenant_id: str, status: TenantStatus
    ) -> Tenant | None:
        """Update tenant lifecycle status (ACTIVE, SUSPENDED, DISABLED)."""
        async with self._lock:
            t = self._tenants.get(tenant_id)
            if not t:
                return None
            updated = t.model_copy(update={"status": status})
            self._tenants[tenant_id] = updated
            return updated

    async def check_admission(
        self,
        context: TenantContext | None = None,
        tenant_id: str | None = None,
        project_id: str | None = None,
        namespace: str | None = None,
        priority: JobPriority = JobPriority.NORMAL,
        current_queue_depth: int = 0,
        provider_id: str | None = None,
        load_shedder: Any = None,
    ) -> tuple[bool, str | None]:
        """Unified admission pipeline:
        Tenant status -> Quotas -> Rate limits -> Resilience.
        """
        if context is None:
            t_id = tenant_id or DEFAULT_TENANT_ID
            p_id = project_id or DEFAULT_PROJECT_ID
            ns = namespace or DEFAULT_NAMESPACE
            context = TenantContext(tenant_id=t_id, project_id=p_id, namespace=ns)
        else:
            t_id = context.tenant_id

        # 1. Tenant validation
        async with self._lock:
            tenant = self._tenants.get(t_id)
            if tenant is not None and not tenant.is_active:
                msg = (
                    f"Tenant '{t_id}' is {tenant.status.value.upper()}; "
                    "new jobs cannot be admitted."
                )
                raise ValueError(msg)

        # 2. Quota check (queue limit)
        can_queue, quota_reason = await self.quota_manager.check_job_admission(t_id)
        if not can_queue:
            from aireliability.tenancy.quota import QuotaExceededError

            raise QuotaExceededError(quota_reason or "Tenant queue quota exceeded")

        # 3. Rate limit check (using scope key)
        rate_decision = await self.rate_limiter.check(context.scope_key)
        if not rate_decision.allowed:
            raise ValueError(
                rate_decision.reason
                or f"Rate limit exceeded for scope '{context.scope_key}'"
            )

        # 4. Resilience check (circuit breakers & failure storm load shedding)
        if load_shedder is not None:
            shed, reason = await load_shedder.should_shed_job(
                priority=priority,
                current_queue_depth=current_queue_depth,
            )
            if shed:
                raise ValueError(reason or "Admission denied by load shedder")
        elif self.resilience_manager is not None:
            res_allowed, res_reason = await self.resilience_manager.check_admission(
                priority=priority,
                current_queue_depth=current_queue_depth,
                provider_id=provider_id,
            )
            if not res_allowed:
                raise ValueError(res_reason or "Admission denied by resilience manager")

        return (True, None)

    async def check_execution_admission(
        self, context: TenantContext
    ) -> tuple[bool, str | None]:
        """Check if job can begin active execution without exceeding slots."""
        return await self.quota_manager.check_job_execution(context.tenant_id)
