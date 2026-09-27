"""SQLite implementation of StorageBackend for lightweight, serverless persistence."""

import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aireliability.core.exceptions import StorageError
from aireliability.core.models import (
    EvaluationResult,
    ExecutionTrace,
    FailureReport,
    RegressionTest,
    RunResult,
    TestCase,
)
from aireliability.regression.baseline import BaselineEntry
from aireliability.storage.base import StorageBackend

SCHEMA_STATEMENTS = [
    # Schema metadata table for version tracking / migrations
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    );
    """,
    # Test cases table
    """
    CREATE TABLE IF NOT EXISTS test_cases (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        input_json TEXT NOT NULL,
        expected_output_json TEXT,
        expectations_json TEXT NOT NULL,
        tags_json TEXT NOT NULL,
        metadata_json TEXT NOT NULL
    );
    """,
    # Executions / traces table
    """
    CREATE TABLE IF NOT EXISTS traces (
        trace_id TEXT PRIMARY KEY,
        test_id TEXT,
        started_at TEXT NOT NULL,
        completed_at TEXT,
        latency_ms REAL,
        cost REAL,
        status TEXT NOT NULL,
        input_json TEXT,
        output_json TEXT,
        steps_json TEXT NOT NULL,
        token_usage_json TEXT NOT NULL,
        metadata_json TEXT NOT NULL
    );
    """,
    # Evaluations table
    """
    CREATE TABLE IF NOT EXISTS evaluations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trace_id TEXT NOT NULL,
        evaluator TEXT NOT NULL,
        passed INTEGER NOT NULL,
        score REAL,
        message TEXT,
        evidence_json TEXT,
        metadata_json TEXT NOT NULL,
        FOREIGN KEY(trace_id) REFERENCES traces(trace_id) ON DELETE CASCADE
    );
    """,
    # Failures table
    """
    CREATE TABLE IF NOT EXISTS failures (
        failure_id TEXT PRIMARY KEY,
        trace_id TEXT NOT NULL,
        test_id TEXT,
        category TEXT NOT NULL,
        type TEXT NOT NULL,
        severity TEXT NOT NULL,
        message TEXT NOT NULL,
        evidence_json TEXT,
        confidence REAL NOT NULL,
        metadata_json TEXT NOT NULL,
        FOREIGN KEY(trace_id) REFERENCES traces(trace_id) ON DELETE CASCADE
    );
    """,
    # Regression tests table
    """
    CREATE TABLE IF NOT EXISTS regression_tests (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        source_failure_id TEXT NOT NULL,
        test_case_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        metadata_json TEXT NOT NULL
    );
    """,
    # Baseline tables
    """
    CREATE TABLE IF NOT EXISTS baselines (
        name TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        metadata_json TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS baseline_entries (
        baseline_name TEXT NOT NULL,
        test_id TEXT NOT NULL,
        test_name TEXT NOT NULL,
        passed INTEGER NOT NULL,
        run_result_json TEXT NOT NULL,
        captured_at TEXT NOT NULL,
        metadata_json TEXT NOT NULL,
        PRIMARY KEY (baseline_name, test_id),
        FOREIGN KEY(baseline_name) REFERENCES baselines(name) ON DELETE CASCADE
    );
    """,
    # Indices for fast queries
    "CREATE INDEX IF NOT EXISTS idx_traces_test_id ON traces(test_id);",
    "CREATE INDEX IF NOT EXISTS idx_evaluations_trace_id ON evaluations(trace_id);",
    "CREATE INDEX IF NOT EXISTS idx_failures_trace_id ON failures(trace_id);",
    "CREATE INDEX IF NOT EXISTS idx_failures_category ON failures(category);",
    (
        "CREATE INDEX IF NOT EXISTS idx_regression_tests_failure_id "
        "ON regression_tests(source_failure_id);"
    ),
    (
        "CREATE INDEX IF NOT EXISTS idx_baseline_entries_name "
        "ON baseline_entries(baseline_name);"
    ),
]


class SQLiteStorage(StorageBackend):
    """SQLite implementation of StorageBackend.

    Provides serverless, atomic, and transactional storage for traces,
    evaluations, failures, regression tests, and baselines.
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        """Initialize SQLiteStorage with database path (default ':memory:')."""
        self.db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None
        self._is_memory = self.db_path == ":memory:"
        self.initialize()

    def _get_connection(self) -> sqlite3.Connection:
        if self._is_memory:
            if self._conn is None:
                self._conn = sqlite3.connect(":memory:")
                self._conn.row_factory = sqlite3.Row
                self._conn.execute("PRAGMA foreign_keys = ON;")
            return self._conn

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    @contextmanager
    def _transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        """Context manager providing atomic transactional execution."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as exc:
            conn.rollback()
            raise StorageError(f"Database transaction error: {exc}") from exc
        finally:
            cursor.close()
            if not self._is_memory:
                conn.close()

    def initialize(self) -> None:
        """Initialize SQLite tables and apply safe schema migrations."""
        try:
            with self._transaction() as cur:
                for stmt in SCHEMA_STATEMENTS:
                    cur.execute(stmt)
                cur.execute(
                    "INSERT OR IGNORE INTO schema_migrations (version, applied_at) "
                    "VALUES (?, ?)",
                    (1, datetime.now(UTC).isoformat()),
                )
        except Exception as exc:
            raise StorageError(f"Failed to initialize SQLite database: {exc}") from exc

    def close(self) -> None:
        """Close connection if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # --- Test Cases ---
    def save_test_case(self, test_case: TestCase) -> None:
        sql = """
        INSERT INTO test_cases (
            id, name, input_json, expected_output_json, expectations_json,
            tags_json, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            input_json = excluded.input_json,
            expected_output_json = excluded.expected_output_json,
            expectations_json = excluded.expectations_json,
            tags_json = excluded.tags_json,
            metadata_json = excluded.metadata_json;
        """
        with self._transaction() as cur:
            cur.execute(
                sql,
                (
                    test_case.id,
                    test_case.name,
                    json.dumps(test_case.input, default=str),
                    (
                        json.dumps(test_case.expected_output, default=str)
                        if test_case.expected_output is not None
                        else None
                    ),
                    json.dumps(test_case.expectations),
                    json.dumps(test_case.tags),
                    json.dumps(test_case.metadata, default=str),
                ),
            )

    def get_test_case(self, test_id: str) -> TestCase | None:
        sql = "SELECT * FROM test_cases WHERE id = ?;"
        with self._transaction() as cur:
            cur.execute(sql, (test_id,))
            row = cur.fetchone()
            if not row:
                return None
            return TestCase(
                id=row["id"],
                name=row["name"],
                input=json.loads(row["input_json"]),
                expected_output=(
                    json.loads(row["expected_output_json"])
                    if row["expected_output_json"] is not None
                    else None
                ),
                expectations=json.loads(row["expectations_json"]),
                tags=json.loads(row["tags_json"]),
                metadata=json.loads(row["metadata_json"]),
            )

    def list_test_cases(self, tags: list[str] | None = None) -> list[TestCase]:
        sql = "SELECT * FROM test_cases ORDER BY name ASC;"
        with self._transaction() as cur:
            cur.execute(sql)
            rows = cur.fetchall()

        cases: list[TestCase] = []
        for r in rows:
            tc_tags = json.loads(r["tags_json"])
            if tags and not all(t in tc_tags for t in tags):
                continue
            cases.append(
                TestCase(
                    id=r["id"],
                    name=r["name"],
                    input=json.loads(r["input_json"]),
                    expected_output=(
                        json.loads(r["expected_output_json"])
                        if r["expected_output_json"] is not None
                        else None
                    ),
                    expectations=json.loads(r["expectations_json"]),
                    tags=tc_tags,
                    metadata=json.loads(r["metadata_json"]),
                )
            )
        return cases

    # --- Execution Traces ---
    def save_trace(self, trace: ExecutionTrace) -> None:
        sql = """
        INSERT INTO traces (
            trace_id, test_id, started_at, completed_at, latency_ms,
            cost, status, input_json, output_json, steps_json,
            token_usage_json, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(trace_id) DO UPDATE SET
            test_id = excluded.test_id,
            started_at = excluded.started_at,
            completed_at = excluded.completed_at,
            latency_ms = excluded.latency_ms,
            cost = excluded.cost,
            status = excluded.status,
            input_json = excluded.input_json,
            output_json = excluded.output_json,
            steps_json = excluded.steps_json,
            token_usage_json = excluded.token_usage_json,
            metadata_json = excluded.metadata_json;
        """
        with self._transaction() as cur:
            cur.execute(
                sql,
                (
                    trace.trace_id,
                    trace.test_id,
                    trace.started_at.isoformat(),
                    trace.completed_at.isoformat() if trace.completed_at else None,
                    trace.latency_ms,
                    trace.cost,
                    trace.status.value,
                    json.dumps(trace.input, default=str),
                    json.dumps(trace.output, default=str),
                    json.dumps([s.model_dump(mode="json") for s in trace.steps]),
                    json.dumps(trace.token_usage),
                    json.dumps(trace.metadata, default=str),
                ),
            )

    def get_trace(self, trace_id: str) -> ExecutionTrace | None:
        sql = "SELECT * FROM traces WHERE trace_id = ?;"
        with self._transaction() as cur:
            cur.execute(sql, (trace_id,))
            row = cur.fetchone()
            if not row:
                return None
            return ExecutionTrace.model_validate(
                {
                    "trace_id": row["trace_id"],
                    "test_id": row["test_id"],
                    "started_at": row["started_at"],
                    "completed_at": row["completed_at"],
                    "latency_ms": row["latency_ms"],
                    "cost": row["cost"],
                    "status": row["status"],
                    "input": json.loads(row["input_json"])
                    if row["input_json"]
                    else None,
                    "output": json.loads(row["output_json"])
                    if row["output_json"]
                    else None,
                    "steps": json.loads(row["steps_json"]),
                    "token_usage": json.loads(row["token_usage_json"]),
                    "metadata": json.loads(row["metadata_json"]),
                }
            )

    def list_traces(
        self,
        test_id: str | None = None,
        limit: int = 100,
    ) -> list[ExecutionTrace]:
        if test_id:
            sql = (
                "SELECT * FROM traces WHERE test_id = ? "
                "ORDER BY started_at DESC LIMIT ?;"
            )
            params: tuple[Any, ...] = (test_id, limit)
        else:
            sql = "SELECT * FROM traces ORDER BY started_at DESC LIMIT ?;"
            params = (limit,)

        with self._transaction() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        return [
            ExecutionTrace.model_validate(
                {
                    "trace_id": r["trace_id"],
                    "test_id": r["test_id"],
                    "started_at": r["started_at"],
                    "completed_at": r["completed_at"],
                    "latency_ms": r["latency_ms"],
                    "cost": r["cost"],
                    "status": r["status"],
                    "input": json.loads(r["input_json"]) if r["input_json"] else None,
                    "output": json.loads(r["output_json"])
                    if r["output_json"]
                    else None,
                    "steps": json.loads(r["steps_json"]),
                    "token_usage": json.loads(r["token_usage_json"]),
                    "metadata": json.loads(r["metadata_json"]),
                }
            )
            for r in rows
        ]

    # --- Evaluations ---
    def save_evaluations(
        self,
        trace_id: str,
        evaluations: list[EvaluationResult],
    ) -> None:
        sql = """
        INSERT INTO evaluations (
            trace_id, evaluator, passed, score, message, evidence_json, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?);
        """
        with self._transaction() as cur:
            for ev in evaluations:
                cur.execute(
                    sql,
                    (
                        trace_id,
                        ev.evaluator,
                        1 if ev.passed else 0,
                        ev.score,
                        ev.message,
                        json.dumps(ev.evidence, default=str)
                        if ev.evidence is not None
                        else None,
                        json.dumps(ev.metadata, default=str),
                    ),
                )

    def get_evaluations(self, trace_id: str) -> list[EvaluationResult]:
        sql = "SELECT * FROM evaluations WHERE trace_id = ? ORDER BY id ASC;"
        with self._transaction() as cur:
            cur.execute(sql, (trace_id,))
            rows = cur.fetchall()

        return [
            EvaluationResult(
                evaluator=r["evaluator"],
                passed=bool(r["passed"]),
                score=r["score"],
                message=r["message"] or "",
                evidence=json.loads(r["evidence_json"]) if r["evidence_json"] else None,
                metadata=json.loads(r["metadata_json"]),
            )
            for r in rows
        ]

    # --- Failure Reports ---
    def save_failure(self, failure: FailureReport) -> None:
        sql = """
        INSERT INTO failures (
            failure_id, trace_id, test_id, category, type, severity,
            message, evidence_json, confidence, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(failure_id) DO UPDATE SET
            trace_id = excluded.trace_id,
            test_id = excluded.test_id,
            category = excluded.category,
            type = excluded.type,
            severity = excluded.severity,
            message = excluded.message,
            evidence_json = excluded.evidence_json,
            confidence = excluded.confidence,
            metadata_json = excluded.metadata_json;
        """
        with self._transaction() as cur:
            cur.execute(
                sql,
                (
                    failure.failure_id,
                    failure.trace_id,
                    failure.test_id,
                    failure.category,
                    failure.type,
                    str(failure.severity),
                    failure.message,
                    json.dumps(failure.evidence, default=str)
                    if failure.evidence is not None
                    else None,
                    failure.confidence,
                    json.dumps(failure.metadata, default=str),
                ),
            )

    def get_failure(self, failure_id: str) -> FailureReport | None:
        sql = "SELECT * FROM failures WHERE failure_id = ?;"
        with self._transaction() as cur:
            cur.execute(sql, (failure_id,))
            row = cur.fetchone()
            if not row:
                return None
            return FailureReport.model_validate(
                {
                    "failure_id": row["failure_id"],
                    "trace_id": row["trace_id"],
                    "test_id": row["test_id"],
                    "category": row["category"],
                    "type": row["type"],
                    "severity": row["severity"],
                    "message": row["message"],
                    "evidence": json.loads(row["evidence_json"])
                    if row["evidence_json"]
                    else None,
                    "confidence": row["confidence"],
                    "metadata": json.loads(row["metadata_json"]),
                }
            )

    def list_failures(
        self,
        category: str | None = None,
        trace_id: str | None = None,
        limit: int = 100,
    ) -> list[FailureReport]:
        conditions: list[str] = []
        params: list[Any] = []
        if category:
            conditions.append("category = ?")
            params.append(category)
        if trace_id:
            conditions.append("trace_id = ?")
            params.append(trace_id)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"SELECT * FROM failures {where_clause} ORDER BY rowid DESC LIMIT ?;"
        params.append(limit)

        with self._transaction() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()

        return [
            FailureReport.model_validate(
                {
                    "failure_id": r["failure_id"],
                    "trace_id": r["trace_id"],
                    "test_id": r["test_id"],
                    "category": r["category"],
                    "type": r["type"],
                    "severity": r["severity"],
                    "message": r["message"],
                    "evidence": json.loads(r["evidence_json"])
                    if r["evidence_json"]
                    else None,
                    "confidence": r["confidence"],
                    "metadata": json.loads(r["metadata_json"]),
                }
            )
            for r in rows
        ]

    # --- Regression Tests ---
    def save_regression_test(self, regression_test: RegressionTest) -> None:
        sql = """
        INSERT INTO regression_tests (
            id, name, source_failure_id, test_case_json, created_at, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            source_failure_id = excluded.source_failure_id,
            test_case_json = excluded.test_case_json,
            created_at = excluded.created_at,
            metadata_json = excluded.metadata_json;
        """
        with self._transaction() as cur:
            cur.execute(
                sql,
                (
                    regression_test.id,
                    regression_test.name,
                    regression_test.source_failure_id,
                    regression_test.test_case.model_dump_json(),
                    regression_test.created_at.isoformat(),
                    json.dumps(regression_test.metadata, default=str),
                ),
            )

    def get_regression_test(self, regression_id: str) -> RegressionTest | None:
        sql = "SELECT * FROM regression_tests WHERE id = ?;"
        with self._transaction() as cur:
            cur.execute(sql, (regression_id,))
            row = cur.fetchone()
            if not row:
                return None
            return RegressionTest.model_validate(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "source_failure_id": row["source_failure_id"],
                    "test_case": json.loads(row["test_case_json"]),
                    "created_at": row["created_at"],
                    "metadata": json.loads(row["metadata_json"]),
                }
            )

    def list_regression_tests(
        self,
        source_failure_id: str | None = None,
    ) -> list[RegressionTest]:
        if source_failure_id:
            sql = (
                "SELECT * FROM regression_tests "
                "WHERE source_failure_id = ? ORDER BY created_at DESC;"
            )
            params: tuple[Any, ...] = (source_failure_id,)
        else:
            sql = "SELECT * FROM regression_tests ORDER BY created_at DESC;"
            params = ()

        with self._transaction() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        return [
            RegressionTest.model_validate(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "source_failure_id": r["source_failure_id"],
                    "test_case": json.loads(r["test_case_json"]),
                    "created_at": r["created_at"],
                    "metadata": json.loads(r["metadata_json"]),
                }
            )
            for r in rows
        ]

    # --- Baselines ---
    def save_baseline(
        self,
        name: str,
        entries: list[BaselineEntry],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        now_iso = datetime.now(UTC).isoformat()
        meta_json = json.dumps(metadata or {}, default=str)
        with self._transaction() as cur:
            # 1. Upsert baseline header
            cur.execute(
                """
                INSERT INTO baselines (name, created_at, metadata_json)
                VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    created_at = excluded.created_at,
                    metadata_json = excluded.metadata_json;
                """,
                (name, now_iso, meta_json),
            )
            # 2. Clear old entries for this baseline
            cur.execute(
                "DELETE FROM baseline_entries WHERE baseline_name = ?;", (name,)
            )

            # 3. Insert new entries
            entry_sql = """
            INSERT INTO baseline_entries (
                baseline_name, test_id, test_name, passed, run_result_json,
                captured_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """
            for e in entries:
                cur.execute(
                    entry_sql,
                    (
                        name,
                        e.test_id,
                        e.test_name,
                        1 if e.passed else 0,
                        e.run_result.model_dump_json(),
                        e.captured_at.isoformat(),
                        json.dumps(e.metadata, default=str),
                    ),
                )

    def get_baseline(self, name: str) -> dict[str, BaselineEntry]:
        sql = (
            "SELECT * FROM baseline_entries WHERE baseline_name = ? "
            "ORDER BY test_name ASC;"
        )
        with self._transaction() as cur:
            cur.execute(sql, (name,))
            rows = cur.fetchall()

        entries: dict[str, BaselineEntry] = {}
        for r in rows:
            entries[r["test_id"]] = BaselineEntry(
                test_id=r["test_id"],
                test_name=r["test_name"],
                passed=bool(r["passed"]),
                run_result=RunResult.model_validate_json(r["run_result_json"]),
                captured_at=datetime.fromisoformat(r["captured_at"]),
                metadata=json.loads(r["metadata_json"]),
            )
        return entries

    def list_baselines(self) -> list[str]:
        sql = "SELECT name FROM baselines ORDER BY name ASC;"
        with self._transaction() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
        return [r["name"] for r in rows]


__all__ = ["SQLiteStorage"]
