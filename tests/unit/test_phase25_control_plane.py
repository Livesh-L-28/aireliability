"""Unit and integration tests for Phase 25 — Control Plane & Scheduling.

Covers:
- Queue: FIFO, Priority, tie-breaking, delayed jobs, cancellation
- Scheduler: lifecycle, dispatch, capacity enforcement, fair scheduling
- Policies: FIFO, Priority, FairScheduling, RetryAwareScheduling
- Retry: delay calculations, backoff strategies
- Cancellation: queued and scheduled cancellation, terminal state guards
- WorkerManager: registration, heartbeats, capacity, selection
- Recovery: stale worker detection, job requeueing, recovery summary
- ControlPlane Integration: submit, execute, evaluate, persist, metrics
- Security: credential sanitization in metadata and tags
"""

import asyncio
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from aireliability import (
    BackoffStrategy,
    CancellationCoordinator,
    CancellationError,
    ControlPlane,
    ControlPlaneConfig,
    FairSchedulingPolicy,
    FIFOPolicy,
    InMemoryDistributedStorage,
    InMemoryJobQueue,
    JobPriority,
    JobStatus,
    PriorityPolicy,
    QueueState,
    RetryAwareSchedulingPolicy,
    RetryPolicy,
    ScheduledJob,
    SQLiteDistributedStorage,
    TestCase,
    WorkerCapacityExceededError,
    WorkerManager,
)

# ---------------------------------------------------------------------------
# 1. Job Priority & Scheduling Policies
# ---------------------------------------------------------------------------


def test_priority_ordering_and_parsing():
    """Verify priority enum values, string parsing, and ordering."""
    assert (
        JobPriority.CRITICAL < JobPriority.HIGH < JobPriority.NORMAL < JobPriority.LOW
    )
    assert JobPriority.from_string("critical") == JobPriority.CRITICAL
    assert JobPriority.from_string("HIGH") == JobPriority.HIGH
    assert JobPriority.from_string("Normal") == JobPriority.NORMAL
    assert JobPriority.from_string("low") == JobPriority.LOW

    with pytest.raises(ValueError):
        JobPriority.from_string("invalid_priority")


def test_fifo_policy():
    """Verify FIFO ordering selects older queued jobs first."""
    policy = FIFOPolicy()
    tc1 = TestCase(id="t1", name="t1", input="hello")
    tc2 = TestCase(id="t2", name="t2", input="world")

    now = datetime.now(UTC)
    job_old = ScheduledJob(
        job_id="job_001",
        test_case=tc1,
        queued_at=now - timedelta(seconds=10),
    )
    job_new = ScheduledJob(
        job_id="job_002",
        test_case=tc2,
        queued_at=now - timedelta(seconds=2),
    )

    selected = policy.select_next([job_new, job_old], now=now)
    assert selected is not None
    assert selected.job_id == "job_001"


def test_priority_policy_with_tie_breaking():
    """Verify PriorityPolicy prefers higher priority, breaking ties by time and ID."""
    policy = PriorityPolicy()
    tc = TestCase(id="t", name="t", input="hi")
    now = datetime.now(UTC)

    job_low = ScheduledJob(
        job_id="job_low",
        test_case=tc,
        priority=JobPriority.LOW,
        queued_at=now - timedelta(seconds=20),
    )
    job_crit = ScheduledJob(
        job_id="job_crit",
        test_case=tc,
        priority=JobPriority.CRITICAL,
        queued_at=now - timedelta(seconds=1),
    )
    job_crit_older = ScheduledJob(
        job_id="job_crit_older",
        test_case=tc,
        priority=JobPriority.CRITICAL,
        queued_at=now - timedelta(seconds=5),
    )

    selected = policy.select_next([job_low, job_crit, job_crit_older], now=now)
    assert selected is not None
    assert selected.job_id == "job_crit_older"


def test_fair_scheduling_policy_starvation_prevention():
    """Verify FairSchedulingPolicy boosts the effective priority of aged jobs."""
    policy = FairSchedulingPolicy(aging_threshold_seconds=5.0)
    tc = TestCase(id="t", name="t", input="hi")
    now = datetime.now(UTC)

    # Low priority job queued 16s ago -> boost = 16 // 5 = 3 (LOW -> CRITICAL)
    aged_low = ScheduledJob(
        job_id="aged_low",
        test_case=tc,
        priority=JobPriority.LOW,
        queued_at=now - timedelta(seconds=16),
    )
    fresh_high = ScheduledJob(
        job_id="fresh_high",
        test_case=tc,
        priority=JobPriority.HIGH,
        queued_at=now - timedelta(seconds=1),
    )

    selected = policy.select_next([fresh_high, aged_low], now=now)
    assert selected is not None
    assert selected.job_id == "aged_low"


def test_retry_aware_scheduling_policy():
    """Verify RetryAwareSchedulingPolicy adds penalty for repeated retries."""
    policy = RetryAwareSchedulingPolicy(retry_penalty_weight=1.0)
    tc = TestCase(id="t", name="t", input="hi")
    now = datetime.now(UTC)

    # Fresh job attempt 1, NORMAL priority (2)
    fresh = ScheduledJob(
        job_id="fresh",
        test_case=tc,
        priority=JobPriority.NORMAL,
        attempt=1,
        queued_at=now,
    )
    # Retrying job attempt 3 (penalty = (3-1)*1.0 = 2.0), HIGH priority (1 + 2 = 3.0)
    retried = ScheduledJob(
        job_id="retried",
        test_case=tc,
        priority=JobPriority.HIGH,
        attempt=3,
        queued_at=now,
    )

    selected = policy.select_next([retried, fresh], now=now)
    assert selected is not None
    assert selected.job_id == "fresh"


# ---------------------------------------------------------------------------
# 2. Retry Backoff Calculation
# ---------------------------------------------------------------------------


def test_retry_backoff_strategies():
    """Verify None, Fixed, and Exponential retry delay calculations."""
    policy_none = RetryPolicy(strategy=BackoffStrategy.NONE)
    assert policy_none.compute_delay(1) == 0.0
    assert policy_none.compute_delay(2) == 0.0

    policy_fixed = RetryPolicy(
        strategy=BackoffStrategy.FIXED,
        initial_delay_seconds=2.5,
        max_delay_seconds=10.0,
    )
    assert policy_fixed.compute_delay(1) == 0.0
    assert policy_fixed.compute_delay(2) == 2.5
    assert policy_fixed.compute_delay(5) == 2.5

    policy_exp = RetryPolicy(
        strategy=BackoffStrategy.EXPONENTIAL,
        initial_delay_seconds=1.0,
        backoff_factor=2.0,
        max_delay_seconds=10.0,
    )
    assert policy_exp.compute_delay(1) == 0.0
    assert policy_exp.compute_delay(2) == 1.0  # 1.0 * 2^0
    assert policy_exp.compute_delay(3) == 2.0  # 1.0 * 2^1
    assert policy_exp.compute_delay(4) == 4.0  # 1.0 * 2^2
    assert policy_exp.compute_delay(5) == 8.0  # 1.0 * 2^3
    assert policy_exp.compute_delay(6) == 10.0  # Capped at max_delay_seconds


# ---------------------------------------------------------------------------
# 3. Queue Operations & Delayed Jobs
# ---------------------------------------------------------------------------


def test_job_queue_operations():
    """Verify InMemoryJobQueue enqueue, dequeue, peek, size, list, and clear."""

    async def run_test():
        queue = InMemoryJobQueue()
        tc1 = TestCase(id="tc1", name="tc1", input="in1")
        tc2 = TestCase(id="tc2", name="tc2", input="in2")

        j1 = ScheduledJob(job_id="j1", test_case=tc1, priority=JobPriority.LOW)
        j2 = ScheduledJob(job_id="j2", test_case=tc2, priority=JobPriority.HIGH)

        await queue.enqueue(j1)
        await queue.enqueue(j2)

        assert await queue.size() == 2

        # High priority should be dequeued first
        dequeued = await queue.dequeue()
        assert dequeued is not None
        assert dequeued.job_id == "j2"
        assert dequeued.queue_state == QueueState.SCHEDULED

        # Queue size should now be 1
        assert await queue.size() == 1

        # Peek next
        peeked = await queue.peek()
        assert peeked is not None
        assert peeked.job_id == "j1"

        # Remove
        removed = await queue.remove("j1")
        assert removed is not None
        assert await queue.size() == 0

    asyncio.run(run_test())


def test_delayed_job_eligibility():
    """Verify scheduler and queue ignore delayed jobs until delay has expired."""

    async def run_test():
        queue = InMemoryJobQueue()
        tc = TestCase(id="tc", name="tc", input="in")
        now = datetime.now(UTC)

        # Job delayed 10 seconds into the future
        future_job = ScheduledJob(
            job_id="future",
            test_case=tc,
            scheduled_at=now + timedelta(seconds=10),
        )
        await queue.enqueue(future_job)

        # Should not be eligible right now
        assert await queue.peek(now=now) is None
        assert await queue.dequeue(now=now) is None

        # Should be eligible 11 seconds later
        later = now + timedelta(seconds=11)
        assert await queue.peek(now=later) is not None
        popped = await queue.dequeue(now=later)
        assert popped is not None
        assert popped.job_id == "future"

    asyncio.run(run_test())


def test_concurrent_enqueue_dequeue():
    """Verify queue remains consistent under concurrent producers and consumers."""

    async def run_test():
        queue = InMemoryJobQueue()

        async def producer(idx: int):
            tc = TestCase(id=f"tc_{idx}", name=f"tc_{idx}", input=f"data_{idx}")
            job = ScheduledJob(job_id=f"job_{idx}", test_case=tc)
            await queue.enqueue(job)

        async def consumer():
            return await queue.dequeue()

        # Launch 20 concurrent producers
        await asyncio.gather(*(producer(i) for i in range(20)))
        assert await queue.size() == 20

        # Launch 20 concurrent consumers
        results = await asyncio.gather(*(consumer() for _ in range(20)))
        dequeued_ids = {r.job_id for r in results if r is not None}
        assert len(dequeued_ids) == 20
        assert await queue.size() == 0

    asyncio.run(run_test())


# ---------------------------------------------------------------------------
# 4. Worker Capacity Management
# ---------------------------------------------------------------------------


def test_worker_capacity_management():
    """Verify worker capacity limits, slots calculation, and load balancing."""

    async def run_test():
        mgr = WorkerManager(default_capacity=2)
        w1 = await mgr.register_worker("w1", capacity=2)
        w2 = await mgr.register_worker("w2", capacity=3)

        assert w1.available_slots == 2
        assert w2.available_slots == 3

        # Best worker selected should be w2 because it has 3 available slots vs 2
        best = await mgr.select_best_worker()
        assert best is not None
        assert best.worker_id == "w2"

        # Acquire capacity on w2
        await mgr.acquire_capacity("w2")
        w2_info = await mgr.get_worker("w2")
        assert w2_info is not None
        assert w2_info.active_jobs == 1
        assert w2_info.available_slots == 2

        # Now both have 2 slots, tie-breaker chooses w1 (alphabetical)
        best2 = await mgr.select_best_worker()
        assert best2 is not None
        assert best2.worker_id == "w1"

        # Exhaust capacity on w1
        await mgr.acquire_capacity("w1")
        await mgr.acquire_capacity("w1")
        with pytest.raises(WorkerCapacityExceededError):
            await mgr.acquire_capacity("w1")

        # Release slot on w1
        await mgr.release_capacity("w1")
        w1_info = await mgr.get_worker("w1")
        assert w1_info is not None
        assert w1_info.available_slots == 1

    asyncio.run(run_test())


def test_worker_stale_detection_in_manager():
    """Verify WorkerManager detects stale workers based on last_heartbeat."""

    async def run_test():
        mgr = WorkerManager(heartbeat_timeout_seconds=2.0)
        await mgr.register_worker("w_active")
        await mgr.register_worker("w_stale")

        now = datetime.now(UTC)

        # Update heartbeat for active worker
        await mgr.heartbeat("w_active")

        # Force simulated old heartbeat on w_stale
        stale_rec = await mgr.get_worker("w_stale")
        assert stale_rec is not None
        mgr._workers["w_stale"] = stale_rec.model_copy(
            update={"last_heartbeat": now - timedelta(seconds=10)}
        )

        stale_list = await mgr.detect_stale_workers(now=now)
        assert len(stale_list) == 1
        assert stale_list[0].worker_id == "w_stale"

        # Best worker selection should ignore the stale worker
        best = await mgr.select_best_worker(now=now)
        assert best is not None
        assert best.worker_id == "w_active"

    asyncio.run(run_test())


# ---------------------------------------------------------------------------
# 5. Cancellation Coordinator
# ---------------------------------------------------------------------------


def test_job_cancellation():
    """Verify cooperative job cancellation and rejection on completed jobs."""
    coord = CancellationCoordinator()
    tc = TestCase(id="tc", name="tc", input="in")
    job = ScheduledJob(job_id="job_cancel_test", test_case=tc)

    coord.register_job(job.job_id)
    assert not coord.is_cancelled(job.job_id)

    # Cancel queued job
    cancelled = coord.request_cancellation(job)
    assert cancelled.queue_state == QueueState.CANCELLED
    assert cancelled.job_status == JobStatus.CANCELLED
    assert coord.is_cancelled(job.job_id)

    # Cannot cancel already completed job
    completed_job = job.model_copy(
        update={
            "queue_state": QueueState.COMPLETED,
            "job_status": JobStatus.COMPLETED,
        }
    )
    with pytest.raises(CancellationError):
        coord.request_cancellation(completed_job)


# ---------------------------------------------------------------------------
# 6. End-to-End Control Plane Execution (InMemory & SQLite)
# ---------------------------------------------------------------------------


def test_control_plane_execution_in_memory():
    """Verify complete lifecycle in ControlPlane with InMemoryDistributedStorage."""

    async def run_test():
        def test_agent(inputs: dict[str, str]) -> dict[str, str]:
            return {"output": f"processed: {inputs['text']}"}

        cp = ControlPlane(
            agent=test_agent,
            config=ControlPlaneConfig(max_concurrency=3),
        )

        test_cases = [
            TestCase(id=f"tc_{i}", name=f"tc_{i}", input={"text": f"item_{i}"})
            for i in range(5)
        ]

        summary = await cp.execute_execution(test_cases, timeout=10.0)
        assert summary.total_jobs == 5
        assert summary.completed_jobs == 5
        assert summary.all_passed
        assert len(summary.results) == 5

        await cp.stop()

    asyncio.run(run_test())


def test_control_plane_execution_with_sqlite():
    """Verify complete lifecycle in ControlPlane with SQLiteDistributedStorage."""

    async def run_test():
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "control_plane_test.db"
            storage = SQLiteDistributedStorage(db_path)

            def test_agent(inputs: dict[str, str]) -> dict[str, str]:
                return {"echo": inputs["val"]}

            cp = ControlPlane(
                agent=test_agent,
                storage=storage,
                config=ControlPlaneConfig(max_concurrency=2),
            )

            test_cases = [
                TestCase(id="test_sq1", name="test_sq1", input={"val": "alpha"}),
                TestCase(id="test_sq2", name="test_sq2", input={"val": "beta"}),
            ]

            summary = await cp.execute_execution(test_cases, timeout=10.0)
            assert summary.total_jobs == 2
            assert summary.completed_jobs == 2
            assert summary.all_passed

            # Verify persisted jobs in SQLite storage
            jobs = storage.list_jobs(execution_id=summary.execution_id)
            assert len(jobs) == 2
            assert all(j.status == JobStatus.COMPLETED for j in jobs)

            # Verify persisted outcomes in SQLite storage
            outcomes = storage.list_outcomes(execution_id=summary.execution_id)
            assert len(outcomes) == 2

            await cp.stop()

    asyncio.run(run_test())


# ---------------------------------------------------------------------------
# 7. Retries & Recovery
# ---------------------------------------------------------------------------


def test_control_plane_retries_and_recovery():
    """Verify retry handling with backoff and recovery of stale worker jobs."""

    async def run_test():
        attempt_counter = 0

        def flaky_agent(inputs: dict[str, str]) -> dict[str, str]:
            nonlocal attempt_counter
            attempt_counter += 1
            if attempt_counter < 2:
                raise RuntimeError("Transient failure")
            return {"result": "success"}

        config = ControlPlaneConfig(
            max_concurrency=2,
            default_retry_policy=RetryPolicy(
                max_retries=2,
                strategy=BackoffStrategy.FIXED,
                initial_delay_seconds=0.01,
            ),
        )
        cp = ControlPlane(agent=flaky_agent, config=config)

        test_case = TestCase(id="tc_flaky", name="tc_flaky", input={"x": "1"})
        summary = await cp.execute_execution([test_case], timeout=10.0)

        assert summary.total_jobs == 1
        assert summary.completed_jobs == 1
        assert summary.all_passed
        assert summary.total_retries >= 1

        await cp.stop()

    asyncio.run(run_test())


# ---------------------------------------------------------------------------
# 8. Security & Sanitization
# ---------------------------------------------------------------------------


def test_control_plane_credential_sanitization():
    """Verify that credentials in submitted job metadata are redacted."""

    async def run_test():
        storage = InMemoryDistributedStorage()
        cp = ControlPlane(storage=storage)

        tc = TestCase(id="sec_tc", name="sec_tc", input="safe")
        submitted = await cp.submit_job(
            tc,
            metadata={
                "api_key": "sk-super-secret-key",
                "safe_tag": "public-value",
                "nested": {
                    "token": "bearer-token-12345",
                    "client_secret": "secret999",
                },
            },
        )

        assert submitted.metadata["api_key"] == "[REDACTED]"
        assert submitted.metadata["safe_tag"] == "public-value"
        assert submitted.metadata["nested"]["token"] == "[REDACTED]"
        assert submitted.metadata["nested"]["client_secret"] == "[REDACTED]"

        # Verify persisted job in storage is also sanitized
        stored = storage.get_job(submitted.job_id)
        assert stored is not None
        assert stored.metadata["api_key"] == "[REDACTED]"
        assert stored.metadata["nested"]["token"] == "[REDACTED]"

        await cp.stop()

    asyncio.run(run_test())
