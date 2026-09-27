"""Provider-neutral job queue abstraction and in-memory implementation."""

import asyncio
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from aireliability.control_plane.errors import JobNotFoundError
from aireliability.control_plane.models import QueueState, ScheduledJob
from aireliability.control_plane.policies import PriorityPolicy, SchedulingPolicy


@runtime_checkable
class JobQueue(Protocol):
    """Protocol for provider-neutral control-plane job queues."""

    async def enqueue(self, job: ScheduledJob) -> ScheduledJob:
        """Enqueue a job for scheduling."""
        ...

    async def dequeue(
        self, policy: SchedulingPolicy | None = None, now: datetime | None = None
    ) -> ScheduledJob | None:
        """Dequeue the next eligible job according to the specified policy."""
        ...

    async def peek(
        self, policy: SchedulingPolicy | None = None, now: datetime | None = None
    ) -> ScheduledJob | None:
        """Inspect the next eligible job without removing it from the queue."""
        ...

    async def get(self, job_id: str) -> ScheduledJob | None:
        """Retrieve a job by ID from the queue."""
        ...

    async def update(self, job: ScheduledJob) -> ScheduledJob:
        """Update an existing job in the queue."""
        ...

    async def remove(self, job_id: str) -> ScheduledJob | None:
        """Remove a job from the queue by ID."""
        ...

    async def size(self, tenant_id: str | None = None) -> int:
        """Total number of queued (unassigned, non-terminal) jobs in queue."""
        ...

    async def list_jobs(
        self,
        execution_id: str | None = None,
        queue_state: QueueState | None = None,
        tenant_id: str | None = None,
        project_id: str | None = None,
        namespace: str | None = None,
    ) -> list[ScheduledJob]:
        """List queued jobs matching optional filters."""
        ...

    async def clear(self) -> None:
        """Remove all jobs from the queue."""
        ...


class InMemoryJobQueue:
    """Thread-safe and async-safe in-memory job queue with zero dependencies."""

    def __init__(self, default_policy: SchedulingPolicy | None = None) -> None:
        self.default_policy = default_policy or PriorityPolicy()
        self._jobs: dict[str, ScheduledJob] = {}
        self._lock = asyncio.Lock()

    async def enqueue(self, job: ScheduledJob) -> ScheduledJob:
        async with self._lock:
            now = datetime.now(UTC)
            updated = job.model_copy(
                update={
                    "queue_state": QueueState.QUEUED,
                    "queued_at": job.queued_at or now,
                }
            )
            self._jobs[job.job_id] = updated
            return updated

    async def dequeue(
        self, policy: SchedulingPolicy | None = None, now: datetime | None = None
    ) -> ScheduledJob | None:
        async with self._lock:
            active_policy = policy or self.default_policy
            candidates = [
                j
                for j in self._jobs.values()
                if j.queue_state in (QueueState.QUEUED, QueueState.RETRYING)
            ]
            selected = active_policy.select_next(candidates, now=now)
            if selected is not None:
                # Mark as scheduled
                updated = selected.model_copy(
                    update={
                        "queue_state": QueueState.SCHEDULED,
                        "scheduled_at": selected.scheduled_at or datetime.now(UTC),
                    }
                )
                self._jobs[selected.job_id] = updated
                return updated
            return None

    async def peek(
        self, policy: SchedulingPolicy | None = None, now: datetime | None = None
    ) -> ScheduledJob | None:
        async with self._lock:
            active_policy = policy or self.default_policy
            candidates = [
                j
                for j in self._jobs.values()
                if j.queue_state in (QueueState.QUEUED, QueueState.RETRYING)
            ]
            return active_policy.select_next(candidates, now=now)

    async def get(self, job_id: str) -> ScheduledJob | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def update(self, job: ScheduledJob) -> ScheduledJob:
        async with self._lock:
            if job.job_id not in self._jobs:
                raise JobNotFoundError(f"Job '{job.job_id}' not found in queue.")
            self._jobs[job.job_id] = job
            return job

    async def remove(self, job_id: str) -> ScheduledJob | None:
        async with self._lock:
            return self._jobs.pop(job_id, None)

    async def size(self, tenant_id: str | None = None) -> int:
        async with self._lock:
            return sum(
                1
                for j in self._jobs.values()
                if j.queue_state in (QueueState.QUEUED, QueueState.RETRYING)
                and (
                    tenant_id is None or getattr(j, "tenant_id", "default") == tenant_id
                )
            )

    async def list_jobs(
        self,
        execution_id: str | None = None,
        queue_state: QueueState | None = None,
        tenant_id: str | None = None,
        project_id: str | None = None,
        namespace: str | None = None,
    ) -> list[ScheduledJob]:
        async with self._lock:
            jobs = list(self._jobs.values())
            if execution_id:
                jobs = [j for j in jobs if j.execution_id == execution_id]
            if queue_state:
                jobs = [j for j in jobs if j.queue_state == queue_state]
            if tenant_id:
                jobs = [
                    j for j in jobs if getattr(j, "tenant_id", "default") == tenant_id
                ]
            if project_id:
                jobs = [
                    j for j in jobs if getattr(j, "project_id", "default") == project_id
                ]
            if namespace:
                jobs = [
                    j for j in jobs if getattr(j, "namespace", "default") == namespace
                ]
            # Deterministic sorting
            return sorted(
                jobs,
                key=lambda j: (
                    int(j.priority),
                    j.queued_at or j.created_at,
                    j.job_id,
                ),
            )

    async def clear(self) -> None:
        async with self._lock:
            self._jobs.clear()
