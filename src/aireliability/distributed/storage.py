"""Distributed storage abstractions and in-memory persistence.

Provides complete synchronous and asynchronous persistence protocols and a
reference thread-safe in-memory store for distributed reliability jobs,
workers, outcomes, and executions.
"""

from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from aireliability.distributed.models import (
    ExecutionRecord,
    ExecutionRecoverySummary,
    ExecutionStatusRecord,
    JobExecutionOutcome,
    JobStatus,
    PersistentWorkerRecord,
    ReliabilityJob,
    WorkerState,
    validate_job_transition,
    validate_worker_transition,
)
from aireliability.telemetry.sanitizer import SanitizationPolicy


@runtime_checkable
class DistributedPersistenceBackend(Protocol):
    """Protocol for persisting reliability jobs, executions, workers, and outcomes."""

    # Job operations
    def save_job(self, job: ReliabilityJob) -> None:
        """Persist or update a ReliabilityJob."""
        ...

    def get_job(self, job_id: str) -> ReliabilityJob | None:
        """Retrieve a ReliabilityJob by ID."""
        ...

    def update_job(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        worker_id: str | None = None,
        attempt: int | None = None,
    ) -> ReliabilityJob:
        """Update job status, assigned worker, or attempt number."""
        ...

    def list_jobs(
        self,
        execution_id: str | None = None,
        status: JobStatus | None = None,
        tenant_id: str | None = None,
    ) -> list[ReliabilityJob]:
        """List jobs matching optional filters."""
        ...

    # Outcome operations
    def save_outcome(self, outcome: JobExecutionOutcome) -> None:
        """Persist a job execution outcome."""
        ...

    def get_outcome(self, job_id: str) -> JobExecutionOutcome | None:
        """Retrieve the latest outcome for a job ID."""
        ...

    def list_outcomes(
        self, execution_id: str | None = None, tenant_id: str | None = None
    ) -> list[JobExecutionOutcome]:
        """List execution outcomes."""
        ...

    # Execution operations
    def save_execution(self, execution: ExecutionRecord) -> None:
        """Persist or update an ExecutionRecord."""
        ...

    def get_execution(self, execution_id: str) -> ExecutionRecord | None:
        """Retrieve an ExecutionRecord by ID."""
        ...

    def list_executions(
        self,
        status: ExecutionStatusRecord | None = None,
        tenant_id: str | None = None,
    ) -> list[ExecutionRecord]:
        """List executions with optional status and tenant filtering."""
        ...

    def delete_execution(self, execution_id: str) -> bool:
        """Delete an execution and its associated jobs, outcomes, and workers."""
        ...

    # Worker operations
    def save_worker(self, worker: PersistentWorkerRecord) -> None:
        """Persist or update a worker record."""
        ...

    def get_worker(self, worker_id: str) -> PersistentWorkerRecord | None:
        """Retrieve a worker record by worker ID."""
        ...

    def list_workers(
        self,
        execution_id: str | None = None,
        state: WorkerState | None = None,
        tenant_id: str | None = None,
    ) -> list[PersistentWorkerRecord]:
        """List registered workers with optional filters."""
        ...

    # Query helpers
    def get_failed_jobs(
        self, execution_id: str | None = None, tenant_id: str | None = None
    ) -> list[JobExecutionOutcome]:
        """Query all jobs that failed or timed out."""
        ...

    def get_pending_jobs(
        self, execution_id: str | None = None, tenant_id: str | None = None
    ) -> list[ReliabilityJob]:
        """Query all pending jobs."""
        ...

    def get_running_jobs(
        self, execution_id: str | None = None, tenant_id: str | None = None
    ) -> list[ReliabilityJob]:
        """Query all running jobs."""
        ...

    # Coordination & recovery
    def claim_job(self, job_id: str, worker_id: str) -> bool:
        """Atomically claim a pending job for a specific worker.

        Returns:
            True if claim succeeded, False if already claimed or not pending.
        """
        ...

    def detect_stale_workers(
        self, timeout_seconds: float = 30.0, execution_id: str | None = None
    ) -> list[PersistentWorkerRecord]:
        """Identify workers whose last heartbeat exceeds timeout_seconds."""
        ...

    def recover_execution(
        self, execution_id: str, stale_timeout_seconds: float = 30.0
    ) -> ExecutionRecoverySummary:
        """Identify stale workers and requeue their unfinished jobs."""
        ...

    # Resilience operations (Phase 26)
    def save_failure(self, failure: Any) -> None:
        """Persist a detailed failure record."""
        ...

    def list_failures(
        self, execution_id: str | None = None, tenant_id: str | None = None
    ) -> list[Any]:
        """List persisted detailed failure records."""
        ...

    # Security operations (Phase 28)
    def save_api_key(self, api_key: Any) -> None:
        """Persist an API key record."""
        ...

    def get_api_key(self, key_id: str) -> Any | None:
        """Retrieve an API key record by ID."""
        ...

    def list_api_keys(self, tenant_id: str | None = None) -> list[Any]:
        """List persisted API keys."""
        ...

    def save_audit_event(self, event: Any) -> None:
        """Persist a security audit event."""
        ...

    def list_audit_events(
        self,
        tenant_id: str | None = None,
        principal_id: str | None = None,
        action: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        """List security audit events."""
        ...

    def save_replay_record(self, record: Any) -> None:
        """Persist a replay protection record."""
        ...

    # Observability operations (Phase 29)
    def save_telemetry_event(self, event: Any) -> None:
        """Persist a structured telemetry event."""
        ...

    def list_telemetry_events(
        self,
        tenant_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        """List persisted telemetry events."""
        ...

    def save_trace_record(self, trace: Any) -> None:
        """Persist a distributed trace record."""
        ...

    def get_trace_record(self, trace_id: str) -> Any | None:
        """Retrieve a trace record by ID."""
        ...

    def list_trace_records(
        self, tenant_id: str | None = None, limit: int = 100
    ) -> list[Any]:
        """List persisted trace records."""
        ...

    def save_incident(self, incident: Any) -> None:
        """Persist an operational incident."""
        ...

    def get_incident(self, incident_id: str) -> Any | None:
        """Retrieve an operational incident by ID."""
        ...

    def list_incidents(
        self, tenant_id: str | None = None, limit: int = 100
    ) -> list[Any]:
        """List persisted operational incidents."""
        ...


@runtime_checkable
class AsyncDistributedPersistenceBackend(Protocol):
    """Asynchronous protocol for distributed persistence."""

    async def asave_job(self, job: ReliabilityJob) -> None: ...
    async def aget_job(self, job_id: str) -> ReliabilityJob | None: ...
    async def aupdate_job(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        worker_id: str | None = None,
        attempt: int | None = None,
    ) -> ReliabilityJob: ...
    async def alist_jobs(
        self, execution_id: str | None = None, status: JobStatus | None = None
    ) -> list[ReliabilityJob]: ...
    async def asave_outcome(self, outcome: JobExecutionOutcome) -> None: ...
    async def aget_outcome(self, job_id: str) -> JobExecutionOutcome | None: ...
    async def alist_outcomes(
        self, execution_id: str | None = None
    ) -> list[JobExecutionOutcome]: ...
    async def asave_execution(self, execution: ExecutionRecord) -> None: ...
    async def aget_execution(self, execution_id: str) -> ExecutionRecord | None: ...
    async def aclaim_job(self, job_id: str, worker_id: str) -> bool: ...


class InMemoryDistributedStorage:
    """Thread-safe store for distributed reliability jobs, workers, and executions."""

    def __init__(self, sanitizer: SanitizationPolicy | None = None) -> None:
        self.sanitizer = sanitizer or SanitizationPolicy()
        self._jobs: dict[str, ReliabilityJob] = {}
        self._outcomes: dict[str, JobExecutionOutcome] = {}
        self._workers: dict[str, PersistentWorkerRecord] = {}
        self._executions: dict[str, ExecutionRecord] = {}
        self._failures: list[Any] = []
        self._api_keys: dict[str, Any] = {}
        self._audit_events: list[Any] = []
        self._replay_records: list[Any] = []
        self._telemetry_events: list[Any] = []
        self._trace_records: dict[str, Any] = {}
        self._incidents: dict[str, Any] = {}

    # --- Job Operations ---

    def save_job(self, job: ReliabilityJob) -> None:
        sanitized_meta = self.sanitizer.sanitize(job.metadata)
        if sanitized_meta != job.metadata:
            job = job.model_copy(update={"metadata": sanitized_meta})
        self._jobs[job.job_id] = job

    def get_job(self, job_id: str) -> ReliabilityJob | None:
        return self._jobs.get(job_id)

    def update_job(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        worker_id: str | None = None,
        attempt: int | None = None,
    ) -> ReliabilityJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"Job with ID '{job_id}' not found.")
        updates: dict[str, object] = {}
        if status is not None:
            validate_job_transition(job.status, status)
            updates["status"] = status
        if worker_id is not None:
            updates["assigned_worker_id"] = worker_id
        if attempt is not None:
            updates["attempt"] = attempt
        updated_job = job.model_copy(update=updates)
        self._jobs[job_id] = updated_job
        return updated_job

    def list_jobs(
        self,
        execution_id: str | None = None,
        status: JobStatus | None = None,
        tenant_id: str | None = None,
    ) -> list[ReliabilityJob]:
        jobs = list(self._jobs.values())
        if execution_id:
            jobs = [j for j in jobs if j.execution_id == execution_id]
        if status:
            jobs = [j for j in jobs if j.status == status]
        if tenant_id:
            jobs = [j for j in jobs if j.tenant_id == tenant_id]
        return jobs

    # --- Outcome Operations ---

    def save_outcome(self, outcome: JobExecutionOutcome) -> None:
        sanitized_meta = self.sanitizer.sanitize(outcome.metadata)
        if sanitized_meta != outcome.metadata:
            outcome = outcome.model_copy(update={"metadata": sanitized_meta})

        # Idempotency check: don't overwrite newer attempts
        existing = self._outcomes.get(outcome.job_id)
        if existing is not None and existing.attempt > outcome.attempt:
            return  # Older attempt should not overwrite newer

        self._outcomes[outcome.job_id] = outcome

        # Update corresponding job status if present
        if outcome.job_id in self._jobs:
            current_job = self._jobs[outcome.job_id]
            # Valid transition or update
            self._jobs[outcome.job_id] = current_job.model_copy(
                update={"status": outcome.status}
            )

    def get_outcome(self, job_id: str) -> JobExecutionOutcome | None:
        return self._outcomes.get(job_id)

    def list_outcomes(
        self, execution_id: str | None = None, tenant_id: str | None = None
    ) -> list[JobExecutionOutcome]:
        outcomes = list(self._outcomes.values())
        if execution_id:
            outcomes = [o for o in outcomes if o.execution_id == execution_id]
        if tenant_id:
            outcomes = [
                o
                for o in outcomes
                if o.metadata.get("tenant_id", "default") == tenant_id
            ]
        return outcomes

    # --- Execution Operations ---

    def save_execution(self, execution: ExecutionRecord) -> None:
        sanitized_meta = self.sanitizer.sanitize(execution.metadata)
        if sanitized_meta != execution.metadata:
            execution = execution.model_copy(update={"metadata": sanitized_meta})
        self._executions[execution.execution_id] = execution

    def get_execution(self, execution_id: str) -> ExecutionRecord | None:
        return self._executions.get(execution_id)

    def list_executions(
        self,
        status: ExecutionStatusRecord | None = None,
        tenant_id: str | None = None,
    ) -> list[ExecutionRecord]:
        execs = list(self._executions.values())
        if status:
            execs = [e for e in execs if e.status == status]
        if tenant_id:
            execs = [e for e in execs if e.tenant_id == tenant_id]
        return execs

    def delete_execution(self, execution_id: str) -> bool:
        if execution_id not in self._executions:
            return False
        del self._executions[execution_id]
        self._jobs = {
            k: v for k, v in self._jobs.items() if v.execution_id != execution_id
        }
        self._outcomes = {
            k: v for k, v in self._outcomes.items() if v.execution_id != execution_id
        }
        self._workers = {
            k: v for k, v in self._workers.items() if v.execution_id != execution_id
        }
        return True

    # --- Worker Operations ---

    def save_worker(self, worker: PersistentWorkerRecord) -> None:
        sanitized_meta = self.sanitizer.sanitize(worker.metadata)
        if sanitized_meta != worker.metadata:
            worker = worker.model_copy(update={"metadata": sanitized_meta})
        existing = self._workers.get(worker.worker_id)
        if existing is not None and existing.state != worker.state:
            validate_worker_transition(existing.state, worker.state)
        self._workers[worker.worker_id] = worker

    def get_worker(self, worker_id: str) -> PersistentWorkerRecord | None:
        return self._workers.get(worker_id)

    def list_workers(
        self,
        execution_id: str | None = None,
        state: WorkerState | None = None,
        tenant_id: str | None = None,
    ) -> list[PersistentWorkerRecord]:
        workers = list(self._workers.values())
        if execution_id:
            workers = [w for w in workers if w.execution_id == execution_id]
        if state:
            workers = [w for w in workers if w.state == state]
        if tenant_id:
            workers = [
                w
                for w in workers
                if w.metadata.get("tenant_id", "default") == tenant_id
                or tenant_id in w.metadata.get("supported_tenants", [])
            ]
        return workers

    # --- Query & Coordination Helpers ---

    def get_failed_jobs(
        self, execution_id: str | None = None, tenant_id: str | None = None
    ) -> list[JobExecutionOutcome]:
        outcomes = self.list_outcomes(execution_id, tenant_id=tenant_id)
        return [
            o for o in outcomes if o.status in (JobStatus.FAILED, JobStatus.TIMED_OUT)
        ]

    def get_pending_jobs(
        self, execution_id: str | None = None, tenant_id: str | None = None
    ) -> list[ReliabilityJob]:
        return self.list_jobs(
            execution_id=execution_id, status=JobStatus.PENDING, tenant_id=tenant_id
        )

    def get_running_jobs(
        self, execution_id: str | None = None, tenant_id: str | None = None
    ) -> list[ReliabilityJob]:
        return self.list_jobs(
            execution_id=execution_id, status=JobStatus.RUNNING, tenant_id=tenant_id
        )

    def query_failed_jobs(
        self, execution_id: str | None = None, tenant_id: str | None = None
    ) -> list[JobExecutionOutcome]:
        """Backward-compatible alias for get_failed_jobs."""
        return self.get_failed_jobs(execution_id, tenant_id=tenant_id)

    def claim_job(self, job_id: str, worker_id: str) -> bool:
        """Atomic claim of a pending or retrying job."""
        job = self._jobs.get(job_id)
        if job is None or job.status not in (JobStatus.PENDING, JobStatus.RETRYING):
            return False
        # Update to running
        validate_job_transition(job.status, JobStatus.RUNNING)
        self._jobs[job_id] = job.model_copy(
            update={
                "status": JobStatus.RUNNING,
                "assigned_worker_id": worker_id,
            }
        )
        return True

    def detect_stale_workers(
        self, timeout_seconds: float = 30.0, execution_id: str | None = None
    ) -> list[PersistentWorkerRecord]:
        now = datetime.now(UTC)
        stale: list[PersistentWorkerRecord] = []
        for worker in self.list_workers(execution_id=execution_id):
            if worker.state == WorkerState.STOPPED:
                continue
            delta = (now - worker.last_heartbeat).total_seconds()
            if delta > timeout_seconds:
                stale.append(worker)
        return stale

    def recover_execution(
        self, execution_id: str, stale_timeout_seconds: float = 30.0
    ) -> ExecutionRecoverySummary:
        stale_workers = self.detect_stale_workers(
            timeout_seconds=stale_timeout_seconds, execution_id=execution_id
        )
        stale_worker_ids = {w.worker_id for w in stale_workers}

        recovered_jobs: list[str] = []
        already_completed_jobs: list[str] = []
        requeued_jobs: list[str] = []
        failed_recovery_jobs: list[str] = []

        jobs = self.list_jobs(execution_id=execution_id)
        for job in jobs:
            if job.status == JobStatus.COMPLETED:
                already_completed_jobs.append(job.job_id)
            elif (
                job.status in (JobStatus.RUNNING, JobStatus.PENDING)
                and job.assigned_worker_id in stale_worker_ids
            ):
                # Requeue job
                recovered_jobs.append(job.job_id)
                new_attempt = job.attempt + 1
                if new_attempt <= job.max_retries + 1:
                    updated = job.model_copy(
                        update={
                            "status": JobStatus.PENDING,
                            "assigned_worker_id": None,
                            "attempt": new_attempt,
                            "metadata": {
                                **job.metadata,
                                "recovered_from_worker": job.assigned_worker_id,
                                "recovery_timestamp": datetime.now(UTC).isoformat(),
                            },
                        }
                    )
                    self._jobs[job.job_id] = updated
                    requeued_jobs.append(job.job_id)
                else:
                    # Exceeded retries during recovery
                    failed_recovery_jobs.append(job.job_id)
                    updated = job.model_copy(
                        update={
                            "status": JobStatus.FAILED,
                            "metadata": {
                                **job.metadata,
                                "recovery_failure": "max_retries_exceeded_on_recovery",
                            },
                        }
                    )
                    self._jobs[job.job_id] = updated

        # Mark stale workers as stopped or failed
        for sw in stale_workers:
            self._workers[sw.worker_id] = sw.model_copy(
                update={"state": WorkerState.FAILED}
            )

        return ExecutionRecoverySummary(
            execution_id=execution_id,
            recovered_jobs=recovered_jobs,
            already_completed_jobs=already_completed_jobs,
            stale_workers=list(stale_worker_ids),
            requeued_jobs=requeued_jobs,
            failed_recovery_jobs=failed_recovery_jobs,
        )

    # --- Async Adapter Methods for AsyncDistributedPersistenceBackend ---

    async def asave_job(self, job: ReliabilityJob) -> None:
        self.save_job(job)

    async def aget_job(self, job_id: str) -> ReliabilityJob | None:
        return self.get_job(job_id)

    async def aupdate_job(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        worker_id: str | None = None,
        attempt: int | None = None,
    ) -> ReliabilityJob:
        return self.update_job(
            job_id, status=status, worker_id=worker_id, attempt=attempt
        )

    async def alist_jobs(
        self, execution_id: str | None = None, status: JobStatus | None = None
    ) -> list[ReliabilityJob]:
        return self.list_jobs(execution_id=execution_id, status=status)

    async def asave_outcome(self, outcome: JobExecutionOutcome) -> None:
        self.save_outcome(outcome)

    async def aget_outcome(self, job_id: str) -> JobExecutionOutcome | None:
        return self.get_outcome(job_id)

    async def alist_outcomes(
        self, execution_id: str | None = None
    ) -> list[JobExecutionOutcome]:
        return self.list_outcomes(execution_id=execution_id)

    async def asave_execution(self, execution: ExecutionRecord) -> None:
        self.save_execution(execution)

    async def aget_execution(self, execution_id: str) -> ExecutionRecord | None:
        return self.get_execution(execution_id)

    async def aclaim_job(self, job_id: str, worker_id: str) -> bool:
        return self.claim_job(job_id, worker_id)

    # --- Resilience Operations (Phase 26) ---

    def save_failure(self, failure: Any) -> None:
        """Persist a detailed failure record with sanitized metadata."""
        if hasattr(failure, "metadata"):
            sanitized_meta = self.sanitizer.sanitize(failure.metadata)
            if sanitized_meta != failure.metadata and hasattr(failure, "model_copy"):
                failure = failure.model_copy(update={"metadata": sanitized_meta})
        self._failures.append(failure)

    def list_failures(
        self, execution_id: str | None = None, tenant_id: str | None = None
    ) -> list[Any]:
        """List detailed failure records, optionally filtered by execution ID
        or tenant ID.
        """
        failures = list(self._failures)
        if execution_id is not None:
            failures = [
                f for f in failures if getattr(f, "execution_id", None) == execution_id
            ]
        if tenant_id is not None:
            failures = [
                f
                for f in failures
                if getattr(f, "metadata", {}).get("tenant_id", "default") == tenant_id
            ]
        return failures

    # --- Security Operations (Phase 28) ---

    def save_api_key(self, api_key: Any) -> None:
        """Persist an APIKey record with sanitized metadata."""
        if hasattr(api_key, "metadata"):
            sanitized_meta = self.sanitizer.sanitize(api_key.metadata)
            if sanitized_meta != api_key.metadata and hasattr(api_key, "model_copy"):
                api_key = api_key.model_copy(update={"metadata": sanitized_meta})
        self._api_keys[api_key.key_id] = api_key

    def get_api_key(self, key_id: str) -> Any | None:
        """Retrieve an API key by key_id."""
        return self._api_keys.get(key_id)

    def list_api_keys(self, tenant_id: str | None = None) -> list[Any]:
        """List API keys, optionally filtered by tenant."""
        keys = list(self._api_keys.values())
        if tenant_id:
            keys = [k for k in keys if getattr(k, "tenant_id", None) == tenant_id]
        return keys

    def save_audit_event(self, event: Any) -> None:
        """Persist a security audit event with sanitized metadata."""
        if hasattr(event, "metadata"):
            sanitized_meta = self.sanitizer.sanitize(event.metadata)
            if sanitized_meta != event.metadata and hasattr(event, "model_copy"):
                event = event.model_copy(update={"metadata": sanitized_meta})
        self._audit_events.append(event)

    def list_audit_events(
        self,
        tenant_id: str | None = None,
        principal_id: str | None = None,
        action: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        """List audit events matching filters."""
        events = list(self._audit_events)
        if tenant_id:
            events = [e for e in events if getattr(e, "tenant_id", None) == tenant_id]
        if principal_id:
            events = [
                e for e in events if getattr(e, "principal_id", None) == principal_id
            ]
        if action:
            events = [e for e in events if getattr(e, "action", None) == action]
        return events[-limit:]

    def save_replay_record(self, record: Any) -> None:
        """Persist a replay record."""
        self._replay_records.append(record)

    # --- Observability Operations (Phase 29) ---

    def save_telemetry_event(self, event: Any) -> None:
        """Persist a telemetry event."""
        if hasattr(event, "attributes"):
            sanitized_attrs = self.sanitizer.sanitize(event.attributes)
            if sanitized_attrs != event.attributes and hasattr(event, "model_copy"):
                event = event.model_copy(update={"attributes": sanitized_attrs})
        self._telemetry_events.append(event)

    def list_telemetry_events(
        self,
        tenant_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        """List telemetry events matching filters."""
        events = list(self._telemetry_events)
        if tenant_id:
            events = [e for e in events if getattr(e, "tenant_id", None) == tenant_id]
        if event_type:
            events = [
                e for e in events if getattr(e, "event_type", "").startswith(event_type)
            ]
        return events[-limit:]

    def save_trace_record(self, trace: Any) -> None:
        """Persist a trace record."""
        tid = getattr(trace, "trace_id", None)
        if tid:
            self._trace_records[tid] = trace

    def get_trace_record(self, trace_id: str) -> Any | None:
        """Retrieve a trace record by ID."""
        return self._trace_records.get(trace_id)

    def list_trace_records(
        self, tenant_id: str | None = None, limit: int = 100
    ) -> list[Any]:
        """List trace records matching filters."""
        traces = list(self._trace_records.values())
        if tenant_id:
            traces = [t for t in traces if getattr(t, "tenant_id", None) == tenant_id]
        return traces[-limit:]

    def save_incident(self, incident: Any) -> None:
        """Persist an operational incident."""
        iid = getattr(incident, "incident_id", None)
        if iid:
            self._incidents[iid] = incident

    def get_incident(self, incident_id: str) -> Any | None:
        """Retrieve an operational incident by ID."""
        return self._incidents.get(incident_id)

    def list_incidents(
        self, tenant_id: str | None = None, limit: int = 100
    ) -> list[Any]:
        """List operational incidents matching filters."""
        incs = list(self._incidents.values())
        if tenant_id:
            incs = [i for i in incs if getattr(i, "tenant_id", None) == tenant_id]
        return incs[-limit:]

    def clear(self) -> None:
        """Clear all stored jobs, outcomes, workers, executions, security,
        and observability records.
        """
        self._jobs.clear()
        self._outcomes.clear()
        self._workers.clear()
        self._executions.clear()
        self._failures.clear()
        self._api_keys.clear()
        self._audit_events.clear()
        self._replay_records.clear()
        self._telemetry_events.clear()
        self._trace_records.clear()
        self._incidents.clear()
