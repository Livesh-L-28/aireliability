"""Worker health management, failure tracking, and automatic quarantine."""

import asyncio
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from aireliability.resilience.circuit_breaker import CircuitBreaker
from aireliability.resilience.models import WorkerHealthStatus


def _utc_now() -> datetime:
    return datetime.now(UTC)


class WorkerHealthProfile(BaseModel):
    """Health metrics and failure statistics for a worker."""

    model_config = ConfigDict(frozen=True)

    worker_id: str
    status: WorkerHealthStatus = WorkerHealthStatus.HEALTHY
    consecutive_failures: int = 0
    total_failures: int = 0
    total_successes: int = 0
    total_timeouts: int = 0
    last_failure_at: datetime | None = None
    last_success_at: datetime | None = None
    last_heartbeat_at: datetime = Field(default_factory=_utc_now)
    quarantined_at: datetime | None = None
    quarantine_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkerHealthManager:
    """Monitors worker execution outcomes, tracks health, and
    quarantines unhealthy workers.
    """

    def __init__(
        self,
        degradation_threshold: int = 2,
        quarantine_threshold: int = 4,
        recovery_success_threshold: int = 2,
    ) -> None:
        self.degradation_threshold = max(1, degradation_threshold)
        self.quarantine_threshold = max(
            self.degradation_threshold + 1, quarantine_threshold
        )
        self.recovery_success_threshold = max(1, recovery_success_threshold)

        self._profiles: dict[str, WorkerHealthProfile] = {}
        self._circuits: dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()

    async def get_or_create_profile(self, worker_id: str) -> WorkerHealthProfile:
        async with self._lock:
            if worker_id not in self._profiles:
                self._profiles[worker_id] = WorkerHealthProfile(worker_id=worker_id)
                self._circuits[worker_id] = CircuitBreaker(
                    name=f"worker:{worker_id}",
                    failure_threshold=self.quarantine_threshold,
                )
            return self._profiles[worker_id]

    async def record_heartbeat(self, worker_id: str) -> None:
        async with self._lock:
            prof = self._profiles.get(worker_id) or WorkerHealthProfile(
                worker_id=worker_id
            )
            self._profiles[worker_id] = prof.model_copy(
                update={"last_heartbeat_at": _utc_now()}
            )

    async def record_execution_success(self, worker_id: str) -> WorkerHealthProfile:
        """Record successful job execution on a worker."""
        async with self._lock:
            prof = self._profiles.get(worker_id) or WorkerHealthProfile(
                worker_id=worker_id
            )
            now = _utc_now()
            new_successes = prof.total_successes + 1

            if prof.status == WorkerHealthStatus.RECOVERING:
                if (prof.total_successes + 1) >= self.recovery_success_threshold:
                    new_status = WorkerHealthStatus.HEALTHY
                else:
                    new_status = WorkerHealthStatus.RECOVERING
            elif prof.status in (
                WorkerHealthStatus.DEGRADED,
                WorkerHealthStatus.UNHEALTHY,
            ):
                new_status = WorkerHealthStatus.HEALTHY
            else:
                new_status = prof.status

            updated = prof.model_copy(
                update={
                    "status": new_status,
                    "consecutive_failures": 0,
                    "total_successes": new_successes,
                    "last_success_at": now,
                    "quarantined_at": None
                    if new_status == WorkerHealthStatus.HEALTHY
                    else prof.quarantined_at,
                    "quarantine_reason": None
                    if new_status == WorkerHealthStatus.HEALTHY
                    else prof.quarantine_reason,
                }
            )
            self._profiles[worker_id] = updated

            if worker_id in self._circuits:
                await self._circuits[worker_id].record_success()

            return updated

    async def record_execution_failure(
        self, worker_id: str, reason: str = "Execution failed", is_timeout: bool = False
    ) -> WorkerHealthProfile:
        """Record execution failure, potentially transitioning to
        DEGRADED or QUARANTINED.
        """
        async with self._lock:
            prof = self._profiles.get(worker_id) or WorkerHealthProfile(
                worker_id=worker_id
            )
            now = _utc_now()
            consec_fail = prof.consecutive_failures + 1
            tot_fail = prof.total_failures + 1
            tot_timeout = prof.total_timeouts + (1 if is_timeout else 0)

            # Health state transitions
            if consec_fail >= self.quarantine_threshold:
                new_status = WorkerHealthStatus.QUARANTINED
                q_at = now
                q_reason = (
                    f"Consecutive failures exceeded threshold "
                    f"({consec_fail}/{self.quarantine_threshold}): {reason}"
                )
            elif consec_fail >= self.degradation_threshold:
                new_status = WorkerHealthStatus.DEGRADED
                q_at = None
                q_reason = None
            else:
                new_status = prof.status
                q_at = None
                q_reason = None

            updated = prof.model_copy(
                update={
                    "status": new_status,
                    "consecutive_failures": consec_fail,
                    "total_failures": tot_fail,
                    "total_timeouts": tot_timeout,
                    "last_failure_at": now,
                    "quarantined_at": q_at or prof.quarantined_at,
                    "quarantine_reason": q_reason or prof.quarantine_reason,
                }
            )
            self._profiles[worker_id] = updated

            if worker_id in self._circuits:
                await self._circuits[worker_id].record_failure()

            return updated

    async def quarantine_worker(
        self, worker_id: str, reason: str = "Manual quarantine"
    ) -> WorkerHealthProfile:
        """Manually quarantine a worker."""
        async with self._lock:
            prof = self._profiles.get(worker_id) or WorkerHealthProfile(
                worker_id=worker_id
            )
            now = _utc_now()
            updated = prof.model_copy(
                update={
                    "status": WorkerHealthStatus.QUARANTINED,
                    "quarantined_at": now,
                    "quarantine_reason": reason,
                }
            )
            self._profiles[worker_id] = updated
            return updated

    async def recover_worker(self, worker_id: str) -> WorkerHealthProfile:
        """Initiate recovery on a quarantined worker, setting state to RECOVERING."""
        async with self._lock:
            prof = self._profiles.get(worker_id) or WorkerHealthProfile(
                worker_id=worker_id
            )
            updated = prof.model_copy(
                update={
                    "status": WorkerHealthStatus.RECOVERING,
                    "consecutive_failures": 0,
                }
            )
            self._profiles[worker_id] = updated
            if worker_id in self._circuits:
                self._circuits[worker_id].reset()
            return updated

    async def is_worker_healthy(self, worker_id: str) -> bool:
        """Check if worker is eligible to receive jobs
        (HEALTHY, DEGRADED, or RECOVERING).
        """
        async with self._lock:
            prof = self._profiles.get(worker_id)
            if prof is None:
                return True
            return prof.status in (
                WorkerHealthStatus.HEALTHY,
                WorkerHealthStatus.DEGRADED,
                WorkerHealthStatus.RECOVERING,
            )

    async def list_profiles(self) -> list[WorkerHealthProfile]:
        async with self._lock:
            return list(self._profiles.values())
