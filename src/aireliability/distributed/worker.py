"""Worker execution abstraction for running reliability jobs.

Provides an explicit, deterministic state machine for worker lifecycles,
heartbeats, registration, error handling, and timeout enforcement.
"""

import asyncio
import contextlib
import inspect
from datetime import UTC, datetime
from typing import Any

from aireliability.core.models import (
    EvaluationResult,
    ExecutionStatus,
    ExecutionTrace,
    FailureReport,
    FailureSeverity,
    RunResult,
)
from aireliability.core.protocols import Evaluator
from aireliability.distributed.models import (
    CorrelationContext,
    JobExecutionOutcome,
    JobStatus,
    PersistentWorkerRecord,
    ReliabilityJob,
    WorkerDescriptor,
    WorkerState,
    _generate_id,
    validate_worker_transition,
)
from aireliability.execution.runner import ReliabilityRunner
from aireliability.telemetry.sanitizer import SanitizationPolicy


class ReliabilityWorker:
    """Worker instance responsible for executing reliability jobs asynchronously."""

    def __init__(
        self,
        worker_id: str | None = None,
        *,
        execution_id: str | None = None,
        agent: Any = None,
        adapter: Any = None,
        evaluators: list[Evaluator] | None = None,
        telemetry_collector: Any | None = None,
        storage: Any | None = None,
        sanitizer: SanitizationPolicy | None = None,
        heartbeat_interval: float = 5.0,
    ) -> None:
        self.worker_id = worker_id or _generate_id("worker")
        self.execution_id = execution_id
        self.agent = agent
        self.adapter = adapter
        self.evaluators = list(evaluators or [])
        self.telemetry_collector = telemetry_collector
        self.storage = storage
        self.sanitizer = sanitizer or SanitizationPolicy()
        self.heartbeat_interval = heartbeat_interval

        self._state: WorkerState = WorkerState.IDLE
        self._current_job_id: str | None = None
        self._started_at: datetime = datetime.now(UTC)
        self._last_heartbeat: datetime = self._started_at
        self._jobs_completed = 0
        self._jobs_failed = 0
        self._error: str | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None

    @property
    def state(self) -> WorkerState:
        """Current lifecycle state of the worker."""
        return self._state

    def _set_state(self, new_state: WorkerState) -> None:
        validate_worker_transition(self._state, new_state)
        self._state = new_state
        self._sync_storage_worker()

    def describe(self) -> WorkerDescriptor:
        """Return a snapshot descriptor of this worker's state."""
        return WorkerDescriptor(
            worker_id=self.worker_id,
            state=self._state,
            current_job_id=self._current_job_id,
            started_at=self._started_at,
            jobs_completed=self._jobs_completed,
            jobs_failed=self._jobs_failed,
            error=self._error,
        )

    def to_record(self) -> PersistentWorkerRecord:
        """Convert worker state into a PersistentWorkerRecord."""
        return PersistentWorkerRecord(
            worker_id=self.worker_id,
            execution_id=self.execution_id,
            state=self._state,
            current_job_id=self._current_job_id,
            started_at=self._started_at,
            last_heartbeat=self._last_heartbeat,
            completed_jobs=self._jobs_completed,
            failed_jobs=self._jobs_failed,
        )

    def heartbeat(self) -> None:
        """Record a heartbeat timestamp and persist if storage is present."""
        self._last_heartbeat = datetime.now(UTC)
        self._sync_storage_worker()

    def register(self) -> None:
        """Register worker as IDLE and record initial heartbeat."""
        self._state = WorkerState.IDLE
        self._last_heartbeat = datetime.now(UTC)
        self._sync_storage_worker()

    def unregister(self) -> None:
        """Unregister worker and transition state to STOPPED."""
        self._set_state(WorkerState.STOPPED)
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()

    def _sync_storage_worker(self) -> None:
        if self.storage is not None and hasattr(self.storage, "save_worker"):
            with contextlib.suppress(Exception):
                self.storage.save_worker(self.to_record())

    async def run_job(self, job: ReliabilityJob) -> JobExecutionOutcome:
        """Execute a ReliabilityJob with timeouts, cancellations, and heartbeats."""
        self._set_state(WorkerState.RUNNING)
        self._current_job_id = job.job_id
        self.heartbeat()
        start_time = datetime.now(UTC)

        correlation = CorrelationContext(
            execution_id=job.execution_id,
            job_id=job.job_id,
            worker_id=self.worker_id,
            test_id=job.test_id,
            attempt=job.attempt,
        )

        try:
            if job.timeout_seconds and job.timeout_seconds > 0:
                outcome = await asyncio.wait_for(
                    self._execute_attempt(job, correlation),
                    timeout=job.timeout_seconds,
                )
            else:
                outcome = await self._execute_attempt(job, correlation)

            if outcome.status == JobStatus.COMPLETED:
                self._jobs_completed += 1
            else:
                self._jobs_failed += 1

            self._current_job_id = None
            self.heartbeat()
            self._set_state(WorkerState.IDLE)
            return outcome

        except TimeoutError:
            self._jobs_failed += 1
            self._current_job_id = None
            self.heartbeat()
            self._set_state(WorkerState.IDLE)
            completed_time = datetime.now(UTC)

            # Synthesize timeout failure run result
            dummy_trace = ExecutionTrace(
                test_id=job.test_id,
                input=job.test_case.input,
                output={"error": f"Job exceeded timeout of {job.timeout_seconds}s"},
                status=ExecutionStatus.FAILED,
                started_at=start_time,
                completed_at=completed_time,
                metadata={"timeout_seconds": job.timeout_seconds},
            )
            fail_report = FailureReport(
                trace_id=dummy_trace.trace_id,
                test_id=job.test_id,
                category="performance",
                type="timeout",
                severity=FailureSeverity.HIGH,
                message=f"Execution exceeded timeout limit ({job.timeout_seconds}s)",
            )
            timeout_result = RunResult(
                test=job.test_case,
                trace=dummy_trace,
                evaluations=[],
                failures=[fail_report],
                passed=False,
                metadata={"execution_id": job.execution_id, "job_id": job.job_id},
            )

            return JobExecutionOutcome(
                job_id=job.job_id,
                execution_id=job.execution_id,
                test_id=job.test_id,
                worker_id=self.worker_id,
                status=JobStatus.TIMED_OUT,
                attempt=job.attempt,
                run_result=timeout_result,
                started_at=start_time,
                completed_at=completed_time,
                error=f"Timeout of {job.timeout_seconds}s exceeded",
                error_type="TimeoutError",
                retryable=True,
            )

        except asyncio.CancelledError:
            self._set_state(WorkerState.STOPPED)
            self._current_job_id = None
            completed_time = datetime.now(UTC)
            return JobExecutionOutcome(
                job_id=job.job_id,
                execution_id=job.execution_id,
                test_id=job.test_id,
                worker_id=self.worker_id,
                status=JobStatus.CANCELLED,
                attempt=job.attempt,
                started_at=start_time,
                completed_at=completed_time,
                error="Job execution cancelled",
                error_type="CancelledError",
                retryable=False,
            )

        except Exception as exc:
            self._jobs_failed += 1
            self._set_state(WorkerState.FAILED)
            self._error = str(exc)
            self._current_job_id = None
            completed_time = datetime.now(UTC)
            return JobExecutionOutcome(
                job_id=job.job_id,
                execution_id=job.execution_id,
                test_id=job.test_id,
                worker_id=self.worker_id,
                status=JobStatus.FAILED,
                attempt=job.attempt,
                started_at=start_time,
                completed_at=completed_time,
                error=str(exc),
                error_type=type(exc).__name__,
                retryable=True,
            )

    async def _execute_attempt(
        self, job: ReliabilityJob, correlation: CorrelationContext
    ) -> JobExecutionOutcome:
        """Internal execution helper running synchronous or asynchronous agent."""
        start_time = datetime.now(UTC)

        runner = ReliabilityRunner(
            agent=self.agent,
            adapter=self.adapter,
            evaluators=self.evaluators,
            suppress_agent_exceptions=True,
            telemetry_collector=self.telemetry_collector,
        )

        if self.adapter is not None and hasattr(self.adapter, "aexecute"):
            if self.agent is not None:
                trace = await self.adapter.aexecute(self.agent, job.test_case)
            else:
                trace = await self.adapter.aexecute(test_case=job.test_case)
            eval_results = []
            for ev in self.evaluators:
                try:
                    eval_results.append(ev.evaluate(trace, job.test_case))
                except Exception as ex:
                    eval_results.append(
                        EvaluationResult(
                            evaluator=getattr(ev, "name", str(ev)),
                            passed=False,
                            message=f"Evaluator error: {ex}",
                        )
                    )
            failures = runner.failure_analyzer.analyze_trace_failures(
                trace=trace,
                evaluation_results=eval_results,
                test_id=job.test_id,
            )
            run_result = RunResult(
                test=job.test_case,
                trace=trace,
                evaluations=eval_results,
                failures=failures,
                passed=len(failures) == 0,
                metadata={
                    "execution_id": job.execution_id,
                    "job_id": job.job_id,
                    "worker_id": self.worker_id,
                },
            )
            if self.telemetry_collector is not None:
                try:
                    from aireliability.telemetry.builder import TelemetryBuilder

                    t_builder = TelemetryBuilder(sanitizer=self.sanitizer)
                    t_trace = t_builder.build_trace(run_result, trace_id=trace.trace_id)
                    self.telemetry_collector.record(t_trace)
                except Exception:
                    pass
        else:
            if inspect.iscoroutinefunction(self.agent):
                raw_out = await self.agent(job.test_case.input)
                trace = ExecutionTrace(
                    test_id=job.test_id,
                    input=job.test_case.input,
                    output=raw_out,
                    status=ExecutionStatus.COMPLETED,
                    started_at=start_time,
                    completed_at=datetime.now(UTC),
                )
                eval_results = []
                for ev in self.evaluators:
                    try:
                        eval_results.append(ev.evaluate(trace, job.test_case))
                    except Exception as ex:
                        eval_results.append(
                            EvaluationResult(
                                evaluator=getattr(ev, "name", str(ev)),
                                passed=False,
                                message=f"Evaluator error: {ex}",
                            )
                        )
                failures = runner.failure_analyzer.analyze_trace_failures(
                    trace=trace,
                    evaluation_results=eval_results,
                    test_id=job.test_id,
                )
                run_result = RunResult(
                    test=job.test_case,
                    trace=trace,
                    evaluations=eval_results,
                    failures=failures,
                    passed=len(failures) == 0,
                    metadata={
                        "execution_id": job.execution_id,
                        "job_id": job.job_id,
                        "worker_id": self.worker_id,
                    },
                )
            else:
                run_result = await asyncio.to_thread(runner.run, job.test_case)
                run_result = run_result.model_copy(
                    update={
                        "metadata": {
                            **run_result.metadata,
                            "execution_id": job.execution_id,
                            "job_id": job.job_id,
                            "worker_id": self.worker_id,
                        }
                    }
                )

        completed_time = datetime.now(UTC)
        is_success = bool(run_result.passed)

        error_msg = None
        error_type = None
        if not is_success:
            if isinstance(run_result.trace.output, dict):
                error_msg = run_result.trace.output.get("error")
                error_type = run_result.trace.output.get("error_type")
            if not error_msg and run_result.failures:
                error_msg = run_result.failures[0].message
                error_type = run_result.failures[0].type

        return JobExecutionOutcome(
            job_id=job.job_id,
            execution_id=job.execution_id,
            test_id=job.test_id,
            worker_id=self.worker_id,
            status=JobStatus.COMPLETED if is_success else JobStatus.FAILED,
            attempt=job.attempt,
            run_result=run_result,
            started_at=start_time,
            completed_at=completed_time,
            error=error_msg,
            error_type=error_type,
            retryable=not is_success,
        )
