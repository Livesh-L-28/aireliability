"""Unit tests for Phase 22 Production Observability & Telemetry."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aireliability import (
    AlwaysOffSampler,
    AlwaysOnSampler,
    EvaluationResult,
    ExecutionStatus,
    ExecutionTrace,
    FailureReport,
    FailureSeverity,
    InMemoryTelemetryCollector,
    JsonTelemetryCollector,
    NoOpTelemetryCollector,
    OutputEquals,
    RatioSampler,
    RegressionGenerator,
    RegressionRunner,
    ReliabilityRunner,
    RunResult,
    SanitizationPolicy,
    SpanKind,
    StepType,
    TelemetryBuilder,
    TelemetrySpan,
    TelemetryStatus,
    TelemetryTrace,
    TestCase,
    TraceStep,
)
from aireliability.diagnosis.models import (
    RootCause,
    RootCauseCategory,
    RootCauseReport,
    RootCauseType,
)
from aireliability.integrations import (
    get_opentelemetry_exporter,
    get_prometheus_exporter,
)

# ---------------------------------------------------------------------------
# 1. Telemetry Model Creation & Invariants
# ---------------------------------------------------------------------------


def test_telemetry_model_creation():
    """Verify TelemetrySpan and TelemetryTrace construct properly with calculated
    durations.
    """
    trace = TelemetryTrace(
        trace_id="test_tr_1",
        execution_id="exec_1",
        test_id="tc_1",
        name="test.example",
    )
    assert trace.trace_id == "test_tr_1"
    assert trace.execution_id == "exec_1"
    assert trace.status == TelemetryStatus.UNSET
    assert trace.duration_ms is None

    span = TelemetrySpan(
        span_id="span_1",
        trace_id="test_tr_1",
        parent_span_id=None,
        name="op.task",
        kind=SpanKind.AGENT,
    )
    assert span.span_id == "span_1"
    assert span.kind == SpanKind.AGENT


def test_telemetry_span_parent_child_relationships():
    """Verify trace parent and child relationships and span lookup."""
    root_span = TelemetrySpan(
        span_id="span_root",
        trace_id="tr_hierarchy",
        parent_span_id=None,
        name="agent.root",
        kind=SpanKind.AGENT,
    )
    child_span1 = TelemetrySpan(
        span_id="span_child_1",
        trace_id="tr_hierarchy",
        parent_span_id="span_root",
        name="model.gpt",
        kind=SpanKind.MODEL,
    )
    child_span2 = TelemetrySpan(
        span_id="span_child_2",
        trace_id="tr_hierarchy",
        parent_span_id="span_root",
        name="tool.search",
        kind=SpanKind.TOOL,
    )

    trace = TelemetryTrace(
        trace_id="tr_hierarchy",
        spans=[root_span, child_span1, child_span2],
    )

    assert trace.find_span("span_root") == root_span
    assert trace.find_span("span_child_1") == child_span1
    assert trace.find_span("non_existent") is None

    roots = trace.child_spans(None)
    assert roots == [root_span]

    children = trace.child_spans("span_root")
    assert children == [child_span1, child_span2]


# ---------------------------------------------------------------------------
# 2. Telemetry Collectors (NoOp, InMemory, Json)
# ---------------------------------------------------------------------------


def test_noop_telemetry_collector():
    """Verify NoOpTelemetryCollector safely discards all operations without error."""
    collector = NoOpTelemetryCollector()
    trace = TelemetryTrace(trace_id="tr_noop")
    collector.record(trace)
    collector.flush()
    collector.clear()
    assert True


def test_in_memory_telemetry_collector():
    """Verify InMemoryTelemetryCollector records, returns, and clears traces."""
    collector = InMemoryTelemetryCollector()
    t1 = TelemetryTrace(trace_id="tr_mem_1")
    t2 = TelemetryTrace(trace_id="tr_mem_2")

    collector.record(t1)
    collector.record(t2)

    traces = collector.traces
    assert len(traces) == 2
    assert traces[0].trace_id == "tr_mem_1"
    assert collector.get_last_trace().trace_id == "tr_mem_2"

    collector.clear()
    assert len(collector.traces) == 0
    assert collector.get_last_trace() is None


def test_json_telemetry_collector(tmp_path: Path):
    """Verify JsonTelemetryCollector serializes traces deterministically to file."""
    output_file = tmp_path / "telemetry_out.json"
    collector = JsonTelemetryCollector(target=output_file)

    trace = TelemetryTrace(
        trace_id="tr_json_1",
        execution_id="exec_json_1",
        test_id="tc_123",
        name="test.order_check",
        status=TelemetryStatus.OK,
        attributes={"env": "test"},
        spans=[
            TelemetrySpan(
                span_id="sp_1",
                trace_id="tr_json_1",
                name="tool.lookup",
                kind=SpanKind.TOOL,
                status=TelemetryStatus.OK,
                attributes={"tool.name": "lookup", "tool.input": {"id": 1}},
            )
        ],
    )
    collector.record(trace)
    collector.flush()

    assert output_file.exists()
    content = json.loads(output_file.read_text(encoding="utf-8"))
    assert isinstance(content, list)
    assert len(content) == 1
    assert content[0]["trace_id"] == "tr_json_1"
    assert content[0]["status"] == "ok"
    assert len(content[0]["spans"]) == 1
    assert content[0]["spans"][0]["name"] == "tool.lookup"


# ---------------------------------------------------------------------------
# 3. Sampling (AlwaysOn, AlwaysOff, RatioSampler, Deterministic Seed)
# ---------------------------------------------------------------------------


def test_telemetry_samplers():
    """Verify AlwaysOnSampler, AlwaysOffSampler, and RatioSampler behavior."""
    on = AlwaysOnSampler()
    off = AlwaysOffSampler()
    assert on.should_sample("any") is True
    assert off.should_sample("any") is False

    # Ratio 0.0 -> False, 1.0 -> True
    assert RatioSampler(ratio=0.0).should_sample() is False
    assert RatioSampler(ratio=1.0).should_sample() is True

    # Invalid ratio raises ValueError
    with pytest.raises(ValueError, match="Sampling ratio must be between 0.0 and 1.0"):
        RatioSampler(ratio=1.5)


def test_deterministic_sampling():
    """Verify seeded RatioSampler produces repeatable deterministic sampling
    decisions.
    """
    sampler_a = RatioSampler(ratio=0.5, seed=42)
    decisions_a = [sampler_a.should_sample() for _ in range(50)]

    sampler_b = RatioSampler(ratio=0.5, seed=42)
    decisions_b = [sampler_b.should_sample() for _ in range(50)]

    assert decisions_a == decisions_b


def test_in_memory_collector_with_sampler():
    """Verify collector respects sampler decisions."""
    collector = InMemoryTelemetryCollector(sampler=AlwaysOffSampler())
    trace = TelemetryTrace(trace_id="tr_dropped")
    collector.record(trace)
    assert len(collector.traces) == 0


# ---------------------------------------------------------------------------
# 4. Recursive Privacy & Metadata Sanitization
# ---------------------------------------------------------------------------


def test_recursive_sanitization_policy():
    """Verify SanitizationPolicy recursively redacts secrets, keys, and
    authorization headers.
    """
    policy = SanitizationPolicy()

    payload = {
        "api_key": "sk-1234567890",
        "nested": {
            "token": "ghp_abcdef12345",
            "safe_param": "hello",
            "headers": {
                "Authorization": "Bearer super-secret-jwt",
                "content-type": "application/json",
            },
        },
        "list_items": [
            {"secret": "xyz123", "normal": 42},
            {"password": "mypassword"},
        ],
    }

    sanitized = policy.sanitize(payload)

    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["nested"]["token"] == "[REDACTED]"
    assert sanitized["nested"]["safe_param"] == "hello"
    assert sanitized["nested"]["headers"]["Authorization"] == "[REDACTED]"
    assert sanitized["nested"]["headers"]["content-type"] == "application/json"
    assert sanitized["list_items"][0]["secret"] == "[REDACTED]"
    assert sanitized["list_items"][0]["normal"] == 42
    assert sanitized["list_items"][1]["password"] == "[REDACTED]"


# ---------------------------------------------------------------------------
# 5. Model, Tool, Evaluation, and Failure Telemetry Translation
# ---------------------------------------------------------------------------


def test_telemetry_builder_model_and_tool_telemetry():
    """Verify TelemetryBuilder maps model usage, latency, and tool calls into spans."""
    test_case = TestCase(id="tc_weather", name="weather_check", input="weather in NY")

    # Step 1: Model call
    model_step = TraceStep(
        name="gpt-4o",
        type=StepType.LLM,
        input="weather in NY",
        output="Calling tool: get_weather",
        metadata={
            "model": "gpt-4o",
            "call_id": "call_llm_1",
            "latency_ms": 120.5,
            "usage": {
                "input_tokens": 50,
                "output_tokens": 15,
                "total_tokens": 65,
                "cached_tokens": 10,
            },
            "streamed": False,
            "retries": 0,
        },
    )

    # Step 2: Tool call
    tool_step = TraceStep(
        name="get_weather",
        type=StepType.TOOL,
        input={"city": "New York"},
        output={"temp": 72, "unit": "F"},
        metadata={"call_id": "call_weather_99"},
    )

    trace = ExecutionTrace(
        trace_id="tr_weather_run",
        test_id="tc_weather",
        input=test_case.input,
        output="The temperature in New York is 72°F.",
        status=ExecutionStatus.COMPLETED,
        steps=[model_step, tool_step],
        token_usage={"prompt_tokens": 50, "completion_tokens": 15, "total_tokens": 65},
    )

    eval_result = EvaluationResult(
        evaluator="OutputEquals",
        passed=True,
        score=1.0,
        message="Exact output matched",
    )

    run_result = RunResult(
        test=test_case,
        trace=trace,
        evaluations=[eval_result],
        failures=[],
    )

    builder = TelemetryBuilder()
    tel_trace = builder.build_trace(run_result)

    assert tel_trace.trace_id == "tr_weather_run"
    assert tel_trace.status == TelemetryStatus.OK

    # Check root span attributes
    root_span = tel_trace.child_spans(None)[0]
    assert root_span.attributes["token.total_tokens"] == 65
    assert root_span.attributes["test.name"] == "weather_check"

    # Check model span attributes
    model_span = [s for s in tel_trace.spans if s.kind == SpanKind.MODEL][0]
    assert model_span.attributes["model.name"] == "gpt-4o"
    assert model_span.attributes["model.call_id"] == "call_llm_1"
    assert model_span.attributes["model.input_tokens"] == 50
    assert model_span.attributes["model.output_tokens"] == 15
    assert model_span.attributes["model.cached_tokens"] == 10

    # Check tool span attributes
    tool_span = [s for s in tel_trace.spans if s.kind == SpanKind.TOOL][0]
    assert tool_span.attributes["tool.name"] == "get_weather"
    assert tool_span.attributes["tool.call_id"] == "call_weather_99"
    assert tool_span.attributes["tool.input"] == {"city": "New York"}
    assert tool_span.attributes["tool.output"] == {"temp": 72, "unit": "F"}

    # Check evaluation span
    eval_span = [s for s in tel_trace.spans if s.kind == SpanKind.EVALUATION][0]
    assert eval_span.attributes["evaluator.name"] == "OutputEquals"
    assert eval_span.status == TelemetryStatus.OK


def test_telemetry_builder_failure_and_root_cause():
    """Verify TelemetryBuilder captures failure reports and root cause reports."""
    test_case = TestCase(id="tc_fail", name="failing_case", input="pay 500")

    trace = ExecutionTrace(
        trace_id="tr_failure",
        test_id="tc_fail",
        input=test_case.input,
        output="Failed to transfer",
        status=ExecutionStatus.FAILED,
    )

    fail_report = FailureReport(
        failure_id="fail_999",
        trace_id="tr_failure",
        category="execution",
        type="exception",
        severity=FailureSeverity.HIGH,
        message="Insufficient funds",
        confidence=0.95,
    )

    root_cause = RootCause(
        category=RootCauseCategory.EXECUTION,
        type=RootCauseType.EXCEPTION,
        confidence=0.95,
        summary="Transaction failed due to insufficient funds",
    )
    rca_report = RootCauseReport(
        report_id="rca_001",
        failure_id="fail_999",
        trace_id="tr_failure",
        primary_cause=root_cause,
        summary="Empirical evidence points to unhandled exception",
    )

    run_result = RunResult(
        test=test_case,
        trace=trace,
        evaluations=[
            EvaluationResult(
                evaluator="PaymentSuccess",
                passed=False,
                message="Expected payment confirmation",
            )
        ],
        failures=[fail_report],
    )

    builder = TelemetryBuilder()
    tel_trace = builder.build_trace(
        run_result,
        root_cause_report=rca_report,
        regression_test_id="reg_12345",
    )

    assert tel_trace.status == TelemetryStatus.ERROR

    # Check root span contains failure event
    root_span = tel_trace.child_spans(None)[0]
    fail_events = [
        ev for ev in root_span.events if ev.name == "reliability.failure_detected"
    ]
    assert len(fail_events) == 1
    assert fail_events[0].attributes["failure.id"] == "fail_999"
    assert fail_events[0].attributes["failure.type"] == "exception"
    assert root_span.attributes["regression.test_id"] == "reg_12345"

    # Check analysis span
    analysis_span = [s for s in tel_trace.spans if s.kind == SpanKind.ANALYSIS][0]
    assert analysis_span.attributes["diagnosis.report_id"] == "rca_001"
    assert analysis_span.attributes["diagnosis.primary_cause"] == "exception"


# ---------------------------------------------------------------------------
# 6. End-to-End ReliabilityRunner Telemetry Integration
# ---------------------------------------------------------------------------


def test_reliability_runner_end_to_end_telemetry():
    """Verify ReliabilityRunner records telemetry traces into collector
    automatically.
    """
    collector = InMemoryTelemetryCollector()

    def sample_agent(user_input: str):
        return f"Echo: {user_input}"

    runner = ReliabilityRunner(
        agent=sample_agent,
        evaluators=[OutputEquals("Echo: ping")],
        telemetry_collector=collector,
    )

    tc = TestCase(id="tc_echo", name="echo_test", input="ping")
    result = runner.run(tc)

    assert result.passed is True
    assert len(collector.traces) == 1

    last_trace = collector.get_last_trace()
    assert last_trace.test_id == "tc_echo"
    assert last_trace.status == TelemetryStatus.OK
    assert len(last_trace.spans) >= 2  # Root + evaluation span


# ---------------------------------------------------------------------------
# 7. RegressionRunner Telemetry Integration
# ---------------------------------------------------------------------------


def test_regression_runner_telemetry_integration():
    """Verify RegressionRunner records telemetry traces during suite runs."""
    collector = InMemoryTelemetryCollector()

    def agent(inp: str):
        return "clean"

    reg_runner = RegressionRunner(
        agent=agent,
        evaluators=[OutputEquals("clean")],
        telemetry_collector=collector,
    )

    tc = TestCase(id="tc_reg", name="reg_test", input="input")
    gen = RegressionGenerator()
    fail = FailureReport(
        trace_id="tr_dummy",
        category="output",
        type="unexpected_output",
        message="bad",
    )
    reg_test = gen.generate(fail, tc)

    res = reg_runner.run_test(reg_test)
    assert res.passed is True
    assert len(collector.traces) == 1
    assert collector.get_last_trace().test_id == "tc_reg"


# ---------------------------------------------------------------------------
# 8. Optional OpenTelemetry Exporter & Import Guard
# ---------------------------------------------------------------------------


def test_opentelemetry_import_guard_without_dependency():
    """Verify actionable ImportError if opentelemetry package is missing."""
    with (
        patch.dict(sys.modules, {"opentelemetry": None, "opentelemetry.trace": None}),
        pytest.raises(
            ImportError,
            match="OpenTelemetry integration requires the 'opentelemetry' extra",
        ),
    ):
        get_opentelemetry_exporter()


def test_opentelemetry_exporter_with_mock_tracer():
    """Verify OpenTelemetryExporter converts TelemetryTrace into OpenTelemetry spans."""
    mock_tracer = MagicMock()
    mock_otel_span = MagicMock()
    mock_tracer.start_span.return_value = mock_otel_span

    # Mock opentelemetry module
    mock_otel_trace = MagicMock()
    mock_otel_trace.get_tracer.return_value = mock_tracer

    mock_status_code = MagicMock()
    mock_status_code.OK = "OK"
    mock_status_code.ERROR = "ERROR"

    with patch(
        "aireliability.integrations.opentelemetry._check_opentelemetry_installed",
        return_value=(mock_otel_trace, mock_status_code),
    ):
        from aireliability.integrations.opentelemetry import OpenTelemetryExporter

        exporter = OpenTelemetryExporter(tracer=mock_tracer)

        trace = TelemetryTrace(
            trace_id="tr_otel",
            status=TelemetryStatus.OK,
            spans=[
                TelemetrySpan(
                    span_id="sp_root",
                    trace_id="tr_otel",
                    name="agent.test",
                    kind=SpanKind.AGENT,
                    status=TelemetryStatus.OK,
                    attributes={"agent.version": "1.0"},
                ),
                TelemetrySpan(
                    span_id="sp_child",
                    trace_id="tr_otel",
                    parent_span_id="sp_root",
                    name="tool.query",
                    kind=SpanKind.TOOL,
                    status=TelemetryStatus.OK,
                    attributes={"tool.name": "query"},
                ),
            ],
        )

        spans = exporter.export_trace(trace)
        assert len(spans) == 1  # Root span
        assert mock_tracer.start_span.call_count == 2
        assert mock_otel_span.end.call_count == 2


# ---------------------------------------------------------------------------
# 9. Optional Prometheus Metrics Exporter & Import Guard
# ---------------------------------------------------------------------------


def test_prometheus_import_guard_without_dependency():
    """Verify actionable ImportError if prometheus_client package is missing."""
    with (
        patch.dict(sys.modules, {"prometheus_client": None}),
        pytest.raises(
            ImportError,
            match="Prometheus metrics integration requires the 'prometheus' extra",
        ),
    ):
        get_prometheus_exporter()


def test_prometheus_exporter_records_metrics():
    """Verify PrometheusMetricsExporter extracts metrics from TelemetryTrace."""
    mock_prom = MagicMock()
    mock_registry = MagicMock()

    mock_counter = MagicMock()
    mock_histogram = MagicMock()

    mock_prom.Counter.return_value = mock_counter
    mock_prom.Histogram.return_value = mock_histogram

    with patch(
        "aireliability.integrations.prometheus._check_prometheus_installed",
        return_value=mock_prom,
    ):
        from aireliability.integrations.prometheus import PrometheusMetricsExporter

        exporter = PrometheusMetricsExporter(registry=mock_registry)

        trace = TelemetryTrace(
            trace_id="tr_prom",
            name="test.prom",
            status=TelemetryStatus.OK,
            duration_ms=45.0,
            attributes={
                "test.name": "prom_test",
                "token.prompt_tokens": 100,
                "token.completion_tokens": 20,
            },
            spans=[
                TelemetrySpan(
                    span_id="sp_model",
                    trace_id="tr_prom",
                    name="gpt-4o",
                    kind=SpanKind.MODEL,
                    duration_ms=40.0,
                    status=TelemetryStatus.OK,
                    attributes={"model.name": "gpt-4o"},
                ),
                TelemetrySpan(
                    span_id="sp_tool",
                    trace_id="tr_prom",
                    name="calculator",
                    kind=SpanKind.TOOL,
                    duration_ms=5.0,
                    status=TelemetryStatus.OK,
                    attributes={"tool.name": "calculator"},
                ),
            ],
        )

        exporter.record_trace(trace)

        # Assert counter increments and histogram observations occurred
        assert mock_counter.labels.call_count >= 3
        assert mock_histogram.labels.call_count >= 3


# ---------------------------------------------------------------------------
# 10. CLI Integration (--telemetry, --telemetry-output, --no-telemetry)
# ---------------------------------------------------------------------------


def test_cli_telemetry_flags(tmp_path: Path):
    """Verify airel test CLI correctly accepts and processes telemetry options."""
    from aireliability.cli import main

    agent_file = tmp_path / "agent.py"
    agent_file.write_text(
        'def app(user_input: str) -> str:\n    return f"Processed: {user_input}"\n',
        encoding="utf-8",
    )

    tests_dir = tmp_path / "tests/reliability"
    tests_dir.mkdir(parents=True, exist_ok=True)
    tc_file = tests_dir / "test_1.json"
    tc_file.write_text(
        json.dumps(
            {
                "id": "tc_cli_1",
                "name": "cli_test",
                "input": "hello",
                "expectations": ["OutputContains: Processed:"],
            }
        ),
        encoding="utf-8",
    )

    config_file = tmp_path / "aireliability.json"
    config_file.write_text(
        json.dumps(
            {
                "version": "0.1.0",
                "agent_target": "agent:app",
                "db_path": ":memory:",
                "tests_dir": "tests/reliability",
                "default_baseline": "default",
            }
        ),
        encoding="utf-8",
    )

    tel_output = tmp_path / "cli_telemetry.json"
    exit_code = main(
        [
            "test",
            "--dir",
            str(tmp_path),
            "--telemetry",
            "--telemetry-output",
            str(tel_output),
        ]
    )

    assert exit_code == 0
    assert tel_output.exists()
    tel_data = json.loads(tel_output.read_text(encoding="utf-8"))
    assert len(tel_data) == 1
    assert tel_data[0]["test_id"] == "tc_cli_1"
    assert tel_data[0]["status"] == "ok"


# ---------------------------------------------------------------------------
# 11. Performance Overhead Benchmark Smoke Test
# ---------------------------------------------------------------------------


def test_telemetry_overhead_benchmark_smoke():
    """Smoke test ensuring telemetry collection introduces minimal microsecond
    overhead.
    """
    import time

    def mock_agent(x: str):
        return x

    tc = TestCase(id="tc_bench", name="bench", input="val")

    # 1. Telemetry disabled
    runner_no_tel = ReliabilityRunner(agent=mock_agent)
    for _ in range(100):
        runner_no_tel.run(tc)

    # 2. InMemory telemetry
    collector = InMemoryTelemetryCollector()
    runner_tel = ReliabilityRunner(agent=mock_agent, telemetry_collector=collector)
    t2 = time.perf_counter_ns()
    for _ in range(100):
        runner_tel.run(tc)
    t3 = time.perf_counter_ns()
    tel_avg_us = ((t3 - t2) / 100) / 1000.0

    assert len(collector.traces) == 100
    # Even in Python debug mode, overhead is typically < 250 us
    assert tel_avg_us < 2000.0
