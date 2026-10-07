"""Usage tracking and resource quota enforcement (Phase 45)."""

from __future__ import annotations

from aireliability.tenancy.models import TenantQuota, TenantUsage


class QuotaExceededError(Exception):
    """Raised when tenant exceeds assigned resource quota."""

    pass


class UsageTracker:
    """Tracks and enforces resource quotas per tenant."""

    def __init__(self) -> None:
        self._usage: dict[str, TenantUsage] = {}
        self._quotas: dict[str, TenantQuota] = {}

    def get_usage(self, tenant_id: str) -> TenantUsage:
        """Retrieve current usage for a tenant."""
        if tenant_id not in self._usage:
            self._usage[tenant_id] = TenantUsage()
        return self._usage[tenant_id]

    def set_quota(self, tenant_id: str, quota: TenantQuota) -> None:
        """Assign or update quota limits for a tenant."""
        self._quotas[tenant_id] = quota

    def get_quota(self, tenant_id: str) -> TenantQuota:
        """Get assigned quota for tenant or return default."""
        return self._quotas.get(tenant_id, TenantQuota())

    def record_usage(
        self,
        tenant_id: str,
        evaluations: int = 0,
        tokens: int = 0,
        requests: int = 0,
        safety_tests: int = 0,
    ) -> None:
        """Record resource consumption and enforce quotas."""
        curr = self.get_usage(tenant_id)
        quota = self.get_quota(tenant_id)

        # Check bounds before recording
        if curr.evaluations_count + evaluations > quota.max_evaluations:
            raise QuotaExceededError(
                f"Evaluation quota exceeded for tenant '{tenant_id}'"
            )
        if curr.requests_count + requests > quota.max_api_requests:
            raise QuotaExceededError(
                f"API request quota exceeded for tenant '{tenant_id}'"
            )
        if curr.safety_tests_run + safety_tests > quota.max_safety_tests:
            raise QuotaExceededError(
                f"Safety test quota exceeded for tenant '{tenant_id}'"
            )

        self._usage[tenant_id] = TenantUsage(
            evaluations_count=curr.evaluations_count + evaluations,
            tokens_used=curr.tokens_used + tokens,
            requests_count=curr.requests_count + requests,
            safety_tests_run=curr.safety_tests_run + safety_tests,
            storage_used_mb=curr.storage_used_mb,
            active_jobs_count=curr.active_jobs_count,
        )
