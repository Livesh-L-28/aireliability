"""Central ResilienceManager coordinating resilience policies,
circuit breakers, and recovery.
"""

import asyncio
from typing import Any

from aireliability.control_plane.models import JobPriority
from aireliability.resilience.bulkhead import Bulkhead
from aireliability.resilience.circuit_breaker import CircuitBreaker
from aireliability.resilience.classifier import FailureClassifier
from aireliability.resilience.health import HealthChecker
from aireliability.resilience.load_shedder import LoadShedder, LoadSheddingConfig
from aireliability.resilience.models import (
    DetailedFailureRecord,
    HealthCheckResult,
)
from aireliability.resilience.retry import ResilientRetryPolicy
from aireliability.resilience.worker_health import (
    WorkerHealthManager,
)
from aireliability.telemetry.sanitizer import SanitizationPolicy


class ResilienceManager:
    """Central orchestration manager for resilience, self-healing,
    and fault tolerance.
    """

    def __init__(
        self,
        *,
        retry_policy: ResilientRetryPolicy | None = None,
        load_shedding_config: LoadSheddingConfig | None = None,
        sanitizer: SanitizationPolicy | None = None,
        circuit_failure_threshold: int = 5,
        circuit_recovery_timeout_seconds: float = 30.0,
        worker_quarantine_threshold: int = 4,
    ) -> None:
        self.sanitizer = sanitizer or SanitizationPolicy()
        self.retry_policy = retry_policy or ResilientRetryPolicy()
        self.classifier = FailureClassifier(sanitizer=self.sanitizer)
        self.bulkhead = Bulkhead()
        self.worker_health = WorkerHealthManager(
            quarantine_threshold=worker_quarantine_threshold,
        )
        self.load_shedder = LoadShedder(config=load_shedding_config)
        self.health_checker = HealthChecker()

        self.circuit_failure_threshold = circuit_failure_threshold
        self.circuit_recovery_timeout_seconds = circuit_recovery_timeout_seconds
        self._provider_circuits: dict[str, CircuitBreaker] = {}
        self._recorded_failures: list[DetailedFailureRecord] = []
        self._lock = asyncio.Lock()

    def get_provider_circuit(self, provider_id: str) -> CircuitBreaker:
        """Get or initialize a CircuitBreaker for a provider partition."""
        if provider_id not in self._provider_circuits:
            self._provider_circuits[provider_id] = CircuitBreaker(
                name=f"provider:{provider_id}",
                failure_threshold=self.circuit_failure_threshold,
                recovery_timeout_seconds=self.circuit_recovery_timeout_seconds,
            )
        return self._provider_circuits[provider_id]

    async def record_failure(
        self,
        exc: BaseException | str | None,
        *,
        execution_id: str | None = None,
        job_id: str | None = None,
        worker_id: str | None = None,
        provider_id: str | None = None,
        attempt: int = 1,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DetailedFailureRecord:
        """Classify and record a failure, updating worker health
        and circuit breakers.
        """
        failure = self.classifier.classify_error(
            exc,
            execution_id=execution_id,
            job_id=job_id,
            worker_id=worker_id,
            provider_id=provider_id,
            attempt=attempt,
            trace_id=trace_id,
            metadata=metadata,
        )

        async with self._lock:
            self._recorded_failures.append(failure)

        # Update load shedder rolling metrics
        await self.load_shedder.record_result(success=False)

        # Update worker health
        if worker_id:
            await self.worker_health.record_execution_failure(
                worker_id=worker_id,
                reason=failure.error or "Execution error",
                is_timeout="timeout" in failure.failure_type.value,
            )

        # Update provider circuit breaker
        if provider_id:
            circuit = self.get_provider_circuit(provider_id)
            await circuit.record_failure(error=failure.error)

        return failure

    async def record_success(
        self,
        *,
        worker_id: str | None = None,
        provider_id: str | None = None,
    ) -> None:
        """Record successful execution, updating worker health and circuit breakers."""
        await self.load_shedder.record_result(success=True)

        if worker_id:
            await self.worker_health.record_execution_success(worker_id)

        if provider_id:
            circuit = self.get_provider_circuit(provider_id)
            await circuit.record_success()

    async def check_admission(
        self,
        priority: JobPriority,
        current_queue_depth: int = 0,
        provider_id: str | None = None,
    ) -> tuple[bool, str | None]:
        """Check if a job should be admitted or shed/circuit-blocked."""
        # 1. Provider circuit check
        if provider_id:
            circuit = self.get_provider_circuit(provider_id)
            if not await circuit.can_execute():
                return (
                    False,
                    f"Provider '{provider_id}' circuit breaker is OPEN or probes full.",
                )

        # 2. Failure storm and queue depth load shedding check
        shed, reason = await self.load_shedder.should_shed_job(
            priority=priority,
            current_queue_depth=current_queue_depth,
        )
        if shed:
            return (False, reason)

        return (True, None)

    async def is_worker_eligible(self, worker_id: str) -> bool:
        """True if worker is healthy and not quarantined."""
        return await self.worker_health.is_worker_healthy(worker_id)

    async def list_failures(
        self,
        execution_id: str | None = None,
        limit: int = 100,
    ) -> list[DetailedFailureRecord]:
        async with self._lock:
            if execution_id:
                filtered = [
                    f for f in self._recorded_failures if f.execution_id == execution_id
                ]
            else:
                filtered = list(self._recorded_failures)
            return filtered[-limit:]

    def get_failure_records(
        self,
        execution_id: str | None = None,
        limit: int = 100,
    ) -> list[DetailedFailureRecord]:
        """Synchronous inspection of recorded failures."""
        if execution_id:
            filtered = [
                f for f in self._recorded_failures if f.execution_id == execution_id
            ]
        else:
            filtered = list(self._recorded_failures)
        return filtered[-limit:]

    async def check_all_health(
        self, storage: Any = None, scheduler: Any = None
    ) -> list[HealthCheckResult]:
        """Run health checks across storage, scheduler, and all registered workers."""
        results: list[HealthCheckResult] = []
        if storage is not None:
            results.append(await self.health_checker.check_storage(storage))
        if scheduler is not None:
            results.append(await self.health_checker.check_scheduler(scheduler))
        profiles = await self.worker_health.list_profiles()
        for p in profiles:
            results.append(
                await self.health_checker.check_worker(p.worker_id, self.worker_health)
            )
        return results
