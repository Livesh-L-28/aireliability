"""Distributed result aggregator and deterministic report builder.

Combines results from multiple parallel workers, dedupes executions, preserves test
and execution identity, and computes aggregate metrics and deterministic ordering.
Capable of rebuilding state directly from persistent storage backends.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from aireliability.core.models import RunResult
from aireliability.distributed.models import JobExecutionOutcome, JobStatus


@dataclass
class DistributedExecutionSummary:
    """Consolidated summary of a distributed reliability test execution."""

    execution_id: str
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    timed_out_jobs: int
    cancelled_jobs: int
    passed_tests: int
    failed_tests: int
    total_retries: int
    total_latency_ms: float
    results: list[RunResult] = field(default_factory=list)
    outcomes: list[JobExecutionOutcome] = field(default_factory=list)
    worker_errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        """True if all executed tests completed with passing assertions."""
        return (
            self.failed_tests == 0
            and self.failed_jobs == 0
            and self.timed_out_jobs == 0
        )


class ResultAggregator:
    """Aggregates distributed job outcomes with deterministic test-order sorting."""

    def __init__(self, execution_id: str) -> None:
        self.execution_id = execution_id
        self._outcomes: dict[str, JobExecutionOutcome] = {}
        self._all_outcomes: list[JobExecutionOutcome] = []

    def add_outcome(self, outcome: JobExecutionOutcome) -> None:
        """Add or update an execution outcome.

        If a test is retried, the latest attempt replaces earlier attempts for
        final test results, while the historical attempt is preserved in all_outcomes.
        """
        self._all_outcomes.append(outcome)
        test_key = outcome.test_id
        existing = self._outcomes.get(test_key)
        if existing is None or outcome.attempt >= existing.attempt:
            self._outcomes[test_key] = outcome

    @classmethod
    def from_storage(cls, storage: Any, execution_id: str) -> "ResultAggregator":
        """Reconstruct aggregator state from a persistent storage backend."""
        aggregator = cls(execution_id=execution_id)
        if hasattr(storage, "list_outcomes"):
            outcomes = storage.list_outcomes(execution_id=execution_id)
            for outcome in outcomes:
                aggregator.add_outcome(outcome)
        return aggregator

    def aggregate(
        self, expected_order: Sequence[str] | None = None
    ) -> DistributedExecutionSummary:
        """Compile a deterministic execution summary.

        Args:
            expected_order: Optional sequence of test IDs specifying the required
                deterministic output sort order. If omitted, sorts by test_id.

        Returns:
            DistributedExecutionSummary containing sorted RunResults and metrics.
        """
        # Sort outcomes according to expected order or test_id
        if expected_order:
            ordered_keys = [k for k in expected_order if k in self._outcomes]
            remaining = sorted(k for k in self._outcomes if k not in expected_order)
            sorted_keys = ordered_keys + remaining
        else:
            sorted_keys = sorted(self._outcomes.keys())

        final_outcomes = [self._outcomes[k] for k in sorted_keys]

        results: list[RunResult] = []
        worker_errors: list[dict[str, Any]] = []

        passed_tests = 0
        failed_tests = 0
        completed_jobs = 0
        failed_jobs = 0
        timed_out_jobs = 0
        cancelled_jobs = 0
        total_latency_ms = 0.0

        for outcome in final_outcomes:
            if outcome.duration_ms:
                total_latency_ms += outcome.duration_ms

            if outcome.status == JobStatus.COMPLETED:
                completed_jobs += 1
            elif outcome.status == JobStatus.TIMED_OUT:
                timed_out_jobs += 1
            elif outcome.status == JobStatus.CANCELLED:
                cancelled_jobs += 1
            else:
                failed_jobs += 1

            if outcome.error:
                worker_errors.append(
                    {
                        "test_id": outcome.test_id,
                        "worker_id": outcome.worker_id,
                        "error": outcome.error,
                        "error_type": outcome.error_type,
                        "status": outcome.status.value,
                    }
                )

            if outcome.run_result is not None:
                results.append(outcome.run_result)
                if outcome.run_result.passed:
                    passed_tests += 1
                else:
                    failed_tests += 1
            else:
                failed_tests += 1

        total_retries = max(0, len(self._all_outcomes) - len(final_outcomes))

        return DistributedExecutionSummary(
            execution_id=self.execution_id,
            total_jobs=len(final_outcomes),
            completed_jobs=completed_jobs,
            failed_jobs=failed_jobs,
            timed_out_jobs=timed_out_jobs,
            cancelled_jobs=cancelled_jobs,
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            total_retries=total_retries,
            total_latency_ms=round(total_latency_ms, 3),
            results=results,
            outcomes=final_outcomes,
            worker_errors=worker_errors,
        )
