"""Cooperative cancellation coordinator for running and scheduled jobs."""

import asyncio
from datetime import UTC, datetime

from aireliability.control_plane.errors import CancellationError
from aireliability.control_plane.models import QueueState, ScheduledJob
from aireliability.distributed.models import JobStatus


class CancellationCoordinator:
    """Manages cancellation tokens, task tracking, and cooperative cancellation."""

    def __init__(self) -> None:
        self._tokens: dict[str, asyncio.Event] = {}
        self._running_tasks: dict[str, asyncio.Task[None]] = {}

    def register_job(self, job_id: str) -> None:
        """Register a cancellation token for a queued or starting job."""
        if job_id not in self._tokens:
            self._tokens[job_id] = asyncio.Event()

    def register_task(self, job_id: str, task: asyncio.Task[None]) -> None:
        """Associate an active asyncio Task with a job ID."""
        self._running_tasks[job_id] = task

    def is_cancelled(self, job_id: str) -> bool:
        """Check if job has received a cancellation signal."""
        token = self._tokens.get(job_id)
        return token.is_set() if token else False

    def request_cancellation(
        self, job: ScheduledJob, force_cancel_task: bool = True
    ) -> ScheduledJob:
        """Cancel a job cooperatively.

        If the job is already COMPLETED, raises CancellationError.
        Updates state to CANCELLED and signals any running task.
        """
        if (
            job.queue_state == QueueState.COMPLETED
            or job.job_status == JobStatus.COMPLETED
        ):
            raise CancellationError(
                f"Cannot cancel job '{job.job_id}': job is already completed."
            )

        if job.queue_state == QueueState.CANCELLED:
            return job  # Idempotent

        # Set cancellation event
        if job.job_id not in self._tokens:
            self._tokens[job.job_id] = asyncio.Event()
        self._tokens[job.job_id].set()

        # Signal running task if requested
        if force_cancel_task:
            task = self._running_tasks.get(job.job_id)
            if task is not None and not task.done():
                task.cancel()

        now = datetime.now(UTC)
        updated_job = job.model_copy(
            update={
                "queue_state": QueueState.CANCELLED,
                "job_status": JobStatus.CANCELLED,
                "completed_at": now,
                "metadata": {
                    **job.metadata,
                    "cancelled_at": now.isoformat(),
                },
            }
        )
        return updated_job

    def cancel_tenant(
        self,
        tenant_id: str,
        jobs: list[ScheduledJob],
        force_cancel_task: bool = True,
    ) -> list[ScheduledJob]:
        """Cancel all pending/running jobs belonging to the specified tenant."""
        cancelled = []
        for job in jobs:
            if (
                getattr(job, "tenant_id", "default") == tenant_id
                and job.queue_state != QueueState.COMPLETED
                and job.job_status != JobStatus.COMPLETED
            ):
                cancelled.append(
                    self.request_cancellation(job, force_cancel_task=force_cancel_task)
                )
        return cancelled

    def cancel_project(
        self,
        project_id: str,
        jobs: list[ScheduledJob],
        tenant_id: str | None = None,
        force_cancel_task: bool = True,
    ) -> list[ScheduledJob]:
        """Cancel all pending/running jobs belonging to the specified project."""
        cancelled = []
        for job in jobs:
            if getattr(job, "project_id", "default") == project_id:
                if tenant_id and getattr(job, "tenant_id", "default") != tenant_id:
                    continue
                if (
                    job.queue_state != QueueState.COMPLETED
                    and job.job_status != JobStatus.COMPLETED
                ):
                    cancelled.append(
                        self.request_cancellation(
                            job, force_cancel_task=force_cancel_task
                        )
                    )
        return cancelled

    def cancel_namespace(
        self,
        namespace: str,
        jobs: list[ScheduledJob],
        tenant_id: str | None = None,
        force_cancel_task: bool = True,
    ) -> list[ScheduledJob]:
        """Cancel all pending/running jobs belonging to the specified namespace."""
        cancelled = []
        for job in jobs:
            if getattr(job, "namespace", "default") == namespace:
                if tenant_id and getattr(job, "tenant_id", "default") != tenant_id:
                    continue
                if (
                    job.queue_state != QueueState.COMPLETED
                    and job.job_status != JobStatus.COMPLETED
                ):
                    cancelled.append(
                        self.request_cancellation(
                            job, force_cancel_task=force_cancel_task
                        )
                    )
        return cancelled

    def unregister(self, job_id: str) -> None:
        """Clean up tokens and task references for a completed/terminated job."""
        self._tokens.pop(job_id, None)
        self._running_tasks.pop(job_id, None)
