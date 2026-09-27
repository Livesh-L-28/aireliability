"""Unit tests for Phase 7 Regression test generation, runner, and baseline tracking."""

from aireliability.core.models import (
    EvaluationResult,
    ExecutionStatus,
    ExecutionTrace,
    FailureReport,
    FailureSeverity,
    RegressionTest,
    RunResult,
    TestCase,
)
from aireliability.evaluation import OutputEquals
from aireliability.regression import (
    BaselineManager,
    ComparisonStatus,
    RegressionGenerator,
    RegressionRunner,
)


def _make_run_result(test_case: TestCase, passed: bool, output: str = "") -> RunResult:
    trace = ExecutionTrace(
        test_id=test_case.id,
        output=output,
        status=ExecutionStatus.COMPLETED if passed else ExecutionStatus.FAILED,
    )
    eval_res = EvaluationResult(
        evaluator="test_eval",
        passed=passed,
        score=1.0 if passed else 0.0,
    )
    failures = (
        []
        if passed
        else [
            FailureReport(
                trace_id=trace.trace_id,
                test_id=test_case.id,
                category="task",
                type="task_incorrect",
                severity=FailureSeverity.HIGH,
                message="Test failed",
            )
        ]
    )
    return RunResult(
        test=test_case,
        trace=trace,
        evaluations=[eval_res],
        failures=failures,
        passed=passed,
    )


# ==============================================================================
# 1. RegressionGenerator Tests
# ==============================================================================


def test_regression_generator_preserves_provenance() -> None:
    """Verify RegressionGenerator preserves source_failure_id and trace linkage."""
    tc = TestCase(
        name="refund_request",
        input="refund $50 for damaged goods",
        expected_output="Refund processed: $50",
        tags=["billing"],
        metadata={"customer_id": "cust_123"},
    )
    failure = FailureReport(
        failure_id="fail_abc123",
        trace_id="trace_xyz789",
        test_id=tc.id,
        category="tool",
        type="wrong_tool",
        severity=FailureSeverity.HIGH,
        message="Called cancel_order instead of refund_order",
        evidence={"called": "cancel_order"},
        confidence=1.0,
    )

    generator = RegressionGenerator()
    reg_test = generator.generate(failure, tc)

    assert isinstance(reg_test, RegressionTest)
    # Critical provenance linking
    assert reg_test.source_failure_id == "fail_abc123"
    assert reg_test.name == "reg_tool_wrong_tool_refund_request"
    assert reg_test.created_at is not None

    # Verify preserved test case details
    gen_tc = reg_test.test_case
    assert gen_tc.input == tc.input
    assert gen_tc.expected_output == tc.expected_output
    assert "regression" in gen_tc.tags
    assert "billing" in gen_tc.tags
    assert "failure:tool" in gen_tc.tags
    assert "type:wrong_tool" in gen_tc.tags

    # Metadata provenance
    assert gen_tc.metadata["source_failure_id"] == "fail_abc123"
    assert gen_tc.metadata["source_trace_id"] == "trace_xyz789"
    assert gen_tc.metadata["failure_category"] == "tool"
    assert gen_tc.metadata["failure_type"] == "wrong_tool"
    assert gen_tc.metadata["customer_id"] == "cust_123"


def test_regression_generator_generate_all() -> None:
    """Verify generate_all handles multiple failures on the same test case."""
    tc = TestCase(name="multi_fail_test", input="data")
    fail1 = FailureReport(
        trace_id="tr1",
        category="output",
        type="schema_error",
        message="Bad schema",
    )
    fail2 = FailureReport(
        trace_id="tr1",
        category="performance",
        type="latency",
        message="Too slow",
    )

    generator = RegressionGenerator()
    reg_tests = generator.generate_all([fail1, fail2], tc)

    assert len(reg_tests) == 2
    assert reg_tests[0].source_failure_id == fail1.failure_id
    assert reg_tests[1].source_failure_id == fail2.failure_id


# ==============================================================================
# 2. BaselineManager Tests
# ==============================================================================


def test_baseline_creation_and_retrieval() -> None:
    """Verify in-memory baseline creation and retrieval."""
    bm = BaselineManager()
    tc1 = TestCase(name="test_1", input="in1")
    tc2 = TestCase(name="test_2", input="in2")

    res1 = _make_run_result(tc1, passed=True)
    res2 = _make_run_result(tc2, passed=False)

    bm.create_baseline([res1, res2], name="v1.0")

    baseline = bm.get_baseline("v1.0")
    assert len(baseline) == 2
    assert baseline[tc1.id].passed is True
    assert baseline[tc2.id].passed is False
    assert "v1.0" in bm.list_baselines()


def test_baseline_detects_regression_previously_passing_now_failing() -> None:
    """REGRESSION: Previously passing + Currently failing."""
    bm = BaselineManager()
    tc = TestCase(name="auth_check", input="token")

    # Baseline: test passed
    base_res = _make_run_result(tc, passed=True)
    bm.create_baseline([base_res])

    # Current run: test fails
    current_res = _make_run_result(tc, passed=False)
    cmp = bm.compare_single(current_res)

    assert cmp.status == ComparisonStatus.REGRESSION
    assert cmp.current_passed is False
    assert cmp.baseline_passed is True
    assert "REGRESSION" in cmp.message


def test_baseline_detects_fixed_previously_failing_now_passing() -> None:
    """FIXED: Previously failing + Currently passing."""
    bm = BaselineManager()
    tc = TestCase(name="bug_fix_check", input="query")

    # Baseline: test failed
    base_res = _make_run_result(tc, passed=False)
    bm.create_baseline([base_res])

    # Current run: bug is fixed, test passes
    current_res = _make_run_result(tc, passed=True)
    cmp = bm.compare_single(current_res)

    assert cmp.status == ComparisonStatus.FIXED
    assert cmp.current_passed is True
    assert cmp.baseline_passed is False
    assert "FIXED" in cmp.message


def test_baseline_detects_known_failure_previously_failing_now_failing() -> None:
    """KNOWN FAILURE: Previously failing + Currently failing."""
    bm = BaselineManager()
    tc = TestCase(name="unresolved_issue", input="query")

    # Baseline: test failed
    base_res = _make_run_result(tc, passed=False)
    bm.create_baseline([base_res])

    # Current run: still fails
    current_res = _make_run_result(tc, passed=False)
    cmp = bm.compare_single(current_res)

    assert cmp.status == ComparisonStatus.KNOWN_FAILURE
    assert cmp.current_passed is False
    assert cmp.baseline_passed is False
    assert "KNOWN FAILURE" in cmp.message


def test_baseline_detects_passing_unchanged() -> None:
    """PASSING: Previously passing + Currently passing."""
    bm = BaselineManager()
    tc = TestCase(name="stable_test", input="data")

    base_res = _make_run_result(tc, passed=True)
    bm.create_baseline([base_res])

    current_res = _make_run_result(tc, passed=True)
    cmp = bm.compare_single(current_res)

    assert cmp.status == ComparisonStatus.PASSING
    assert cmp.current_passed is True
    assert cmp.baseline_passed is True


def test_baseline_detects_new_test() -> None:
    """NEW: Test not in baseline."""
    bm = BaselineManager()
    bm.create_baseline([])  # empty baseline

    new_tc = TestCase(name="brand_new_test", input="data")
    current_res = _make_run_result(new_tc, passed=True)
    cmp = bm.compare_single(current_res)

    assert cmp.status == ComparisonStatus.NEW
    assert cmp.baseline_passed is None


def test_baseline_suite_comparison_summary() -> None:
    """Verify aggregated comparison of full suite against baseline."""
    bm = BaselineManager()

    tc_reg = TestCase(name="reg_tc", input="1")
    tc_fix = TestCase(name="fix_tc", input="2")
    tc_known = TestCase(name="known_tc", input="3")
    tc_pass = TestCase(name="pass_tc", input="4")
    tc_new = TestCase(name="new_tc", input="5")

    # Baseline
    bm.create_baseline(
        [
            _make_run_result(tc_reg, passed=True),
            _make_run_result(tc_fix, passed=False),
            _make_run_result(tc_known, passed=False),
            _make_run_result(tc_pass, passed=True),
        ]
    )

    # Current run
    current_results = [
        _make_run_result(tc_reg, passed=False),  # REGRESSION
        _make_run_result(tc_fix, passed=True),  # FIXED
        _make_run_result(tc_known, passed=False),  # KNOWN_FAILURE
        _make_run_result(tc_pass, passed=True),  # PASSING
        _make_run_result(tc_new, passed=True),  # NEW
    ]

    summary = bm.compare(current_results)
    assert summary.total_tests == 5
    assert summary.has_regressions is True
    assert len(summary.regressions) == 1
    assert summary.regressions[0].test_name == "reg_tc"
    assert len(summary.fixed) == 1
    assert summary.fixed[0].test_name == "fix_tc"
    assert len(summary.known_failures) == 1
    assert summary.known_failures[0].test_name == "known_tc"
    assert len(summary.passing) == 1
    assert summary.passing[0].test_name == "pass_tc"
    assert len(summary.new_tests) == 1
    assert summary.new_tests[0].test_name == "new_tc"


# ==============================================================================
# 3. RegressionRunner Tests
# ==============================================================================


def test_regression_runner_executes_suite_and_checks_baseline() -> None:
    """Verify RegressionRunner executes a test suite with baseline comparison."""
    # Build baseline
    tc_fixed_target = TestCase(name="billing_calc", input=10, expected_output=20)
    fail = FailureReport(
        trace_id="tr_old",
        category="task",
        type="task_incorrect",
        message="Off by one",
    )
    generator = RegressionGenerator()
    reg_test = generator.generate(fail, tc_fixed_target)

    bm = BaselineManager()
    # Baseline recorded earlier failure on this test
    bm.create_baseline([_make_run_result(tc_fixed_target, passed=False)])

    # Now agent is fixed: returns 20
    def fixed_agent(x: int) -> int:
        return x * 2

    runner = RegressionRunner(
        agent=fixed_agent,
        evaluators=[OutputEquals(20)],
        baseline_manager=bm,
    )

    suite_result = runner.run_suite([reg_test], compare_baseline="default")

    assert suite_result.total_runs == 1
    assert suite_result.passed_count == 1
    assert suite_result.failed_count == 0
    assert suite_result.all_passed is True

    # Check baseline comparison was attached
    cmp_summary = suite_result.comparison_summary
    assert cmp_summary is not None
    assert len(cmp_summary.fixed) == 1
    assert cmp_summary.fixed[0].status == ComparisonStatus.FIXED
    assert cmp_summary.has_regressions is False
