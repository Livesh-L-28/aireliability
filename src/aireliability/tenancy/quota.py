"""Tenant-aware resource quota tracking, reservation, and enforcement."""

import asyncio

from aireliability.tenancy.models import (
    QuotaUsage,
    QuotaViolation,
    ResourceQuota,
)


class QuotaExceededError(RuntimeError):
    """Raised when an operation would violate allocated tenant quotas."""


class QuotaManager:
    """Manages and enforces real-time resource quotas per tenant."""

    def __init__(self) -> None:
        self._quotas: dict[str, ResourceQuota] = {}
        self._usage: dict[str, dict[str, float]] = {}  # tenant_id -> metric -> current
        self._violations: list[QuotaViolation] = []
        self._lock = asyncio.Lock()

    def set_quota(self, tenant_id: str, quota: ResourceQuota) -> None:
        """Configure quota for a tenant."""
        self._quotas[tenant_id] = quota

    def get_quota(self, tenant_id: str) -> ResourceQuota:
        """Get quota for tenant or default."""
        return self._quotas.get(tenant_id, ResourceQuota())

    async def get_usage(self, tenant_id: str) -> QuotaUsage:
        """Get current usage snapshot for tenant."""
        async with self._lock:
            u = self._usage.get(tenant_id, {})
            return QuotaUsage(
                tenant_id=tenant_id,
                active_jobs=int(u.get("active_jobs", 0)),
                queued_jobs=int(u.get("queued_jobs", 0)),
                active_workers=int(u.get("active_workers", 0)),
                total_tokens_consumed=int(u.get("tokens", 0)),
            )

    async def check_job_admission(
        self, tenant_id: str, requested_jobs: int = 1
    ) -> tuple[bool, str | None]:
        """Check if tenant can queue new jobs without violating limits."""
        async with self._lock:
            quota = self.get_quota(tenant_id)
            u = self._usage.get(tenant_id, {})
            curr_queued = u.get("queued_jobs", 0)

            if curr_queued + requested_jobs > quota.max_queued_jobs:
                msg = (
                    f"Tenant '{tenant_id}' queued jobs quota exceeded "
                    f"({curr_queued + requested_jobs}/{quota.max_queued_jobs})"
                )
                self._violations.append(
                    QuotaViolation(
                        tenant_id=tenant_id,
                        quota_metric="max_queued_jobs",
                        limit_value=float(quota.max_queued_jobs),
                        current_value=float(curr_queued + requested_jobs),
                        details=msg,
                    )
                )
                return (False, msg)

            return (True, None)

    async def check_job_execution(
        self, tenant_id: str, requested_concurrency: int = 1
    ) -> tuple[bool, str | None]:
        """Check if tenant can start executing a job without exceeding concurrency."""
        async with self._lock:
            quota = self.get_quota(tenant_id)
            u = self._usage.get(tenant_id, {})
            curr_active = u.get("active_jobs", 0)

            if curr_active + requested_concurrency > quota.max_concurrent_jobs:
                msg = (
                    f"Tenant '{tenant_id}' concurrent jobs quota exceeded "
                    f"({curr_active + requested_concurrency}/"
                    f"{quota.max_concurrent_jobs})"
                )
                self._violations.append(
                    QuotaViolation(
                        tenant_id=tenant_id,
                        quota_metric="max_concurrent_jobs",
                        limit_value=float(quota.max_concurrent_jobs),
                        current_value=float(curr_active + requested_concurrency),
                        details=msg,
                    )
                )
                return (False, msg)

            return (True, None)

    async def record_job_enqueued(self, tenant_id: str, count: int = 1) -> None:
        """Increment queued jobs count for tenant."""
        async with self._lock:
            if tenant_id not in self._usage:
                self._usage[tenant_id] = {}
            self._usage[tenant_id]["queued_jobs"] = (
                self._usage[tenant_id].get("queued_jobs", 0) + count
            )

    async def acquire_concurrency(self, tenant_id: str, count: int = 1) -> None:
        """Acquire concurrent job slot(s) for tenant."""
        async with self._lock:
            if tenant_id not in self._usage:
                self._usage[tenant_id] = {}
            self._usage[tenant_id]["active_jobs"] = (
                self._usage[tenant_id].get("active_jobs", 0) + count
            )

    async def release_concurrency(self, tenant_id: str, count: int = 1) -> None:
        """Release concurrent job slot(s) for tenant."""
        async with self._lock:
            if tenant_id in self._usage:
                self._usage[tenant_id]["active_jobs"] = max(
                    0, self._usage[tenant_id].get("active_jobs", 0) - count
                )

    async def record_job_dispatched(self, tenant_id: str, count: int = 1) -> None:
        """Decrement queued jobs and increment active jobs."""
        async with self._lock:
            if tenant_id not in self._usage:
                self._usage[tenant_id] = {}
            self._usage[tenant_id]["queued_jobs"] = max(
                0, self._usage[tenant_id].get("queued_jobs", 0) - count
            )
            self._usage[tenant_id]["active_jobs"] = (
                self._usage[tenant_id].get("active_jobs", 0) + count
            )

    async def record_job_finished(self, tenant_id: str, count: int = 1) -> None:
        """Decrement active jobs count for tenant."""
        async with self._lock:
            if tenant_id in self._usage:
                self._usage[tenant_id]["active_jobs"] = max(
                    0, self._usage[tenant_id].get("active_jobs", 0) - count
                )

    async def record_job_dequeued(self, tenant_id: str, count: int = 1) -> None:
        """Decrement queued jobs (e.g. on cancellation)."""
        async with self._lock:
            if tenant_id in self._usage:
                self._usage[tenant_id]["queued_jobs"] = max(
                    0, self._usage[tenant_id].get("queued_jobs", 0) - count
                )

    async def record_token_usage(self, tenant_id: str, tokens: int) -> None:
        """Accumulate token consumption for tenant."""
        async with self._lock:
            if tenant_id not in self._usage:
                self._usage[tenant_id] = {}
            self._usage[tenant_id]["tokens"] = (
                self._usage[tenant_id].get("tokens", 0) + tokens
            )

    def list_violations(self, tenant_id: str | None = None) -> list[QuotaViolation]:
        """List recorded quota violations."""
        if tenant_id:
            return [v for v in self._violations if v.tenant_id == tenant_id]
        return list(self._violations)
