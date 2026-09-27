"""Asynchronous and concurrent execution runner for AI reliability testing.

Provides first-class async execution, bounded concurrency, per-test timeouts,
automated retries with provenance tracking, persistent storage integration,
and execution resumption.
"""

import asyncio
import contextlib
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from aireliability.core.models import RunResult, TestCase
from aireliability.core.protocols import Evaluator
from aireliability.distributed.aggregator import (
    DistributedExecutionSummary,
    ResultAggregator,
)
from aireliability.distributed.models import (
    ExecutionRecord,
    ExecutionStatusRecord,
    JobStatus,
    ReliabilityJob,
    _generate_id,
)
from aireliability.distributed.storage import (
    DistributedPersistenceBackend,
    InMemoryDistributedStorage,
)
from aireliability.distributed.worker import ReliabilityWorker
from aireliability.telemetry.sanitizer import SanitizationPolicy


class AsyncReliabilityRunner:
    """Asynchronous and concurrent runner executing tests over worker pools."""

    def __init__(
        self,
        agent: Any = None,
        evaluators: Sequence[Evaluator] | None = None,
        *,
        adapter: Any = None,
        max_concurrency: int = 5,
        test_timeout_seconds: float | None = 60.0,
        max_retries: int = 0,
        telemetry_collector: Any | None = None,
        storage: DistributedPersistenceBackend | None = None,
        sanitizer: SanitizationPolicy | None = None,
    ) -> None:
        """Initialize AsyncReliabilityRunner.

        Args:
            agent: The AI agent or callable to run.
            evaluators: Evaluators/expectations to run on each execution.
            adapter: Optional ExecutionAdapter.
            max_concurrency: Maximum number of concurrent worker tasks (default: 5).
            test_timeout_seconds: Maximum time allowed per individual test case.
            max_retries: Number of retries permitted for failed attempts (default: 0).
            telemetry_collector: Optional sync or async telemetry collector.
            storage: Optional persistence backend for jobs and outcomes.
            sanitizer: Optional sanitization policy for redacting credentials.
        """
        if agent is None and adapter is None:
            raise ValueError(
                "Either agent or adapter must be provided to AsyncReliabilityRunner."
            )
        if max_concurrency < 1:
            raise ValueError(f"max_concurrency must be >= 1, got {max_concurrency}")

        self.agent = agent
        self.adapter = adapter
        self.evaluators = list(evaluators or [])
        self.max_concurrency = max_concurrency
        self.test_timeout_seconds = test_timeout_seconds
        self.max_retries = max_retries
        self.telemetry_collector = telemetry_collector
        self.storage = storage or InMemoryDistributedStorage()
        self.sanitizer = sanitizer or SanitizationPolicy()

    async def execute(self, test_case: TestCase) -> RunResult:
        """Asynchronously execute a single test case."""
        summary = await self.execute_many([test_case])
        if summary.results:
            return summary.results[0]
        # Return fallback failed result if job failed without producing RunResult
        outcome = summary.outcomes[0]
        if outcome.run_result:
            return outcome.run_result
        raise RuntimeError(f"Test execution failed: {outcome.error}")

    async def aexecute(self, test_case: TestCase) -> RunResult:
        """Alias for execute() to adhere to async naming conventions."""
        return await self.execute(test_case)

    async def execute_many(
        self,
        test_cases: Sequence[TestCase],
        *,
        execution_id: str | None = None,
    ) -> DistributedExecutionSummary:
        """Execute a collection of test cases concurrently with bounded concurrency.

        Args:
            test_cases: Sequence of test cases to evaluate.
            execution_id: Optional correlation execution ID.

        Returns:
            DistributedExecutionSummary with deterministically ordered RunResults.
        """
        exec_id = execution_id or _generate_id("exec")
        expected_order = [tc.id for tc in test_cases]
        aggregator = ResultAggregator(execution_id=exec_id)
        semaphore = asyncio.Semaphore(self.max_concurrency)

        # Create execution record
        exec_record = ExecutionRecord(
            execution_id=exec_id,
            status=ExecutionStatusRecord.RUNNING,
            started_at=datetime.now(UTC),
            total_jobs=len(test_cases),
        )
        if hasattr(self.storage, "save_execution"):
            self.storage.save_execution(exec_record)

        # Create jobs
        jobs = [
            ReliabilityJob(
                execution_id=exec_id,
                test_case=tc,
                max_retries=self.max_retries,
                timeout_seconds=self.test_timeout_seconds,
            )
            for tc in test_cases
        ]

        for job in jobs:
            self.storage.save_job(job)

        async def worker_task(job: ReliabilityJob, worker_idx: int) -> None:
            async with semaphore:
                worker = ReliabilityWorker(
                    worker_id=f"worker_{worker_idx}",
                    execution_id=exec_id,
                    agent=self.agent,
                    adapter=self.adapter,
                    evaluators=self.evaluators,
                    telemetry_collector=self.telemetry_collector,
                    storage=self.storage,
                    sanitizer=self.sanitizer,
                )
                worker.register()

                current_attempt = 1
                while True:
                    attempt_job = job.model_copy(update={"attempt": current_attempt})
                    outcome = await worker.run_job(attempt_job)
                    self.storage.save_outcome(outcome)
                    aggregator.add_outcome(outcome)

                    # Check retry conditions
                    should_retry = (
                        outcome.status != JobStatus.COMPLETED
                        and outcome.retryable
                        and current_attempt <= self.max_retries
                    )
                    if should_retry:
                        current_attempt += 1
                        continue
                    break
                worker.unregister()

        tasks = [
            asyncio.create_task(worker_task(job, idx % self.max_concurrency))
            for idx, job in enumerate(jobs)
        ]

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=False)

        # Flush telemetry if supported
        if self.telemetry_collector is not None:
            if hasattr(self.telemetry_collector, "aflush"):
                with contextlib.suppress(Exception):
                    await self.telemetry_collector.aflush()
            elif hasattr(self.telemetry_collector, "flush"):
                with contextlib.suppress(Exception):
                    self.telemetry_collector.flush()

        summary = aggregator.aggregate(expected_order=expected_order)

        # Update execution record on completion
        if hasattr(self.storage, "save_execution"):
            exec_record = exec_record.model_copy(
                update={
                    "status": (
                        ExecutionStatusRecord.COMPLETED
                        if summary.all_passed
                        else ExecutionStatusRecord.FAILED
                    ),
                    "completed_at": datetime.now(UTC),
                    "completed_jobs": summary.completed_jobs,
                    "failed_jobs": summary.failed_jobs,
                    "timed_out_jobs": summary.timed_out_jobs,
                    "cancelled_jobs": summary.cancelled_jobs,
                    "retry_count": summary.total_retries,
                }
            )
            self.storage.save_execution(exec_record)

        return summary

    async def resume_execution(
        self, execution_id: str, stale_timeout_seconds: float = 30.0
    ) -> DistributedExecutionSummary:
        """Resume an interrupted execution by identifying unfinished/failed jobs."""
        if hasattr(self.storage, "recover_execution"):
            self.storage.recover_execution(
                execution_id, stale_timeout_seconds=stale_timeout_seconds
            )

        all_jobs = self.storage.list_jobs(execution_id=execution_id)
        if not all_jobs:
            raise KeyError(f"Execution '{execution_id}' has no jobs in storage.")

        # Re-run jobs that are still PENDING, FAILED, or TIMED_OUT
        unfinished_jobs = [
            j
            for j in all_jobs
            if j.status in (JobStatus.PENDING, JobStatus.FAILED, JobStatus.TIMED_OUT)
        ]

        expected_order = [j.test_id for j in all_jobs]
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def worker_task(job: ReliabilityJob, worker_idx: int) -> None:
            async with semaphore:
                worker = ReliabilityWorker(
                    worker_id=f"worker_resume_{worker_idx}",
                    execution_id=execution_id,
                    agent=self.agent,
                    adapter=self.adapter,
                    evaluators=self.evaluators,
                    telemetry_collector=self.telemetry_collector,
                    storage=self.storage,
                    sanitizer=self.sanitizer,
                )
                worker.register()
                current_attempt = job.attempt
                while True:
                    attempt_job = job.model_copy(update={"attempt": current_attempt})
                    outcome = await worker.run_job(attempt_job)
                    self.storage.save_outcome(outcome)
                    if (
                        outcome.status != JobStatus.COMPLETED
                        and outcome.retryable
                        and current_attempt <= self.max_retries
                    ):
                        current_attempt += 1
                        continue
                    break
                worker.unregister()

        if unfinished_jobs:
            tasks = [
                asyncio.create_task(worker_task(job, idx % self.max_concurrency))
                for idx, job in enumerate(unfinished_jobs)
            ]
            await asyncio.gather(*tasks, return_exceptions=False)

        # Rebuild full execution state from storage
        aggregator = ResultAggregator.from_storage(self.storage, execution_id)
        summary = aggregator.aggregate(expected_order=expected_order)

        if hasattr(self.storage, "get_execution") and hasattr(
            self.storage, "save_execution"
        ):
            rec = self.storage.get_execution(execution_id)
            if rec is not None:
                updated_rec = rec.model_copy(
                    update={
                        "status": (
                            ExecutionStatusRecord.COMPLETED
                            if summary.all_passed
                            else ExecutionStatusRecord.FAILED
                        ),
                        "completed_at": datetime.now(UTC),
                        "completed_jobs": summary.completed_jobs,
                        "failed_jobs": summary.failed_jobs,
                        "timed_out_jobs": summary.timed_out_jobs,
                        "cancelled_jobs": summary.cancelled_jobs,
                        "retry_count": summary.total_retries,
                    }
                )
                self.storage.save_execution(updated_rec)

        return summary
