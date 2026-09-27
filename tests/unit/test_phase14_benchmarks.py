"""Unit and integration tests for Phase 14 Real-World Reliability Benchmark."""

from datetime import UTC, datetime, timedelta

from aireliability.core.models import (
    ExecutionStatus,
    ExecutionTrace,
    RunResult,
    TestCase,
)
from aireliability.evaluation import MaxLatency
from aireliability.execution.runner import ReliabilityRunner
from aireliability.failures.taxonomy import FailureCategory, FailureType
from aireliability.regression.baseline import (
    BaselineManager,
    ComparisonStatus,
)
from aireliability.regression.generator import RegressionGenerator
from benchmarks.scenarios.latency_regression import get_scenario_f
from benchmarks.scenarios.missing_tool import (
    agent_d_faulty,
    agent_d_nominal,
    get_scenario_d,
)
from benchmarks.scenarios.output_regression import (
    agent_e_faulty,
    agent_e_nominal,
    get_scenario_e,
)
from benchmarks.scenarios.tool_order import (
    agent_a_faulty,
    agent_a_nominal,
    get_scenario_a,
)
from benchmarks.scenarios.wrong_arguments import (
    agent_c_faulty,
    agent_c_nominal,
    get_scenario_c,
)
from benchmarks.scenarios.wrong_tool import (
    agent_b_faulty,
    agent_b_nominal,
    get_scenario_b,
)


class DeterministicLatencyAdapter:
    """Execution adapter that simulates a deterministic latency duration."""

    def __init__(self, latency_ms: float) -> None:
        self.latency_ms = latency_ms

    def execute(self, agent: object, test_case: TestCase) -> ExecutionTrace:
        start = datetime.now(UTC)
        end = start + timedelta(milliseconds=self.latency_ms)
        output = agent(test_case.input) if callable(agent) else "ok"
        return ExecutionTrace(
            test_id=test_case.id,
            input=test_case.input,
            output=output,
            status=ExecutionStatus.COMPLETED,
            started_at=start,
            completed_at=end,
            latency_ms=self.latency_ms,
        )


def test_scenario_a_tool_order_detection() -> None:
    """Scenario A: Verify WRONG_ORDER is detected on faulty tool ordering."""
    tc, evals, nominal_steps, faulty_steps = get_scenario_a()

    # 1. Nominal run passes
    runner_nominal = ReliabilityRunner(agent=agent_a_nominal, evaluators=evals)
    res_nominal = runner_nominal.run(tc, steps=nominal_steps)
    assert res_nominal.passed is True
    assert len(res_nominal.failures) == 0

    # 2. Faulty run fails with WRONG_ORDER
    runner_faulty = ReliabilityRunner(agent=agent_a_faulty, evaluators=evals)
    res_faulty = runner_faulty.run(tc, steps=faulty_steps)
    assert res_faulty.passed is False
    assert len(res_faulty.failures) == 1
    failure = res_faulty.failures[0]
    assert failure.category == FailureCategory.TOOL.value
    assert failure.type == FailureType.WRONG_ORDER.value


def test_scenario_b_wrong_tool_detection() -> None:
    """Scenario B: Verify WRONG_TOOL is detected on wrong tool call."""
    tc, evals, nominal_steps, faulty_steps = get_scenario_b()

    runner_nominal = ReliabilityRunner(agent=agent_b_nominal, evaluators=evals)
    res_nominal = runner_nominal.run(tc, steps=nominal_steps)
    assert res_nominal.passed is True

    runner_faulty = ReliabilityRunner(agent=agent_b_faulty, evaluators=evals)
    res_faulty = runner_faulty.run(tc, steps=faulty_steps)
    assert res_faulty.passed is False
    # delete_order is an uncalled expected get_order + forbidden delete_order
    types = [f.type for f in res_faulty.failures]
    assert FailureType.WRONG_TOOL.value in types


def test_scenario_c_wrong_arguments_detection() -> None:
    """Scenario C: Verify WRONG_ARGUMENT is detected on argument mismatch."""
    tc, evals, nominal_steps, faulty_steps = get_scenario_c()

    runner_nominal = ReliabilityRunner(agent=agent_c_nominal, evaluators=evals)
    res_nominal = runner_nominal.run(tc, steps=nominal_steps)
    assert res_nominal.passed is True

    runner_faulty = ReliabilityRunner(agent=agent_c_faulty, evaluators=evals)
    res_faulty = runner_faulty.run(tc, steps=faulty_steps)
    assert res_faulty.passed is False
    failure = res_faulty.failures[0]
    assert failure.category == FailureCategory.TOOL.value
    assert failure.type == FailureType.WRONG_ARGUMENT.value


def test_scenario_d_missing_tool_detection() -> None:
    """Scenario D: Verify missing refund_order operation is detected."""
    tc, evals, nominal_steps, faulty_steps = get_scenario_d()

    runner_nominal = ReliabilityRunner(agent=agent_d_nominal, evaluators=evals)
    res_nominal = runner_nominal.run(tc, steps=nominal_steps)
    assert res_nominal.passed is True

    runner_faulty = ReliabilityRunner(agent=agent_d_faulty, evaluators=evals)
    res_faulty = runner_faulty.run(tc, steps=faulty_steps)
    assert res_faulty.passed is False
    # Missing required tool refund_order
    assert any(
        f.category == FailureCategory.TOOL.value
        and f.type == FailureType.WRONG_TOOL.value
        for f in res_faulty.failures
    )


def test_scenario_e_output_regression_detection() -> None:
    """Scenario E: Verify output regression is detected."""
    tc, evals, nominal_steps, faulty_steps = get_scenario_e()

    runner_nominal = ReliabilityRunner(agent=agent_e_nominal, evaluators=evals)
    res_nominal = runner_nominal.run(tc, steps=nominal_steps)
    assert res_nominal.passed is True

    runner_faulty = ReliabilityRunner(agent=agent_e_faulty, evaluators=evals)
    res_faulty = runner_faulty.run(tc, steps=faulty_steps)
    assert res_faulty.passed is False
    assert any(
        f.category == FailureCategory.TASK.value
        and f.type == FailureType.TASK_INCORRECT.value
        for f in res_faulty.failures
    )


def test_scenario_f_latency_regression_detection() -> None:
    """Scenario F: Verify latency degradation (100ms vs 500ms) is detected."""
    tc, evals, _, _ = get_scenario_f()

    adapter_nominal = DeterministicLatencyAdapter(100.0)
    runner_nominal = ReliabilityRunner(
        agent=lambda _: "ok",
        adapter=adapter_nominal,
        evaluators=evals,
    )
    res_nominal = runner_nominal.run(tc)
    assert res_nominal.passed is True
    assert res_nominal.trace.latency_ms == 100.0

    adapter_faulty = DeterministicLatencyAdapter(500.0)
    runner_faulty = ReliabilityRunner(
        agent=lambda _: "ok",
        adapter=adapter_faulty,
        evaluators=evals,
    )
    res_faulty = runner_faulty.run(tc)
    assert res_faulty.passed is False
    assert res_faulty.trace.latency_ms == 500.0
    failure = res_faulty.failures[0]
    assert failure.category == FailureCategory.PERFORMANCE.value
    assert failure.type == FailureType.LATENCY.value


def test_end_to_end_regression_lifecycle_and_reintroduction() -> None:
    """Test full cycle: Faulty -> Test -> Fix -> Pass -> Bug returns -> REGRESSION."""
    tc, evals, nominal_steps, faulty_steps = get_scenario_a()

    # Step 1: Faulty agent runs and produces failure
    runner_faulty = ReliabilityRunner(agent=agent_a_faulty, evaluators=evals)
    res_faulty = runner_faulty.run(tc, steps=faulty_steps)
    assert res_faulty.passed is False
    assert len(res_faulty.failures) > 0
    failure = res_faulty.failures[0]

    # Step 2: Synthesize regression test from failure
    generator = RegressionGenerator()
    reg_test = generator.generate(failure, tc)
    assert reg_test.source_failure_id == failure.failure_id
    assert reg_test.test_case.metadata["source_failure_id"] == failure.failure_id
    assert reg_test.test_case.metadata["source_trace_id"] == res_faulty.trace.trace_id

    # Step 3: Fix agent logic and verify regression test passes
    runner_fixed = ReliabilityRunner(agent=agent_a_nominal, evaluators=evals)
    res_fixed = runner_fixed.run(reg_test.test_case, steps=nominal_steps)
    assert res_fixed.passed is True
    assert len(res_fixed.failures) == 0

    # Step 4: Establish baseline with fixed passing run
    baseline_mgr = BaselineManager()
    baseline_mgr.create_baseline([res_fixed], name="main_baseline")

    # Step 5: Intentionally reintroduce the bug
    res_reintroduced = runner_faulty.run(reg_test.test_case, steps=faulty_steps)
    assert res_reintroduced.passed is False

    # Step 6: Baseline comparison detects REGRESSION
    summary = baseline_mgr.compare([res_reintroduced], baseline_name="main_baseline")
    assert summary.has_regressions is True
    assert len(summary.regressions) == 1
    reg_result = summary.regressions[0]
    assert reg_result.status == ComparisonStatus.REGRESSION
    assert reg_result.current_passed is False
    assert reg_result.baseline_passed is True


def test_baseline_all_four_classification_states() -> None:
    """Verify all 4 baseline states: REGRESSION, KNOWN_FAILURE, FIXED, and PASSING."""
    mgr = BaselineManager()
    tc1 = TestCase(id="tc_1", name="test_one", input="1")
    tc2 = TestCase(id="tc_2", name="test_two", input="2")
    tc3 = TestCase(id="tc_3", name="test_three", input="3")
    tc4 = TestCase(id="tc_4", name="test_four", input="4")

    trace1 = ExecutionTrace(test_id=tc1.id)
    trace2 = ExecutionTrace(test_id=tc2.id)
    trace3 = ExecutionTrace(test_id=tc3.id)
    trace4 = ExecutionTrace(test_id=tc4.id)

    # Historical Baseline:
    # tc1: passed (True)
    # tc2: failed (False)
    # tc3: failed (False)
    # tc4: passed (True)
    run_b1 = RunResult(test=tc1, trace=trace1, evaluations=[], failures=[], passed=True)
    run_b2 = RunResult(
        test=tc2, trace=trace2, evaluations=[], failures=[], passed=False
    )
    run_b3 = RunResult(
        test=tc3, trace=trace3, evaluations=[], failures=[], passed=False
    )
    run_b4 = RunResult(test=tc4, trace=trace4, evaluations=[], failures=[], passed=True)

    mgr.create_baseline([run_b1, run_b2, run_b3, run_b4], name="v1")

    # Current Runs:
    # tc1: now failing -> REGRESSION (Previous: PASS, Current: FAIL)
    # tc2: still failing -> KNOWN_FAILURE (Previous: FAIL, Current: FAIL)
    # tc3: now passing -> FIXED (Previous: FAIL, Current: PASS)
    # tc4: still passing -> PASSING / UNCHANGED (Previous: PASS, Current: PASS)
    run_c1 = RunResult(
        test=tc1, trace=trace1, evaluations=[], failures=[], passed=False
    )
    run_c2 = RunResult(
        test=tc2, trace=trace2, evaluations=[], failures=[], passed=False
    )
    run_c3 = RunResult(test=tc3, trace=trace3, evaluations=[], failures=[], passed=True)
    run_c4 = RunResult(test=tc4, trace=trace4, evaluations=[], failures=[], passed=True)

    summary = mgr.compare([run_c1, run_c2, run_c3, run_c4], baseline_name="v1")

    assert len(summary.regressions) == 1
    assert summary.regressions[0].status == ComparisonStatus.REGRESSION
    assert summary.regressions[0].test_id == "tc_1"

    assert len(summary.known_failures) == 1
    assert summary.known_failures[0].status == ComparisonStatus.KNOWN_FAILURE
    assert summary.known_failures[0].test_id == "tc_2"

    assert len(summary.fixed) == 1
    assert summary.fixed[0].status == ComparisonStatus.FIXED
    assert summary.fixed[0].test_id == "tc_3"

    assert len(summary.passing) == 1
    assert summary.passing[0].status == ComparisonStatus.PASSING
    assert summary.passing[0].test_id == "tc_4"


def test_failure_traceability_chain() -> None:
    """Verify audit trail: RegressionTest -> failure_id -> FailureReport -> trace_id."""
    tc = TestCase(
        id="tc_traceability_root",
        name="test_traceability",
        input="sample_input",
    )
    runner = ReliabilityRunner(
        agent=lambda _: "too_slow",
        evaluators=[MaxLatency(10.0)],
        adapter=DeterministicLatencyAdapter(50.0),
    )
    res = runner.run(tc)
    assert res.passed is False
    assert len(res.failures) == 1

    failure_report = res.failures[0]
    generator = RegressionGenerator()
    reg_test = generator.generate(failure_report, tc)

    # 1. Regression test points to source failure ID
    assert reg_test.source_failure_id == failure_report.failure_id
    assert reg_test.test_case.metadata["source_failure_id"] == failure_report.failure_id

    # 2. Failure report points to execution trace ID
    assert failure_report.trace_id == res.trace.trace_id
    assert reg_test.test_case.metadata["source_trace_id"] == res.trace.trace_id

    # 3. Execution trace points to originating test ID
    assert res.trace.test_id == tc.id

    # 4. Reason regression test exists is preserved directly in metadata
    assert reg_test.test_case.metadata["failure_category"] == failure_report.category
    assert reg_test.test_case.metadata["failure_type"] == failure_report.type
    assert reg_test.test_case.metadata["failure_message"] == failure_report.message
