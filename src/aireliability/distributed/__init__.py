"""Distributed and concurrent reliability execution layer for AI Reliability Engine."""

from aireliability.distributed.aggregator import (
    DistributedExecutionSummary,
    ResultAggregator,
)
from aireliability.distributed.metrics import DistributedMetrics
from aireliability.distributed.models import (
    CorrelationContext,
    ExecutionRecord,
    ExecutionRecoverySummary,
    ExecutionStatusRecord,
    InvalidStateTransitionError,
    JobExecutionOutcome,
    JobStatus,
    PersistentJobRecord,
    PersistentOutcomeRecord,
    PersistentWorkerRecord,
    ReliabilityJob,
    WorkerDescriptor,
    WorkerState,
    validate_job_transition,
    validate_worker_transition,
)
from aireliability.distributed.runner import AsyncReliabilityRunner
from aireliability.distributed.sqlite_storage import SQLiteDistributedStorage
from aireliability.distributed.storage import (
    AsyncDistributedPersistenceBackend,
    DistributedPersistenceBackend,
    InMemoryDistributedStorage,
)
from aireliability.distributed.worker import ReliabilityWorker

__all__ = [
    "AsyncDistributedPersistenceBackend",
    "AsyncReliabilityRunner",
    "CorrelationContext",
    "DistributedExecutionSummary",
    "DistributedMetrics",
    "DistributedPersistenceBackend",
    "ExecutionRecord",
    "ExecutionRecoverySummary",
    "ExecutionStatusRecord",
    "InMemoryDistributedStorage",
    "InvalidStateTransitionError",
    "JobExecutionOutcome",
    "JobStatus",
    "PersistentJobRecord",
    "PersistentOutcomeRecord",
    "PersistentWorkerRecord",
    "ReliabilityJob",
    "ReliabilityWorker",
    "ResultAggregator",
    "SQLiteDistributedStorage",
    "WorkerDescriptor",
    "WorkerState",
    "validate_job_transition",
    "validate_worker_transition",
]
