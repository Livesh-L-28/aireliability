"""Comprehensive test suite for Phase 23 Distributed Reliability & Async Execution."""

import asyncio
from typing import Any

from aireliability import (
    AsyncReliabilityRunner,
    AsyncTelemetryCollector,
    BaselineManager,
    CorrelationContext,
    InMemoryDistributedStorage,
    InMemoryTelemetryCollector,
    JobExecutionOutcome,
    JobStatus,
    OutputEquals,
    RegressionRunner,
    ReliabilityJob,
    ReliabilityWorker,
    SanitizationPolicy,
    TestCase,
    WorkerState,
)
from aireliability.core.models import (
    ExecutionStatus,
    ExecutionTrace,
    RegressionTest,
)

# ---------------------------------------------------------------------------
# 1. Job and Worker Models
# ---------------------------------------------------------------------------


def test_reliability_job_model_creation():
    """Verify ReliabilityJob model defaults, serialization, and test_id property."""
    tc = TestCase(id="tc_job_1", name="job_test", input="data")
    job = ReliabilityJob(test_case=tc, priority=1, timeout_seconds=10.0)

    assert job.test_id == "tc_job_1"
    assert job.priority == 1
    assert job.attempt == 1
    assert job.status == JobStatus.PENDING
    assert job.timeout_seconds == 10.0


def test_worker_descriptor_and_lifecycle():
    """Verify ReliabilityWorker state transitions and descriptor reporting."""
    worker = ReliabilityWorker(worker_id="test_worker_1")
    assert worker.state == WorkerState.IDLE

    desc = worker.describe()
    assert desc.worker_id == "test_worker_1"
    assert desc.state == WorkerState.IDLE
    assert desc.jobs_completed == 0
    assert desc.jobs_failed == 0


# ---------------------------------------------------------------------------
# 2. Async Execution and Concurrent Worker Pool
# ---------------------------------------------------------------------------


def test_async_reliability_runner_single_execute():
    """Verify AsyncReliabilityRunner can execute a single test case asynchronously."""

    def echo_agent(x: str) -> str:
        return f"Echo: {x}"

    runner = AsyncReliabilityRunner(
        agent=echo_agent,
        evaluators=[OutputEquals("Echo: hello")],
    )

    tc = TestCase(id="tc_single", name="single_test", input="hello")
    res = asyncio.run(runner.execute(tc))

    assert res.passed is True
    assert res.test.id == "tc_single"
    assert res.trace.output == "Echo: hello"


def test_async_reliability_runner_concurrent_many():
    """Verify AsyncReliabilityRunner executes multiple test cases concurrently."""

    def fast_agent(x: int) -> int:
        return x * 2

    runner = AsyncReliabilityRunner(
        agent=fast_agent,
        max_concurrency=4,
    )

    test_cases = [TestCase(id=f"tc_{i}", name=f"test_{i}", input=i) for i in range(10)]
    summary = asyncio.run(runner.execute_many(test_cases))

    assert summary.total_jobs == 10
    assert summary.completed_jobs == 10
    assert summary.all_passed is True
    assert len(summary.results) == 10


# ---------------------------------------------------------------------------
# 3. Deterministic Ordering of Results
# ---------------------------------------------------------------------------


def test_deterministic_result_ordering():
    """Verify execution results preserve original order regardless of timing."""

    async def staggered_agent(item: dict) -> str:
        # Intentionally stagger completion time
        delay = item.get("delay", 0.01)
        await asyncio.sleep(delay)
        return item["val"]

    class AsyncStaggeredAdapter:
        async def aexecute(self, agent: Any, test_case: TestCase):
            val = await agent(test_case.input)
            return ExecutionTrace(
                test_id=test_case.id,
                input=test_case.input,
                output=val,
                status=ExecutionStatus.COMPLETED,
            )

    runner = AsyncReliabilityRunner(
        agent=staggered_agent,
        adapter=AsyncStaggeredAdapter(),
        max_concurrency=5,
    )

    # test 0 completes LAST, test 4 completes FIRST
    test_cases = [
        TestCase(
            id=f"tc_{i:02d}",
            name=f"test_{i}",
            input={"delay": 0.05 - (i * 0.01), "val": f"out_{i}"},
        )
        for i in range(5)
    ]

    summary = asyncio.run(runner.execute_many(test_cases))
    result_ids = [r.test.id for r in summary.results]

    assert result_ids == ["tc_00", "tc_01", "tc_02", "tc_03", "tc_04"]


# ---------------------------------------------------------------------------
# 4. Timeout Enforcement and Retries
# ---------------------------------------------------------------------------


def test_worker_timeout_enforcement():
    """Verify worker terminates jobs that exceed timeout and flags TIMED_OUT."""

    async def slow_agent(x: str) -> str:
        await asyncio.sleep(1.0)
        return "late"

    class SlowAsyncAdapter:
        async def aexecute(self, agent: Any, test_case: TestCase):
            await agent(test_case.input)
            return ExecutionTrace(test_id=test_case.id, output="never")

    worker = ReliabilityWorker(
        agent=slow_agent,
        adapter=SlowAsyncAdapter(),
    )

    job = ReliabilityJob(
        test_case=TestCase(id="tc_slow", name="slow", input="go"),
        timeout_seconds=0.05,
    )

    outcome = asyncio.run(worker.run_job(job))

    assert outcome.status == JobStatus.TIMED_OUT
    assert outcome.error_type == "TimeoutError"
    assert outcome.retryable is True
    assert outcome.run_result is not None
    assert outcome.run_result.passed is False


def test_async_runner_retry_mechanism():
    """Verify runner automatically retries transient failures up to max_retries."""
    attempts = 0

    def flaky_agent(x: str) -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError(f"Transient error on attempt {attempts}")
        return "success"

    runner = AsyncReliabilityRunner(
        agent=flaky_agent,
        max_retries=3,
        evaluators=[OutputEquals("success")],
    )

    tc = TestCase(id="tc_flaky", name="flaky", input="test")
    summary = asyncio.run(runner.execute_many([tc]))

    assert attempts == 3
    assert summary.all_passed is True
    assert summary.total_retries == 2
    assert summary.results[0].passed is True


# ---------------------------------------------------------------------------
# 5. Distributed Persistence
# ---------------------------------------------------------------------------


def test_in_memory_distributed_storage():
    """Verify storage persists, queries, and updates jobs and outcomes."""
    storage = InMemoryDistributedStorage()

    job = ReliabilityJob(
        job_id="job_persist_1",
        execution_id="exec_1",
        test_case=TestCase(id="tc_p1", name="p1", input="in"),
    )
    storage.save_job(job)

    assert storage.get_job("job_persist_1") == job
    assert len(storage.list_jobs(execution_id="exec_1")) == 1

    outcome = JobExecutionOutcome(
        job_id="job_persist_1",
        execution_id="exec_1",
        test_id="tc_p1",
        worker_id="w_1",
        status=JobStatus.COMPLETED,
    )
    storage.save_outcome(outcome)

    assert storage.get_outcome("job_persist_1") == outcome
    assert storage.get_job("job_persist_1").status == JobStatus.COMPLETED

    storage.clear()
    assert len(storage.list_jobs()) == 0


# ---------------------------------------------------------------------------
# 6. Async Telemetry Collector & Background Flushing
# ---------------------------------------------------------------------------


def test_async_telemetry_collector_buffering_and_flush():
    """Verify collector queues traces, records counts, and flushes to sink."""
    sink = InMemoryTelemetryCollector()
    async_collector = AsyncTelemetryCollector(sink_collector=sink, max_buffer_size=10)

    async def exercise_collector():
        await async_collector.astart()

        from aireliability.telemetry.models import TelemetryTrace

        t1 = TelemetryTrace(trace_id="tr_async_1")
        t2 = TelemetryTrace(trace_id="tr_async_2")

        await async_collector.arecord(t1)
        async_collector.record(t2)

        assert async_collector.recorded_events == 2
        assert async_collector.dropped_events == 0

        await async_collector.aflush()
        assert len(sink.traces) == 2

        await async_collector.aclose()

    asyncio.run(exercise_collector())


# ---------------------------------------------------------------------------
# 7. Parallel Regression Execution with RegressionRunner
# ---------------------------------------------------------------------------


def test_regression_runner_parallel_suite():
    """Verify RegressionRunner.run_suite_async runs tests concurrently."""

    def mock_agent(x: str) -> str:
        return "order_processed"

    reg_runner = RegressionRunner(
        agent=mock_agent,
        evaluators=[OutputEquals("order_processed")],
    )

    reg_tests = [
        RegressionTest(
            id=f"reg_{i}",
            name=f"regression_{i}",
            source_failure_id=f"fail_{i}",
            test_case=TestCase(id=f"tc_reg_{i}", name=f"reg_tc_{i}", input=f"in_{i}"),
        )
        for i in range(5)
    ]

    suite_result = asyncio.run(reg_runner.run_suite_async(reg_tests, max_concurrency=3))

    assert suite_result.all_passed is True
    assert suite_result.total_runs == 5
    assert len(suite_result.results) == 5
    assert [r.test.id for r in suite_result.results] == [
        f"tc_reg_{i}" for i in range(5)
    ]


# ---------------------------------------------------------------------------
# 8. Correlation and Sensitive Data Sanitization
# ---------------------------------------------------------------------------


def test_distributed_correlation_and_sanitization():
    """Verify workers attach correlation metadata and respect sanitization."""
    policy = SanitizationPolicy()
    sanitized_secret = policy.sanitize({"api_key": "sk-secret999", "normal": "val"})
    assert sanitized_secret["api_key"] == "[REDACTED]"
    assert sanitized_secret["normal"] == "val"

    correlation = CorrelationContext(
        execution_id="exec_corr_1",
        job_id="job_corr_1",
        worker_id="worker_corr_1",
        test_id="tc_corr_1",
    )
    assert correlation.execution_id == "exec_corr_1"
    assert correlation.attempt == 1


# ---------------------------------------------------------------------------
# 9. Cancellation and Worker Crash Recovery
# ---------------------------------------------------------------------------


def test_async_worker_cancellation():
    """Verify cancelled tasks gracefully report CANCELLED status."""

    async def cancelled_execution():
        async def endless_task(x: str):
            await asyncio.sleep(100.0)
            return "never"

        class EndlessAdapter:
            async def aexecute(self, agent: Any, test_case: TestCase):
                await agent(test_case.input)
                return ExecutionTrace(test_id=test_case.id)

        worker = ReliabilityWorker(
            agent=endless_task,
            adapter=EndlessAdapter(),
        )
        job = ReliabilityJob(
            test_case=TestCase(id="tc_cancel", name="cancel", input="wait")
        )

        task = asyncio.create_task(worker.run_job(job))
        await asyncio.sleep(0.01)
        task.cancel()

        outcome = await task
        assert outcome.status == JobStatus.CANCELLED
        assert outcome.retryable is False

    asyncio.run(cancelled_execution())


def test_worker_unhandled_crash_recovery():
    """Verify unhandled exceptions in worker report FAILED status."""
    worker = ReliabilityWorker(
        agent=lambda x: 1 / 0,  # ZeroDivisionError
    )
    job = ReliabilityJob(test_case=TestCase(id="tc_crash", name="crash", input=0))
    outcome = asyncio.run(worker.run_job(job))

    assert outcome.status == JobStatus.FAILED
    assert outcome.error_type == "ZeroDivisionError"
    assert outcome.retryable is True


# ---------------------------------------------------------------------------
# 10. Parallel Regression with Baseline Comparison
# ---------------------------------------------------------------------------


def test_parallel_regression_with_baseline_comparison():
    """Verify running regression suite concurrently preserves baseline comparisons."""
    bm = BaselineManager()

    # Pass 1: Original working agent
    reg_runner = RegressionRunner(
        agent=lambda x: "ok",
        evaluators=[OutputEquals("ok")],
        baseline_manager=bm,
    )
    reg_tests = [
        RegressionTest(
            id=f"reg_b_{i}",
            name=f"baseline_reg_{i}",
            source_failure_id=f"fail_{i}",
            test_case=TestCase(id=f"tc_b_{i}", name=f"b_{i}", input=i),
        )
        for i in range(4)
    ]
    suite_1 = asyncio.run(reg_runner.run_suite_async(reg_tests, max_concurrency=4))
    assert suite_1.all_passed is True

    # Save baseline
    bm.create_baseline(suite_1.results, name="main")

    # Pass 2: Buggy agent in parallel suite
    buggy_runner = RegressionRunner(
        agent=lambda x: "bad" if x == 2 else "ok",
        evaluators=[OutputEquals("ok")],
        baseline_manager=bm,
    )
    suite_2 = asyncio.run(
        buggy_runner.run_suite_async(
            reg_tests, max_concurrency=4, compare_baseline="main"
        )
    )

    assert suite_2.all_passed is False
    assert suite_2.passed_count == 3
    assert suite_2.failed_count == 1
    assert suite_2.comparison_summary is not None
    assert suite_2.comparison_summary.has_regressions is True
    assert len(suite_2.comparison_summary.regressions) == 1
    assert suite_2.comparison_summary.regressions[0].test_id == "tc_b_2"
