"""Fault tolerance, resilience, and self-healing package for AI Reliability Engine.

Provides structured failure classification, circuit breakers, backoff with jitter,
bulkhead isolation, worker health tracking, automatic quarantine, and load shedding.
"""

from aireliability.resilience.bulkhead import (
    Bulkhead,
    BulkheadCapacityExceededError,
)
from aireliability.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
)
from aireliability.resilience.classifier import FailureClassifier
from aireliability.resilience.health import HealthChecker
from aireliability.resilience.load_shedder import (
    LoadShedder,
    LoadSheddingConfig,
)
from aireliability.resilience.manager import ResilienceManager
from aireliability.resilience.models import (
    CircuitState,
    DetailedFailureRecord,
    HealthCheckResult,
    ResilienceFailureCategory,
    WorkerHealthStatus,
)
from aireliability.resilience.retry import (
    ResilienceBackoffStrategy,
    ResilientRetryPolicy,
)
from aireliability.resilience.worker_health import (
    WorkerHealthManager,
    WorkerHealthProfile,
)

__all__ = [
    "Bulkhead",
    "BulkheadCapacityExceededError",
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "CircuitState",
    "DetailedFailureRecord",
    "FailureClassifier",
    "HealthCheckResult",
    "HealthChecker",
    "LoadShedder",
    "LoadSheddingConfig",
    "ResilienceBackoffStrategy",
    "ResilienceFailureCategory",
    "ResilienceManager",
    "ResilientRetryPolicy",
    "WorkerHealthManager",
    "WorkerHealthProfile",
    "WorkerHealthStatus",
]
