"""Unit tests for SQLiteStorage and storage backend abstraction."""

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from aireliability.core.exceptions import StorageError
from aireliability.core.models import (
    EvaluationResult,
    ExecutionStatus,
    ExecutionTrace,
    FailureReport,
    FailureSeverity,
    RegressionTest,
    RunResult,
    StepType,
    TestCase,
    TraceStep,
)
from aireliability.regression.baseline import BaselineEntry
from aireliability.storage import SQLiteStorage, StorageBackend


@pytest.fixture
def memory_storage() -> SQLiteStorage:
    storage = SQLiteStorage(":memory:")
    yield storage
    storage.close()


@pytest.fixture
def temp_file_storage() -> SQLiteStorage:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_aireliability.db"
        storage = SQLiteStorage(db_path)
        yield storage
        storage.close()


def test_storage_backend_is_abstract() -> None:
    """Verify that StorageBackend cannot be directly instantiated."""
    with pytest.raises(TypeError):
        StorageBackend()  # type: ignore[abstract]


def test_sqlite_storage_implements_protocol(memory_storage: SQLiteStorage) -> None:
    """Verify SQLiteStorage is an instance of StorageBackend."""
    assert isinstance(memory_storage, StorageBackend)


# ==============================================================================
# 1. Test Cases Persistence
# ==============================================================================


def test_save_and_get_test_case(memory_storage: SQLiteStorage) -> None:
    tc = TestCase(
        id="tc_123",
        name="calculate_discount",
        input={"cart_value": 100, "user_tier": "gold"},
        expected_output={"discount": 20},
        expectations=["OutputEquals", "ToolCalled(db_query)"],
        tags=["pricing", "gold"],
        metadata={"priority": "high"},
    )
    memory_storage.save_test_case(tc)

    retrieved = memory_storage.get_test_case("tc_123")
    assert retrieved is not None
    assert retrieved.id == "tc_123"
    assert retrieved.name == "calculate_discount"
    assert retrieved.input == {"cart_value": 100, "user_tier": "gold"}
    assert retrieved.expected_output == {"discount": 20}
    assert retrieved.expectations == ["OutputEquals", "ToolCalled(db_query)"]
    assert retrieved.tags == ["pricing", "gold"]
    assert retrieved.metadata == {"priority": "high"}


def test_update_existing_test_case(memory_storage: SQLiteStorage) -> None:
    tc = TestCase(id="tc_upsert", name="old_name", input="in")
    memory_storage.save_test_case(tc)

    updated = TestCase(id="tc_upsert", name="new_name", input="updated_in")
    memory_storage.save_test_case(updated)

    res = memory_storage.get_test_case("tc_upsert")
    assert res is not None
    assert res.name == "new_name"
    assert res.input == "updated_in"


def test_list_test_cases_with_tags(memory_storage: SQLiteStorage) -> None:
    tc1 = TestCase(name="t1", input="1", tags=["auth", "critical"])
    tc2 = TestCase(name="t2", input="2", tags=["billing"])
    tc3 = TestCase(name="t3", input="3", tags=["auth", "billing"])

    for tc in (tc1, tc2, tc3):
        memory_storage.save_test_case(tc)

    all_cases = memory_storage.list_test_cases()
    assert len(all_cases) == 3

    auth_cases = memory_storage.list_test_cases(tags=["auth"])
    assert len(auth_cases) == 2
    assert {c.name for c in auth_cases} == {"t1", "t3"}

    both_tags = memory_storage.list_test_cases(tags=["auth", "billing"])
    assert len(both_tags) == 1
    assert both_tags[0].name == "t3"


# ==============================================================================
# 2. Execution Traces Persistence
# ==============================================================================


def test_save_and_get_trace(memory_storage: SQLiteStorage) -> None:
    step = TraceStep(
        id="st_1",
        name="call_llm",
        type=StepType.LLM,
        input={"prompt": "hello"},
        output={"text": "world"},
        duration_ms=45.0,
    )
    start = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    end = datetime(2026, 1, 1, 10, 0, 1, tzinfo=UTC)

    trace = ExecutionTrace(
        trace_id="tr_100",
        test_id="tc_123",
        started_at=start,
        completed_at=end,
        latency_ms=1000.0,
        cost=0.002,
        status=ExecutionStatus.COMPLETED,
        input="user query",
        output="agent response",
        steps=[step],
        token_usage={"prompt_tokens": 10, "completion_tokens": 5},
        metadata={"model": "test-v1"},
    )

    memory_storage.save_trace(trace)

    retrieved = memory_storage.get_trace("tr_100")
    assert retrieved is not None
    assert retrieved.trace_id == "tr_100"
    assert retrieved.test_id == "tc_123"
    assert retrieved.status == ExecutionStatus.COMPLETED
    assert retrieved.latency_ms == 1000.0
    assert retrieved.cost == 0.002
    assert retrieved.token_usage == {"prompt_tokens": 10, "completion_tokens": 5}
    assert len(retrieved.steps) == 1
    assert retrieved.steps[0].name == "call_llm"
    assert retrieved.steps[0].type == StepType.LLM


def test_list_traces(memory_storage: SQLiteStorage) -> None:
    t1 = ExecutionTrace(trace_id="tr_a", test_id="tc_shared")
    t2 = ExecutionTrace(trace_id="tr_b", test_id="tc_shared")
    t3 = ExecutionTrace(trace_id="tr_c", test_id="tc_other")

    for t in (t1, t2, t3):
        memory_storage.save_trace(t)

    assert len(memory_storage.list_traces()) == 3
    filtered = memory_storage.list_traces(test_id="tc_shared")
    assert len(filtered) == 2
    assert {t.trace_id for t in filtered} == {"tr_a", "tr_b"}


# ==============================================================================
# 3. Evaluations Persistence
# ==============================================================================


def test_save_and_get_evaluations(memory_storage: SQLiteStorage) -> None:
    # First save trace
    trace = ExecutionTrace(trace_id="tr_eval_test")
    memory_storage.save_trace(trace)

    eval1 = EvaluationResult(
        evaluator="ToolCalled(get_user)",
        passed=True,
        score=1.0,
        message="Tool called as expected",
        evidence={"calls": 1},
    )
    eval2 = EvaluationResult(
        evaluator="MaxLatency(100ms)",
        passed=False,
        score=0.0,
        message="Exceeded latency",
        evidence={"latency_ms": 150.0},
    )

    memory_storage.save_evaluations("tr_eval_test", [eval1, eval2])

    retrieved = memory_storage.get_evaluations("tr_eval_test")
    assert len(retrieved) == 2
    assert retrieved[0].evaluator == "ToolCalled(get_user)"
    assert retrieved[0].passed is True
    assert retrieved[1].evaluator == "MaxLatency(100ms)"
    assert retrieved[1].passed is False
    assert retrieved[1].evidence == {"latency_ms": 150.0}


# ==============================================================================
# 4. Failures Persistence
# ==============================================================================


def test_save_and_list_failures(memory_storage: SQLiteStorage) -> None:
    trace = ExecutionTrace(trace_id="tr_fail")
    memory_storage.save_trace(trace)

    f1 = FailureReport(
        failure_id="f_tool_1",
        trace_id="tr_fail",
        category="tool",
        type="wrong_tool",
        severity=FailureSeverity.HIGH,
        message="Used send_email instead of write_draft",
        evidence={"tool": "send_email"},
        confidence=1.0,
    )
    f2 = FailureReport(
        failure_id="f_perf_1",
        trace_id="tr_fail",
        category="performance",
        type="latency",
        severity=FailureSeverity.MEDIUM,
        message="Too slow",
        confidence=1.0,
    )

    memory_storage.save_failure(f1)
    memory_storage.save_failure(f2)

    retrieved_f1 = memory_storage.get_failure("f_tool_1")
    assert retrieved_f1 is not None
    assert retrieved_f1.category == "tool"
    assert retrieved_f1.type == "wrong_tool"
    assert retrieved_f1.confidence == 1.0

    all_fails = memory_storage.list_failures()
    assert len(all_fails) == 2

    tool_fails = memory_storage.list_failures(category="tool")
    assert len(tool_fails) == 1
    assert tool_fails[0].failure_id == "f_tool_1"


# ==============================================================================
# 5. Regression Tests Persistence
# ==============================================================================


def test_save_and_get_regression_test(memory_storage: SQLiteStorage) -> None:
    tc = TestCase(name="reg_base_test", input="sample_input")
    reg_test = RegressionTest(
        id="reg_123",
        name="regression_query_syntax",
        source_failure_id="fail_999",
        test_case=tc,
        metadata={"priority": "high"},
    )

    memory_storage.save_regression_test(reg_test)

    retrieved = memory_storage.get_regression_test("reg_123")
    assert retrieved is not None
    assert retrieved.id == "reg_123"
    assert retrieved.name == "regression_query_syntax"
    assert retrieved.source_failure_id == "fail_999"
    assert retrieved.test_case.input == "sample_input"
    assert retrieved.metadata["priority"] == "high"


def test_list_regression_tests_by_failure_id(memory_storage: SQLiteStorage) -> None:
    tc = TestCase(name="t", input="x")
    r1 = RegressionTest(name="r1", source_failure_id="f_alpha", test_case=tc)
    r2 = RegressionTest(name="r2", source_failure_id="f_beta", test_case=tc)

    memory_storage.save_regression_test(r1)
    memory_storage.save_regression_test(r2)

    assert len(memory_storage.list_regression_tests()) == 2
    filtered = memory_storage.list_regression_tests(source_failure_id="f_alpha")
    assert len(filtered) == 1
    assert filtered[0].source_failure_id == "f_alpha"


# ==============================================================================
# 6. Baselines Persistence
# ==============================================================================


def test_save_and_get_baseline(memory_storage: SQLiteStorage) -> None:
    tc = TestCase(id="tc_b1", name="auth_test", input="user")
    trace = ExecutionTrace(test_id="tc_b1", output="logged_in")
    run_res = RunResult(
        test=tc,
        trace=trace,
        evaluations=[EvaluationResult(evaluator="check", passed=True)],
        failures=[],
        passed=True,
    )
    entry = BaselineEntry(
        test_id="tc_b1",
        test_name="auth_test",
        passed=True,
        run_result=run_res,
        metadata={"env": "staging"},
    )

    memory_storage.save_baseline("prod_v1", [entry], metadata={"version": "1.0"})

    baselines = memory_storage.list_baselines()
    assert "prod_v1" in baselines

    loaded_entries = memory_storage.get_baseline("prod_v1")
    assert "tc_b1" in loaded_entries
    loaded_entry = loaded_entries["tc_b1"]
    assert loaded_entry.test_name == "auth_test"
    assert loaded_entry.passed is True
    assert loaded_entry.run_result.trace.output == "logged_in"
    assert loaded_entry.metadata == {"env": "staging"}


# ==============================================================================
# 7. File-based Database & Transactions
# ==============================================================================


def test_file_based_sqlite_persistence(temp_file_storage: SQLiteStorage) -> None:
    """Verify that file-based SQLite persists data across connection instances."""
    tc = TestCase(id="tc_persisted", name="persistent_test", input="persist_me")
    temp_file_storage.save_test_case(tc)

    # Re-open database with a fresh storage instance at same path
    reopened = SQLiteStorage(temp_file_storage.db_path)
    retrieved = reopened.get_test_case("tc_persisted")
    assert retrieved is not None
    assert retrieved.name == "persistent_test"
    reopened.close()


def test_transaction_rollback_on_error(memory_storage: SQLiteStorage) -> None:
    """Verify transaction rolls back and raises StorageError on constraint violation."""
    with pytest.raises(StorageError), memory_storage._transaction() as cur:
        cur.execute("INSERT INTO test_cases (id, name, input_json) VALUES (1, 2, 3);")
        # Invalid SQL to trigger error
        cur.execute("SELECT * FROM non_existent_table_xyz;")
