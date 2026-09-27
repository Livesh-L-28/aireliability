"""Production-grade SQLite persistence backend for distributed AI reliability.

Provides ACID transactions, index optimization, thread safety, graceful
schema migrations, and sensitive metadata sanitization without external
database servers.
"""

import asyncio
import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aireliability.core.models import RunResult, TestCase
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

SQLITE_SCHEMA_STATEMENTS = [
    # Schema version tracking
    """
    CREATE TABLE IF NOT EXISTS distributed_schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    );
    """,
    # Executions table
    """
    CREATE TABLE IF NOT EXISTS distributed_executions (
        execution_id TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        started_at TEXT,
        completed_at TEXT,
        total_jobs INTEGER NOT NULL DEFAULT 0,
        completed_jobs INTEGER NOT NULL DEFAULT 0,
        failed_jobs INTEGER NOT NULL DEFAULT 0,
        timed_out_jobs INTEGER NOT NULL DEFAULT 0,
        cancelled_jobs INTEGER NOT NULL DEFAULT 0,
        retry_count INTEGER NOT NULL DEFAULT 0,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    """,
    # Workers table
    """
    CREATE TABLE IF NOT EXISTS distributed_workers (
        worker_id TEXT PRIMARY KEY,
        execution_id TEXT,
        state TEXT NOT NULL,
        current_job_id TEXT,
        started_at TEXT NOT NULL,
        last_heartbeat TEXT NOT NULL,
        completed_jobs INTEGER NOT NULL DEFAULT 0,
        failed_jobs INTEGER NOT NULL DEFAULT 0,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    """,
    # Jobs table
    """
    CREATE TABLE IF NOT EXISTS distributed_jobs (
        job_id TEXT PRIMARY KEY,
        execution_id TEXT NOT NULL,
        test_id TEXT NOT NULL,
        status TEXT NOT NULL,
        priority INTEGER NOT NULL DEFAULT 0,
        attempt INTEGER NOT NULL DEFAULT 1,
        max_retries INTEGER NOT NULL DEFAULT 0,
        assigned_worker_id TEXT,
        created_at TEXT NOT NULL,
        timeout_seconds REAL,
        test_case_json TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    """,
    # Outcomes table
    """
    CREATE TABLE IF NOT EXISTS distributed_outcomes (
        outcome_id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL,
        execution_id TEXT NOT NULL,
        test_id TEXT NOT NULL,
        worker_id TEXT NOT NULL,
        status TEXT NOT NULL,
        attempt INTEGER NOT NULL DEFAULT 1,
        duration_ms REAL NOT NULL DEFAULT 0.0,
        run_result_json TEXT,
        error TEXT,
        error_type TEXT,
        retryable INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    """,
    # Failures table (Phase 26)
    """
    CREATE TABLE IF NOT EXISTS distributed_failures (
        failure_id TEXT PRIMARY KEY,
        execution_id TEXT,
        job_id TEXT,
        worker_id TEXT,
        provider_id TEXT,
        failure_type TEXT NOT NULL,
        severity TEXT NOT NULL,
        retryable INTEGER NOT NULL DEFAULT 1,
        timestamp TEXT NOT NULL,
        attempt INTEGER NOT NULL DEFAULT 1,
        error TEXT,
        error_type TEXT,
        trace_id TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    """,
    # Indexes for high performance querying
    (
        "CREATE INDEX IF NOT EXISTS idx_dist_jobs_exec "
        "ON distributed_jobs(execution_id);"
    ),
    "CREATE INDEX IF NOT EXISTS idx_dist_jobs_status ON distributed_jobs(status);",
    "CREATE INDEX IF NOT EXISTS idx_dist_jobs_test ON distributed_jobs(test_id);",
    (
        "CREATE INDEX IF NOT EXISTS idx_dist_workers_exec "
        "ON distributed_workers(execution_id);"
    ),
    "CREATE INDEX IF NOT EXISTS idx_dist_workers_state ON distributed_workers(state);",
    (
        "CREATE INDEX IF NOT EXISTS idx_dist_outcomes_exec "
        "ON distributed_outcomes(execution_id);"
    ),
    "CREATE INDEX IF NOT EXISTS idx_dist_outcomes_job ON distributed_outcomes(job_id);",
    (
        "CREATE INDEX IF NOT EXISTS idx_dist_outcomes_status "
        "ON distributed_outcomes(status);"
    ),
    (
        "CREATE INDEX IF NOT EXISTS idx_dist_failures_exec "
        "ON distributed_failures(execution_id);"
    ),
    # Multi-tenancy Indexes (Phase 27)
    (
        "CREATE INDEX IF NOT EXISTS idx_dist_jobs_created "
        "ON distributed_jobs(created_at);"
    ),
    (
        "CREATE INDEX IF NOT EXISTS idx_dist_exec_status "
        "ON distributed_executions(status, created_at);"
    ),
    # Security Tables & Indexes (Phase 28)
    """
    CREATE TABLE IF NOT EXISTS security_api_keys (
        key_id TEXT PRIMARY KEY,
        key_prefix TEXT NOT NULL,
        hashed_secret TEXT NOT NULL,
        salt TEXT NOT NULL,
        tenant_id TEXT NOT NULL DEFAULT 'default',
        project_id TEXT NOT NULL DEFAULT 'default',
        namespace TEXT NOT NULL DEFAULT 'default',
        name TEXT NOT NULL,
        roles_json TEXT NOT NULL DEFAULT '[]',
        permissions_json TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL,
        expires_at TEXT,
        revoked INTEGER NOT NULL DEFAULT 0,
        revoked_at TEXT,
        last_used_at TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_sec_keys_tenant ON security_api_keys(tenant_id);",
    """
    CREATE TABLE IF NOT EXISTS security_audit_events (
        event_id TEXT PRIMARY KEY,
        timestamp TEXT NOT NULL,
        principal_id TEXT NOT NULL,
        tenant_id TEXT NOT NULL DEFAULT 'default',
        project_id TEXT NOT NULL DEFAULT 'default',
        namespace TEXT NOT NULL DEFAULT 'default',
        action TEXT NOT NULL,
        resource TEXT NOT NULL,
        result TEXT NOT NULL,
        reason TEXT,
        request_id TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    """,
    (
        "CREATE INDEX IF NOT EXISTS idx_sec_audit_tenant "
        "ON security_audit_events(tenant_id);"
    ),
    "CREATE INDEX IF NOT EXISTS idx_sec_audit_action ON security_audit_events(action);",
    """
    CREATE TABLE IF NOT EXISTS security_replay_records (
        record_id TEXT PRIMARY KEY,
        request_id TEXT NOT NULL,
        nonce TEXT,
        principal_id TEXT NOT NULL,
        timestamp REAL NOT NULL
    );
    """,
    (
        "CREATE INDEX IF NOT EXISTS idx_sec_replay_req "
        "ON security_replay_records(request_id);"
    ),
    # Observability Tables & Indexes (Phase 29)
    """
    CREATE TABLE IF NOT EXISTS telemetry_events (
        event_id TEXT PRIMARY KEY,
        event_type TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        severity TEXT NOT NULL,
        source TEXT NOT NULL,
        tenant_id TEXT NOT NULL DEFAULT 'default',
        project_id TEXT NOT NULL DEFAULT 'default',
        namespace TEXT NOT NULL DEFAULT 'default',
        execution_id TEXT,
        job_id TEXT,
        worker_id TEXT,
        provider_id TEXT,
        trace_id TEXT,
        span_id TEXT,
        parent_span_id TEXT,
        duration_ms REAL,
        status TEXT NOT NULL,
        attributes_json TEXT NOT NULL DEFAULT '{}'
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_telem_tenant ON telemetry_events(tenant_id);",
    "CREATE INDEX IF NOT EXISTS idx_telem_type ON telemetry_events(event_type);",
    "CREATE INDEX IF NOT EXISTS idx_telem_trace ON telemetry_events(trace_id);",
    """
    CREATE TABLE IF NOT EXISTS trace_records (
        trace_id TEXT PRIMARY KEY,
        root_span_id TEXT,
        tenant_id TEXT NOT NULL DEFAULT 'default',
        project_id TEXT NOT NULL DEFAULT 'default',
        namespace TEXT NOT NULL DEFAULT 'default',
        execution_id TEXT,
        job_id TEXT,
        start_time TEXT NOT NULL,
        end_time TEXT,
        status TEXT NOT NULL,
        attributes_json TEXT NOT NULL DEFAULT '{}',
        spans_json TEXT NOT NULL DEFAULT '[]'
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_traces_tenant ON trace_records(tenant_id);",
    """
    CREATE TABLE IF NOT EXISTS operational_incidents (
        incident_id TEXT PRIMARY KEY,
        severity TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        detected_at TEXT NOT NULL,
        acknowledged_at TEXT,
        resolved_at TEXT,
        tenant_id TEXT NOT NULL DEFAULT 'default',
        trace_ids_json TEXT NOT NULL DEFAULT '[]',
        execution_ids_json TEXT NOT NULL DEFAULT '[]',
        affected_workers_json TEXT NOT NULL DEFAULT '[]',
        affected_providers_json TEXT NOT NULL DEFAULT '[]',
        related_events_json TEXT NOT NULL DEFAULT '[]',
        status TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    """,
    (
        "CREATE INDEX IF NOT EXISTS idx_incidents_tenant "
        "ON operational_incidents(tenant_id);"
    ),
    (
        "CREATE INDEX IF NOT EXISTS idx_incidents_status "
        "ON operational_incidents(status);"
    ),
]


class SQLiteDistributedStorage:
    """Thread-safe and process-safe SQLite persistence for distributed reliability."""

    def __init__(
        self,
        db_path: str | Path = ":memory:",
        *,
        sanitizer: SanitizationPolicy | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.db_path = str(db_path)
        self.sanitizer = sanitizer or SanitizationPolicy()
        self.timeout = timeout
        self._is_memory = self.db_path == ":memory:"

        if not self._is_memory:
            Path(self.db_path).resolve().parent.mkdir(parents=True, exist_ok=True)
            self._shared_conn: sqlite3.Connection | None = None
        else:
            # Persistent in-memory connection across queries in the same process
            self._shared_conn = sqlite3.connect(
                ":memory:", timeout=self.timeout, check_same_thread=False
            )
            self._shared_conn.row_factory = sqlite3.Row

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._is_memory and self._shared_conn is not None:
            return self._shared_conn
        conn = sqlite3.connect(
            self.db_path, timeout=self.timeout, check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for high concurrency
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self._get_connection()
        try:
            yield conn
        finally:
            if not self._is_memory:
                conn.close()

    def _init_db(self) -> None:
        with self._connection() as conn, conn:
            for stmt in SQLITE_SCHEMA_STATEMENTS:
                conn.execute(stmt)
            conn.execute(
                "INSERT OR IGNORE INTO distributed_schema_migrations "
                "(version, applied_at) VALUES (1, ?)",
                (datetime.now(UTC).isoformat(),),
            )

    # --- Job Operations ---

    def save_job(self, job: ReliabilityJob) -> None:
        sanitized_meta = self.sanitizer.sanitize(job.metadata)
        test_case_json = job.test_case.model_dump_json()
        with self._connection() as conn, conn:
            conn.execute(
                """
                    INSERT INTO distributed_jobs (
                        job_id, execution_id, test_id, status, priority, attempt,
                        max_retries, assigned_worker_id, created_at, timeout_seconds,
                        test_case_json, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(job_id) DO UPDATE SET
                        status = excluded.status,
                        attempt = excluded.attempt,
                        assigned_worker_id = excluded.assigned_worker_id,
                        metadata_json = excluded.metadata_json;
                    """,
                (
                    job.job_id,
                    job.execution_id,
                    job.test_id,
                    job.status.value,
                    job.priority,
                    job.attempt,
                    job.max_retries,
                    job.assigned_worker_id,
                    job.created_at.isoformat(),
                    job.timeout_seconds,
                    test_case_json,
                    json.dumps(sanitized_meta),
                ),
            )

    def get_job(self, job_id: str) -> ReliabilityJob | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM distributed_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_job(row)

    def update_job(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        worker_id: str | None = None,
        attempt: int | None = None,
    ) -> ReliabilityJob:
        with self._connection() as conn, conn:
            row = conn.execute(
                "SELECT * FROM distributed_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if not row:
                raise KeyError(f"Job with ID '{job_id}' not found.")

            current_status = JobStatus(row["status"])
            if status is not None:
                validate_job_transition(current_status, status)
                new_status = status.value
            else:
                new_status = current_status.value

            new_worker = (
                worker_id if worker_id is not None else row["assigned_worker_id"]
            )
            new_attempt = attempt if attempt is not None else row["attempt"]

            conn.execute(
                """
                    UPDATE distributed_jobs
                    SET status = ?, assigned_worker_id = ?, attempt = ?
                    WHERE job_id = ?
                    """,
                (new_status, new_worker, new_attempt, job_id),
            )
            updated_row = conn.execute(
                "SELECT * FROM distributed_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            return self._row_to_job(updated_row)

    def list_jobs(
        self,
        execution_id: str | None = None,
        status: JobStatus | None = None,
        tenant_id: str | None = None,
    ) -> list[ReliabilityJob]:
        query = "SELECT * FROM distributed_jobs WHERE 1=1"
        params: list[Any] = []
        if execution_id:
            query += " AND execution_id = ?"
            params.append(execution_id)
        if status:
            query += " AND status = ?"
            params.append(status.value)
        query += " ORDER BY priority DESC, created_at ASC"

        with self._connection() as conn:
            rows = conn.execute(query, params).fetchall()
            jobs = [self._row_to_job(r) for r in rows]
            if tenant_id:
                jobs = [j for j in jobs if j.tenant_id == tenant_id]
            return jobs

    def _row_to_job(self, row: sqlite3.Row) -> ReliabilityJob:
        test_case = TestCase.model_validate_json(row["test_case_json"])
        meta = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        return ReliabilityJob(
            job_id=row["job_id"],
            execution_id=row["execution_id"],
            test_case=test_case,
            priority=row["priority"],
            attempt=row["attempt"],
            max_retries=row["max_retries"],
            timeout_seconds=row["timeout_seconds"],
            created_at=datetime.fromisoformat(row["created_at"]),
            status=JobStatus(row["status"]),
            assigned_worker_id=row["assigned_worker_id"],
            metadata=meta,
        )

    # --- Outcome Operations ---

    def save_outcome(self, outcome: JobExecutionOutcome) -> None:
        sanitized_meta = self.sanitizer.sanitize(outcome.metadata)
        run_res_json = (
            outcome.run_result.model_dump_json() if outcome.run_result else None
        )
        outcome_id = f"out_{outcome.job_id}_{outcome.attempt}"

        with self._connection() as conn, conn:
            # Idempotency check: don't overwrite if existing attempt is newer
            existing = conn.execute(
                "SELECT attempt FROM distributed_outcomes "
                "WHERE job_id = ? ORDER BY attempt DESC LIMIT 1",
                (outcome.job_id,),
            ).fetchone()
            if existing and existing["attempt"] > outcome.attempt:
                return

            conn.execute(
                """
                INSERT INTO distributed_outcomes (
                    outcome_id, job_id, execution_id, test_id, worker_id, status,
                    attempt, duration_ms, run_result_json, error, error_type,
                    retryable, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(outcome_id) DO UPDATE SET
                    status = excluded.status,
                    duration_ms = excluded.duration_ms,
                    run_result_json = excluded.run_result_json,
                    error = excluded.error,
                    error_type = excluded.error_type,
                    metadata_json = excluded.metadata_json;
                """,
                (
                    outcome_id,
                    outcome.job_id,
                    outcome.execution_id,
                    outcome.test_id,
                    outcome.worker_id,
                    outcome.status.value,
                    outcome.attempt,
                    outcome.duration_ms or 0.0,
                    run_res_json,
                    outcome.error,
                    outcome.error_type,
                    1 if outcome.retryable else 0,
                    (outcome.completed_at or outcome.started_at).isoformat(),
                    json.dumps(sanitized_meta),
                ),
            )
            # Update corresponding job status
            conn.execute(
                "UPDATE distributed_jobs SET status = ? WHERE job_id = ?",
                (outcome.status.value, outcome.job_id),
            )

    def get_outcome(self, job_id: str) -> JobExecutionOutcome | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM distributed_outcomes "
                "WHERE job_id = ? ORDER BY attempt DESC LIMIT 1",
                (job_id,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_outcome(row)

    def list_outcomes(
        self, execution_id: str | None = None, tenant_id: str | None = None
    ) -> list[JobExecutionOutcome]:
        query = "SELECT * FROM distributed_outcomes WHERE 1=1"
        params: list[Any] = []
        if execution_id:
            query += " AND execution_id = ?"
            params.append(execution_id)
        query += " ORDER BY created_at ASC"

        with self._connection() as conn:
            rows = conn.execute(query, params).fetchall()
            outcomes = [self._row_to_outcome(r) for r in rows]
            if tenant_id:
                outcomes = [
                    o
                    for o in outcomes
                    if o.metadata.get("tenant_id", "default") == tenant_id
                ]
            return outcomes

    def _row_to_outcome(self, row: sqlite3.Row) -> JobExecutionOutcome:
        run_res = (
            RunResult.model_validate_json(row["run_result_json"])
            if row["run_result_json"]
            else None
        )
        meta = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        ts = datetime.fromisoformat(row["created_at"])
        return JobExecutionOutcome(
            job_id=row["job_id"],
            execution_id=row["execution_id"],
            test_id=row["test_id"],
            worker_id=row["worker_id"],
            status=JobStatus(row["status"]),
            attempt=row["attempt"],
            run_result=run_res,
            started_at=ts,
            completed_at=ts,
            duration_ms=row["duration_ms"],
            error=row["error"],
            error_type=row["error_type"],
            retryable=bool(row["retryable"]),
            metadata=meta,
        )

    # --- Execution Operations ---

    def save_execution(self, execution: ExecutionRecord) -> None:
        sanitized_meta = self.sanitizer.sanitize(execution.metadata)
        with self._connection() as conn, conn:
            conn.execute(
                """
                    INSERT INTO distributed_executions (
                        execution_id, status, created_at, started_at, completed_at,
                        total_jobs, completed_jobs, failed_jobs, timed_out_jobs,
                        cancelled_jobs, retry_count, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(execution_id) DO UPDATE SET
                        status = excluded.status,
                        started_at = excluded.started_at,
                        completed_at = excluded.completed_at,
                        total_jobs = excluded.total_jobs,
                        completed_jobs = excluded.completed_jobs,
                        failed_jobs = excluded.failed_jobs,
                        timed_out_jobs = excluded.timed_out_jobs,
                        cancelled_jobs = excluded.cancelled_jobs,
                        retry_count = excluded.retry_count,
                        metadata_json = excluded.metadata_json;
                    """,
                (
                    execution.execution_id,
                    execution.status.value,
                    execution.created_at.isoformat(),
                    execution.started_at.isoformat() if execution.started_at else None,
                    execution.completed_at.isoformat()
                    if execution.completed_at
                    else None,
                    execution.total_jobs,
                    execution.completed_jobs,
                    execution.failed_jobs,
                    execution.timed_out_jobs,
                    execution.cancelled_jobs,
                    execution.retry_count,
                    json.dumps(sanitized_meta),
                ),
            )

    def get_execution(self, execution_id: str) -> ExecutionRecord | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM distributed_executions WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_execution(row)

    def list_executions(
        self,
        status: ExecutionStatusRecord | None = None,
        tenant_id: str | None = None,
    ) -> list[ExecutionRecord]:
        query = "SELECT * FROM distributed_executions WHERE 1=1"
        params: list[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status.value)
        query += " ORDER BY created_at DESC"

        with self._connection() as conn:
            rows = conn.execute(query, params).fetchall()
            execs = [self._row_to_execution(r) for r in rows]
            if tenant_id:
                execs = [e for e in execs if e.tenant_id == tenant_id]
            return execs

    def delete_execution(self, execution_id: str) -> bool:
        with self._connection() as conn, conn:
            row = conn.execute(
                "SELECT execution_id FROM distributed_executions "
                "WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
            if not row:
                return False
            conn.execute(
                "DELETE FROM distributed_executions WHERE execution_id = ?",
                (execution_id,),
            )
            conn.execute(
                "DELETE FROM distributed_jobs WHERE execution_id = ?",
                (execution_id,),
            )
            conn.execute(
                "DELETE FROM distributed_outcomes WHERE execution_id = ?",
                (execution_id,),
            )
            conn.execute(
                "DELETE FROM distributed_workers WHERE execution_id = ?",
                (execution_id,),
            )
            return True

    def _row_to_execution(self, row: sqlite3.Row) -> ExecutionRecord:
        meta = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        return ExecutionRecord(
            execution_id=row["execution_id"],
            status=ExecutionStatusRecord(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=datetime.fromisoformat(row["started_at"])
            if row["started_at"]
            else None,
            completed_at=datetime.fromisoformat(row["completed_at"])
            if row["completed_at"]
            else None,
            total_jobs=row["total_jobs"],
            completed_jobs=row["completed_jobs"],
            failed_jobs=row["failed_jobs"],
            timed_out_jobs=row["timed_out_jobs"],
            cancelled_jobs=row["cancelled_jobs"],
            retry_count=row["retry_count"],
            metadata=meta,
        )

    # --- Worker Operations ---

    def save_worker(self, worker: PersistentWorkerRecord) -> None:
        sanitized_meta = self.sanitizer.sanitize(worker.metadata)
        with self._connection() as conn, conn:
            existing = conn.execute(
                "SELECT state FROM distributed_workers WHERE worker_id = ?",
                (worker.worker_id,),
            ).fetchone()
            if existing:
                validate_worker_transition(WorkerState(existing["state"]), worker.state)

            conn.execute(
                """
                    INSERT INTO distributed_workers (
                        worker_id, execution_id, state, current_job_id, started_at,
                        last_heartbeat, completed_jobs, failed_jobs, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(worker_id) DO UPDATE SET
                        execution_id = excluded.execution_id,
                        state = excluded.state,
                        current_job_id = excluded.current_job_id,
                        last_heartbeat = excluded.last_heartbeat,
                        completed_jobs = excluded.completed_jobs,
                        failed_jobs = excluded.failed_jobs,
                        metadata_json = excluded.metadata_json;
                    """,
                (
                    worker.worker_id,
                    worker.execution_id,
                    worker.state.value,
                    worker.current_job_id,
                    worker.started_at.isoformat(),
                    worker.last_heartbeat.isoformat(),
                    worker.completed_jobs,
                    worker.failed_jobs,
                    json.dumps(sanitized_meta),
                ),
            )

    def get_worker(self, worker_id: str) -> PersistentWorkerRecord | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM distributed_workers WHERE worker_id = ?", (worker_id,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_worker(row)

    def list_workers(
        self,
        execution_id: str | None = None,
        state: WorkerState | None = None,
        tenant_id: str | None = None,
    ) -> list[PersistentWorkerRecord]:
        query = "SELECT * FROM distributed_workers WHERE 1=1"
        params: list[Any] = []
        if execution_id:
            query += " AND execution_id = ?"
            params.append(execution_id)
        if state:
            query += " AND state = ?"
            params.append(state.value)
        query += " ORDER BY started_at ASC"

        with self._connection() as conn:
            rows = conn.execute(query, params).fetchall()
            workers = [self._row_to_worker(r) for r in rows]
            if tenant_id:
                workers = [
                    w
                    for w in workers
                    if w.metadata.get("tenant_id", "default") == tenant_id
                    or tenant_id in w.metadata.get("supported_tenants", [])
                ]
            return workers

    def _row_to_worker(self, row: sqlite3.Row) -> PersistentWorkerRecord:
        meta = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        return PersistentWorkerRecord(
            worker_id=row["worker_id"],
            execution_id=row["execution_id"],
            state=WorkerState(row["state"]),
            current_job_id=row["current_job_id"],
            started_at=datetime.fromisoformat(row["started_at"]),
            last_heartbeat=datetime.fromisoformat(row["last_heartbeat"]),
            completed_jobs=row["completed_jobs"],
            failed_jobs=row["failed_jobs"],
            metadata=meta,
        )

    # --- Coordination & Recovery ---

    def claim_job(self, job_id: str, worker_id: str) -> bool:
        """Atomically claim a pending or retrying job using transactional write lock."""
        with self._connection() as conn, conn:
            row = conn.execute(
                "SELECT status FROM distributed_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if not row or row["status"] not in (
                JobStatus.PENDING.value,
                JobStatus.RETRYING.value,
            ):
                return False

            cursor = conn.execute(
                """
                    UPDATE distributed_jobs
                    SET status = ?, assigned_worker_id = ?
                    WHERE job_id = ? AND (status = ? OR status = ?)
                    """,
                (
                    JobStatus.RUNNING.value,
                    worker_id,
                    job_id,
                    JobStatus.PENDING.value,
                    JobStatus.RETRYING.value,
                ),
            )
            return cursor.rowcount > 0

    def detect_stale_workers(
        self, timeout_seconds: float = 30.0, execution_id: str | None = None
    ) -> list[PersistentWorkerRecord]:
        now = datetime.now(UTC)
        workers = self.list_workers(execution_id=execution_id)
        stale: list[PersistentWorkerRecord] = []
        for w in workers:
            if w.state == WorkerState.STOPPED:
                continue
            if (now - w.last_heartbeat).total_seconds() > timeout_seconds:
                stale.append(w)
        return stale

    def recover_execution(
        self, execution_id: str, stale_timeout_seconds: float = 30.0
    ) -> ExecutionRecoverySummary:
        stale_workers = self.detect_stale_workers(
            timeout_seconds=stale_timeout_seconds, execution_id=execution_id
        )
        stale_ids = {w.worker_id for w in stale_workers}

        recovered_jobs: list[str] = []
        already_completed: list[str] = []
        requeued_jobs: list[str] = []
        failed_recovery_jobs: list[str] = []

        jobs = self.list_jobs(execution_id=execution_id)
        for job in jobs:
            if job.status == JobStatus.COMPLETED:
                already_completed.append(job.job_id)
            elif (
                job.status in (JobStatus.RUNNING, JobStatus.PENDING)
                and job.assigned_worker_id in stale_ids
            ):
                recovered_jobs.append(job.job_id)
                new_attempt = job.attempt + 1
                if new_attempt <= job.max_retries + 1:
                    new_meta = {
                        **job.metadata,
                        "recovered_from_worker": job.assigned_worker_id,
                        "recovery_timestamp": datetime.now(UTC).isoformat(),
                    }
                    with self._connection() as conn, conn:
                        conn.execute(
                            """
                                UPDATE distributed_jobs
                                SET status = ?, assigned_worker_id = NULL,
                                    attempt = ?, metadata_json = ?
                                WHERE job_id = ?
                                """,
                            (
                                JobStatus.PENDING.value,
                                new_attempt,
                                json.dumps(new_meta),
                                job.job_id,
                            ),
                        )
                    requeued_jobs.append(job.job_id)
                else:
                    new_meta = {
                        **job.metadata,
                        "recovery_failure": "max_retries_exceeded_on_recovery",
                    }
                    with self._connection() as conn, conn:
                        conn.execute(
                            """
                                UPDATE distributed_jobs
                                SET status = ?, metadata_json = ?
                                WHERE job_id = ?
                                """,
                            (
                                JobStatus.FAILED.value,
                                json.dumps(new_meta),
                                job.job_id,
                            ),
                        )
                    failed_recovery_jobs.append(job.job_id)

        # Mark stale workers as FAILED
        with self._connection() as conn, conn:
            for sid in stale_ids:
                conn.execute(
                    "UPDATE distributed_workers SET state = ? WHERE worker_id = ?",
                    (WorkerState.FAILED.value, sid),
                )

        return ExecutionRecoverySummary(
            execution_id=execution_id,
            recovered_jobs=recovered_jobs,
            already_completed_jobs=already_completed,
            stale_workers=list(stale_ids),
            requeued_jobs=requeued_jobs,
            failed_recovery_jobs=failed_recovery_jobs,
        )

    def get_failed_jobs(
        self, execution_id: str | None = None, tenant_id: str | None = None
    ) -> list[JobExecutionOutcome]:
        query = "SELECT * FROM distributed_outcomes WHERE status IN (?, ?)"
        params: list[Any] = [JobStatus.FAILED.value, JobStatus.TIMED_OUT.value]
        if execution_id:
            query += " AND execution_id = ?"
            params.append(execution_id)
        query += " ORDER BY created_at ASC"

        with self._connection() as conn:
            rows = conn.execute(query, params).fetchall()
            outcomes = [self._row_to_outcome(r) for r in rows]
            if tenant_id:
                outcomes = [
                    o
                    for o in outcomes
                    if o.metadata.get("tenant_id", "default") == tenant_id
                ]
            return outcomes

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
        return self.get_failed_jobs(execution_id, tenant_id=tenant_id)

    # --- Async Support ---

    async def asave_job(self, job: ReliabilityJob) -> None:
        await asyncio.to_thread(self.save_job, job)

    async def aget_job(self, job_id: str) -> ReliabilityJob | None:
        return await asyncio.to_thread(self.get_job, job_id)

    async def aupdate_job(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        worker_id: str | None = None,
        attempt: int | None = None,
    ) -> ReliabilityJob:
        return await asyncio.to_thread(
            self.update_job,
            job_id,
            status=status,
            worker_id=worker_id,
            attempt=attempt,
        )

    async def alist_jobs(
        self, execution_id: str | None = None, status: JobStatus | None = None
    ) -> list[ReliabilityJob]:
        return await asyncio.to_thread(self.list_jobs, execution_id, status)

    async def asave_outcome(self, outcome: JobExecutionOutcome) -> None:
        await asyncio.to_thread(self.save_outcome, outcome)

    async def aget_outcome(self, job_id: str) -> JobExecutionOutcome | None:
        return await asyncio.to_thread(self.get_outcome, job_id)

    async def alist_outcomes(
        self, execution_id: str | None = None
    ) -> list[JobExecutionOutcome]:
        return await asyncio.to_thread(self.list_outcomes, execution_id)

    async def asave_execution(self, execution: ExecutionRecord) -> None:
        await asyncio.to_thread(self.save_execution, execution)

    async def aget_execution(self, execution_id: str) -> ExecutionRecord | None:
        return await asyncio.to_thread(self.get_execution, execution_id)

    async def aclaim_job(self, job_id: str, worker_id: str) -> bool:
        return await asyncio.to_thread(self.claim_job, job_id, worker_id)

    # --- Resilience Operations (Phase 26) ---

    def save_failure(self, failure: Any) -> None:
        """Persist a detailed failure record to SQLite with sanitized metadata."""
        meta = getattr(failure, "metadata", {})
        sanitized_meta = self.sanitizer.sanitize(meta)
        meta_json = json.dumps(sanitized_meta)

        with self._connection() as conn, conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO distributed_failures (
                    failure_id, execution_id, job_id, worker_id, provider_id,
                    failure_type, severity, retryable, timestamp, attempt,
                    error, error_type, trace_id, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    getattr(failure, "failure_id", ""),
                    getattr(failure, "execution_id", None),
                    getattr(failure, "job_id", None),
                    getattr(failure, "worker_id", None),
                    getattr(failure, "provider_id", None),
                    str(getattr(failure, "failure_type", "unknown")),
                    str(getattr(failure, "severity", "high")),
                    1 if getattr(failure, "retryable", True) else 0,
                    getattr(failure, "timestamp", datetime.now(UTC)).isoformat(),
                    getattr(failure, "attempt", 1),
                    getattr(failure, "error", None),
                    getattr(failure, "error_type", None),
                    getattr(failure, "trace_id", None),
                    meta_json,
                ),
            )

    def list_failures(
        self,
        execution_id: str | None = None,
        tenant_id: str | None = None,
    ) -> list[Any]:
        """List persisted detailed failure records."""
        from aireliability.core.models import FailureSeverity
        from aireliability.resilience.models import (
            DetailedFailureRecord,
            ResilienceFailureCategory,
        )

        query = "SELECT * FROM distributed_failures"
        clauses: list[str] = []
        params: list[Any] = []
        if execution_id:
            clauses.append("execution_id = ?")
            params.append(execution_id)
        if tenant_id:
            clauses.append("json_extract(metadata_json, '$.tenant_id') = ?")
            params.append(tenant_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY timestamp ASC"

        with self._connection() as conn:
            rows = conn.execute(query, params).fetchall()
            results = []
            for r in rows:
                meta = json.loads(r["metadata_json"]) if r["metadata_json"] else {}
                try:
                    ftype = ResilienceFailureCategory(r["failure_type"])
                except Exception:
                    ftype = ResilienceFailureCategory.UNKNOWN_FAILURE
                try:
                    sev = FailureSeverity(r["severity"])
                except Exception:
                    sev = FailureSeverity.HIGH

                results.append(
                    DetailedFailureRecord(
                        failure_id=r["failure_id"],
                        execution_id=r["execution_id"],
                        job_id=r["job_id"],
                        worker_id=r["worker_id"],
                        provider_id=r["provider_id"],
                        failure_type=ftype,
                        severity=sev,
                        retryable=bool(r["retryable"]),
                        timestamp=datetime.fromisoformat(r["timestamp"]),
                        attempt=r["attempt"],
                        error=r["error"],
                        error_type=r["error_type"],
                        trace_id=r["trace_id"],
                        metadata=meta,
                    )
                )
            return results

    # --- Security Operations (Phase 28) ---

    def save_api_key(self, api_key: Any) -> None:
        """Persist or update an APIKey record with sanitized metadata."""

        sanitized_meta = self.sanitizer.sanitize(api_key.metadata)
        roles_json = json.dumps(list(api_key.roles))
        perms_json = json.dumps(list(api_key.permissions))
        created_str = (
            api_key.created_at.isoformat()
            if hasattr(api_key.created_at, "isoformat")
            else str(api_key.created_at)
        )
        expires_str = (
            api_key.expires_at.isoformat()
            if api_key.expires_at and hasattr(api_key.expires_at, "isoformat")
            else (str(api_key.expires_at) if api_key.expires_at else None)
        )
        revoked_str = (
            api_key.revoked_at.isoformat()
            if api_key.revoked_at and hasattr(api_key.revoked_at, "isoformat")
            else (str(api_key.revoked_at) if api_key.revoked_at else None)
        )
        last_used_str = (
            api_key.last_used_at.isoformat()
            if api_key.last_used_at and hasattr(api_key.last_used_at, "isoformat")
            else (str(api_key.last_used_at) if api_key.last_used_at else None)
        )

        with self._connection() as conn, conn:
            conn.execute(
                """
                INSERT INTO security_api_keys (
                    key_id, key_prefix, hashed_secret, salt, tenant_id, project_id,
                    namespace, name, roles_json, permissions_json, created_at,
                    expires_at, revoked, revoked_at, last_used_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(key_id) DO UPDATE SET
                    revoked = excluded.revoked,
                    revoked_at = excluded.revoked_at,
                    last_used_at = excluded.last_used_at,
                    metadata_json = excluded.metadata_json;
                """,
                (
                    api_key.key_id,
                    api_key.key_prefix,
                    api_key.hashed_secret,
                    api_key.salt,
                    api_key.tenant_id,
                    api_key.project_id,
                    api_key.namespace,
                    api_key.name,
                    roles_json,
                    perms_json,
                    created_str,
                    expires_str,
                    1 if api_key.revoked else 0,
                    revoked_str,
                    last_used_str,
                    json.dumps(sanitized_meta),
                ),
            )

    def get_api_key(self, key_id: str) -> Any | None:
        """Retrieve an APIKey record by key_id."""

        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM security_api_keys WHERE key_id = ?", (key_id,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_api_key(row)

    def list_api_keys(self, tenant_id: str | None = None) -> list[Any]:
        """List API keys, optionally filtered by tenant ID."""
        query = "SELECT * FROM security_api_keys"
        params: list[Any] = []
        if tenant_id:
            query += " WHERE tenant_id = ?"
            params.append(tenant_id)
        query += " ORDER BY created_at DESC"

        with self._connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_api_key(r) for r in rows]

    def _row_to_api_key(self, r: Any) -> Any:
        from aireliability.security.api_keys import APIKey

        meta = json.loads(r["metadata_json"]) if r["metadata_json"] else {}
        roles = json.loads(r["roles_json"]) if r["roles_json"] else []
        perms = json.loads(r["permissions_json"]) if r["permissions_json"] else []
        return APIKey(
            key_id=r["key_id"],
            key_prefix=r["key_prefix"],
            hashed_secret=r["hashed_secret"],
            salt=r["salt"],
            tenant_id=r["tenant_id"],
            project_id=r["project_id"],
            namespace=r["namespace"],
            name=r["name"],
            roles=roles,
            permissions=perms,
            created_at=datetime.fromisoformat(r["created_at"]),
            expires_at=datetime.fromisoformat(r["expires_at"])
            if r["expires_at"]
            else None,
            revoked=bool(r["revoked"]),
            revoked_at=datetime.fromisoformat(r["revoked_at"])
            if r["revoked_at"]
            else None,
            last_used_at=datetime.fromisoformat(r["last_used_at"])
            if r["last_used_at"]
            else None,
            metadata=meta,
        )

    def save_audit_event(self, event: Any) -> None:
        """Persist a security audit event with sanitized metadata."""
        sanitized_meta = self.sanitizer.sanitize(event.metadata)
        ts_str = (
            event.timestamp.isoformat()
            if hasattr(event.timestamp, "isoformat")
            else str(event.timestamp)
        )
        with self._connection() as conn, conn:
            conn.execute(
                """
                INSERT INTO security_audit_events (
                    event_id, timestamp, principal_id, tenant_id, project_id,
                    namespace, action, resource, result, reason, request_id,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO NOTHING;
                """,
                (
                    event.event_id,
                    ts_str,
                    event.principal_id,
                    event.tenant_id,
                    event.project_id,
                    event.namespace,
                    event.action,
                    event.resource,
                    event.result,
                    event.reason,
                    event.request_id,
                    json.dumps(sanitized_meta),
                ),
            )

    def list_audit_events(
        self,
        tenant_id: str | None = None,
        principal_id: str | None = None,
        action: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        """List audit events matching filters."""
        from aireliability.security.audit import AuditEvent

        query = "SELECT * FROM security_audit_events"
        clauses: list[str] = []
        params: list[Any] = []
        if tenant_id:
            clauses.append("tenant_id = ?")
            params.append(tenant_id)
        if principal_id:
            clauses.append("principal_id = ?")
            params.append(principal_id)
        if action:
            clauses.append("action = ?")
            params.append(action)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._connection() as conn:
            rows = conn.execute(query, params).fetchall()
            results = []
            for r in rows:
                meta = json.loads(r["metadata_json"]) if r["metadata_json"] else {}
                results.append(
                    AuditEvent(
                        event_id=r["event_id"],
                        timestamp=datetime.fromisoformat(r["timestamp"]),
                        principal_id=r["principal_id"],
                        tenant_id=r["tenant_id"],
                        project_id=r["project_id"],
                        namespace=r["namespace"],
                        action=r["action"],
                        resource=r["resource"],
                        result=r["result"],
                        reason=r["reason"],
                        request_id=r["request_id"],
                        metadata=meta,
                    )
                )
            return results

    def save_replay_record(self, record: Any) -> None:
        """Persist a replay record."""
        with self._connection() as conn, conn:
            conn.execute(
                """
                INSERT INTO security_replay_records (
                    record_id, request_id, nonce, principal_id, timestamp
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(record_id) DO NOTHING;
                """,
                (
                    record.record_id,
                    record.request_id,
                    record.nonce,
                    record.principal_id,
                    record.timestamp,
                ),
            )

    # --- Observability Operations (Phase 29) ---

    def save_telemetry_event(self, event: Any) -> None:
        """Persist a telemetry event."""
        attrs = getattr(event, "attributes", {})
        sanitized_attrs = self.sanitizer.sanitize(attrs)
        ts = getattr(event, "timestamp", datetime.now(UTC)).isoformat()
        with self._connection() as conn, conn:
            conn.execute(
                """
                INSERT INTO telemetry_events (
                    event_id, event_type, timestamp, severity, source,
                    tenant_id, project_id, namespace, execution_id, job_id,
                    worker_id, provider_id, trace_id, span_id, parent_span_id,
                    duration_ms, status, attributes_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    status=excluded.status,
                    attributes_json=excluded.attributes_json;
                """,
                (
                    event.event_id,
                    event.event_type,
                    ts,
                    event.severity,
                    event.source,
                    event.tenant_id,
                    event.project_id,
                    event.namespace,
                    event.execution_id,
                    event.job_id,
                    event.worker_id,
                    event.provider_id,
                    event.trace_id,
                    event.span_id,
                    event.parent_span_id,
                    event.duration_ms,
                    event.status,
                    json.dumps(sanitized_attrs),
                ),
            )

    def list_telemetry_events(
        self,
        tenant_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        """List telemetry events matching filters."""
        query = "SELECT * FROM telemetry_events"
        params: list[Any] = []
        clauses: list[str] = []

        if tenant_id:
            clauses.append("tenant_id = ?")
            params.append(tenant_id)
        if event_type:
            clauses.append("event_type LIKE ?")
            params.append(f"{event_type}%")

        if clauses:
            query += " WHERE " + " AND ".join(clauses)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        from aireliability.observability.models import TelemetryEvent

        results = []
        with self._connection() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            for r in rows:
                attrs = json.loads(r["attributes_json"])
                results.append(
                    TelemetryEvent(
                        event_id=r["event_id"],
                        event_type=r["event_type"],
                        timestamp=datetime.fromisoformat(r["timestamp"]),
                        severity=r["severity"],
                        source=r["source"],
                        tenant_id=r["tenant_id"],
                        project_id=r["project_id"],
                        namespace=r["namespace"],
                        execution_id=r["execution_id"],
                        job_id=r["job_id"],
                        worker_id=r["worker_id"],
                        provider_id=r["provider_id"],
                        trace_id=r["trace_id"],
                        span_id=r["span_id"],
                        parent_span_id=r["parent_span_id"],
                        duration_ms=r["duration_ms"],
                        status=r["status"],
                        attributes=attrs,
                    )
                )
        return results

    def save_trace_record(self, trace: Any) -> None:
        """Persist a trace record."""
        attrs = getattr(trace, "attributes", {})
        sanitized_attrs = self.sanitizer.sanitize(attrs)
        st = getattr(trace, "start_time", datetime.now(UTC)).isoformat()
        et = (
            getattr(trace, "end_time", None).isoformat()
            if getattr(trace, "end_time", None)
            else None
        )
        spans_json = json.dumps(
            [
                s.model_dump(mode="json") if hasattr(s, "model_dump") else s
                for s in getattr(trace, "spans", [])
            ]
        )
        with self._connection() as conn, conn:
            conn.execute(
                """
                INSERT INTO trace_records (
                    trace_id, root_span_id, tenant_id, project_id, namespace,
                    execution_id, job_id, start_time, end_time, status,
                    attributes_json, spans_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trace_id) DO UPDATE SET
                    end_time=excluded.end_time,
                    status=excluded.status,
                    attributes_json=excluded.attributes_json,
                    spans_json=excluded.spans_json;
                """,
                (
                    trace.trace_id,
                    trace.root_span_id,
                    trace.tenant_id,
                    trace.project_id,
                    trace.namespace,
                    trace.execution_id,
                    trace.job_id,
                    st,
                    et,
                    trace.status,
                    json.dumps(sanitized_attrs),
                    spans_json,
                ),
            )

    def get_trace_record(self, trace_id: str) -> Any | None:
        """Retrieve a trace record by ID."""
        from aireliability.observability.models import (
            SpanKind,
            SpanRecord,
            TraceRecord,
        )

        with self._connection() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM trace_records WHERE trace_id = ?", (trace_id,)
            ).fetchone()
            if not row:
                return None
            spans_raw = json.loads(row["spans_json"])
            spans = []
            for s in spans_raw:
                st = datetime.fromisoformat(s["start_time"])
                et = (
                    datetime.fromisoformat(s["end_time"]) if s.get("end_time") else None
                )
                spans.append(
                    SpanRecord(
                        span_id=s["span_id"],
                        trace_id=s["trace_id"],
                        parent_span_id=s.get("parent_span_id"),
                        name=s["name"],
                        start_time=st,
                        end_time=et,
                        duration_ms=s.get("duration_ms"),
                        status=s.get("status", "ok"),
                        kind=SpanKind(s.get("kind", "INTERNAL")),
                        attributes=s.get("attributes", {}),
                        events=s.get("events", []),
                    )
                )
            return TraceRecord(
                trace_id=row["trace_id"],
                root_span_id=row["root_span_id"],
                tenant_id=row["tenant_id"],
                project_id=row["project_id"],
                namespace=row["namespace"],
                execution_id=row["execution_id"],
                job_id=row["job_id"],
                start_time=datetime.fromisoformat(row["start_time"]),
                end_time=datetime.fromisoformat(row["end_time"])
                if row["end_time"]
                else None,
                status=row["status"],
                attributes=json.loads(row["attributes_json"]),
                spans=spans,
            )

    def list_trace_records(
        self, tenant_id: str | None = None, limit: int = 100
    ) -> list[Any]:
        """List trace records matching tenant."""
        query = "SELECT trace_id FROM trace_records"
        params: list[Any] = []
        if tenant_id:
            query += " WHERE tenant_id = ?"
            params.append(tenant_id)
        query += " ORDER BY start_time DESC LIMIT ?"
        params.append(limit)

        records = []
        with self._connection() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            for r in rows:
                rec = self.get_trace_record(r["trace_id"])
                if rec:
                    records.append(rec)
        return records

    def save_incident(self, incident: Any) -> None:
        """Persist an operational incident."""
        meta = getattr(incident, "metadata", {})
        sanitized_meta = self.sanitizer.sanitize(meta)
        da = getattr(incident, "detected_at", datetime.now(UTC)).isoformat()
        aa = (
            getattr(incident, "acknowledged_at", None).isoformat()
            if getattr(incident, "acknowledged_at", None)
            else None
        )
        ra = (
            getattr(incident, "resolved_at", None).isoformat()
            if getattr(incident, "resolved_at", None)
            else None
        )
        status_val = (
            incident.status.value
            if hasattr(incident.status, "value")
            else str(incident.status)
        )
        with self._connection() as conn, conn:
            conn.execute(
                """
                INSERT INTO operational_incidents (
                    incident_id, severity, title, description, detected_at,
                    acknowledged_at, resolved_at, tenant_id, trace_ids_json,
                    execution_ids_json, affected_workers_json,
                    affected_providers_json, related_events_json, status,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(incident_id) DO UPDATE SET
                    status=excluded.status,
                    acknowledged_at=excluded.acknowledged_at,
                    resolved_at=excluded.resolved_at,
                    metadata_json=excluded.metadata_json;
                """,
                (
                    incident.incident_id,
                    incident.severity,
                    incident.title,
                    incident.description,
                    da,
                    aa,
                    ra,
                    incident.tenant_id,
                    json.dumps(incident.trace_ids),
                    json.dumps(incident.execution_ids),
                    json.dumps(incident.affected_workers),
                    json.dumps(incident.affected_providers),
                    json.dumps(incident.related_events),
                    status_val,
                    json.dumps(sanitized_meta),
                ),
            )

    def get_incident(self, incident_id: str) -> Any | None:
        """Retrieve an operational incident by ID."""
        from aireliability.observability.incidents import IncidentRecord
        from aireliability.observability.models import IncidentStatus

        with self._connection() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM operational_incidents WHERE incident_id = ?",
                (incident_id,),
            ).fetchone()
            if not row:
                return None
            return IncidentRecord(
                incident_id=row["incident_id"],
                severity=row["severity"],
                title=row["title"],
                description=row["description"],
                detected_at=datetime.fromisoformat(row["detected_at"]),
                acknowledged_at=datetime.fromisoformat(row["acknowledged_at"])
                if row["acknowledged_at"]
                else None,
                resolved_at=datetime.fromisoformat(row["resolved_at"])
                if row["resolved_at"]
                else None,
                tenant_id=row["tenant_id"],
                trace_ids=json.loads(row["trace_ids_json"]),
                execution_ids=json.loads(row["execution_ids_json"]),
                affected_workers=json.loads(row["affected_workers_json"]),
                affected_providers=json.loads(row["affected_providers_json"]),
                related_events=json.loads(row["related_events_json"]),
                status=IncidentStatus(row["status"]),
                metadata=json.loads(row["metadata_json"]),
            )

    def list_incidents(
        self, tenant_id: str | None = None, limit: int = 100
    ) -> list[Any]:
        """List operational incidents matching tenant."""
        query = "SELECT incident_id FROM operational_incidents"
        params: list[Any] = []
        if tenant_id:
            query += " WHERE tenant_id = ?"
            params.append(tenant_id)
        query += " ORDER BY detected_at DESC LIMIT ?"
        params.append(limit)

        records = []
        with self._connection() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            for r in rows:
                rec = self.get_incident(r["incident_id"])
                if rec:
                    records.append(rec)
        return records

    def clear(self) -> None:
        """Clear all tables."""
        with self._connection() as conn, conn:
            conn.execute("DELETE FROM operational_incidents;")
            conn.execute("DELETE FROM trace_records;")
            conn.execute("DELETE FROM telemetry_events;")
            conn.execute("DELETE FROM security_replay_records;")
            conn.execute("DELETE FROM security_audit_events;")
            conn.execute("DELETE FROM security_api_keys;")
            conn.execute("DELETE FROM distributed_failures;")
            conn.execute("DELETE FROM distributed_outcomes;")
            conn.execute("DELETE FROM distributed_jobs;")
            conn.execute("DELETE FROM distributed_workers;")
            conn.execute("DELETE FROM distributed_executions;")
