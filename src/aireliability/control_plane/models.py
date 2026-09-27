"""Control-plane models and scheduling enums for AI Reliability Engine.

Defines priority levels, queue states, backoff strategies, and data models
for the provider-neutral control plane.
"""

from datetime import UTC, datetime
from enum import IntEnum, StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from aireliability.core.models import TestCase
from aireliability.distributed.models import JobStatus


def _generate_control_plane_id(prefix: str = "") -> str:
    """Generate a unique hex identifier, optionally with a prefix."""
    generated = uuid4().hex
    return f"{prefix}_{generated}" if prefix else generated


def _utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(UTC)


class JobPriority(IntEnum):
    """Priority levels for job scheduling.

    Lower integer values indicate higher priority for deterministic sorting:
    CRITICAL (0) > HIGH (1) > NORMAL (2) > LOW (3).
    """

    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3

    @classmethod
    def from_string(cls, val: str) -> "JobPriority":
        """Convert case-insensitive string name to JobPriority."""
        cleaned = val.strip().upper()
        if cleaned == "CRITICAL":
            return cls.CRITICAL
        if cleaned == "HIGH":
            return cls.HIGH
        if cleaned == "NORMAL":
            return cls.NORMAL
        if cleaned == "LOW":
            return cls.LOW
        raise ValueError(
            f"Unknown priority '{val}'. Valid options: CRITICAL, HIGH, NORMAL, LOW"
        )


class QueueState(StrEnum):
    """Lifecycle state of a job within the control-plane queue and scheduler."""

    CREATED = "created"
    QUEUED = "queued"
    SCHEDULED = "scheduled"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class SchedulerStatus(StrEnum):
    """Lifecycle status of the control-plane scheduler service."""

    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class BackoffStrategy(StrEnum):
    """Retry backoff timing strategy."""

    NONE = "none"
    FIXED = "fixed"
    EXPONENTIAL = "exponential"


class ScheduledJob(BaseModel):
    """Control-plane scheduled job wrapping a reliability test specification."""

    model_config = ConfigDict(frozen=True)

    job_id: str = Field(default_factory=lambda: _generate_control_plane_id("job"))
    execution_id: str = Field(
        default_factory=lambda: _generate_control_plane_id("exec")
    )
    test_case: TestCase
    priority: JobPriority = JobPriority.NORMAL
    queue_state: QueueState = QueueState.CREATED
    job_status: JobStatus = JobStatus.PENDING

    attempt: int = 1
    max_retries: int = 0
    timeout_seconds: float | None = 60.0

    created_at: datetime = Field(default_factory=_utc_now)
    queued_at: datetime | None = None
    scheduled_at: datetime | None = None
    assigned_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    assigned_worker_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def tenant_id(self) -> str:
        """Tenant ID associated with this scheduled job, defaulting to 'default'."""
        return self.metadata.get("tenant_id", "default")

    @property
    def project_id(self) -> str:
        """Project ID associated with this scheduled job, defaulting to 'default'."""
        return self.metadata.get("project_id", "default")

    @property
    def namespace(self) -> str:
        """Resource namespace associated with this job, defaulting to 'default'."""
        return self.metadata.get("namespace", "default")

    @property
    def test_id(self) -> str:
        """Convenience property for accessing the underlying test case ID."""
        return self.test_case.id

    def is_eligible_at(self, target_time: datetime | None = None) -> bool:
        """Check if delayed job has reached its scheduled execution time."""
        if self.scheduled_at is None:
            return True
        now = target_time or _utc_now()
        return now >= self.scheduled_at


class WorkerCapacityInfo(BaseModel):
    """Capacity and load metrics for a registered worker."""

    model_config = ConfigDict(frozen=True)

    worker_id: str
    capacity: int = 1
    active_jobs: int = 0
    last_heartbeat: datetime = Field(default_factory=_utc_now)
    is_active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def available_slots(self) -> int:
        """Number of remaining job slots available on this worker."""
        return max(0, self.capacity - self.active_jobs)

    @property
    def has_capacity(self) -> bool:
        """True if worker has at least 1 free slot and is active."""
        return self.is_active and self.available_slots > 0

    @property
    def supported_tenants(self) -> list[str]:
        """List of tenant IDs supported by this worker (empty means all)."""
        return self.metadata.get("supported_tenants", [])

    @property
    def supported_projects(self) -> list[str]:
        """List of project IDs supported by this worker (empty means all)."""
        return self.metadata.get("supported_projects", [])

    @property
    def supported_namespaces(self) -> list[str]:
        """List of namespaces supported by this worker (empty means all)."""
        return self.metadata.get("supported_namespaces", [])

    def supports(
        self,
        tenant_id: str | None = None,
        project_id: str | None = None,
        namespace: str | None = None,
    ) -> bool:
        """Check if this worker satisfies tenant, project, and namespace constraints."""
        if (
            tenant_id
            and self.supported_tenants
            and tenant_id not in self.supported_tenants
        ):
            return False
        if (
            project_id
            and self.supported_projects
            and project_id not in self.supported_projects
        ):
            return False
        return not (
            namespace
            and self.supported_namespaces
            and namespace not in self.supported_namespaces
        )


class RetryPolicy(BaseModel):
    """Configuration governing job retries and backoff calculation."""

    model_config = ConfigDict(frozen=True)

    max_retries: int = 0
    strategy: BackoffStrategy = BackoffStrategy.NONE
    initial_delay_seconds: float = 1.0
    backoff_factor: float = 2.0
    max_delay_seconds: float = 60.0

    def compute_delay(self, attempt: int) -> float:
        """Compute the delay in seconds before an attempt should run."""
        if self.strategy == BackoffStrategy.NONE or attempt <= 1:
            return 0.0
        if self.strategy == BackoffStrategy.FIXED:
            return min(self.initial_delay_seconds, self.max_delay_seconds)
        if self.strategy == BackoffStrategy.EXPONENTIAL:
            # attempt 2: delay = initial * factor^(0) = initial
            # attempt 3: delay = initial * factor^(1) = initial * factor
            exponent = max(0, attempt - 2)
            delay = self.initial_delay_seconds * (self.backoff_factor**exponent)
            return min(delay, self.max_delay_seconds)
        return 0.0


class ControlPlaneConfig(BaseModel):
    """Configuration settings for the ControlPlane controller and scheduler."""

    model_config = ConfigDict(frozen=True)

    max_concurrency: int = 10
    scheduling_policy: str = "priority"
    default_retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    heartbeat_timeout_seconds: float = 30.0
    worker_default_capacity: int = 2
    fairness_aging_threshold_seconds: float = 10.0
    telemetry_enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
