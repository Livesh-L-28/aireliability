"""Failure storm protection and intelligent load shedding."""

import asyncio
from collections import deque
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from aireliability.control_plane.models import JobPriority


class LoadSheddingConfig(BaseModel):
    """Configuration for failure storm detection and load shedding."""

    model_config = ConfigDict(frozen=True)

    failure_rate_threshold: float = 0.5  # Shed if > 50% failures in window
    window_seconds: float = 30.0
    min_samples: int = 10
    max_queue_depth: int = 500
    shed_priority_threshold: JobPriority = (
        JobPriority.NORMAL
    )  # Shed NORMAL & LOW under pressure


class LoadShedder:
    """Monitors rolling failure rates and sheds lower-priority load
    under failure storms.
    """

    def __init__(self, config: LoadSheddingConfig | None = None) -> None:
        self.config = config or LoadSheddingConfig()
        self._samples: deque[tuple[datetime, bool]] = deque()
        self._lock = asyncio.Lock()
        self._shed_count = 0

    @property
    def shed_count(self) -> int:
        return self._shed_count

    async def record_result(self, success: bool) -> None:
        """Record an outcome in the rolling window."""
        async with self._lock:
            now = datetime.now(UTC)
            self._samples.append((now, success))
            self._prune_samples(now)

    async def get_failure_rate(self) -> float:
        """Calculate current failure rate in the rolling window."""
        async with self._lock:
            now = datetime.now(UTC)
            self._prune_samples(now)
            if len(self._samples) < self.config.min_samples:
                return 0.0
            failures = sum(1 for _, success in self._samples if not success)
            return failures / len(self._samples)

    async def should_shed_job(
        self, priority: JobPriority, current_queue_depth: int = 0
    ) -> tuple[bool, str | None]:
        """Determine if a job submission should be shed or rejected."""
        async with self._lock:
            now = datetime.now(UTC)
            self._prune_samples(now)

            # Check queue depth overload
            if current_queue_depth > self.config.max_queue_depth and int(
                priority
            ) >= int(self.config.shed_priority_threshold):
                self._shed_count += 1
                return (
                    True,
                    f"Load shed: queue depth ({current_queue_depth}) exceeds "
                    f"limit ({self.config.max_queue_depth}) "
                    f"for priority {priority.name}.",
                )

            # Check failure rate storm
            if len(self._samples) >= self.config.min_samples:
                failures = sum(1 for _, success in self._samples if not success)
                rate = failures / len(self._samples)
                if rate >= self.config.failure_rate_threshold and int(priority) >= int(
                    self.config.shed_priority_threshold
                ):
                    self._shed_count += 1
                    return (
                        True,
                        f"Failure storm protection: rolling failure rate {rate:.1%} "
                        f"exceeds threshold {self.config.failure_rate_threshold:.1%}.",
                    )

            return (False, None)

    def _prune_samples(self, now: datetime) -> None:
        cutoff = now.timestamp() - self.config.window_seconds
        while self._samples and self._samples[0][0].timestamp() < cutoff:
            self._samples.popleft()
