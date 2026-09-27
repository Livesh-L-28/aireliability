"""Unit and integration tests for Phase 18 Intelligent Regression Generation.

Covers:
1. Failure-Type-Specific Generation:
   - WRONG_TOOL
   - WRONG_ARGUMENT
   - WRONG_ORDER
   - MISSING_TOOL
   - Output mismatch (exact & contains)
   - Semantic mismatch (criteria, threshold, judge rationale)
   - Latency regression (MaxLatency)
2. Conservative Minimization:
   - Input field pruning supported by evidence
   - Trace step pruning preserving failure steps and causal links
   - Fallback when minimization cannot be safely established
3. Regression Quality Validation:
   - Identity and source failure presence
   - Reproducibility (input + assertions)
   - Specificity (rejecting trivial assert output != '')
   - Traceability (failure ID + root cause ID)
4. Duplicate Detection:
   - Equivalence detection based on failure type, inputs, and expectations
   - Status reporting DUPLICATE without creating duplicate tests
5. Insufficient Evidence Handling:
   - Safety behavior reporting INSUFFICIENT_EVIDENCE
6. Provenance Tracking:
   - Full chain: RegressionCandidate -> RootCause -> FailureReport -> ExecutionTrace
7. End-to-End Workflow:
   - Faulty Agent -> Trace -> FailureReport -> RootCause -> Synthesizer ->
     Validated Regression -> RegressionRunner (FAIL) -> Fixed Agent (PASS) ->
     Bug Reintroduced (REGRESSION)
"""

from aireliability import (
    BaselineManager,
    CallableAdapter,
    ComparisonStatus,
    Evidence,
    ExecutionTrace,
    FailureReport,
    GenerationMethod,
    GenerationStatus,
    RegressionCandidate,
    RegressionGenerator,
    RegressionMinimizer,
    RegressionRunner,
    RegressionSynthesizer,
    RegressionTest,
    RegressionValidator,
    ReliabilityRunner,
    RootCause,
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
# 1. Failure-Type-Specific Synthesis Tests
# ---------------------------------------------------------------------------


def test_synthesize_wrong_order_regression():
    """Verify intelligent synthesis captures minimal tool order expectation."""
    tc = TestCase(
        name="refund_flow",
        input={"order_id": "ORD-101", "unrelated_session": "sess_99"},
        expectations=["ToolOrder:get_order,cancel_order,refund_order"],
    )
    failure = FailureReport(
        trace_id="trace_order_01",
        test_id=tc.id,
        category="tool",
        type="wrong_order",
        message="Tools executed out of order",
        evidence={
            "expected_order": ["get_order", "cancel_order", "refund_order"],
            "actual_order": ["get_order", "refund_order", "cancel_order"],
        },
    )
    rc = RootCause(
        category=RootCauseCategory.TOOL,
        type=RootCauseType.WRONG_ORDER,
        description="Tools out of order",
        affected_step="step_2",
        evidence=[
            Evidence(
                source="execution_trace",
                trace_id="trace_order_01",
                field="tool_order",
                expected="get_order → cancel_order → refund_order",
                actual="get_order → refund_order → cancel_order",
            )
        ],
    )

    synthesizer = RegressionSynthesizer()
    cand = synthesizer.synthesize(failure, tc, root_cause=rc)

    assert cand.status == GenerationStatus.SUCCESS
    assert cand.validation is not None
    assert cand.validation.valid is True
    assert cand.validation.reproducible is True
    assert cand.validation.specific is True
    assert cand.test_case.metadata["expected_order"] == [
        "get_order",
        "cancel_order",
        "refund_order",
    ]
    expected_rule = "ToolOrder:get_order,cancel_order,refund_order"
    assert expected_rule in cand.test_case.expectations
    assert cand.generation_method == GenerationMethod.DETERMINISTIC_TRACE_SYNTHESIS
    assert cand.root_cause_id == rc.id


def test_synthesize_wrong_argument_regression():
    """Verify intelligent synthesis captures target tool arguments."""
    tc = TestCase(
        name="refund_args",
        input={"order_id": "ORD-555", "user_note": "urgent"},
    )
    failure = FailureReport(
        trace_id="trace_args_01",
        test_id=tc.id,
        category="tool",
        type="wrong_argument",
        message="Tool argument mismatch",
        evidence={
            "tool_name": "refund_order",
            "expected_arguments": {"order_id": "ORD-555", "amount": 100},
            "actual_arguments": {"order_id": "ORD-999", "amount": 100},
        },
    )
    rc = RootCause(
        category=RootCauseCategory.TOOL,
        type=RootCauseType.WRONG_ARGUMENT,
        description="Wrong argument order_id",
        evidence=[
            Evidence(
                source="evaluator_result",
                field="arguments",
                expected={"order_id": "ORD-555", "amount": 100},
                actual={"order_id": "ORD-999", "amount": 100},
            )
        ],
    )

    synthesizer = RegressionSynthesizer()
    cand = synthesizer.synthesize(failure, tc, root_cause=rc)

    assert cand.status == GenerationStatus.SUCCESS
    assert "ToolArguments:refund_order" in cand.test_case.expectations
    assert cand.test_case.metadata["expected_arguments"] == {
        "order_id": "ORD-555",
        "amount": 100,
    }
    assert cand.test_case.metadata["expected_tool"] == "refund_order"


def test_synthesize_missing_tool_regression():
    """Verify intelligent synthesis captures missing required tool expectation."""
    tc = TestCase(name="fetch_profile", input="user_123")
    failure = FailureReport(
        trace_id="trace_missing_01",
        test_id=tc.id,
        category="tool",
        type="wrong_tool",
        message="Expected tool 'get_profile' was not called",
        evidence={"expected_tool": "get_profile", "actual_calls": 0},
    )
    rc = RootCause(
        category=RootCauseCategory.TOOL,
        type=RootCauseType.MISSING_TOOL,
        description="Required tool omitted",
        evidence=[
            Evidence(
                source="evaluator_result",
                field="tool_called",
                expected="get_profile",
                actual="[]",
            )
        ],
    )

    synthesizer = RegressionSynthesizer()
    cand = synthesizer.synthesize(failure, tc, root_cause=rc)

    assert cand.status == GenerationStatus.SUCCESS
    assert "ToolCalled:get_profile" in cand.test_case.expectations
    assert cand.test_case.metadata["expected_tool"] == "get_profile"


def test_synthesize_semantic_mismatch_regression():
    """Verify semantic failure captures criteria, threshold, and reference."""
    tc = TestCase(
        name="semantic_summary",
        input="Summarize customer claim",
        expected_output="Customer requested refund for broken item",
    )
    failure = FailureReport(
        trace_id="trace_sem_01",
        test_id=tc.id,
        category="output",
        type="semantic_violation",
        message="Summary lacked critical details",
        evidence={
            "score": 0.52,
            "threshold": 0.85,
            "criteria": ["completeness", "accuracy"],
            "reference": "Customer requested refund for broken item",
            "evaluator": "SemanticExpectation",
        },
    )
    rc = RootCause(
        category=RootCauseCategory.OUTPUT,
        type=RootCauseType.SEMANTIC_MISMATCH,
        description="Semantic score 0.52 below threshold 0.85",
        evidence=[
            Evidence(
                source="semantic_evaluator",
                field="output_semantics",
                expected="Score >= 0.85",
                actual="Score 0.52",
            )
        ],
    )

    synthesizer = RegressionSynthesizer()
    cand = synthesizer.synthesize(failure, tc, root_cause=rc)

    assert cand.status == GenerationStatus.SUCCESS
    assert cand.generation_method == GenerationMethod.SEMANTIC_FAILURE_CAPTURE
    assert cand.test_case.metadata["semantic_threshold"] == 0.85
    assert cand.test_case.metadata["semantic_criteria"] == [
        "completeness",
        "accuracy",
    ]
    assert (
        cand.test_case.metadata["semantic_reference"]
        == "Customer requested refund for broken item"
    )
    assert "SemanticMatch:threshold=0.85" in cand.test_case.expectations


def test_synthesize_performance_latency_regression():
    """Verify latency regressions preserve max latency expectation."""
    tc = TestCase(name="fast_lookup", input="order_1")
    failure = FailureReport(
        trace_id="trace_lat_01",
        test_id=tc.id,
        category="performance",
        type="latency",
        message="Elapsed latency 620ms exceeded 200ms limit",
        evidence={"max_latency_ms": 200.0, "actual_latency_ms": 620.0},
    )
    rc = RootCause(
        category=RootCauseCategory.PERFORMANCE,
        type=RootCauseType.LATENCY_REGRESSION,
        description="Latency exceeded limit",
        evidence=[
            Evidence(
                source="execution_trace",
                field="latency_ms",
                expected="<= 200.0ms",
                actual="620.0ms",
            )
        ],
    )

    synthesizer = RegressionSynthesizer()
    cand = synthesizer.synthesize(failure, tc, root_cause=rc)

    assert cand.status == GenerationStatus.SUCCESS
    assert cand.test_case.metadata["max_latency_ms"] == 200.0
    assert "MaxLatency:200.0" in cand.test_case.expectations


# ---------------------------------------------------------------------------
# 2. Minimization Tests
# ---------------------------------------------------------------------------


def test_conservative_input_minimizer_reduces_unrelated_fields():
    """Verify input fields not referenced in evidence or metadata are pruned."""
    minimizer = RegressionMinimizer()
    original_input = {
        "order_id": "ORD-99",
        "client_session": "sess_abc",
        "user_agent": "Mozilla/5.0",
        "timestamp_device": 1720000000,
    }
    rc = RootCause(
        category=RootCauseCategory.TOOL,
        type=RootCauseType.WRONG_ARGUMENT,
        description="Wrong order_id",
        evidence=[
            Evidence(
                source="evaluator_result",
                field="order_id",
                expected="ORD-99",
                actual="ORD-100",
            )
        ],
    )
    tc = TestCase(name="tc_min", input=original_input)

    minimized, was_min = minimizer.minimize_input(
        original_input, root_cause=rc, test_case=tc
    )

    assert was_min is True
    assert minimized == {"order_id": "ORD-99"}
    assert "client_session" not in minimized
    assert "user_agent" not in minimized


def test_conservative_input_minimizer_preserves_input_when_unsafe():
    """Verify minimizer retains original input if no key can be safely isolated."""
    minimizer = RegressionMinimizer()
    original_input = {"unknown_a": 1, "unknown_b": 2}
    rc = RootCause(
        category=RootCauseCategory.UNKNOWN,
        type=RootCauseType.UNKNOWN,
        description="Generic error",
        evidence=[Evidence(source="evaluator", field="", expected="", actual="")],
    )

    minimized, was_min = minimizer.minimize_input(original_input, root_cause=rc)

    assert was_min is False
    assert minimized == original_input


def test_conservative_trace_minimizer_prunes_unrelated_steps():
    """Verify execution steps unrelated to failure or causal links are safely pruned."""
    minimizer = RegressionMinimizer()
    steps = [
        TraceStep(id="s1", name="log_start", type=StepType.SYSTEM),
        TraceStep(id="s2", name="get_order", type=StepType.TOOL),
        TraceStep(id="s3", name="metric_counter", type=StepType.SYSTEM),
        TraceStep(id="s4", name="refund_order", type=StepType.TOOL),
        TraceStep(id="s5", name="log_end", type=StepType.SYSTEM),
    ]
    trace = ExecutionTrace(trace_id="tr_steps_01", steps=steps)
    rc = RootCause(
        category=RootCauseCategory.TOOL,
        type=RootCauseType.WRONG_ORDER,
        description="Order error",
        evidence=[
            Evidence(
                source="evaluator_result",
                field="tool_order",
                expected="get_order → cancel_order → refund_order",
                actual="get_order → refund_order",
            )
        ],
    )

    pruned_steps, was_min = minimizer.minimize_trace_steps(trace, root_cause=rc)

    assert was_min is True
    assert len(pruned_steps) == 2
    step_names = [s.name for s in pruned_steps]
    assert step_names == ["get_order", "refund_order"]


# ---------------------------------------------------------------------------
# 3. Quality Validation and Duplicate Detection Tests
# ---------------------------------------------------------------------------


def test_validator_rejects_trivial_assertions():
    """Verify validator catches and rejects trivial, non-specific assertions."""
    validator = RegressionValidator()
    tc = TestCase(
        name="trivial_test",
        input={"order_id": "ORD-1"},
        expectations=["assert output != ''"],
    )
    cand = RegressionCandidate(
        name="cand_trivial",
        source_failure_id="fail_triv_01",
        test_case=tc,
    )

    val = validator.validate(cand)
    assert val.valid is False
    assert val.specific is False
    assert any("trivial" in r for r in val.reasons)


def test_duplicate_detection_identifies_equivalent_test():
    """Verify duplicate detection identifies existing test with matching criteria."""
    validator = RegressionValidator()
    existing_tc = TestCase(
        name="existing_reg",
        input={"order_id": "ORD-777"},
        expectations=["ToolOrder:a,b,c"],
        metadata={"failure_type": "wrong_order"},
    )
    existing_test = RegressionTest(
        id="reg_existing_001",
        name="reg_existing_001",
        source_failure_id="fail_old_01",
        test_case=existing_tc,
    )

    new_tc = TestCase(
        name="new_candidate",
        input={"order_id": "ORD-777"},
        expectations=["ToolOrder:a,b,c"],
        metadata={"failure_type": "wrong_order"},
    )
    cand = RegressionCandidate(
        name="cand_dup",
        source_failure_id="fail_new_02",
        test_case=new_tc,
    )

    val = validator.validate(cand, existing_tests=[existing_test])
    assert val.duplicate is True
    assert val.valid is False
    assert any("reg_existing_001" in r for r in val.reasons)


def test_insufficient_evidence_safety_handling():
    """Verify empty/unsupported failure produces INSUFFICIENT_EVIDENCE without crash."""
    synthesizer = RegressionSynthesizer()
    tc = TestCase(name="empty_tc", input=None)
    empty_failure = FailureReport(
        trace_id="tr_empty",
        category="unknown",
        type="unknown",
        message="",
        evidence=None,
    )

    cand = synthesizer.synthesize(empty_failure, tc, root_cause=None)

    assert cand.status == GenerationStatus.INSUFFICIENT_EVIDENCE
    assert cand.validation is not None
    assert cand.validation.valid is False


# ---------------------------------------------------------------------------
# 4. Provenance and RegressionGenerator Integration
# ---------------------------------------------------------------------------


def test_regression_generator_synthesize_provenance():
    """Verify RegressionGenerator.synthesize preserves full provenance chain."""
    gen = RegressionGenerator()
    tc = TestCase(
        name="support_test",
        input={"order_id": "ORD-321", "noise": "abc"},
    )
    failure = FailureReport(
        trace_id="tr_prov_01",
        test_id=tc.id,
        category="tool",
        type="wrong_tool",
        message="Forbidden tool called",
        evidence={"expected_tool": "get_order", "called_tools": ["delete_order"]},
    )
    rc = RootCause(
        category=RootCauseCategory.TOOL,
        type=RootCauseType.WRONG_TOOL,
        description="Tool delete_order called instead of get_order",
        evidence=[
            Evidence(
                source="execution_trace",
                trace_id="tr_prov_01",
                field="tool_name",
                expected="get_order",
                actual="delete_order",
            )
        ],
    )

    cand = gen.synthesize(failure, tc, root_cause=rc)
    reg_test = cand.to_regression_test()

    assert reg_test.source_failure_id == failure.failure_id
    assert reg_test.metadata["root_cause_id"] == rc.id
    assert reg_test.metadata["source_trace_id"] == "tr_prov_01"
    assert reg_test.metadata["generation_method"] == "deterministic_trace_synthesis"
    assert reg_test.test_case.metadata["source_failure_id"] == failure.failure_id
    assert reg_test.test_case.metadata["root_cause_id"] == rc.id


# ---------------------------------------------------------------------------
# 5. Complete End-to-End Workflow Test (Lifecycle)
# ---------------------------------------------------------------------------


def test_end_to_end_intelligent_regression_lifecycle():
    """Complete Phase 18 lifecycle:
    Faulty Agent -> Trace -> FailureReport -> RootCause -> Synthesizer ->
    Validated Regression -> RegressionRunner (FAIL) -> Fixed Agent (PASS) ->
    Bug Reintroduced (REGRESSION).
    """
    # 1. Setup Faulty Agent
    agent = LocalSupportAgent(mode="faulty")
    adapter = CallableAdapter(agent=agent)

    test_case = TestCase(
        id="refund_order_tc",
        name="refund_order_lifecycle",
        input="refund order 123",
        expectations=["ToolOrder:get_order,cancel_order,refund_order"],
    )

    evaluators = [
        ToolOrder(
            expected_order=["get_order", "cancel_order", "refund_order"],
            exact_match=True,
        )
    ]

    runner = ReliabilityRunner(agent=agent, adapter=adapter, evaluators=evaluators)
    run_res = runner.run(test_case)

    assert run_res.passed is False
    assert len(run_res.failures) > 0

    # 2. Root Cause Analysis
    analyzer = RootCauseAnalyzer()
    diag = analyzer.diagnose(
        trace=run_res.trace,
        failures=run_res.failures,
        test_case=test_case,
    )
    assert diag.status == "FAIL"
    assert diag.primary_cause is not None
    assert diag.primary_cause.category == RootCauseCategory.TOOL
    assert diag.primary_cause.type == RootCauseType.WRONG_ORDER

    # 3. Intelligent Regression Synthesis with Minimization & Validation
    gen = RegressionGenerator()
    candidate = gen.synthesize(
        failure=run_res.failures[0],
        test_case=test_case,
        trace=run_res.trace,
        root_cause=diag.primary_cause,
        root_cause_report=diag,
    )

    assert candidate.status == GenerationStatus.SUCCESS
    assert candidate.validation is not None
    assert candidate.validation.valid is True
    assert candidate.validation.reproducible is True
    assert candidate.validation.specific is True
    assert candidate.validation.duplicate is False
    assert candidate.root_cause_id == diag.primary_cause.id

    reg_test = candidate.to_regression_test()

    # 4. Verify RegressionRunner fails on the faulty agent
    baseline_mgr = BaselineManager()
    reg_runner = RegressionRunner(
        agent=agent,
        adapter=adapter,
        evaluators=evaluators,
        baseline_manager=baseline_mgr,
    )
    res_faulty = reg_runner.run_test(reg_test)
    assert res_faulty.passed is False

    # 5. Fix the Agent -> verify RegressionRunner passes
    fixed_agent = LocalSupportAgent(mode="nominal")
    fixed_adapter = CallableAdapter(agent=fixed_agent)
    reg_runner_fixed = RegressionRunner(
        agent=fixed_agent,
        adapter=fixed_adapter,
        evaluators=evaluators,
        baseline_manager=baseline_mgr,
    )
    res_fixed = reg_runner_fixed.run_test(reg_test)
    assert res_fixed.passed is True

    # 6. Capture Baseline with Fixed Agent
    baseline_mgr.create_baseline(
        name="p18_verified_baseline",
        results=[res_fixed],
    )

    # 7. Reintroduce Faulty Agent -> verify BaselineManager flags REGRESSION
    reg_runner_reintro = RegressionRunner(
        agent=agent,
        adapter=adapter,
        evaluators=evaluators,
        baseline_manager=baseline_mgr,
    )
    suite_res = reg_runner_reintro.run_suite(
        regression_tests=[reg_test],
        compare_baseline="p18_verified_baseline",
    )

    assert suite_res.all_passed is False
    assert suite_res.comparison_summary is not None
    assert suite_res.comparison_summary.has_regressions is True
    reg_comparison = suite_res.comparison_summary.regressions[0]
    assert reg_comparison.status == ComparisonStatus.REGRESSION
    assert reg_comparison.test_name == reg_test.test_case.name
