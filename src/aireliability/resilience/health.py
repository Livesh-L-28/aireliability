"""Provider-neutral health checks for system components."""

import time
from datetime import UTC, datetime
from typing import Any

from aireliability.resilience.models import HealthCheckResult


class HealthChecker:
    """Executes structured health checks across persistence, schedulers, and workers."""

    @staticmethod
    async def check_storage(storage: Any) -> HealthCheckResult:
        """Check persistence backend reachability and responsiveness."""
        t0 = time.perf_counter()
        try:
            if hasattr(storage, "list_executions"):
                storage.list_executions()
            latency = (time.perf_counter() - t0) * 1000.0
            return HealthCheckResult(
                component="storage",
                status="healthy",
                latency_ms=latency,
                timestamp=datetime.now(UTC),
            )
        except Exception as exc:
            latency = (time.perf_counter() - t0) * 1000.0
            return HealthCheckResult(
                component="storage",
                status="unhealthy",
                latency_ms=latency,
                timestamp=datetime.now(UTC),
                error=str(exc),
            )

    @staticmethod
    async def check_scheduler(scheduler: Any) -> HealthCheckResult:
        """Check scheduler service state."""
        t0 = time.perf_counter()
        try:
            status_val = str(getattr(scheduler, "status", "unknown"))
            latency = (time.perf_counter() - t0) * 1000.0
            is_healthy = status_val in ("running", "SchedulerStatus.RUNNING")
            return HealthCheckResult(
                component="scheduler",
                status="healthy" if is_healthy else "degraded",
                latency_ms=latency,
                timestamp=datetime.now(UTC),
                metadata={"scheduler_status": status_val},
            )
        except Exception as exc:
            latency = (time.perf_counter() - t0) * 1000.0
            return HealthCheckResult(
                component="scheduler",
                status="unhealthy",
                latency_ms=latency,
                timestamp=datetime.now(UTC),
                error=str(exc),
            )

    @staticmethod
    async def check_worker(worker_id: str, health_manager: Any) -> HealthCheckResult:
        """Check health profile of a specific worker."""
        t0 = time.perf_counter()
        try:
            prof = await health_manager.get_or_create_profile(worker_id)
            latency = (time.perf_counter() - t0) * 1000.0
            return HealthCheckResult(
                component=f"worker:{worker_id}",
                status=prof.status.value,
                latency_ms=latency,
                timestamp=datetime.now(UTC),
                metadata={
                    "consecutive_failures": prof.consecutive_failures,
                    "total_failures": prof.total_failures,
                },
            )
        except Exception as exc:
            latency = (time.perf_counter() - t0) * 1000.0
            return HealthCheckResult(
                component=f"worker:{worker_id}",
                status="unhealthy",
                latency_ms=latency,
                timestamp=datetime.now(UTC),
                error=str(exc),
            )
