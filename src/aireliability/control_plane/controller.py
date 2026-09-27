"""High-level ControlPlane orchestrator tying queues, retries, and workers."""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from aireliability.control_plane.cancellation import CancellationCoordinator
from aireliability.control_plane.errors import (
    JobNotFoundError,
)
from aireliability.control_plane.models import (
    ControlPlaneConfig,
    JobPriority,
    QueueState,
    ScheduledJob,
    _generate_control_plane_id,
)
from aireliability.control_plane.policies import get_scheduling_policy
from aireliability.control_plane.queue import InMemoryJobQueue, JobQueue
from aireliability.control_plane.scheduler import JobScheduler
from aireliability.control_plane.worker_manager import WorkerManager
from aireliability.core.models import TestCase
from aireliability.core.protocols import Evaluator
from aireliability.distributed.aggregator import (
    DistributedExecutionSummary,
    ResultAggregator,
)
from aireliability.distributed.metrics import DistributedMetrics
from aireliability.distributed.models import (
    ExecutionRecord,
    ExecutionRecoverySummary,
    ExecutionStatusRecord,
    JobStatus,
    ReliabilityJob,
)
from aireliability.distributed.storage import (
    DistributedPersistenceBackend,
    InMemoryDistributedStorage,
)
from aireliability.distributed.worker import ReliabilityWorker
from aireliability.resilience.manager import ResilienceManager
from aireliability.telemetry.sanitizer import SanitizationPolicy

logger = logging.getLogger(__name__)


class ControlPlane:
    """Production-grade, provider-neutral control plane coordinating execution."""

    def __init__(
        self,
        *,
        agent: Any = None,
        adapter: Any = None,
        evaluators: list[Evaluator] | None = None,
        storage: DistributedPersistenceBackend | None = None,
        queue: JobQueue | None = None,
        config: ControlPlaneConfig | None = None,
        metrics: DistributedMetrics | None = None,
        telemetry_collector: Any | None = None,
        sanitizer: SanitizationPolicy | None = None,
        resilience_manager: ResilienceManager | None = None,
        governance_manager: Any | None = None,
        gateway: Any | None = None,
        observability_manager: Any | None = None,
    ) -> None:
        from aireliability.observability.manager import ObservabilityManager
        from aireliability.security.gateway import SecurityGateway
        from aireliability.tenancy.governance import ResourceGovernanceManager

        self.agent = agent
        self.adapter = adapter
        self.evaluators = list(evaluators or [])
        self.config = config or ControlPlaneConfig()
        self.storage = storage or InMemoryDistributedStorage()
        self.sanitizer = sanitizer or SanitizationPolicy()
        self.metrics = metrics or DistributedMetrics()
        self.telemetry_collector = telemetry_collector
        self.resilience = resilience_manager or ResilienceManager(
            sanitizer=self.sanitizer
        )
        self.governance: ResourceGovernanceManager = (
            governance_manager
            or ResourceGovernanceManager(
                storage=self.storage,
                sanitizer=self.sanitizer,
            )
        )
        self.gateway: SecurityGateway = gateway or SecurityGateway(
            storage=self.storage,
            sanitizer=self.sanitizer,
            rate_limiter=self.governance.rate_limiter,
        )
        self.observability: ObservabilityManager = (
            observability_manager
            or ObservabilityManager(
                sanitizer=self.sanitizer,
                resilience_manager=self.resilience,
                resource_governor=self.governance,
                security_gateway=self.gateway,
                control_plane=self,
                storage_backend=self.storage,
            )
        )

        # Initialize internal subsystems
        policy = get_scheduling_policy(self.config.scheduling_policy)
        self.queue = queue or InMemoryJobQueue(default_policy=policy)
        self.worker_manager = WorkerManager(
            storage=self.storage,
            heartbeat_timeout_seconds=self.config.heartbeat_timeout_seconds,
            default_capacity=self.config.worker_default_capacity,
        )
        self.cancellation = CancellationCoordinator()

        # Initialize scheduler with resilience and governance checks
        self.scheduler = JobScheduler(
            queue=self.queue,
            worker_manager=self.worker_manager,
            policy=policy,
            storage=self.storage,
            metrics=self.metrics,
            dispatch_handler=self._dispatch_job,
            worker_health_filter=self.resilience.is_worker_eligible,
        )

        self._active_worker_instances: dict[str, ReliabilityWorker] = {}
        self._aggregators: dict[str, ResultAggregator] = {}
        self._execution_completion_events: dict[str, asyncio.Event] = {}

    async def start(self) -> None:
        """Start the control plane and background scheduler."""
        await self.scheduler.start()

    async def stop(self) -> None:
        """Gracefully stop the scheduler and flush state."""
        await self.scheduler.stop()
        if self.telemetry_collector is not None:
            if hasattr(self.telemetry_collector, "aflush"):
                with contextlib.suppress(Exception):
                    await self.telemetry_collector.aflush()
            elif hasattr(self.telemetry_collector, "flush"):
                with contextlib.suppress(Exception):
                    self.telemetry_collector.flush()

    async def register_worker(
        self,
        worker_id: str,
        capacity: int | None = None,
        worker_instance: ReliabilityWorker | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register a worker into the control plane."""
        await self.worker_manager.register_worker(
            worker_id=worker_id,
            capacity=capacity,
            metadata=metadata,
        )
        if worker_instance is not None:
            self._active_worker_instances[worker_id] = worker_instance

    async def unregister_worker(self, worker_id: str) -> None:
        """Unregister a worker."""
        await self.worker_manager.unregister_worker(worker_id)
        self._active_worker_instances.pop(worker_id, None)

    async def submit_job(
        self,
        test_case: TestCase,
        *,
        execution_id: str | None = None,
        priority: JobPriority | str = JobPriority.NORMAL,
        delay_seconds: float = 0.0,
        max_retries: int | None = None,
        timeout_seconds: float | None = 60.0,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ScheduledJob:
        """Submit a new test case into the control plane queue."""
        if isinstance(priority, str):
            priority_val = JobPriority.from_string(priority)
        else:
            priority_val = priority

        now = datetime.now(UTC)
        scheduled_at = (
            now + timedelta(seconds=delay_seconds) if delay_seconds > 0 else None
        )
        exec_id = execution_id or _generate_control_plane_id("exec")
        retries = (
            max_retries
            if max_retries is not None
            else self.config.default_retry_policy.max_retries
        )

        # Extract security credentials before metadata sanitization
        raw_meta = metadata or {}
        raw_api_key = raw_meta.get("api_key")
        raw_bearer_token = raw_meta.get("bearer_token")

        # Build sanitized metadata and resolve tenant context
        from aireliability.observability.context import get_current_context

        obs_ctx = get_current_context()
        sanitized_meta = self.sanitizer.sanitize(raw_meta)
        tenant_id = sanitized_meta.get("tenant_id") or (
            obs_ctx.tenant_id
            if obs_ctx and obs_ctx.tenant_id != "default"
            else "default"
        )
        project_id = sanitized_meta.get("project_id") or (
            obs_ctx.project_id
            if obs_ctx and obs_ctx.project_id != "default"
            else "default"
        )
        namespace = sanitized_meta.get("namespace") or (
            obs_ctx.namespace
            if obs_ctx and obs_ctx.namespace != "default"
            else "default"
        )
        sanitized_meta["tenant_id"] = tenant_id
        sanitized_meta["project_id"] = project_id
        sanitized_meta["namespace"] = namespace

        # Phase 28: Security Gateway Request Verification (before resource consumption)
        from aireliability.security.models import GatewayRequest

        # Distinguish between system aireliability API keys vs arbitrary
        # agent metadata keys
        is_airel_key = bool(raw_api_key and str(raw_api_key).startswith("airel_"))
        sec_api_key = raw_api_key if is_airel_key else None

        sec_req = GatewayRequest(
            action="jobs.submit",
            tenant_id=tenant_id,
            project_id=project_id,
            namespace=namespace,
            api_key=sec_api_key,
            bearer_token=raw_bearer_token,
            payload={"test_id": test_case.id, "execution_id": exec_id},
        )
        gw_resp = self.gateway.handle_request(sec_req)
        if not gw_resp.allowed:
            from aireliability.security.errors import SecurityError

            raise SecurityError(gw_resp.reason or "Security gateway rejected request.")

        # Phase 27: Resource Governance Check before admission
        await self.governance.check_admission(
            tenant_id=tenant_id,
            project_id=project_id,
            namespace=namespace,
            load_shedder=getattr(self.resilience, "load_shedder", None),
        )

        job = ScheduledJob(
            execution_id=exec_id,
            test_case=test_case,
            priority=priority_val,
            queue_state=QueueState.CREATED,
            job_status=JobStatus.PENDING,
            attempt=1,
            max_retries=retries,
            timeout_seconds=timeout_seconds,
            created_at=now,
            scheduled_at=scheduled_at,
            tags=tags or [],
            metadata=sanitized_meta,
        )

        # Register in cancellation coordinator
        self.cancellation.register_job(job.job_id)

        # Persist to storage backend if available
        if self.storage is not None:
            rel_job = ReliabilityJob(
                job_id=job.job_id,
                execution_id=job.execution_id,
                test_case=job.test_case,
                priority=int(job.priority),
                attempt=job.attempt,
                max_retries=job.max_retries,
                timeout_seconds=job.timeout_seconds,
                status=JobStatus.PENDING,
                metadata=job.metadata,
            )
            self.storage.save_job(rel_job)

        # Ensure at least one worker is available if none registered yet
        workers = await self.worker_manager.list_workers()
        if not workers:
            await self.register_worker(
                "cp_worker_0", capacity=self.config.worker_default_capacity
            )

        # Enqueue job
        enqueued = await self.queue.enqueue(job)
        await self.governance.quota_manager.record_job_enqueued(tenant_id)
        if self.metrics:
            self.metrics.record_job_created(exec_id)
            if hasattr(self.metrics, "record_tenant_job"):
                self.metrics.record_tenant_job(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    namespace=namespace,
                )

        # Phase 29: Observability event recording
        if hasattr(self, "observability") and self.observability is not None:
            self.observability.events.record_event(
                event_type="job.submitted",
                tenant_id=tenant_id,
                project_id=project_id,
                namespace=namespace,
                execution_id=exec_id,
                job_id=job.job_id,
                attributes={"test_id": test_case.id, "priority": str(priority_val)},
            )

        return enqueued

    async def cancel_job(self, job_id: str) -> ScheduledJob:
        """Cancel a queued, scheduled, or running job."""
        job = await self.queue.get(job_id)
        if job is None:
            # Check storage if not in memory queue
            if self.storage is not None:
                rel_job = self.storage.get_job(job_id)
                if rel_job is not None:
                    job = ScheduledJob(
                        job_id=rel_job.job_id,
                        execution_id=rel_job.execution_id,
                        test_case=rel_job.test_case,
                        priority=JobPriority(rel_job.priority)
                        if rel_job.priority in (0, 1, 2, 3)
                        else JobPriority.NORMAL,
                        queue_state=QueueState(rel_job.status.value)
                        if rel_job.status.value in QueueState.__members__.values()
                        else QueueState.CANCELLED,
                        job_status=rel_job.status,
                        attempt=rel_job.attempt,
                        max_retries=rel_job.max_retries,
                        metadata=rel_job.metadata,
                    )
            if job is None:
                raise JobNotFoundError(f"Job '{job_id}' not found.")

        updated = self.cancellation.request_cancellation(job)
        await self.queue.update(updated)

        # Sync storage
        if self.storage is not None:
            with contextlib.suppress(Exception):
                self.storage.update_job(job_id, status=JobStatus.CANCELLED)

        return updated

    async def get_job(self, job_id: str) -> ScheduledJob | None:
        """Retrieve a job by ID from queue or storage."""
        job = await self.queue.get(job_id)
        if job is not None:
            return job
        if self.storage is not None:
            rel = self.storage.get_job(job_id)
            if rel is not None:
                return ScheduledJob(
                    job_id=rel.job_id,
                    execution_id=rel.execution_id,
                    test_case=rel.test_case,
                    priority=JobPriority(rel.priority)
                    if rel.priority in (0, 1, 2, 3)
                    else JobPriority.NORMAL,
                    queue_state=QueueState.COMPLETED
                    if rel.status == JobStatus.COMPLETED
                    else QueueState.QUEUED,
                    job_status=rel.status,
                    attempt=rel.attempt,
                    max_retries=rel.max_retries,
                    metadata=rel.metadata,
                )
        return None

    async def list_jobs(
        self,
        execution_id: str | None = None,
        queue_state: QueueState | None = None,
    ) -> list[ScheduledJob]:
        """List jobs matching filters."""
        return await self.queue.list_jobs(
            execution_id=execution_id, queue_state=queue_state
        )

    async def _dispatch_job(self, job: ScheduledJob, worker_id: str) -> None:
        """Internal dispatch execution handler."""
        # Check cancellation before dispatching
        if self.cancellation.is_cancelled(job.job_id):
            return

        worker = self._active_worker_instances.get(worker_id)
        if worker is None:
            # Instantiate worker dynamically if not already registered
            worker = ReliabilityWorker(
                worker_id=worker_id,
                execution_id=job.execution_id,
                agent=self.agent,
                adapter=self.adapter,
                evaluators=self.evaluators,
                telemetry_collector=self.telemetry_collector,
                storage=self.storage,
                sanitizer=self.sanitizer,
            )
            worker.register()
            self._active_worker_instances[worker_id] = worker

        # Update job to running in queue
        running_job = job.model_copy(
            update={
                "queue_state": QueueState.RUNNING,
                "job_status": JobStatus.RUNNING,
                "started_at": datetime.now(UTC),
            }
        )
        await self.queue.update(running_job)
        tenant_id = (
            job.metadata.get("tenant_id", "default") if job.metadata else "default"
        )
        await self.governance.quota_manager.record_job_dispatched(tenant_id)

        rel_job = ReliabilityJob(
            job_id=job.job_id,
            execution_id=job.execution_id,
            test_case=job.test_case,
            priority=int(job.priority),
            attempt=job.attempt,
            max_retries=job.max_retries,
            timeout_seconds=job.timeout_seconds,
            status=JobStatus.RUNNING,
            assigned_worker_id=worker_id,
            metadata=job.metadata,
        )

        outcome = await worker.run_job(rel_job)
        await self.governance.quota_manager.release_concurrency(tenant_id)

        # Safely extract token consumption if available
        tokens_used = 0
        if outcome.run_result is not None and getattr(
            outcome.run_result, "tokens_used", None
        ):
            tokens_used = outcome.run_result.tokens_used
        elif outcome.metadata.get("tokens_used"):
            tokens_used = int(outcome.metadata["tokens_used"])
        if tokens_used:
            await self.governance.quota_manager.record_token_usage(
                tenant_id, tokens_used
            )

        # Save outcome to storage
        if self.storage is not None:
            self.storage.save_outcome(outcome)

        # Track in aggregator
        if job.execution_id in self._aggregators:
            self._aggregators[job.execution_id].add_outcome(outcome)

        # Handle completion or retry with resilience tracking
        if outcome.status == JobStatus.COMPLETED:
            await self.resilience.record_success(worker_id=worker_id)
            completed_job = running_job.model_copy(
                update={
                    "queue_state": QueueState.COMPLETED,
                    "job_status": JobStatus.COMPLETED,
                    "completed_at": datetime.now(UTC),
                }
            )
            await self.queue.update(completed_job)
            self.cancellation.unregister(job.job_id)
            if self.metrics:
                self.metrics.record_job_completed(status="completed")
                dur_s = (outcome.duration_ms / 1000.0) if outcome.duration_ms else 0.0
                if hasattr(self.metrics, "record_tenant_duration") and dur_s > 0:
                    self.metrics.record_tenant_duration(tenant_id, dur_s)

            if hasattr(self, "observability") and self.observability is not None:
                self.observability.events.record_event(
                    event_type="job.completed",
                    tenant_id=tenant_id,
                    execution_id=job.execution_id,
                    job_id=job.job_id,
                    worker_id=worker_id,
                    duration_ms=outcome.duration_ms,
                    status="completed",
                )

        else:
            # Record failure in ResilienceManager
            fail_record = await self.resilience.record_failure(
                exc=outcome.error,
                execution_id=job.execution_id,
                job_id=job.job_id,
                worker_id=worker_id,
                attempt=job.attempt,
                metadata=job.metadata,
            )
            # Persist failure record if storage supports save_failure
            if self.storage is not None and hasattr(self.storage, "save_failure"):
                self.storage.save_failure(fail_record)

            if self.metrics:
                self.metrics.record_failure_metric(
                    failure_type=fail_record.failure_type.value,
                    severity=fail_record.severity.value,
                )

            if hasattr(self, "observability") and self.observability is not None:
                self.observability.events.record_event(
                    event_type="job.failed",
                    tenant_id=tenant_id,
                    execution_id=job.execution_id,
                    job_id=job.job_id,
                    worker_id=worker_id,
                    duration_ms=outcome.duration_ms,
                    status="failed",
                    severity="ERROR",
                    attributes={
                        "error": str(outcome.error),
                        "failure_type": fail_record.failure_type.value,
                        "retryable": outcome.retryable,
                    },
                )

            # Check if retryable
            if (
                outcome.retryable
                and fail_record.retryable
                and job.attempt <= job.max_retries
                and not self.cancellation.is_cancelled(job.job_id)
            ):
                # Compute retry backoff
                next_attempt = job.attempt + 1
                retry_policy = self.config.default_retry_policy
                delay_sec = retry_policy.compute_delay(next_attempt)
                scheduled_retry_time = datetime.now(UTC) + timedelta(seconds=delay_sec)

                retrying_job = running_job.model_copy(
                    update={
                        "queue_state": QueueState.RETRYING,
                        "job_status": JobStatus.RETRYING,
                        "attempt": next_attempt,
                        "scheduled_at": scheduled_retry_time,
                        "assigned_worker_id": None,
                        "metadata": {
                            **job.metadata,
                            f"attempt_{job.attempt}_error": outcome.error,
                            f"attempt_{job.attempt}_status": outcome.status.value,
                            f"attempt_{job.attempt}_category": (
                                fail_record.failure_type.value
                            ),
                        },
                    }
                )
                await self.queue.update(retrying_job)
                if self.storage is not None:
                    self.storage.update_job(
                        job.job_id,
                        status=JobStatus.RETRYING,
                        attempt=next_attempt,
                    )
                if self.metrics:
                    self.metrics.record_job_retry()
            else:
                # Terminal failure
                failed_job = running_job.model_copy(
                    update={
                        "queue_state": QueueState.FAILED,
                        "job_status": outcome.status,
                        "completed_at": datetime.now(UTC),
                    }
                )
                await self.queue.update(failed_job)
                self.cancellation.unregister(job.job_id)
                if self.metrics:
                    self.metrics.record_job_failed(
                        error_type=outcome.error_type or "JobFailed"
                    )

    async def execute_execution(
        self,
        test_cases: list[TestCase],
        *,
        execution_id: str | None = None,
        priority: JobPriority = JobPriority.NORMAL,
        poll_interval: float = 0.05,
        timeout: float = 300.0,
    ) -> DistributedExecutionSummary:
        """Submit a collection of test cases and run the scheduler until completion."""
        exec_id = execution_id or _generate_control_plane_id("exec")
        expected_order = [tc.id for tc in test_cases]
        aggregator = ResultAggregator(execution_id=exec_id)
        self._aggregators[exec_id] = aggregator

        # Save initial execution record
        if self.storage is not None and hasattr(self.storage, "save_execution"):
            rec = ExecutionRecord(
                execution_id=exec_id,
                status=ExecutionStatusRecord.RUNNING,
                started_at=datetime.now(UTC),
                total_jobs=len(test_cases),
            )
            self.storage.save_execution(rec)

        # Submit all jobs
        submitted_jobs: list[ScheduledJob] = []
        for tc in test_cases:
            j = await self.submit_job(
                tc,
                execution_id=exec_id,
                priority=priority,
            )
            submitted_jobs.append(j)

        # Ensure workers exist
        worker_count = min(self.config.max_concurrency, len(test_cases))
        for w_idx in range(max(1, worker_count)):
            w_id = f"cp_worker_{w_idx}"
            if await self.worker_manager.get_worker(w_id) is None:
                await self.register_worker(
                    w_id, capacity=self.config.worker_default_capacity
                )

        # Start scheduler if not running
        await self.start()

        # Wait until all jobs for this execution reach terminal state
        start_time = datetime.now(UTC)
        while True:
            jobs = await self.list_jobs(execution_id=exec_id)
            all_terminal = all(
                j.queue_state
                in (QueueState.COMPLETED, QueueState.FAILED, QueueState.CANCELLED)
                for j in jobs
            )
            if all_terminal and len(jobs) == len(test_cases):
                break

            elapsed = (datetime.now(UTC) - start_time).total_seconds()
            if elapsed > timeout:
                raise TimeoutError(f"Execution {exec_id} timed out after {timeout}s")

            await asyncio.sleep(poll_interval)

        summary = aggregator.aggregate(expected_order=expected_order)

        # Update execution record
        if self.storage is not None and hasattr(self.storage, "save_execution"):
            rec = ExecutionRecord(
                execution_id=exec_id,
                status=(
                    ExecutionStatusRecord.COMPLETED
                    if summary.all_passed
                    else ExecutionStatusRecord.FAILED
                ),
                started_at=start_time,
                completed_at=datetime.now(UTC),
                total_jobs=summary.total_jobs,
                completed_jobs=summary.completed_jobs,
                failed_jobs=summary.failed_jobs,
                timed_out_jobs=summary.timed_out_jobs,
                cancelled_jobs=summary.cancelled_jobs,
                retry_count=summary.total_retries,
            )
            self.storage.save_execution(rec)

        return summary

    async def recover_stale_workers(
        self,
        execution_id: str | None = None,
        stale_timeout_seconds: float = 30.0,
    ) -> ExecutionRecoverySummary:
        """Detect stale workers and recover their unfinished jobs."""
        if hasattr(self.storage, "recover_execution") and execution_id:
            summary = self.storage.recover_execution(
                execution_id, stale_timeout_seconds=stale_timeout_seconds
            )
            # Requeue recovered jobs into in-memory queue
            for job_id in summary.requeued_jobs:
                rel_job = self.storage.get_job(job_id)
                if rel_job is not None:
                    job = ScheduledJob(
                        job_id=rel_job.job_id,
                        execution_id=rel_job.execution_id,
                        test_case=rel_job.test_case,
                        priority=JobPriority(rel_job.priority)
                        if rel_job.priority in (0, 1, 2, 3)
                        else JobPriority.NORMAL,
                        queue_state=QueueState.QUEUED,
                        job_status=JobStatus.PENDING,
                        attempt=rel_job.attempt,
                        max_retries=rel_job.max_retries,
                        metadata=rel_job.metadata,
                    )
                    await self.queue.enqueue(job)
            return summary

        # Fallback empty summary
        return ExecutionRecoverySummary(
            execution_id=execution_id or "",
            recovered_jobs=[],
            already_completed_jobs=[],
            stale_workers=[],
            requeued_jobs=[],
            failed_recovery_jobs=[],
        )
