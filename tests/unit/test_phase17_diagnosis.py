"""Unit tests for Phase 17 Evidence-Based Root Cause Analysis.

Covers:
1. Deterministic Root-Cause Rules:
   - Wrong tool
   - Wrong arguments
   - Wrong order
   - Missing tool
   - Output mismatch
   - Latency regression
2. Semantic Failure Diagnosis:
   - Score below threshold
   - Evaluation criteria preserved
   - Judge rationale & evidence captured
3. Multi-Failure Handling & Primary/Secondary Classification:
   - Primary vs. secondary cause selection based on category/severity precedence
   - Causal link generation (e.g. tool error -> output discrepancy)
4. Evidence Traceability & Non-speculation:
   - Every field grounded in actual trace or evaluation output
   - No hidden model intentions claimed
5. End-to-End Workflow:
   - Faulty Agent -> Trace -> FailureReport -> RootCauseAnalyzer
     -> RegressionGenerator -> RegressionTest -> Fixed (PASS) -> Bug (REGRESSION)
"""

from aireliability import (
    BaselineManager,
    CallableAdapter,
    ComparisonStatus,
    ExecutionTrace,
    FailureCategory,
    FailureReport,
    FailureSeverity,
    FailureType,
    RegressionGenerator,
    ReliabilityRunner,
    RootCauseAnalyzer,
    RootCauseCategory,
    RootCauseType,
    TestCase,
    ToolOrder,
    TraceStep,
)
from aireliability.core.models import StepType
from examples.local_agent import LocalSupportAgent

# ---------------------------------------------------------------------------
# 1. Deterministic Diagnosis Rules
# ---------------------------------------------------------------------------


def test_diagnose_wrong_tool_missing():
    """Verify missing required tool diagnosis."""
    tc = TestCase(name="test_missing_tool", input="ping")
    trace = ExecutionTrace(
        test_id=tc.id,
        steps=[TraceStep(name="other_tool", type=StepType.TOOL)],
    )
    failure = FailureReport(
        trace_id=trace.trace_id,
        test_id=tc.id,
        category=FailureCategory.TOOL.value,
        type=FailureType.WRONG_TOOL.value,
        message="Expected tool 'get_order' was not called.",
        evidence={
            "expected_tool": "get_order",
            "actual_calls": 0,
            "called_tools": ["other_tool"],
        },
        confidence=1.0,
    )

    analyzer = RootCauseAnalyzer()
    report = analyzer.diagnose(trace, [failure], test_case=tc)

    assert report.status == "FAIL"
    assert report.primary_cause is not None
    pc = report.primary_cause
    assert pc.category == RootCauseCategory.TOOL
    assert pc.type == RootCauseType.MISSING_TOOL
    assert pc.confidence == 1.0
    assert len(pc.evidence) == 1
    ev = pc.evidence[0]
    assert ev.field == "tool_called"
    assert "get_order" in ev.expected


def test_diagnose_wrong_arguments():
    """Verify wrong tool arguments diagnosis."""
    step = TraceStep(name="refund_order", type=StepType.TOOL, input={"order_id": "456"})
    trace = ExecutionTrace(steps=[step])
    failure = FailureReport(
        trace_id=trace.trace_id,
        category=FailureCategory.TOOL.value,
        type=FailureType.WRONG_ARGUMENT.value,
        message="Tool argument mismatch",
        evidence={
            "tool_name": "refund_order",
            "expected_arguments": {"order_id": "123"},
            "actual_arguments": {"order_id": "456"},
        },
        confidence=1.0,
    )

    analyzer = RootCauseAnalyzer()
    report = analyzer.diagnose(trace, [failure])

    assert report.primary_cause is not None
    pc = report.primary_cause
    assert pc.category == RootCauseCategory.TOOL
    assert pc.type == RootCauseType.WRONG_ARGUMENT
    assert pc.affected_step == step.id
    assert pc.evidence[0].expected == {"order_id": "123"}
    assert pc.evidence[0].actual == {"order_id": "456"}


def test_diagnose_wrong_order():
    """Verify tool ordering sequence diagnosis."""
    s1 = TraceStep(name="get_order", type=StepType.TOOL)
    s2 = TraceStep(name="refund_order", type=StepType.TOOL)
    s3 = TraceStep(name="cancel_order", type=StepType.TOOL)
    trace = ExecutionTrace(steps=[s1, s2, s3])

    failure = FailureReport(
        trace_id=trace.trace_id,
        category=FailureCategory.TOOL.value,
        type=FailureType.WRONG_ORDER.value,
        message="Tool sequence violated",
        evidence={
            "expected_order": ["get_order", "cancel_order", "refund_order"],
            "actual_order": ["get_order", "refund_order", "cancel_order"],
        },
        confidence=1.0,
    )

    analyzer = RootCauseAnalyzer()
    report = analyzer.diagnose(trace, [failure])

    assert report.primary_cause is not None
    pc = report.primary_cause
    assert pc.category == RootCauseCategory.TOOL
    assert pc.type == RootCauseType.WRONG_ORDER
    assert pc.affected_step == s2.id
    assert "expected 'get_order → cancel_order → refund_order'" in pc.description


def test_diagnose_output_mismatch():
    """Verify output discrepancy diagnosis."""
    tc = TestCase(name="out_test", input="123", expected_output="Success")
    trace = ExecutionTrace(input="123", output="Failed")
    failure = FailureReport(
        trace_id=trace.trace_id,
        category=FailureCategory.TASK.value,
        type=FailureType.TASK_INCORRECT.value,
        message="Output mismatch",
        evidence={"expected": "Success", "actual": "Failed"},
        confidence=1.0,
    )

    analyzer = RootCauseAnalyzer()
    report = analyzer.diagnose(trace, [failure], test_case=tc)

    pc = report.primary_cause
    assert pc is not None
    assert pc.category == RootCauseCategory.OUTPUT
    assert pc.type == RootCauseType.UNEXPECTED_OUTPUT
    assert pc.evidence[0].actual == "Failed"
    assert pc.evidence[0].expected == "Success"


def test_diagnose_latency_regression():
    """Verify execution duration regression diagnosis."""
    trace = ExecutionTrace(latency_ms=512.4)
    failure = FailureReport(
        trace_id=trace.trace_id,
        category=FailureCategory.PERFORMANCE.value,
        type=FailureType.LATENCY.value,
        message="Latency exceeded",
        evidence={"max_latency_ms": 150.0, "actual_latency_ms": 512.4},
        confidence=1.0,
    )

    analyzer = RootCauseAnalyzer()
    report = analyzer.diagnose(trace, [failure])

    pc = report.primary_cause
    assert pc is not None
    assert pc.category == RootCauseCategory.PERFORMANCE
    assert pc.type == RootCauseType.LATENCY_REGRESSION
    assert "exceeding budget of 150.0ms" in pc.description


# ---------------------------------------------------------------------------
# 2. Semantic Failure Diagnosis
# ---------------------------------------------------------------------------


def test_diagnose_semantic_mismatch():
    """Verify semantic judge failure diagnosis with preserved evidence."""
    trace = ExecutionTrace(input="Help", output="No help available.")
    failure = FailureReport(
        trace_id=trace.trace_id,
        category=FailureCategory.OUTPUT.value,
        type=FailureType.SEMANTIC_RELEVANCE.value,
        message="Semantic relevance failed",
        evidence={
            "score": 0.42,
            "threshold": 0.80,
            "judge_explanation": "Response unhelpful to user request.",
            "provider": "mock",
            "model": "mock-judge-v1",
            "criteria_results": {"relevance": False},
        },
        confidence=0.85,
    )

    analyzer = RootCauseAnalyzer()
    report = analyzer.diagnose(trace, [failure])

    pc = report.primary_cause
    assert pc is not None
    assert pc.category == RootCauseCategory.OUTPUT
    assert pc.type == RootCauseType.SEMANTIC_MISMATCH
    assert pc.confidence == 0.85
    assert len(pc.evidence) == 1
    ev = pc.evidence[0]
    assert ev.expected == "Score >= 0.8"
    assert ev.actual == "Score 0.42"
    assert "Response unhelpful" in ev.explanation


# ---------------------------------------------------------------------------
# 3. Multi-Failure Handling & Primary/Secondary Precedence
# ---------------------------------------------------------------------------


def test_multi_failure_primary_secondary_and_causal_link():
    """Verify tool error takes precedence over output mismatch with causal link."""
    step = TraceStep(name="delete_order", type=StepType.TOOL)
    trace = ExecutionTrace(steps=[step], output="Order deleted")

    f_tool = FailureReport(
        trace_id=trace.trace_id,
        category=FailureCategory.TOOL.value,
        type=FailureType.WRONG_TOOL.value,
        severity=FailureSeverity.HIGH,
        message="Wrong tool called",
        evidence={"expected_tool": "get_order", "called_tools": ["delete_order"]},
    )
    f_output = FailureReport(
        trace_id=trace.trace_id,
        category=FailureCategory.OUTPUT.value,
        type=FailureType.SCHEMA_ERROR.value,
        severity=FailureSeverity.MEDIUM,
        message="Output schema invalid",
        evidence={"schema": "order_view"},
    )

    analyzer = RootCauseAnalyzer()
    report = analyzer.diagnose(trace, [f_output, f_tool])

    assert report.primary_cause is not None
    # Tool error prioritized over output schema failure
    assert report.primary_cause.category == RootCauseCategory.TOOL
    assert len(report.secondary_causes) == 1
    assert report.secondary_causes[0].category == RootCauseCategory.OUTPUT

    # Check causal link generated
    assert len(report.causal_chain) == 1
    link = report.causal_chain[0]
    assert link.source == step.id
    assert link.target == "final_output"
    assert "directly preceded" in link.reason


# ---------------------------------------------------------------------------
# 4. Terminal Report Formatting
# ---------------------------------------------------------------------------


def test_root_cause_report_terminal_formatting():
    """Verify format_terminal() contains clean, readable data."""
    trace = ExecutionTrace(
        test_id="test_demo", steps=[TraceStep(name="s1", type=StepType.TOOL)]
    )
    f = FailureReport(
        trace_id=trace.trace_id,
        test_id="test_demo",
        category=FailureCategory.TOOL.value,
        type=FailureType.WRONG_ORDER.value,
        message="Wrong order",
        evidence={"expected_order": ["a", "b"], "actual_order": ["b", "a"]},
    )
    analyzer = RootCauseAnalyzer()
    report = analyzer.diagnose(trace, [f])

    terminal_text = report.format_terminal()
    assert "AI Reliability Root Cause Analysis" in terminal_text
    assert "Primary Detected Cause: TOOL.WRONG_ORDER" in terminal_text
    assert "Expected: a → b" in terminal_text
    assert "Actual:   b → a" in terminal_text


# ---------------------------------------------------------------------------
# 5. End-to-End Workflow with Regression Generation
# ---------------------------------------------------------------------------


def test_end_to_end_root_cause_and_regression_workflow():
    """Complete lifecycle: Faulty -> Cause -> Regression -> Fix -> Reintroduce."""
    test = TestCase(
        id="support_diag_tc",
        name="support_diag",
        input="I need a refund for order 123.",
        expected_output=(
            "Your refund and cancellation for order 123 has been processed."
        ),
    )

    evaluators = [
        ToolOrder(
            expected_order=["get_order", "cancel_order", "refund_order"],
            exact_match=True,
        )
    ]

    # 1. Execute Faulty Agent
    faulty_agent = LocalSupportAgent(mode="faulty")
    adapter = CallableAdapter(agent=faulty_agent)
    runner = ReliabilityRunner(
        agent=faulty_agent, adapter=adapter, evaluators=evaluators
    )
    run_faulty = runner.run(test)

    assert not run_faulty.passed
    assert len(run_faulty.failures) == 1

    # 2. Diagnose Root Cause
    analyzer = RootCauseAnalyzer()
    diag_report = analyzer.diagnose_run_result(run_faulty)

    assert diag_report.status == "FAIL"
    assert diag_report.primary_cause is not None
    assert diag_report.primary_cause.category == RootCauseCategory.TOOL
    assert diag_report.primary_cause.type == RootCauseType.WRONG_ORDER

    # 3. Generate Regression Test with Root Cause Provenance
    generator = RegressionGenerator()
    reg_test = generator.generate(
        failure=run_faulty.failures[0],
        test_case=test,
        root_cause=diag_report.primary_cause,
    )

    assert reg_test.source_failure_id == run_faulty.failures[0].failure_id
    assert reg_test.metadata["root_cause_id"] == diag_report.primary_cause.id
    assert "root_cause_evidence" in reg_test.metadata
    assert reg_test.test_case.metadata["root_cause_id"] == diag_report.primary_cause.id

    # 4. Baseline Manager tracks initial failure
    baseline_mgr = BaselineManager()
    baseline_mgr.create_baseline([run_faulty], name="default")

    # 5. Fixed Agent passes
    fixed_agent = LocalSupportAgent(mode="nominal")
    fixed_runner = ReliabilityRunner(
        agent=fixed_agent,
        adapter=CallableAdapter(agent=fixed_agent),
        evaluators=evaluators,
    )
    run_fixed = fixed_runner.run(test)
    assert run_fixed.passed

    comp_fixed = baseline_mgr.compare_single(run_fixed, baseline_name="default")
    assert comp_fixed.status == ComparisonStatus.FIXED

    # Update baseline with passing run
    baseline_mgr.create_baseline([run_fixed], name="default")

    # 6. Reintroduce Bug -> REGRESSION
    run_reintroduced = runner.run(test)
    assert not run_reintroduced.passed

    comp_reintroduced = baseline_mgr.compare_single(
        run_reintroduced, baseline_name="default"
    )
    assert comp_reintroduced.status == ComparisonStatus.REGRESSION
