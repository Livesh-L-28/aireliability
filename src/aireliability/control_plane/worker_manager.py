"""Worker capacity management and intelligent load balancing for control plane."""

import asyncio
from datetime import UTC, datetime
from typing import Any

from aireliability.control_plane.errors import (
    WorkerCapacityExceededError,
    WorkerNotFoundError,
)
from aireliability.control_plane.models import WorkerCapacityInfo
from aireliability.distributed.models import PersistentWorkerRecord, WorkerState
from aireliability.distributed.storage import DistributedPersistenceBackend


class WorkerManager:
    """Manages worker registration, capacity tracking, and load balancing."""

    def __init__(
        self,
        storage: DistributedPersistenceBackend | None = None,
        heartbeat_timeout_seconds: float = 30.0,
        default_capacity: int = 2,
    ) -> None:
        self.storage = storage
        self.heartbeat_timeout_seconds = heartbeat_timeout_seconds
        self.default_capacity = default_capacity
        self._workers: dict[str, WorkerCapacityInfo] = {}
        self._lock = asyncio.Lock()

    async def register_worker(
        self,
        worker_id: str,
        capacity: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WorkerCapacityInfo:
        """Register a worker with a specified capacity limit."""
        async with self._lock:
            info = WorkerCapacityInfo(
                worker_id=worker_id,
                capacity=capacity if capacity is not None else self.default_capacity,
                active_jobs=0,
                last_heartbeat=datetime.now(UTC),
                is_active=True,
                metadata=metadata or {},
            )
            self._workers[worker_id] = info

            # Sync with persistence backend if present
            if self.storage is not None and hasattr(self.storage, "save_worker"):
                rec = PersistentWorkerRecord(
                    worker_id=worker_id,
                    state=WorkerState.IDLE,
                    started_at=datetime.now(UTC),
                    last_heartbeat=datetime.now(UTC),
                    metadata=metadata or {},
                )
                self.storage.save_worker(rec)

            return info

    async def unregister_worker(self, worker_id: str) -> None:
        """Unregister worker and mark inactive."""
        async with self._lock:
            if worker_id in self._workers:
                current = self._workers[worker_id]
                self._workers[worker_id] = current.model_copy(
                    update={"is_active": False}
                )

            if self.storage is not None and hasattr(self.storage, "save_worker"):
                rec = self.storage.get_worker(worker_id)
                if rec:
                    self.storage.save_worker(
                        rec.model_copy(update={"state": WorkerState.STOPPED})
                    )

    async def heartbeat(self, worker_id: str) -> None:
        """Record worker heartbeat timestamp."""
        async with self._lock:
            if worker_id not in self._workers:
                # Auto-register if worker heartbeats before explicit registration
                self._workers[worker_id] = WorkerCapacityInfo(
                    worker_id=worker_id,
                    capacity=self.default_capacity,
                    active_jobs=0,
                    last_heartbeat=datetime.now(UTC),
                    is_active=True,
                )
            else:
                current = self._workers[worker_id]
                self._workers[worker_id] = current.model_copy(
                    update={"last_heartbeat": datetime.now(UTC), "is_active": True}
                )

    async def get_worker(self, worker_id: str) -> WorkerCapacityInfo | None:
        """Retrieve capacity and state info for a registered worker."""
        async with self._lock:
            return self._workers.get(worker_id)

    async def list_workers(self) -> list[WorkerCapacityInfo]:
        """List all registered worker capacity records."""
        async with self._lock:
            return list(self._workers.values())

    async def acquire_capacity(self, worker_id: str) -> None:
        """Reserve one capacity slot on the specified worker."""
        async with self._lock:
            info = self._workers.get(worker_id)
            if info is None:
                raise WorkerNotFoundError(f"Worker '{worker_id}' is not registered.")
            if not info.is_active:
                raise WorkerCapacityExceededError(f"Worker '{worker_id}' is inactive.")
            if info.available_slots <= 0:
                raise WorkerCapacityExceededError(
                    f"Worker '{worker_id}' has reached maximum "
                    f"capacity ({info.capacity})."
                )
            self._workers[worker_id] = info.model_copy(
                update={"active_jobs": info.active_jobs + 1}
            )

    async def release_capacity(self, worker_id: str) -> None:
        """Release one capacity slot on the specified worker."""
        async with self._lock:
            info = self._workers.get(worker_id)
            if info is not None:
                self._workers[worker_id] = info.model_copy(
                    update={"active_jobs": max(0, info.active_jobs - 1)}
                )

    async def select_best_worker(
        self,
        now: datetime | None = None,
        health_filter: Any = None,
        tenant_id: str | None = None,
        project_id: str | None = None,
        namespace: str | None = None,
    ) -> WorkerCapacityInfo | None:
        """Deterministically select the best available worker.

        Criteria:
        1. Must be active and have available capacity (available_slots > 0).
        2. Heartbeat must not be stale (within heartbeat_timeout_seconds).
        3. Must pass optional health_filter(worker_id) -> bool check.
        4. Must support tenant, project, and namespace if constrained.
        5. Prefer worker with the MOST available slots (least loaded).
        6. Tie-breaking: worker_id alphabetical ordering.
        """
        async with self._lock:
            current_time = now or datetime.now(UTC)
            eligible: list[WorkerCapacityInfo] = []

            for info in self._workers.values():
                if not info.is_active or info.available_slots <= 0:
                    continue
                delta = (current_time - info.last_heartbeat).total_seconds()
                if delta > self.heartbeat_timeout_seconds:
                    continue
                if not info.supports(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    namespace=namespace,
                ):
                    continue
                if health_filter is not None:
                    res = health_filter(info.worker_id)
                    if asyncio.iscoroutine(res):
                        res = await res
                    if not res:
                        continue
                eligible.append(info)

            if not eligible:
                return None

            # Sort by -available_slots (most available first), then worker_id ASC
            return min(
                eligible,
                key=lambda w: (-w.available_slots, w.worker_id),
            )

    async def detect_stale_workers(
        self, now: datetime | None = None
    ) -> list[WorkerCapacityInfo]:
        """Detect workers whose heartbeat exceeds the timeout."""
        async with self._lock:
            current_time = now or datetime.now(UTC)
            stale: list[WorkerCapacityInfo] = []
            for info in self._workers.values():
                if not info.is_active:
                    continue
                delta = (current_time - info.last_heartbeat).total_seconds()
                if delta > self.heartbeat_timeout_seconds:
                    stale.append(info)
            return stale
