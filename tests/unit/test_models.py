"""Comprehensive unit tests for Core Data Models (Phase 2)."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from aireliability import (
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


class TestTestCase:
    """Unit tests for TestCase model."""

    def test_valid_construction_minimal(self) -> None:
        tc = TestCase(name="summarize_email", input="Please summarize this email...")
        assert tc.name == "summarize_email"
        assert tc.input == "Please summarize this email..."
        assert tc.expected_output is None
        assert tc.expectations == []
        assert tc.tags == []
        assert tc.metadata == {}
        assert tc.id.startswith("tc_")

    def test_valid_construction_full(self) -> None:
        tc = TestCase(
            id="custom_id_123",
            name="summarize_email",
            input={"email_body": "Hello world"},
            expected_output={"summary": "Greeting"},
            expectations=["length < 100", "sentiment == positive"],
            tags=["summarization", "prod"],
            metadata={"version": 1},
        )
        assert tc.id == "custom_id_123"
        assert tc.name == "summarize_email"
        assert tc.input == {"email_body": "Hello world"}
        assert tc.expected_output == {"summary": "Greeting"}
        assert len(tc.expectations) == 2
        assert tc.tags == ["summarization", "prod"]
        assert tc.metadata["version"] == 1

    def test_required_fields_missing(self) -> None:
        with pytest.raises(ValidationError):
            TestCase()  # type: ignore[call-arg]

        with pytest.raises(ValidationError):
            TestCase(name="no_input")  # type: ignore[call-arg]

    def test_immutability(self) -> None:
        tc = TestCase(name="frozen_test", input="data")
        with pytest.raises(ValidationError):
            tc.name = "new_name"  # type: ignore[misc]

    def test_serialization_roundtrip(self) -> None:
        tc = TestCase(
            name="serializable_test",
            input="in",
            expected_output="out",
            tags=["tag1"],
        )
        data = tc.model_dump()
        json_str = tc.model_dump_json()
        assert "serializable_test" in json_str

        restored = TestCase.model_validate(data)
        assert restored == tc
        restored_json = TestCase.model_validate_json(json_str)
        assert restored_json == tc


class TestTraceStep:
    """Unit tests for TraceStep model."""

    def test_valid_construction_defaults(self) -> None:
        step = TraceStep(name="llm_call")
        assert step.id.startswith("step_")
        assert step.name == "llm_call"
        assert step.type == StepType.CUSTOM
        assert step.input is None
        assert step.output is None
        assert step.completed_at is None
        assert step.duration_ms is None
        assert step.metadata == {}
        assert step.started_at.tzinfo is not None

    def test_supported_step_types(self) -> None:
        for st in [
            StepType.LLM,
            StepType.TOOL,
            StepType.RETRIEVAL,
            StepType.MEMORY,
            StepType.AGENT,
            StepType.SYSTEM,
            StepType.CUSTOM,
        ]:
            step = TraceStep(name="typed_step", type=st)
            assert step.type == st
            assert isinstance(step.type, StepType)

    def test_string_coercion_step_types(self) -> None:
        step = TraceStep(name="tool_step", type="tool")  # type: ignore[arg-type]
        assert step.type == StepType.TOOL

    def test_invalid_step_type(self) -> None:
        with pytest.raises(ValidationError):
            TraceStep(name="invalid", type="nonexistent_type")  # type: ignore[arg-type]

    def test_duration_auto_calculation(self) -> None:
        t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        t1 = datetime(2026, 1, 1, 12, 0, 1, 500000, tzinfo=UTC)
        step = TraceStep(name="timed_step", started_at=t0, completed_at=t1)
        assert step.duration_ms == 1500.0

    def test_explicit_duration_preserved(self) -> None:
        t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        t1 = datetime(2026, 1, 1, 12, 0, 1, tzinfo=UTC)
        step = TraceStep(
            name="timed_step",
            started_at=t0,
            completed_at=t1,
            duration_ms=42.0,
        )
        assert step.duration_ms == 42.0

    def test_invalid_timestamps_completed_before_started(self) -> None:
        t0 = datetime(2026, 1, 1, 12, 0, 1, tzinfo=UTC)
        t1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        with pytest.raises(ValidationError, match="completed_at cannot be earlier"):
            TraceStep(name="invalid_time", started_at=t0, completed_at=t1)


class TestExecutionTrace:
    """Unit tests for ExecutionTrace model."""

    def test_valid_construction_minimal(self) -> None:
        trace = ExecutionTrace()
        assert trace.trace_id.startswith("trace_")
        assert trace.test_id is None
        assert trace.status == ExecutionStatus.COMPLETED
        assert trace.steps == []
        assert trace.token_usage == {}
        assert trace.latency_ms is None
        assert trace.cost is None
        assert trace.metadata == {}
        assert trace.started_at.tzinfo is not None

    def test_trace_with_steps_and_latency_auto_calculation(self) -> None:
        t0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
        t1 = datetime(2026, 1, 1, 10, 0, 2, tzinfo=UTC)

        step1 = TraceStep(
            name="search_tool",
            type=StepType.TOOL,
            input={"q": "rag"},
            output={"docs": ["doc1"]},
            started_at=t0,
            completed_at=t0 + timedelta(seconds=1),
        )
        step2 = TraceStep(
            name="generate_answer",
            type=StepType.LLM,
            input={"prompt": "rag doc1"},
            output={"completion": "answer"},
            started_at=t0 + timedelta(seconds=1),
            completed_at=t1,
        )

        trace = ExecutionTrace(
            test_id="tc_123",
            started_at=t0,
            completed_at=t1,
            steps=[step1, step2],
            token_usage={"prompt_tokens": 150, "completion_tokens": 50, "total": 200},
            cost=0.0042,
            metadata={"environment": "ci"},
        )

        assert trace.test_id == "tc_123"
        assert len(trace.steps) == 2
        assert trace.latency_ms == 2000.0
        assert trace.cost == 0.0042
        assert trace.token_usage["total"] == 200

    def test_invalid_trace_timestamps(self) -> None:
        t0 = datetime(2026, 1, 1, 10, 0, 2, tzinfo=UTC)
        t1 = datetime(2026, 1, 1, 10, 0, 1, tzinfo=UTC)
        with pytest.raises(ValidationError, match="completed_at cannot be earlier"):
            ExecutionTrace(started_at=t0, completed_at=t1)


class TestEvaluationResult:
    """Unit tests for EvaluationResult model."""

    def test_valid_construction_minimal(self) -> None:
        eval_res = EvaluationResult(evaluator="contains_keywords", passed=True)
        assert eval_res.evaluator == "contains_keywords"
        assert eval_res.passed is True
        assert eval_res.score is None
        assert eval_res.message == ""
        assert eval_res.evidence is None
        assert eval_res.metadata == {}

    def test_valid_construction_with_score_and_evidence(self) -> None:
        eval_res = EvaluationResult(
            evaluator="semantic_similarity",
            passed=True,
            score=0.92,
            message="High semantic match",
            evidence={"cosine_sim": 0.92, "threshold": 0.85},
            metadata={"model": "embed-v1"},
        )
        assert eval_res.score == 0.92
        assert eval_res.evidence["cosine_sim"] == 0.92

    def test_score_validation_bounds(self) -> None:
        with pytest.raises(ValidationError, match="score must be between 0.0 and 1.0"):
            EvaluationResult(evaluator="judge", passed=False, score=-0.1)

        with pytest.raises(ValidationError, match="score must be between 0.0 and 1.0"):
            EvaluationResult(evaluator="judge", passed=True, score=1.05)


class TestFailureReport:
    """Unit tests for FailureReport model."""

    def test_valid_construction_minimal(self) -> None:
        fail = FailureReport(
            trace_id="trace_001",
            category="hallucination",
            type="factual_contradiction",
            message="Output contradicts ground truth fact.",
        )
        assert fail.failure_id.startswith("fail_")
        assert fail.trace_id == "trace_001"
        assert fail.test_id is None
        assert fail.severity == FailureSeverity.MEDIUM
        assert fail.confidence == 1.0
        assert fail.evidence is None

    def test_valid_construction_full(self) -> None:
        fail = FailureReport(
            failure_id="custom_fail_42",
            trace_id="trace_999",
            test_id="tc_123",
            category="tool_error",
            type="timeout",
            severity=FailureSeverity.CRITICAL,
            message="Database query timed out after 30s.",
            evidence={"query": "SELECT *", "timeout_sec": 30},
            confidence=0.95,
            metadata={"attempt": 3},
        )
        assert fail.failure_id == "custom_fail_42"
        assert fail.severity == FailureSeverity.CRITICAL
        assert fail.confidence == 0.95
        assert fail.test_id == "tc_123"

    def test_confidence_validation(self) -> None:
        with pytest.raises(ValidationError, match="confidence must be between"):
            FailureReport(
                trace_id="t1",
                category="cat",
                type="typ",
                message="msg",
                confidence=1.5,
            )

        with pytest.raises(ValidationError, match="confidence must be between"):
            FailureReport(
                trace_id="t1",
                category="cat",
                type="typ",
                message="msg",
                confidence=-0.05,
            )


class TestRegressionTest:
    """Unit tests for RegressionTest model."""

    def test_valid_construction(self) -> None:
        tc = TestCase(
            name="prevent_sql_injection",
            input="user'; DROP TABLE users;--",
            expected_output="Sanitized input",
        )
        reg = RegressionTest(
            name="reg_sql_injection_01",
            source_failure_id="fail_sql_99",
            test_case=tc,
            metadata={"origin": "pentest"},
        )
        assert reg.id.startswith("reg_")
        assert reg.name == "reg_sql_injection_01"
        assert reg.source_failure_id == "fail_sql_99"
        assert reg.test_case.name == "prevent_sql_injection"
        assert reg.created_at.tzinfo is not None
        assert reg.metadata["origin"] == "pentest"

    def test_nested_serialization(self) -> None:
        tc = TestCase(name="reg_tc", input={"x": 1})
        reg = RegressionTest(
            source_failure_id="fail_1",
            name="reg_1",
            test_case=tc,
        )
        dumped = reg.model_dump()
        assert dumped["test_case"]["name"] == "reg_tc"
        restored = RegressionTest.model_validate(dumped)
        assert restored == reg


class TestRunResult:
    """Unit tests for RunResult model."""

    def test_run_result_success_auto_passed(self) -> None:
        tc = TestCase(name="greet_test", input="hello")
        trace = ExecutionTrace(
            input="hello", output="hi there", status=ExecutionStatus.COMPLETED
        )
        ev1 = EvaluationResult(evaluator="length_check", passed=True)
        ev2 = EvaluationResult(evaluator="greeting_check", passed=True)

        rr = RunResult(
            test=tc,
            trace=trace,
            evaluations=[ev1, ev2],
            failures=[],
        )

        assert rr.passed is True
        assert len(rr.evaluations) == 2
        assert len(rr.failures) == 0

    def test_run_result_failed_due_to_failed_evaluation(self) -> None:
        tc = TestCase(name="greet_test", input="hello")
        trace = ExecutionTrace(
            input="hello", output="bye", status=ExecutionStatus.COMPLETED
        )
        ev = EvaluationResult(evaluator="greeting_check", passed=False)

        rr = RunResult(
            test=tc,
            trace=trace,
            evaluations=[ev],
        )

        assert rr.passed is False

    def test_run_result_failed_due_to_failures(self) -> None:
        tc = TestCase(name="tool_call_test", input="weather in NY")
        trace = ExecutionTrace(status=ExecutionStatus.COMPLETED)
        fail = FailureReport(
            trace_id=trace.trace_id,
            category="tool",
            type="connection_refused",
            message="Weather API down",
        )

        rr = RunResult(
            test=tc,
            trace=trace,
            failures=[fail],
        )

        assert rr.passed is False

    def test_run_result_failed_due_to_trace_failure(self) -> None:
        tc = TestCase(name="crash_test", input="bad input")
        trace = ExecutionTrace(status=ExecutionStatus.FAILED)

        rr = RunResult(
            test=tc,
            trace=trace,
            evaluations=[],
            failures=[],
        )

        assert rr.passed is False

    def test_run_result_explicit_passed_override(self) -> None:
        tc = TestCase(name="override_test", input="data")
        trace = ExecutionTrace(status=ExecutionStatus.FAILED)

        # Explicitly setting passed to True overrides the automated deduction
        rr = RunResult(test=tc, trace=trace, passed=True)
        assert rr.passed is True

    def test_complete_run_result_serialization(self) -> None:
        tc = TestCase(name="full_run", input={"q": "hi"})
        step = TraceStep(
            name="llm_call",
            type=StepType.LLM,
            input={"q": "hi"},
            output={"a": "hello"},
        )
        trace = ExecutionTrace(steps=[step], status=ExecutionStatus.COMPLETED)
        ev = EvaluationResult(evaluator="truthfulness", passed=True, score=0.98)

        rr = RunResult(
            test=tc,
            trace=trace,
            evaluations=[ev],
            failures=[],
            metadata={"run_env": "production"},
        )

        serialized = rr.model_dump_json()
        raw_json: dict[str, Any] = json.loads(serialized)
        assert raw_json["passed"] is True
        assert raw_json["test"]["name"] == "full_run"
        assert raw_json["trace"]["steps"][0]["type"] == "llm"

        deserialized = RunResult.model_validate_json(serialized)
        assert deserialized == rr
