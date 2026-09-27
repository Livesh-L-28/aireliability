"""Bulkhead isolation partitioning resources across providers and priorities."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager


class BulkheadCapacityExceededError(RuntimeError):
    """Raised when an isolated partition has no available concurrency capacity."""


class Bulkhead:
    """Manages independent, bounded concurrency limits for partitions."""

    def __init__(self, default_limit: int = 10) -> None:
        self.default_limit = max(1, default_limit)
        self._limits: dict[str, int] = {}
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._active: dict[str, int] = {}
        self._lock = asyncio.Lock()

    def set_limit(self, partition_key: str, limit: int) -> None:
        """Configure concurrency limit for a partition (e.g. 'provider:openai')."""
        self._limits[partition_key] = max(1, limit)
        self._semaphores[partition_key] = asyncio.Semaphore(limit)

    def get_limit(self, partition_key: str) -> int:
        return self._limits.get(partition_key, self.default_limit)

    def get_active(self, partition_key: str) -> int:
        return self._active.get(partition_key, 0)

    def get_available(self, partition_key: str) -> int:
        return max(0, self.get_limit(partition_key) - self.get_active(partition_key))

    @asynccontextmanager
    async def acquire(self, partition_key: str) -> AsyncGenerator[None, None]:
        """Async context manager acquiring an isolated concurrency slot."""
        async with self._lock:
            if partition_key not in self._semaphores:
                limit = self.get_limit(partition_key)
                self._semaphores[partition_key] = asyncio.Semaphore(limit)

        sem = self._semaphores[partition_key]
        if sem.locked():
            raise BulkheadCapacityExceededError(
                f"Bulkhead partition '{partition_key}' capacity exhausted "
                f"({self.get_limit(partition_key)} concurrent slots occupied)."
            )

        await sem.acquire()
        async with self._lock:
            self._active[partition_key] = self._active.get(partition_key, 0) + 1
        try:
            yield
        finally:
            sem.release()
            async with self._lock:
                self._active[partition_key] = max(
                    0, self._active.get(partition_key, 1) - 1
                )
