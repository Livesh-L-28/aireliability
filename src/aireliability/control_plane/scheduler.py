"""Autonomous job scheduler coordinating queues, policies, and worker capacity."""

import asyncio
import contextlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from aireliability.control_plane.errors import (
    WorkerCapacityExceededError,
)
from aireliability.control_plane.models import (
    QueueState,
    ScheduledJob,
    SchedulerStatus,
)
from aireliability.control_plane.policies import PriorityPolicy, SchedulingPolicy
from aireliability.control_plane.queue import JobQueue
from aireliability.control_plane.worker_manager import WorkerManager
from aireliability.distributed.metrics import DistributedMetrics
from aireliability.distributed.storage import DistributedPersistenceBackend

logger = logging.getLogger(__name__)


class JobScheduler:
    """Core scheduler coordinating queue dequeuing and dispatching."""

    def __init__(
        self,
        queue: JobQueue,
        worker_manager: WorkerManager,
        *,
        policy: SchedulingPolicy | None = None,
        storage: DistributedPersistenceBackend | None = None,
        metrics: DistributedMetrics | None = None,
        dispatch_handler: Callable[[ScheduledJob, str], Any] | None = None,
        poll_interval_seconds: float = 0.05,
        worker_health_filter: Callable[[str], Any] | None = None,
    ) -> None:
        self.queue = queue
        self.worker_manager = worker_manager
        self.policy = policy or PriorityPolicy()
        self.storage = storage
        self.metrics = metrics
        self.dispatch_handler = dispatch_handler
        self.poll_interval_seconds = poll_interval_seconds
        self.worker_health_filter = worker_health_filter

        self._status: SchedulerStatus = SchedulerStatus.STOPPED
        self._loop_task: asyncio.Task[None] | None = None
        self._dispatch_tasks: set[asyncio.Task[Any]] = set()
        self._lock = asyncio.Lock()
        self._total_scheduled = 0
        self._total_dispatches = 0
        self._total_assignment_failures = 0

    @property
    def status(self) -> SchedulerStatus:
        """Current lifecycle status of the scheduler."""
        return self._status

    @property
    def total_scheduled(self) -> int:
        return self._total_scheduled

    @property
    def total_dispatches(self) -> int:
        return self._total_dispatches

    @property
    def total_assignment_failures(self) -> int:
        return self._total_assignment_failures

    async def start(self) -> None:
        """Start the background scheduler dispatch loop."""
        async with self._lock:
            if self._status == SchedulerStatus.RUNNING:
                return
            self._status = SchedulerStatus.STARTING
            self._loop_task = asyncio.create_task(self._run_dispatch_loop())
            self._status = SchedulerStatus.RUNNING

    async def stop(self) -> None:
        """Stop the background scheduler loop gracefully."""
        async with self._lock:
            if self._status in (SchedulerStatus.STOPPED, SchedulerStatus.STOPPING):
                return
            self._status = SchedulerStatus.STOPPING
            if self._loop_task and not self._loop_task.done():
                self._loop_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._loop_task
            if self._dispatch_tasks:
                await asyncio.gather(
                    *list(self._dispatch_tasks), return_exceptions=True
                )
            self._status = SchedulerStatus.STOPPED

    async def tick(self) -> ScheduledJob | None:
        """Alias for schedule_once() to execute and wait for dispatch."""
        job = await self.schedule_once()
        if self._dispatch_tasks:
            await asyncio.gather(*list(self._dispatch_tasks), return_exceptions=True)
        return job

    async def schedule_once(self) -> ScheduledJob | None:
        """Perform a single schedule-and-dispatch pass.

        Returns:
            The assigned ScheduledJob if successful, or None if no job or worker.
        """
        now = datetime.now(UTC)
        # Check if an eligible job is available before dequeuing
        peeked = await self.queue.peek(policy=self.policy, now=now)
        if peeked is None:
            return None

        # Check if an active worker with capacity is available
        worker = await self.worker_manager.select_best_worker(
            now=now, health_filter=self.worker_health_filter
        )
        if worker is None:
            return None

        # Dequeue the job
        job = await self.queue.dequeue(policy=self.policy, now=now)
        if job is None:
            return None

        # Acquire capacity on the worker
        try:
            await self.worker_manager.acquire_capacity(worker.worker_id)
        except WorkerCapacityExceededError:
            # Requeue job if worker capacity was exhausted in race
            self._total_assignment_failures += 1
            await self.queue.enqueue(job)
            return None

        # Update job to ASSIGNED
        assigned_job = job.model_copy(
            update={
                "queue_state": QueueState.ASSIGNED,
                "assigned_worker_id": worker.worker_id,
                "assigned_at": datetime.now(UTC),
            }
        )
        await self.queue.update(assigned_job)
        self._total_scheduled += 1

        # Attempt atomic storage claim if storage backend is present
        if self.storage is not None and hasattr(self.storage, "claim_job"):
            claimed = self.storage.claim_job(assigned_job.job_id, worker.worker_id)
            if not claimed:
                # Another process or worker claimed it
                self._total_assignment_failures += 1
                await self.worker_manager.release_capacity(worker.worker_id)
                # Mark as already claimed or remove from queue
                await self.queue.remove(assigned_job.job_id)
                return None

        # Dispatch job to handler if configured
        if self.dispatch_handler is not None:
            self._total_dispatches += 1
            res = self.dispatch_handler(assigned_job, worker.worker_id)
            if asyncio.iscoroutine(res):
                # Run dispatch in background task so scheduler is not blocked
                task = asyncio.create_task(
                    self._wrap_dispatch(res, assigned_job, worker.worker_id)
                )
                self._dispatch_tasks.add(task)
                task.add_done_callback(self._dispatch_tasks.discard)

        return assigned_job

    async def _wrap_dispatch(
        self, coro: Any, job: ScheduledJob, worker_id: str
    ) -> None:
        try:
            await coro
        except Exception as exc:
            logger.exception(
                "Error executing dispatched job %s on %s: %s",
                job.job_id,
                worker_id,
                exc,
            )
        finally:
            await self.worker_manager.release_capacity(worker_id)

    async def _run_dispatch_loop(self) -> None:
        """Continuous polling dispatch loop."""
        while self._status == SchedulerStatus.RUNNING:
            try:
                assigned = await self.schedule_once()
                if assigned is None:
                    await asyncio.sleep(self.poll_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in scheduler loop: %s", exc)
                await asyncio.sleep(self.poll_interval_seconds)
