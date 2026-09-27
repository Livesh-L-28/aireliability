"""Optional PostgreSQL storage backend for distributed AI reliability.

Requires: pip install 'aireliability[postgres]' (psycopg or psycopg2).
"""

import importlib.util
from typing import Any

from aireliability.distributed.models import (
    ExecutionRecord,
    ExecutionRecoverySummary,
    JobExecutionOutcome,
    JobStatus,
    PersistentWorkerRecord,
    ReliabilityJob,
    WorkerState,
)
from aireliability.distributed.storage import DistributedPersistenceBackend
from aireliability.telemetry.sanitizer import SanitizationPolicy

__all__ = [
    "DistributedPersistenceBackend",
    "PostgresDistributedStorage",
]

PSYCOPG_AVAILABLE = bool(
    importlib.util.find_spec("psycopg") or importlib.util.find_spec("psycopg2")
)


class PostgresDistributedStorage:
    """Optional PostgreSQL backend for multi-node distributed reliability."""

    def __init__(
        self,
        connection_url: str,
        *,
        sanitizer: SanitizationPolicy | None = None,
    ) -> None:
        if not PSYCOPG_AVAILABLE:
            raise ImportError(
                "PostgreSQL storage requires 'psycopg' or 'psycopg2'. "
                "Install with: pip install 'aireliability[postgres]'"
            )
        self.connection_url = connection_url
        self.sanitizer = sanitizer or SanitizationPolicy()

    def save_job(self, job: ReliabilityJob) -> None:
        raise NotImplementedError("PostgreSQL integration is an optional backend.")

    def get_job(self, job_id: str) -> ReliabilityJob | None:
        raise NotImplementedError("PostgreSQL integration is an optional backend.")

    def update_job(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        worker_id: str | None = None,
        attempt: int | None = None,
    ) -> ReliabilityJob:
        raise NotImplementedError("PostgreSQL integration is an optional backend.")

    def list_jobs(
        self, execution_id: str | None = None, status: JobStatus | None = None
    ) -> list[ReliabilityJob]:
        raise NotImplementedError("PostgreSQL integration is an optional backend.")

    def save_outcome(self, outcome: JobExecutionOutcome) -> None:
        raise NotImplementedError("PostgreSQL integration is an optional backend.")

    def get_outcome(self, job_id: str) -> JobExecutionOutcome | None:
        raise NotImplementedError("PostgreSQL integration is an optional backend.")

    def list_outcomes(
        self, execution_id: str | None = None
    ) -> list[JobExecutionOutcome]:
        raise NotImplementedError("PostgreSQL integration is an optional backend.")

    def save_execution(self, execution: ExecutionRecord) -> None:
        raise NotImplementedError("PostgreSQL integration is an optional backend.")

    def get_execution(self, execution_id: str) -> ExecutionRecord | None:
        raise NotImplementedError("PostgreSQL integration is an optional backend.")

    def list_executions(self, status: Any = None) -> list[ExecutionRecord]:
        raise NotImplementedError("PostgreSQL integration is an optional backend.")

    def delete_execution(self, execution_id: str) -> bool:
        raise NotImplementedError("PostgreSQL integration is an optional backend.")

    def save_worker(self, worker: PersistentWorkerRecord) -> None:
        raise NotImplementedError("PostgreSQL integration is an optional backend.")

    def get_worker(self, worker_id: str) -> PersistentWorkerRecord | None:
        raise NotImplementedError("PostgreSQL integration is an optional backend.")

    def list_workers(
        self, execution_id: str | None = None, state: WorkerState | None = None
    ) -> list[PersistentWorkerRecord]:
        raise NotImplementedError("PostgreSQL integration is an optional backend.")

    def get_failed_jobs(
        self, execution_id: str | None = None
    ) -> list[JobExecutionOutcome]:
        raise NotImplementedError("PostgreSQL integration is an optional backend.")

    def get_pending_jobs(self, execution_id: str | None = None) -> list[ReliabilityJob]:
        raise NotImplementedError("PostgreSQL integration is an optional backend.")

    def get_running_jobs(self, execution_id: str | None = None) -> list[ReliabilityJob]:
        raise NotImplementedError("PostgreSQL integration is an optional backend.")

    def claim_job(self, job_id: str, worker_id: str) -> bool:
        raise NotImplementedError("PostgreSQL integration is an optional backend.")

    def detect_stale_workers(
        self, timeout_seconds: float = 30.0, execution_id: str | None = None
    ) -> list[PersistentWorkerRecord]:
        raise NotImplementedError("PostgreSQL integration is an optional backend.")

    def recover_execution(
        self, execution_id: str, stale_timeout_seconds: float = 30.0
    ) -> ExecutionRecoverySummary:
        raise NotImplementedError("PostgreSQL integration is an optional backend.")
