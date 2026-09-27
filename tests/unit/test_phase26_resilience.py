"""Tests for Phase 26 Fault Tolerance, Resilience & Self-Healing."""

import asyncio

import pytest

from aireliability.control_plane import (
    ControlPlane,
    ControlPlaneConfig,
    JobPriority,
    JobScheduler,
    WorkerManager,
)
from aireliability.core.models import FailureSeverity
from aireliability.distributed.sqlite_storage import SQLiteDistributedStorage
from aireliability.distributed.storage import InMemoryDistributedStorage
from aireliability.resilience import (
    Bulkhead,
    CircuitBreaker,
    CircuitState,
    DetailedFailureRecord,
    FailureClassifier,
    HealthChecker,
    LoadShedder,
    ResilienceBackoffStrategy,
    ResilienceFailureCategory,
    ResilienceManager,
    ResilientRetryPolicy,
    WorkerHealthManager,
    WorkerHealthStatus,
)
from aireliability.resilience.bulkhead import BulkheadCapacityExceededError
from aireliability.resilience.load_shedder import LoadSheddingConfig

# ==============================================================================
# 1 & 2. Failure Classification & Retryable vs Non-Retryable
# ==============================================================================


def test_failure_classifier_classifies_correctly():
    """Test deterministic categorization across distinct failure exceptions."""
    classifier = FailureClassifier()

    timeout_err = TimeoutError("Connection to LLM endpoint timed out")
    rec = classifier.classify_error(
        timeout_err,
        execution_id="exec-1",
        job_id="job-1",
        worker_id="w-1",
        metadata={"api_key": "sk-secret-password-12345", "user": "alice"},
    )

    assert rec.failure_type == ResilienceFailureCategory.JOB_TIMEOUT
    assert rec.retryable is True
    assert rec.execution_id == "exec-1"
    assert rec.job_id == "job-1"
    assert rec.worker_id == "w-1"
    # Metadata sanitization check
    assert "sk-secret-password-12345" not in str(rec.metadata)
    assert rec.metadata.get("api_key") == "[REDACTED]"
    assert rec.metadata.get("user") == "alice"


def test_failure_classifier_non_retryable_auth():
    """Authentication and permission errors should be classified as non-retryable."""
    classifier = FailureClassifier()
    auth_err = PermissionError("401 Unauthorized invalid credentials")
    rec = classifier.classify_error(auth_err)

    assert rec.failure_type == ResilienceFailureCategory.AUTHENTICATION_FAILURE
    assert rec.retryable is False


def test_failure_classifier_cancellation():
    """Cancellation errors should be classified as cancellation category."""
    classifier = FailureClassifier()
    cancel_err = asyncio.CancelledError("Operation cancelled")
    rec = classifier.classify_error(cancel_err)

    assert rec.failure_type == ResilienceFailureCategory.CANCELLATION
    assert rec.retryable is False


# ==============================================================================
# 3 & 4. Exponential Backoff & Jitter
# ==============================================================================


def test_retry_policy_backoff_strategies():
    """Verify fixed, linear, exponential, and jitter calculations."""
    policy_fixed = ResilientRetryPolicy(
        max_retries=3,
        strategy=ResilienceBackoffStrategy.FIXED,
        initial_delay_seconds=2.0,
    )
    assert policy_fixed.compute_delay(1) == 0.0
    assert policy_fixed.compute_delay(2) == 2.0
    assert policy_fixed.compute_delay(3) == 2.0

    policy_linear = ResilientRetryPolicy(
        strategy=ResilienceBackoffStrategy.LINEAR,
        initial_delay_seconds=1.5,
    )
    assert policy_linear.compute_delay(1) == 0.0
    assert policy_linear.compute_delay(2) == 1.5
    assert policy_linear.compute_delay(3) == 3.0
    assert policy_linear.compute_delay(4) == 4.5

    policy_exp = ResilientRetryPolicy(
        strategy=ResilienceBackoffStrategy.EXPONENTIAL,
        initial_delay_seconds=1.0,
        backoff_factor=2.0,
        max_delay_seconds=10.0,
    )
    assert policy_exp.compute_delay(1) == 0.0
    assert policy_exp.compute_delay(2) == 1.0
    assert policy_exp.compute_delay(3) == 2.0
    assert policy_exp.compute_delay(4) == 4.0
    assert policy_exp.compute_delay(10) == 10.0  # capped at max_delay

    policy_jitter = ResilientRetryPolicy(
        strategy=ResilienceBackoffStrategy.EXPONENTIAL_JITTER,
        initial_delay_seconds=1.0,
        backoff_factor=2.0,
        jitter_factor=0.25,
    )
    for i in range(10):
        d = policy_jitter.compute_delay(3, seed=i)
        assert 1.5 <= d <= 2.5


# ==============================================================================
# 5, 6 & 7. Circuit Breaker Opening, Recovery, Half-Open
# ==============================================================================


def test_circuit_breaker_flow():
    """Test transitions CLOSED -> OPEN -> HALF_OPEN -> CLOSED."""

    async def run_test():
        cb = CircuitBreaker(
            name="test_provider",
            failure_threshold=2,
            recovery_timeout_seconds=0.05,
            half_open_probe_count=1,
            success_threshold=1,
        )

        assert cb.state == CircuitState.CLOSED
        assert await cb.can_execute() is True

        # Record first failure -> still CLOSED
        await cb.record_failure()
        assert cb.state == CircuitState.CLOSED

        # Record second failure -> moves to OPEN
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert await cb.can_execute() is False

        # Wait for recovery timeout
        await asyncio.sleep(0.06)

        # State transitions dynamically to HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN
        assert await cb.can_execute() is True

        # Successful call in HALF_OPEN recovers to CLOSED
        await cb.record_success()
        assert cb.state == CircuitState.CLOSED

    asyncio.run(run_test())


def test_circuit_breaker_half_open_failure_reopens():
    """Failure during HALF_OPEN should immediately re-open the circuit."""

    async def run_test():
        cb = CircuitBreaker(
            failure_threshold=1,
            recovery_timeout_seconds=0.02,
        )
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN
        await asyncio.sleep(0.03)
        assert cb.state == CircuitState.HALF_OPEN

        await cb.record_failure()
        assert cb.state == CircuitState.OPEN

    asyncio.run(run_test())


# ==============================================================================
# 8. Bulkhead Isolation
# ==============================================================================


def test_bulkhead_concurrency_isolation():
    """Ensure independent partitions respect maximum concurrency."""

    async def run_test():
        bulkhead = Bulkhead(default_limit=2)
        bulkhead.set_limit("slow_provider", limit=1)

        async def worker_task(partition: str, delay: float):
            async with bulkhead.acquire(partition):
                await asyncio.sleep(delay)
                return partition

        t1 = asyncio.create_task(worker_task("slow_provider", 0.05))
        await asyncio.sleep(0.01)

        # slow_provider capacity is currently 0
        assert bulkhead.get_available("slow_provider") == 0
        # other partitions still have full capacity
        assert bulkhead.get_available("fast_provider") == 2

        # Exceeding limit raises BulkheadCapacityExceededError
        with pytest.raises(BulkheadCapacityExceededError):
            async with bulkhead.acquire("slow_provider"):
                pass

        await t1
        assert bulkhead.get_available("slow_provider") == 1

    asyncio.run(run_test())


# ==============================================================================
# 9, 10 & 11. Worker Degradation, Quarantine & Recovery
# ==============================================================================


def test_worker_health_quarantine_and_recovery():
    """Track worker failures from HEALTHY -> DEGRADED -> QUARANTINED
    -> RECOVERING -> HEALTHY.
    """

    async def run_test():
        whm = WorkerHealthManager(
            degradation_threshold=2,
            quarantine_threshold=4,
            recovery_success_threshold=1,
        )

        w_id = "worker-xyz"
        prof = await whm.get_or_create_profile(w_id)
        assert prof.status == WorkerHealthStatus.HEALTHY
        assert await whm.is_worker_healthy(w_id) is True

        # 2 failures -> DEGRADED
        await whm.record_execution_failure(w_id)
        p2 = await whm.record_execution_failure(w_id)
        assert p2.status == WorkerHealthStatus.DEGRADED
        assert await whm.is_worker_healthy(w_id) is True  # still eligible, but degraded

        # 4 failures -> QUARANTINED
        await whm.record_execution_failure(w_id)
        p4 = await whm.record_execution_failure(w_id)
        assert p4.status == WorkerHealthStatus.QUARANTINED
        assert await whm.is_worker_healthy(w_id) is False

        # Recover worker
        await whm.recover_worker(w_id)
        prof_rec = await whm.get_or_create_profile(w_id)
        assert prof_rec.status == WorkerHealthStatus.RECOVERING

        # Successful probe resets to HEALTHY
        p_healthy = await whm.record_execution_success(w_id)
        assert p_healthy.status == WorkerHealthStatus.HEALTHY

    asyncio.run(run_test())


# ==============================================================================
# 12. Failure Storm Protection & Load Shedding
# ==============================================================================


def test_load_shedder_storm_and_priority():
    """Test failure rate window detection and priority-based shedding."""

    async def run_test():
        config = LoadSheddingConfig(
            failure_rate_threshold=0.5,
            window_seconds=10.0,
            min_samples=10,
            max_queue_depth=5,
        )
        shedder = LoadShedder(config=config)

        # 4 successes, 6 failures out of 10 samples -> 60% failure rate
        for _ in range(4):
            await shedder.record_result(success=True)
        for _ in range(6):
            await shedder.record_result(success=False)

        rate = await shedder.get_failure_rate()
        assert rate == 0.6

        # Critical jobs should NOT be shed during normal storm
        shed_crit, _ = await shedder.should_shed_job(priority=JobPriority.CRITICAL)
        assert shed_crit is False

        # Low priority jobs SHOULD be shed during storm
        shed_low, reason_low = await shedder.should_shed_job(priority=JobPriority.LOW)
        assert shed_low is True
        assert reason_low is not None
        assert "Failure storm protection" in reason_low

    asyncio.run(run_test())


# ==============================================================================
# 13. Health Checks
# ==============================================================================


def test_health_checker_components():
    """Test multi-component health checking (storage, scheduler, workers)."""

    async def run_test():
        from aireliability.control_plane.queue import InMemoryJobQueue

        storage = InMemoryDistributedStorage()
        wm = WorkerManager(storage=storage)
        queue = InMemoryJobQueue()
        scheduler = JobScheduler(queue=queue, worker_manager=wm, storage=storage)
        worker_health = WorkerHealthManager()
        await worker_health.get_or_create_profile("w-test")

        checker = HealthChecker()
        st_res = await checker.check_storage(storage)
        assert st_res.is_healthy is True
        assert st_res.component == "storage"

        sc_res = await checker.check_scheduler(scheduler)
        assert sc_res.component == "scheduler"

        w_res = await checker.check_worker("w-test", worker_health)
        assert w_res.is_healthy is True
        assert "worker:w-test" in w_res.component

    asyncio.run(run_test())


# ==============================================================================
# 14 & 15. Persistence of Resilience State (SQLite & InMemory)
# ==============================================================================


def test_storage_failure_persistence(tmp_path):
    """Test saving and retrieving DetailedFailureRecord in InMemory and SQLite."""
    # InMemory
    mem_storage = InMemoryDistributedStorage()
    rec = DetailedFailureRecord(
        failure_id="f-1",
        execution_id="exec-1",
        job_id="job-1",
        worker_id="w-1",
        failure_type=ResilienceFailureCategory.PROVIDER_FAILURE,
        severity=FailureSeverity.HIGH,
        retryable=True,
        error="LLM Rate Limit",
    )
    mem_storage.save_failure(rec)
    saved_mem = mem_storage.list_failures(execution_id="exec-1")
    assert len(saved_mem) == 1
    assert saved_mem[0].failure_id == "f-1"

    # SQLite
    db_file = str(tmp_path / "resilience.db")
    sql_storage = SQLiteDistributedStorage(db_file)
    sql_storage.save_failure(rec)
    saved_sql = sql_storage.list_failures(execution_id="exec-1")
    assert len(saved_sql) == 1
    assert saved_sql[0].failure_id == "f-1"
    assert saved_sql[0].failure_type == ResilienceFailureCategory.PROVIDER_FAILURE
    assert saved_sql[0].retryable is True


# ==============================================================================
# 16. Central ResilienceManager & Admission Control
# ==============================================================================


def test_resilience_manager_coordination():
    """Verify that ResilienceManager coordinates classification,
    circuits, and shedding.
    """

    async def run_test():
        mgr = ResilienceManager(circuit_failure_threshold=2)

        # Record 2 failures for provider 'p-faulty'
        await mgr.record_failure(
            RuntimeError("Provider 503 service unavailable"),
            execution_id="exec-test",
            job_id="job-test",
            provider_id="p-faulty",
        )
        await mgr.record_failure(
            RuntimeError("Provider 503 service unavailable"),
            execution_id="exec-test",
            job_id="job-test",
            provider_id="p-faulty",
        )

        # Circuit should now block admissions
        allowed, reason = await mgr.check_admission(
            priority=JobPriority.HIGH,
            provider_id="p-faulty",
        )
        assert allowed is False
        assert reason is not None
        assert "circuit breaker is OPEN" in reason

        # Another healthy provider is admitted
        allowed_healthy, _ = await mgr.check_admission(
            priority=JobPriority.HIGH,
            provider_id="p-healthy",
        )
        assert allowed_healthy is True

    asyncio.run(run_test())


# ==============================================================================
# 17. ControlPlane Self-Healing & Worker Selection Integration
# ==============================================================================


def test_control_plane_resilience_integration():
    """Verify that ControlPlane uses worker health filtering and failure
    classification.
    """

    async def run_test():
        storage = InMemoryDistributedStorage()
        wm = WorkerManager(storage=storage)
        resilience = ResilienceManager()

        # Register 2 workers via WorkerManager
        await wm.register_worker("w-healthy", capacity=2)
        await wm.register_worker("w-bad", capacity=2)

        # Quarantine w-bad
        await resilience.worker_health.quarantine_worker("w-bad", reason="flaky")

        # Worker health filter should exclude w-bad and select w-healthy
        healthy_id = await resilience.is_worker_eligible("w-healthy")
        assert healthy_id is True
        bad_id = await resilience.is_worker_eligible("w-bad")
        assert bad_id is False

        cp = ControlPlane(
            config=ControlPlaneConfig(),
            storage=storage,
            resilience_manager=resilience,
        )

        # Verify controller resilience wiring
        assert cp.resilience is not None
        assert cp.scheduler.worker_health_filter is not None

    asyncio.run(run_test())


# ==============================================================================
# 18. Prometheus Metrics & Telemetry Emission
# ==============================================================================


def test_distributed_metrics_resilience_methods():
    """Verify that DistributedMetrics resilience methods work without errors."""
    from aireliability.distributed.metrics import DistributedMetrics

    metrics = DistributedMetrics()
    metrics.record_failure_metric("provider_failure", "high")
    metrics.record_retry_attempt("exponential_jitter")
    metrics.set_circuit_state("openai", 1)
    metrics.set_quarantined_workers(2)
    metrics.record_worker_recovery()
    metrics.record_job_reassigned()
    metrics.record_job_shed("failure_storm")
    metrics.record_recovery_duration(0.25)
    metrics.set_failure_rate(0.15)


# ==============================================================================
# 19. CLI Resilience Command Handler
# ==============================================================================


def test_cli_resilience_subcommands(capsys):
    """Test CLI commands: status, failures, workers, circuits, quarantine, recover."""
    from aireliability.cli import main

    # Status
    ret_status = main(["resilience", "status"])
    assert ret_status == 0
    out_status = capsys.readouterr().out
    assert "Resilience Manager Status" in out_status

    # Failures
    ret_fail = main(["resilience", "failures"])
    assert ret_fail == 0
    out_fail = capsys.readouterr().out
    assert "failures" in out_fail.lower()

    # Quarantine worker
    ret_q = main(["resilience", "quarantine", "w-cli-1"])
    assert ret_q == 0
    out_q = capsys.readouterr().out
    assert "quarantined successfully" in out_q

    # Unquarantine worker
    ret_uq = main(["resilience", "unquarantine", "w-cli-1"])
    assert ret_uq == 0
    out_uq = capsys.readouterr().out
    assert "unquarantined" in out_uq

    # Trigger recovery
    ret_rec = main(["resilience", "recover"])
    assert ret_rec == 0
    out_rec = capsys.readouterr().out
    assert "Self-healing sweep completed" in out_rec


# ==============================================================================
# 20. End-to-End Self-Healing & Job Reassignment Flow
# ==============================================================================


def test_end_to_end_self_healing_flow():
    """Simulate end-to-end worker degradation, quarantine, and recovery."""

    async def run_test():
        whm = WorkerHealthManager(
            degradation_threshold=1,
            quarantine_threshold=2,
            recovery_success_threshold=1,
        )

        w = "worker-e2e"
        assert await whm.is_worker_healthy(w) is True

        # First failure -> DEGRADED
        await whm.record_execution_failure(w, "Transient 502")
        prof = await whm.get_or_create_profile(w)
        assert prof.status == WorkerHealthStatus.DEGRADED

        # Second failure -> QUARANTINED
        await whm.record_execution_failure(w, "Timeout error")
        prof = await whm.get_or_create_profile(w)
        assert prof.status == WorkerHealthStatus.QUARANTINED
        assert await whm.is_worker_healthy(w) is False

        # Self-healing recovery triggered
        await whm.recover_worker(w)
        prof = await whm.get_or_create_profile(w)
        assert prof.status == WorkerHealthStatus.RECOVERING

        # Probe execution passes -> worker restored to HEALTHY
        await whm.record_execution_success(w)
        prof = await whm.get_or_create_profile(w)
        assert prof.status == WorkerHealthStatus.HEALTHY
        assert await whm.is_worker_healthy(w) is True

    asyncio.run(run_test())
