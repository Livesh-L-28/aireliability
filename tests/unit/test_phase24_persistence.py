"""Unit and integration tests for Phase 24 — Production Persistence.

Covers:
- Storage operations (save/get/update/list/delete)
- SQLite distributed storage (tables, transactions, queries, indices)
- State machine lifecycle validations (valid/invalid transitions)
- Atomic job claiming and duplicate claim prevention
- Stale worker heartbeat detection and execution recovery
- Idempotent execution outcome handling
- Execution resumption (preserving completed jobs, re-running unfinished)
- Async persistence operations
- Credential sanitization in persisted records
- Backward compatibility with Phase 23 InMemoryDistributedStorage
"""

import asyncio
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from aireliability import (
    AsyncReliabilityRunner,
    ExecutionRecord,
    ExecutionStatusRecord,
    InMemoryDistributedStorage,
    InvalidStateTransitionError,
    JobExecutionOutcome,
    JobStatus,
    PersistentWorkerRecord,
    ReliabilityJob,
    SQLiteDistributedStorage,
    TestCase,
    WorkerState,
    validate_job_transition,
    validate_worker_transition,
)
from aireliability.core.models import ExecutionTrace, RunResult
from aireliability.telemetry.sanitizer import SanitizationPolicy

# ---------------------------------------------------------------------------
# 1. State Machine Validations
# ---------------------------------------------------------------------------


def test_job_state_machine_valid_transitions():
    """Verify standard legal state transitions for jobs."""
    # PENDING -> RUNNING
    validate_job_transition(JobStatus.PENDING, JobStatus.RUNNING)
    # RUNNING -> COMPLETED
    validate_job_transition(JobStatus.RUNNING, JobStatus.COMPLETED)
    # RUNNING -> FAILED
    validate_job_transition(JobStatus.RUNNING, JobStatus.FAILED)
    # RUNNING -> TIMED_OUT
    validate_job_transition(JobStatus.RUNNING, JobStatus.TIMED_OUT)
    # FAILED -> RETRYING
    validate_job_transition(JobStatus.FAILED, JobStatus.RETRYING)
    # RETRYING -> RUNNING
    validate_job_transition(JobStatus.RETRYING, JobStatus.RUNNING)
    # Idempotent same-state
    validate_job_transition(JobStatus.RUNNING, JobStatus.RUNNING)


def test_job_state_machine_invalid_transitions():
    """Verify illegal job state transitions raise InvalidStateTransitionError."""
    # COMPLETED is terminal
    with pytest.raises(InvalidStateTransitionError):
        validate_job_transition(JobStatus.COMPLETED, JobStatus.RUNNING)

    # CANCELLED is terminal
    with pytest.raises(InvalidStateTransitionError):
        validate_job_transition(JobStatus.CANCELLED, JobStatus.RUNNING)

    # PENDING cannot jump directly to COMPLETED without RUNNING
    with pytest.raises(InvalidStateTransitionError):
        validate_job_transition(JobStatus.PENDING, JobStatus.COMPLETED)


def test_worker_state_machine_valid_and_invalid():
    """Verify worker lifecycle state transitions."""
    # IDLE -> RUNNING
    validate_worker_transition(WorkerState.IDLE, WorkerState.RUNNING)
    # RUNNING -> IDLE
    validate_worker_transition(WorkerState.RUNNING, WorkerState.IDLE)
    # RUNNING -> STOPPED
    validate_worker_transition(WorkerState.RUNNING, WorkerState.STOPPED)

    # STOPPED cannot jump directly to RUNNING without IDLE
    with pytest.raises(InvalidStateTransitionError):
        validate_worker_transition(WorkerState.STOPPED, WorkerState.RUNNING)


# ---------------------------------------------------------------------------
# 2. InMemory Storage Operations
# ---------------------------------------------------------------------------


def test_in_memory_complete_crud():
    """Verify in-memory backend supports full CRUD operations."""
    storage = InMemoryDistributedStorage()

    # Execution CRUD
    exec_rec = ExecutionRecord(
        execution_id="exec_test_1",
        status=ExecutionStatusRecord.RUNNING,
        total_jobs=3,
    )
    storage.save_execution(exec_rec)
    assert storage.get_execution("exec_test_1") is not None
    assert len(storage.list_executions()) == 1

    # Worker CRUD
    worker = PersistentWorkerRecord(
        worker_id="worker_test_1",
        execution_id="exec_test_1",
        state=WorkerState.IDLE,
    )
    storage.save_worker(worker)
    assert storage.get_worker("worker_test_1") is not None
    assert len(storage.list_workers(execution_id="exec_test_1")) == 1

    # Job CRUD
    job = ReliabilityJob(
        job_id="job_test_1",
        execution_id="exec_test_1",
        test_case=TestCase(id="tc_1", name="t1", input="in"),
    )
    storage.save_job(job)
    assert storage.get_job("job_test_1") is not None
    assert len(storage.get_pending_jobs(execution_id="exec_test_1")) == 1

    # Job update
    updated_job = storage.update_job(
        "job_test_1", status=JobStatus.RUNNING, worker_id="worker_test_1"
    )
    assert updated_job.status == JobStatus.RUNNING
    assert updated_job.assigned_worker_id == "worker_test_1"
    assert len(storage.get_running_jobs(execution_id="exec_test_1")) == 1

    # Outcome CRUD
    outcome = JobExecutionOutcome(
        job_id="job_test_1",
        execution_id="exec_test_1",
        test_id="tc_1",
        worker_id="worker_test_1",
        status=JobStatus.COMPLETED,
    )
    storage.save_outcome(outcome)
    assert storage.get_outcome("job_test_1") is not None
    assert storage.get_job("job_test_1").status == JobStatus.COMPLETED

    # Delete Execution cascade
    assert storage.delete_execution("exec_test_1") is True
    assert storage.get_execution("exec_test_1") is None
    assert len(storage.list_jobs(execution_id="exec_test_1")) == 0
    assert len(storage.list_outcomes(execution_id="exec_test_1")) == 0
    assert len(storage.list_workers(execution_id="exec_test_1")) == 0


# ---------------------------------------------------------------------------
# 3. SQLite Storage Persistence & Transactions
# ---------------------------------------------------------------------------


def test_sqlite_distributed_storage_crud():
    """Verify SQLiteDistributedStorage persists across file handles."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "distributed_test.db"
        storage = SQLiteDistributedStorage(db_path=db_path)

        exec_rec = ExecutionRecord(
            execution_id="exec_sq_1",
            status=ExecutionStatusRecord.RUNNING,
            total_jobs=2,
            metadata={"environment": "ci"},
        )
        storage.save_execution(exec_rec)

        job_1 = ReliabilityJob(
            job_id="job_sq_1",
            execution_id="exec_sq_1",
            test_case=TestCase(id="tc_sq_1", name="t1", input="val1"),
        )
        job_2 = ReliabilityJob(
            job_id="job_sq_2",
            execution_id="exec_sq_1",
            test_case=TestCase(id="tc_sq_2", name="t2", input="val2"),
        )
        storage.save_job(job_1)
        storage.save_job(job_2)

        worker = PersistentWorkerRecord(
            worker_id="w_sq_1",
            execution_id="exec_sq_1",
            state=WorkerState.IDLE,
        )
        storage.save_worker(worker)

        # Reopen database with new instance to ensure disk persistence
        storage2 = SQLiteDistributedStorage(db_path=db_path)
        assert storage2.get_execution("exec_sq_1") is not None
        assert len(storage2.list_jobs(execution_id="exec_sq_1")) == 2
        assert storage2.get_worker("w_sq_1") is not None

        # Atomic claim test
        assert storage2.claim_job("job_sq_1", "w_sq_1") is True
        # Second claim should fail
        assert storage2.claim_job("job_sq_1", "w_sq_2") is False

        # Save outcome
        run_res = RunResult(
            test=job_1.test_case,
            trace=ExecutionTrace(test_id="tc_sq_1", input="val1", output="out1"),
            passed=True,
        )
        outcome = JobExecutionOutcome(
            job_id="job_sq_1",
            execution_id="exec_sq_1",
            test_id="tc_sq_1",
            worker_id="w_sq_1",
            status=JobStatus.COMPLETED,
            run_result=run_res,
        )
        storage2.save_outcome(outcome)

        saved_out = storage2.get_outcome("job_sq_1")
        assert saved_out is not None
        assert saved_out.status == JobStatus.COMPLETED
        assert saved_out.run_result.trace.output == "out1"


# ---------------------------------------------------------------------------
# 4. Atomic Claiming & Concurrency
# ---------------------------------------------------------------------------


def test_atomic_job_claiming():
    """Verify only one worker can successfully claim a pending job."""
    storage = SQLiteDistributedStorage(":memory:")
    job = ReliabilityJob(
        job_id="job_claim_1",
        execution_id="exec_c1",
        test_case=TestCase(id="tc_c1", name="c1", input="in"),
    )
    storage.save_job(job)

    # Worker A claims
    claimed_a = storage.claim_job("job_claim_1", "worker_A")
    assert claimed_a is True

    # Worker B tries to claim same job -> must fail
    claimed_b = storage.claim_job("job_claim_1", "worker_B")
    assert claimed_b is False

    # Job is now RUNNING and assigned to Worker A
    current_job = storage.get_job("job_claim_1")
    assert current_job.status == JobStatus.RUNNING
    assert current_job.assigned_worker_id == "worker_A"


# ---------------------------------------------------------------------------
# 5. Stale Worker Detection & Recovery
# ---------------------------------------------------------------------------


def test_stale_worker_detection_and_recovery():
    """Verify stale workers are detected and their unfinished jobs requeued."""
    storage = SQLiteDistributedStorage(":memory:")
    exec_id = "exec_stale_1"

    # Worker 1 heartbeat is 60 seconds old
    old_time = datetime.now(UTC) - timedelta(seconds=60)
    worker_stale = PersistentWorkerRecord(
        worker_id="w_stale_1",
        execution_id=exec_id,
        state=WorkerState.RUNNING,
        last_heartbeat=old_time,
    )
    storage.save_worker(worker_stale)

    # Active Worker 2 heartbeat is fresh
    worker_active = PersistentWorkerRecord(
        worker_id="w_active_1",
        execution_id=exec_id,
        state=WorkerState.RUNNING,
        last_heartbeat=datetime.now(UTC),
    )
    storage.save_worker(worker_active)

    # Job assigned to stale worker
    job = ReliabilityJob(
        job_id="job_stale_1",
        execution_id=exec_id,
        test_case=TestCase(id="tc_s1", name="s1", input="in"),
        status=JobStatus.RUNNING,
        assigned_worker_id="w_stale_1",
        max_retries=2,
        attempt=1,
    )
    storage.save_job(job)

    # Detect stale workers with 30s threshold
    stale = storage.detect_stale_workers(timeout_seconds=30.0, execution_id=exec_id)
    assert len(stale) == 1
    assert stale[0].worker_id == "w_stale_1"

    # Recover execution
    recovery_summary = storage.recover_execution(exec_id, stale_timeout_seconds=30.0)
    assert "job_stale_1" in recovery_summary.recovered_jobs
    assert "job_stale_1" in recovery_summary.requeued_jobs
    assert "w_stale_1" in recovery_summary.stale_workers

    # Job should now be PENDING with attempt=2 and unassigned worker
    recovered_job = storage.get_job("job_stale_1")
    assert recovered_job.status == JobStatus.PENDING
    assert recovered_job.attempt == 2
    assert recovered_job.assigned_worker_id is None
    assert recovered_job.metadata.get("recovered_from_worker") == "w_stale_1"

    # Stale worker should be marked FAILED
    updated_worker = storage.get_worker("w_stale_1")
    assert updated_worker.state == WorkerState.FAILED


# ---------------------------------------------------------------------------
# 6. Idempotency Handling
# ---------------------------------------------------------------------------


def test_idempotent_outcome_recording():
    """Verify older attempts or duplicates do not overwrite newer execution outcomes."""
    storage = SQLiteDistributedStorage(":memory:")
    job_id = "job_idem_1"

    outcome_attempt_2 = JobExecutionOutcome(
        job_id=job_id,
        execution_id="exec_i",
        test_id="tc_i",
        worker_id="w1",
        status=JobStatus.COMPLETED,
        attempt=2,
    )
    storage.save_outcome(outcome_attempt_2)

    # Try saving an older attempt (attempt 1) -> should be rejected/ignored
    outcome_attempt_1 = JobExecutionOutcome(
        job_id=job_id,
        execution_id="exec_i",
        test_id="tc_i",
        worker_id="w1",
        status=JobStatus.FAILED,
        attempt=1,
    )
    storage.save_outcome(outcome_attempt_1)

    latest = storage.get_outcome(job_id)
    assert latest.attempt == 2
    assert latest.status == JobStatus.COMPLETED


# ---------------------------------------------------------------------------
# 7. Execution Resumption via AsyncReliabilityRunner
# ---------------------------------------------------------------------------


def test_execution_resumption_skips_completed_jobs():
    """Verify resume_execution only re-executes unfinished jobs."""
    storage = SQLiteDistributedStorage(":memory:")
    exec_id = "exec_resume_test"

    executed_tests = []

    async def flaky_agent(x: str) -> str:
        executed_tests.append(x)
        return f"result_{x}"

    # Setup: 1 already completed job, 1 pending job
    tc1 = TestCase(id="tc_res_1", name="res1", input="item1")
    tc2 = TestCase(id="tc_res_2", name="res2", input="item2")

    job1 = ReliabilityJob(
        job_id="job_res_1",
        execution_id=exec_id,
        test_case=tc1,
        status=JobStatus.COMPLETED,
    )
    job2 = ReliabilityJob(
        job_id="job_res_2",
        execution_id=exec_id,
        test_case=tc2,
        status=JobStatus.PENDING,
    )
    storage.save_job(job1)
    storage.save_job(job2)

    # Save completed outcome for job 1
    run_res1 = RunResult(
        test=tc1,
        trace=ExecutionTrace(test_id="tc_res_1", input="item1", output="result_item1"),
        passed=True,
    )
    storage.save_outcome(
        JobExecutionOutcome(
            job_id="job_res_1",
            execution_id=exec_id,
            test_id="tc_res_1",
            worker_id="w_prev",
            status=JobStatus.COMPLETED,
            run_result=run_res1,
        )
    )

    runner = AsyncReliabilityRunner(
        agent=flaky_agent,
        storage=storage,
        max_concurrency=2,
    )

    summary = asyncio.run(runner.resume_execution(exec_id))

    assert summary.all_passed is True
    assert summary.total_jobs == 2
    assert summary.passed_tests == 2
    # Only tc2 should have been executed by agent during resume
    assert executed_tests == ["item2"]


# ---------------------------------------------------------------------------
# 8. Async Persistence Operations
# ---------------------------------------------------------------------------


def test_async_persistence_backend():
    """Verify AsyncDistributedPersistenceBackend operations."""

    async def run_async_storage_test():
        storage = SQLiteDistributedStorage(":memory:")
        job = ReliabilityJob(
            job_id="job_async_1",
            execution_id="exec_a1",
            test_case=TestCase(id="tc_a1", name="a1", input="val"),
        )
        await storage.asave_job(job)

        fetched = await storage.aget_job("job_async_1")
        assert fetched is not None
        assert fetched.job_id == "job_async_1"

        updated = await storage.aupdate_job("job_async_1", status=JobStatus.RUNNING)
        assert updated.status == JobStatus.RUNNING

        jobs = await storage.alist_jobs(execution_id="exec_a1")
        assert len(jobs) == 1

        claimed = await storage.aclaim_job("job_async_1", "w1")
        # Already RUNNING, cannot claim
        assert claimed is False

    asyncio.run(run_async_storage_test())


# ---------------------------------------------------------------------------
# 9. Sensitive Credential Sanitization
# ---------------------------------------------------------------------------


def test_persistence_sanitization():
    """Verify credentials and tokens in metadata are sanitized before storage."""
    policy = SanitizationPolicy()
    storage = SQLiteDistributedStorage(":memory:", sanitizer=policy)

    job = ReliabilityJob(
        job_id="job_sec_1",
        execution_id="exec_sec_1",
        test_case=TestCase(id="tc_sec", name="sec", input="in"),
        metadata={
            "api_key": "sk-secret-live-12345",
            "bearer_token": "Bearer abcxyz",
            "nested": {"client_secret": "my-secret-pw", "allowed": "ok"},
        },
    )
    storage.save_job(job)

    saved_job = storage.get_job("job_sec_1")
    assert saved_job.metadata["api_key"] == "[REDACTED]"
    assert saved_job.metadata["nested"]["client_secret"] == "[REDACTED]"
    assert saved_job.metadata["nested"]["allowed"] == "ok"
