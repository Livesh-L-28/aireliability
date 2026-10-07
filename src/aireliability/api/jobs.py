"""Asynchronous job execution and management (Phase 46)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from aireliability.api.models import Job, JobStatus


class JobManager:
    """Manages asynchronous long-running reliability jobs."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def submit_job(
        self,
        operation: str,
        payload: dict[str, Any],
        tenant_id: str = "default",
    ) -> Job:
        """Submit a new background job."""
        job = Job(
            operation=operation,
            status=JobStatus.QUEUED,
            tenant_id=tenant_id,
            input_payload=payload,
        )
        self._jobs[job.job_id] = job
        return job

    def get_job(self, job_id: str, tenant_id: str | None = None) -> Job | None:
        """Retrieve job by identifier, verifying tenant isolation."""
        job = self._jobs.get(job_id)
        if not job:
            return None
        if tenant_id and job.tenant_id != tenant_id:
            return None
        return job

    def list_jobs(self, tenant_id: str | None = None) -> list[Job]:
        """List all jobs, optionally filtered by tenant."""
        jobs = list(self._jobs.values())
        if tenant_id:
            jobs = [j for j in jobs if j.tenant_id == tenant_id]
        return jobs

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> Job | None:
        """Update job status and results."""
        job = self._jobs.get(job_id)
        if not job:
            return None

        completed = (
            datetime.now(UTC)
            if status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED)
            else None
        )
        updated = Job(
            job_id=job.job_id,
            operation=job.operation,
            status=status,
            tenant_id=job.tenant_id,
            input_payload=job.input_payload,
            result=result or job.result,
            error=error or job.error,
            created_at=job.created_at,
            completed_at=completed,
        )
        self._jobs[job_id] = updated
        return updated

    def cancel_job(self, job_id: str, tenant_id: str | None = None) -> bool:
        """Cancel a running or queued job, verifying tenant isolation."""
        job = self._jobs.get(job_id)
        if not job:
            return False
        if tenant_id and job.tenant_id != tenant_id:
            return False
        if job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
            self.update_status(job_id, JobStatus.CANCELLED)
            return True
        return False
