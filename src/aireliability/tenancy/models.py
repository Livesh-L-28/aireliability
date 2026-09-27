"""Multi-tenancy, isolation, and resource governance models for AI Reliability
Engine (Phase 27).

Defines tenant models, resource quotas, rate limit policies, access policies,
and hierarchical execution contexts (tenant, project, namespace).
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_TENANT_ID = "default"
DEFAULT_PROJECT_ID = "default"
DEFAULT_NAMESPACE = "default"


def _generate_tenant_entity_id(prefix: str = "") -> str:
    """Generate a unique hex identifier, optionally with a prefix."""
    generated = uuid4().hex
    return f"{prefix}_{generated}" if prefix else generated


def _utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(UTC)


class TenantStatus(StrEnum):
    """Lifecycle status for a registered tenant."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    DISABLED = "disabled"


class TenantContext(BaseModel):
    """Hierarchical context defining tenant, project, and namespace boundaries."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str = DEFAULT_TENANT_ID
    project_id: str = DEFAULT_PROJECT_ID
    namespace: str = DEFAULT_NAMESPACE
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def scope_key(self) -> str:
        """Fully qualified composite scope identifier."""
        return f"{self.tenant_id}:{self.project_id}:{self.namespace}"


class ProjectContext(BaseModel):
    """Lightweight project boundary within a tenant."""

    model_config = ConfigDict(frozen=True)

    project_id: str = DEFAULT_PROJECT_ID
    tenant_id: str = DEFAULT_TENANT_ID
    name: str = "Default Project"
    created_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def scope_key(self) -> str:
        return f"{self.tenant_id}:{self.project_id}"


class ResourceNamespace(BaseModel):
    """Logical partitioning namespace within a tenant project."""

    model_config = ConfigDict(frozen=True)

    namespace: str = DEFAULT_NAMESPACE
    project_id: str = DEFAULT_PROJECT_ID
    tenant_id: str = DEFAULT_TENANT_ID
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def scope_key(self) -> str:
        return f"{self.tenant_id}:{self.namespace}"


class ResourceQuota(BaseModel):
    """Configurable resource capacity limits for a tenant or namespace."""

    model_config = ConfigDict(frozen=True)

    max_concurrent_jobs: int = 10
    max_queued_jobs: int = 100
    max_workers: int = 5
    max_retries_per_job: int = 3
    max_execution_timeout: float = 300.0  # seconds
    max_tokens: int = 1_000_000
    max_execution_duration: float = 3600.0  # seconds
    max_requests_per_window: int = 600  # requests per rate limit window


class QuotaUsage(BaseModel):
    """Real-time utilization metrics against allocated tenant quotas."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str
    active_jobs: int = 0
    queued_jobs: int = 0
    active_workers: int = 0
    total_tokens_consumed: int = 0
    window_requests: int = 0
    last_updated: datetime = Field(default_factory=_utc_now)


class QuotaViolation(BaseModel):
    """Structured record of a tenant quota violation."""

    model_config = ConfigDict(frozen=True)

    violation_id: str = Field(
        default_factory=lambda: _generate_tenant_entity_id("viol")
    )
    tenant_id: str
    quota_metric: str
    limit_value: float
    current_value: float
    timestamp: datetime = Field(default_factory=_utc_now)
    details: str = ""


class RateLimitAlgorithm(StrEnum):
    """Algorithm choices for provider-neutral rate limiting."""

    FIXED_WINDOW = "fixed_window"
    SLIDING_WINDOW = "sliding_window"
    TOKEN_BUCKET = "token_bucket"


class RateLimitPolicy(BaseModel):
    """Rate limit configuration for tenant, project, or namespace scopes."""

    model_config = ConfigDict(frozen=True)

    algorithm: RateLimitAlgorithm = RateLimitAlgorithm.TOKEN_BUCKET
    rate: float = 20.0  # allowed requests per window
    window_seconds: float = 60.0
    burst_capacity: float = 30.0  # For token bucket

    def __init__(self, **data: Any) -> None:
        if "burst" in data and "burst_capacity" not in data:
            data["burst_capacity"] = float(data.pop("burst"))
        super().__init__(**data)

    @property
    def burst(self) -> float:
        return self.burst_capacity


class RateLimitDecision(BaseModel):
    """Result of evaluating a rate limit request."""

    model_config = ConfigDict(frozen=True)

    allowed: bool
    remaining_tokens: float = 0.0
    reset_after_seconds: float = 0.0
    reason: str | None = None

    @property
    def remaining(self) -> float:
        return self.remaining_tokens


class Tenant(BaseModel):
    """Tenant entity defining ownership, status, quota, and policies."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str
    name: str
    status: TenantStatus = TenantStatus.ACTIVE
    created_at: datetime = Field(default_factory=_utc_now)
    quota: ResourceQuota = Field(default_factory=ResourceQuota)
    rate_limit: RateLimitPolicy = Field(default_factory=RateLimitPolicy)
    scheduling_weight: float = 1.0  # Priority weight for fair tenant scheduling
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.status == TenantStatus.ACTIVE


class TenantAction(StrEnum):
    """Action categories for authorization checking."""

    READ = "read"
    SUBMIT = "submit"
    CANCEL = "cancel"
    RETRY = "retry"
    ADMINISTER = "administer"


class TenantAccessPolicy:
    """Provider-neutral authorization boundary for tenant operations."""

    @staticmethod
    def _extract_id_and_admin(requestor: Any, is_admin: bool) -> tuple[str, bool]:
        if isinstance(requestor, TenantContext):
            role = requestor.metadata.get("role", "")
            return requestor.tenant_id, is_admin or (role == "system_admin")
        if isinstance(requestor, str):
            return requestor, is_admin
        if requestor is None:
            return DEFAULT_TENANT_ID, is_admin
        return str(getattr(requestor, "tenant_id", DEFAULT_TENANT_ID)), is_admin

    @staticmethod
    def can_access(
        requestor: Any,
        target_tenant_id: str | None = None,
        action: TenantAction = TenantAction.READ,
        is_admin: bool = False,
    ) -> bool:
        """Evaluate if requestor has access to target tenant resource."""
        req_id, admin = TenantAccessPolicy._extract_id_and_admin(requestor, is_admin)
        if admin:
            return True
        tgt_id = target_tenant_id or DEFAULT_TENANT_ID
        return req_id == tgt_id

    @staticmethod
    def can_read(
        requestor: Any,
        target_tenant_id: str | None = None,
        is_admin: bool = False,
    ) -> bool:
        return TenantAccessPolicy.can_access(
            requestor, target_tenant_id, TenantAction.READ, is_admin
        )

    @staticmethod
    def can_submit(
        requestor: Any,
        target_tenant_id: str | None = None,
        is_admin: bool = False,
    ) -> bool:
        return TenantAccessPolicy.can_access(
            requestor, target_tenant_id, TenantAction.SUBMIT, is_admin
        )

    @staticmethod
    def can_cancel(
        requestor: Any,
        target_tenant_id: str | None = None,
        is_admin: bool = False,
    ) -> bool:
        return TenantAccessPolicy.can_access(
            requestor, target_tenant_id, TenantAction.CANCEL, is_admin
        )

    @staticmethod
    def can_retry(
        requestor: Any,
        target_tenant_id: str | None = None,
        is_admin: bool = False,
    ) -> bool:
        return TenantAccessPolicy.can_access(
            requestor, target_tenant_id, TenantAction.RETRY, is_admin
        )

    @staticmethod
    def can_administer(
        requestor: Any,
        target_tenant_id: str | None = None,
        is_admin: bool = False,
    ) -> bool:
        return TenantAccessPolicy.can_access(
            requestor, target_tenant_id, TenantAction.ADMINISTER, is_admin
        )
