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


class TenantRole(StrEnum):
    """Enterprise multi-tenant role taxonomy."""

    OWNER = "OWNER"
    ADMIN = "ADMIN"
    ENGINEER = "ENGINEER"
    ANALYST = "ANALYST"
    VIEWER = "VIEWER"
    AUDITOR = "AUDITOR"
    SERVICE_ACCOUNT = "SERVICE_ACCOUNT"


class TenantPermission(StrEnum):
    """Granular permissions for enterprise operations."""

    READ = "READ"
    WRITE = "WRITE"
    EXECUTE = "EXECUTE"
    EVALUATE = "EVALUATE"
    MANAGE_POLICIES = "MANAGE_POLICIES"
    MANAGE_USERS = "MANAGE_USERS"
    MANAGE_TENANTS = "MANAGE_TENANTS"
    RUN_SAFETY = "RUN_SAFETY"
    RUN_OPTIMIZATION = "RUN_OPTIMIZATION"
    RUN_HEALING = "RUN_HEALING"
    MANAGE_API_KEYS = "MANAGE_API_KEYS"
    READ_AUDIT = "READ_AUDIT"
    ADMIN = "ADMIN"


class TenantContext(BaseModel):
    """Hierarchical context defining tenant, project, and namespace boundaries."""

    model_config = ConfigDict(frozen=True)

    organization_id: str = "default_org"
    tenant_id: str = DEFAULT_TENANT_ID
    project_id: str = DEFAULT_PROJECT_ID
    environment_id: str | None = None
    namespace: str = DEFAULT_NAMESPACE
    actor_id: str = "system"
    roles: list[TenantRole] = Field(default_factory=lambda: [TenantRole.VIEWER])
    permissions: list[TenantPermission] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def environment(self) -> str | None:
        return self.environment_id

    def __init__(self, **data: Any) -> None:
        if "environment" in data and "environment_id" not in data:
            data["environment_id"] = data.pop("environment")
        super().__init__(**data)

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
    organization_id: str = "default_org"
    name: str
    status: TenantStatus = TenantStatus.ACTIVE
    enabled: bool = True
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


class Organization(BaseModel):
    """Top-level enterprise organizational container."""

    model_config = ConfigDict(frozen=True)

    organization_id: str = Field(
        default_factory=lambda: _generate_tenant_entity_id("org")
    )
    name: str
    created_at: datetime = Field(default_factory=_utc_now)


class Project(BaseModel):
    """Project workspace within a tenant boundary."""

    model_config = ConfigDict(frozen=True)

    project_id: str = Field(default_factory=lambda: _generate_tenant_entity_id("proj"))
    tenant_id: str = DEFAULT_TENANT_ID
    name: str = "Default Project"
    created_at: datetime = Field(default_factory=_utc_now)


class Environment(BaseModel):
    """Execution environment (dev, staging, production) within a project."""

    model_config = ConfigDict(frozen=True)

    environment_id: str = Field(
        default_factory=lambda: _generate_tenant_entity_id("env")
    )
    project_id: str = DEFAULT_PROJECT_ID
    name: str = "dev"
    created_at: datetime = Field(default_factory=_utc_now)


class TenantMembership(BaseModel):
    """User membership assignment to a tenant."""

    model_config = ConfigDict(frozen=True)

    membership_id: str = Field(
        default_factory=lambda: _generate_tenant_entity_id("mem")
    )
    user_id: str
    tenant_id: str
    roles: list[TenantRole] = Field(default_factory=lambda: [TenantRole.VIEWER])
    created_at: datetime = Field(default_factory=_utc_now)


class TenantQuota(BaseModel):
    """Resource consumption limits for a tenant."""

    model_config = ConfigDict(frozen=True)

    max_evaluations: int = 100_000
    max_tokens: int = 100_000_000
    max_api_requests: int = 500_000
    max_safety_tests: int = 10_000
    max_storage_mb: int = 50_000
    max_concurrent_jobs: int = 10


class TenantUsage(BaseModel):
    """Observed resource consumption for a tenant."""

    model_config = ConfigDict(frozen=True)

    evaluations_count: int = 0
    tokens_used: int = 0
    requests_count: int = 0
    safety_tests_run: int = 0
    storage_used_mb: int = 0
    active_jobs_count: int = 0


class TenantResource(BaseModel):
    """A generic resource owned strictly by a tenant."""

    model_config = ConfigDict(frozen=True)

    resource_id: str
    tenant_id: str
    organization_id: str | None = None
    project_id: str | None = None
    environment_id: str | None = None
    resource_type: str  # dataset, evaluation, trace, policy, graph_node
    name: str = ""
    created_at: datetime = Field(default_factory=_utc_now)


class TenantPolicy(BaseModel):
    """Policy preferences bound to a specific tenant."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str
    policies: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TenantAuditEvent(BaseModel):
    """Immutable audit log entry recording privileged or cross-boundary attempts."""

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(default_factory=lambda: _generate_tenant_entity_id("taudit"))
    timestamp: datetime = Field(default_factory=_utc_now)
    tenant_id: str
    actor_id: str
    action: str
    resource: str
    decision: str  # ALLOW, DENY
    request_id: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
