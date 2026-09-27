"""Distributed models, schemas, and state enumerations for AI Reliability Engine.

Defines serializable job models, worker execution states, correlation identifiers,
execution results, persistent records, and lifecycle state machines for concurrent
and distributed reliability evaluations.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aireliability.core.models import RunResult, TestCase


def _generate_id(prefix: str = "") -> str:
    """Generate a unique hex identifier, optionally with a prefix."""
    generated = uuid4().hex
    return f"{prefix}_{generated}" if prefix else generated


def _utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(UTC)


class WorkerState(StrEnum):
    """Lifecycle states for a reliability worker executing jobs."""

    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class JobStatus(StrEnum):
    """Execution status for a reliability test job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal state machine transition is attempted."""


class ExecutionStatusRecord(StrEnum):
    """Lifecycle status for a distributed reliability execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RESUMED = "resumed"


# Valid state transitions for jobs
VALID_JOB_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.PENDING: {JobStatus.RUNNING, JobStatus.CANCELLED},
    JobStatus.RUNNING: {
        JobStatus.COMPLETED,
        JobStatus.FAILED,
        JobStatus.TIMED_OUT,
        JobStatus.CANCELLED,
        JobStatus.RETRYING,
    },
    JobStatus.FAILED: {JobStatus.RETRYING, JobStatus.PENDING},
    JobStatus.TIMED_OUT: {JobStatus.RETRYING, JobStatus.PENDING},
    JobStatus.RETRYING: {JobStatus.PENDING, JobStatus.RUNNING, JobStatus.CANCELLED},
    JobStatus.COMPLETED: set(),  # Terminal state
    JobStatus.CANCELLED: set(),  # Terminal state
}

# Valid state transitions for workers
VALID_WORKER_TRANSITIONS: dict[WorkerState, set[WorkerState]] = {
    WorkerState.IDLE: {WorkerState.STARTING, WorkerState.RUNNING, WorkerState.STOPPED},
    WorkerState.STARTING: {
        WorkerState.RUNNING,
        WorkerState.FAILED,
        WorkerState.STOPPED,
    },
    WorkerState.RUNNING: {
        WorkerState.IDLE,
        WorkerState.FAILED,
        WorkerState.STOPPED,
        WorkerState.COMPLETED,
    },
    WorkerState.COMPLETED: {WorkerState.IDLE, WorkerState.STOPPED},
    WorkerState.FAILED: {WorkerState.IDLE, WorkerState.STOPPED},
    WorkerState.STOPPED: {WorkerState.IDLE},  # Can be re-registered or restarted
}


def validate_job_transition(current: JobStatus, target: JobStatus) -> None:
    """Validate that a job transition from current to target is allowed.

    Raises:
        InvalidStateTransitionError: If the transition violates the state machine.
    """
    if current == target:
        return
    allowed = VALID_JOB_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidStateTransitionError(
            f"Illegal job status transition from '{current}' to '{target}'. "
            f"Allowed transitions from '{current}': {sorted(s.value for s in allowed)}"
        )


def validate_worker_transition(current: WorkerState, target: WorkerState) -> None:
    """Validate that a worker transition from current to target is allowed.

    Raises:
        InvalidStateTransitionError: If the transition violates the state machine.
    """
    if current == target:
        return
    allowed = VALID_WORKER_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidStateTransitionError(
            f"Illegal worker state transition from '{current}' to '{target}'. "
            f"Allowed transitions from '{current}': {sorted(s.value for s in allowed)}"
        )


class CorrelationContext(BaseModel):
    """Distributed correlation context tracking identity across executions."""

    model_config = ConfigDict(frozen=True)

    execution_id: str = Field(default_factory=lambda: _generate_id("exec"))
    job_id: str | None = None
    worker_id: str | None = None
    test_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    attempt: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReliabilityJob(BaseModel):
    """Serializable specification of an individual reliability test job."""

    model_config = ConfigDict(frozen=True)

    job_id: str = Field(default_factory=lambda: _generate_id("job"))
    execution_id: str = Field(default_factory=lambda: _generate_id("exec"))
    test_case: TestCase
    priority: int = 0
    attempt: int = 1
    max_retries: int = 0
    timeout_seconds: float | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    status: JobStatus = JobStatus.PENDING
    assigned_worker_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def tenant_id(self) -> str:
        """Tenant ID associated with this reliability job, defaulting to 'default'."""
        return self.metadata.get("tenant_id", "default")

    @property
    def project_id(self) -> str:
        """Project ID associated with this reliability job, defaulting to 'default'."""
        return self.metadata.get("project_id", "default")

    @property
    def namespace(self) -> str:
        """Namespace associated with this reliability job, defaulting to 'default'."""
        return self.metadata.get("namespace", "default")

    @property
    def test_id(self) -> str:
        """Convenience property for accessing the underlying test case ID."""
        return self.test_case.id


class JobExecutionOutcome(BaseModel):
    """The outcome of executing a single attempt of a ReliabilityJob."""

    model_config = ConfigDict(frozen=True)

    job_id: str
    execution_id: str
    test_id: str
    worker_id: str
    status: JobStatus
    attempt: int = 1
    run_result: RunResult | None = None
    started_at: datetime = Field(default_factory=_utc_now)
    completed_at: datetime | None = None
    duration_ms: float | None = None
    error: str | None = None
    error_type: str | None = None
    retryable: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_duration(self) -> "JobExecutionOutcome":
        if self.completed_at is not None and self.duration_ms is None:
            calc_ms = (self.completed_at - self.started_at).total_seconds() * 1000.0
            object.__setattr__(self, "duration_ms", max(0.0, calc_ms))
        return self


class WorkerDescriptor(BaseModel):
    """Snapshot metadata describing a reliability worker."""

    model_config = ConfigDict(frozen=True)

    worker_id: str = Field(default_factory=lambda: _generate_id("worker"))
    state: WorkerState = WorkerState.IDLE
    current_job_id: str | None = None
    started_at: datetime = Field(default_factory=_utc_now)
    completed_at: datetime | None = None
    jobs_completed: int = 0
    jobs_failed: int = 0
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionRecord(BaseModel):
    """Persistent representation of a distributed reliability execution."""

    model_config = ConfigDict(frozen=True)

    execution_id: str = Field(default_factory=lambda: _generate_id("exec"))
    status: ExecutionStatusRecord = ExecutionStatusRecord.PENDING
    created_at: datetime = Field(default_factory=_utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_jobs: int = 0
    completed_jobs: int = 0
    failed_jobs: int = 0
    timed_out_jobs: int = 0
    cancelled_jobs: int = 0
    retry_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def tenant_id(self) -> str:
        """Tenant ID associated with this execution, defaulting to 'default'."""
        return self.metadata.get("tenant_id", "default")

    @property
    def project_id(self) -> str:
        """Project ID associated with this execution, defaulting to 'default'."""
        return self.metadata.get("project_id", "default")

    @property
    def namespace(self) -> str:
        """Namespace associated with this execution, defaulting to 'default'."""
        return self.metadata.get("namespace", "default")


class PersistentWorkerRecord(BaseModel):
    """Persistent record of an active or registered reliability worker."""

    model_config = ConfigDict(frozen=True)

    worker_id: str = Field(default_factory=lambda: _generate_id("worker"))
    execution_id: str | None = None
    state: WorkerState = WorkerState.IDLE
    current_job_id: str | None = None
    started_at: datetime = Field(default_factory=_utc_now)
    last_heartbeat: datetime = Field(default_factory=_utc_now)
    completed_jobs: int = 0
    failed_jobs: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class PersistentJobRecord(BaseModel):
    """Persistent record of an individual reliability test job."""

    model_config = ConfigDict(frozen=True)

    job_id: str = Field(default_factory=lambda: _generate_id("job"))
    execution_id: str
    test_id: str
    status: JobStatus = JobStatus.PENDING
    attempt: int = 1
    max_retries: int = 0
    worker_id: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    timeout_seconds: float | None = None
    retryable: bool = False
    error: str | None = None
    error_type: str | None = None
    test_case: TestCase | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PersistentOutcomeRecord(BaseModel):
    """Persistent record of an execution attempt outcome."""

    model_config = ConfigDict(frozen=True)

    outcome_id: str = Field(default_factory=lambda: _generate_id("out"))
    job_id: str
    execution_id: str
    test_id: str
    worker_id: str
    status: JobStatus
    attempt: int = 1
    duration_ms: float = 0.0
    run_result: RunResult | None = None
    error: str | None = None
    error_type: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionRecoverySummary(BaseModel):
    """Summary of execution recovery operations."""

    model_config = ConfigDict(frozen=True)

    execution_id: str
    recovered_jobs: list[str] = Field(default_factory=list)
    already_completed_jobs: list[str] = Field(default_factory=list)
    stale_workers: list[str] = Field(default_factory=list)
    requeued_jobs: list[str] = Field(default_factory=list)
    failed_recovery_jobs: list[str] = Field(default_factory=list)
