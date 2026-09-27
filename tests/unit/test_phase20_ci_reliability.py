"""Unit and integration tests for Phase 20 CI/CD and PR Reliability.

Covers:
1. Deterministic scenario testing using fixtures:
   - tool_order.json
   - wrong_tool.json
   - wrong_arguments.json
   - output_regression.json
2. BaselineManager transition states:
   - PASSING (prev pass -> curr pass)
   - FIXED (prev fail -> curr pass)
   - KNOWN_FAILURE (prev fail -> curr fail)
   - REGRESSION (prev pass -> curr fail)
   - NEW (not in baseline)
3. CI Exit Code & Baseline Policy:
   - Genuine PASS -> FAIL transition sets has_regressions=True and exits with 1
   - FAIL -> FAIL transition (KNOWN_FAILURE) does NOT set has_regressions=True
4. CLI Machine-readable JSON and Markdown Step Summary report generation:
   - --report-json output file structure and contents
   - --report-markdown output file structure and contents
5. End-to-End CI lifecycle simulation:
   - main baseline established (all passing)
   - introduce behavioral bug
   - run reliability evaluation in PR CI
   - failure detected -> root cause identified -> regression synthesized
   - baseline comparison identifies REGRESSION
   - CI job fails deterministically with exit code 1
"""

import json
from pathlib import Path

from aireliability import (
    BaselineManager,
    CallableAdapter,
    ComparisonStatus,
    ExecutionTrace,
    RegressionGenerator,
    ReliabilityRunner,
    RootCauseAnalyzer,
    TestCase,
    TraceStep,
)
from aireliability.cli import main
from aireliability.core.models import RunResult
from aireliability.evaluation import (
    OutputEquals,
    ToolArguments,
    ToolCalled,
    ToolOrder,
)


def _load_fixture(filename: str) -> dict:
    fixture_path = Path(__file__).parent.parent / "fixtures" / "reliability" / filename
    return json.loads(fixture_path.read_text())


# ==============================================================================
# 1. Deterministic Fixture Evaluation
# ==============================================================================


def test_fixture_tool_order_scenarios():
    """Verify tool_order.json fixture evaluates traces deterministically."""
    data = _load_fixture("tool_order.json")
    exp = ToolOrder(
        expected_order=data["expectations"][0]["expected_order"], exact_match=True
    )

    # Passing trace
    p_trace_data = data["traces"]["passing"]
    p_trace = ExecutionTrace(
        trace_id="p-trace-1",
        input=p_trace_data["input"],
        output=p_trace_data["output"],
        steps=[
            TraceStep(
                name=tc["tool"],
                step_type="tool",
                input=tc["args"],
                output=tc["result"],
            )
            for tc in p_trace_data["tool_calls"]
        ],
    )
    p_res = exp.evaluate(p_trace)
    assert p_res.passed is True

    # Failing trace
    f_trace_data = data["traces"]["failing"]
    f_trace = ExecutionTrace(
        trace_id="f-trace-1",
        input=f_trace_data["input"],
        output=f_trace_data["output"],
        steps=[
            TraceStep(
                name=tc["tool"],
                step_type="tool",
                input=tc["args"],
                output=tc["result"],
            )
            for tc in f_trace_data["tool_calls"]
        ],
    )
    f_res = exp.evaluate(f_trace)
    assert f_res.passed is False
    assert "Tool sequence did not match exactly" in f_res.message


def test_fixture_wrong_tool_scenarios():
    """Verify wrong_tool.json fixture evaluates correctly."""
    data = _load_fixture("wrong_tool.json")
    exp = ToolCalled(tool_name=data["expectations"][0]["expected_tool"])

    p_trace = ExecutionTrace(
        trace_id="p-trace-2",
        input=data["traces"]["passing"]["input"],
        output=data["traces"]["passing"]["output"],
        steps=[
            TraceStep(name="calculate_tax", step_type="tool", input={"item_id": 456})
        ],
    )
    assert exp.evaluate(p_trace).passed is True

    f_trace = ExecutionTrace(
        trace_id="f-trace-2",
        input=data["traces"]["failing"]["input"],
        output=data["traces"]["failing"]["output"],
        steps=[TraceStep(name="charge_card", step_type="tool", input={"item_id": 456})],
    )
    assert exp.evaluate(f_trace).passed is False


def test_fixture_wrong_arguments_scenarios():
    """Verify wrong_arguments.json fixture evaluates correctly."""
    data = _load_fixture("wrong_arguments.json")
    exp_cfg = data["expectations"][0]
    exp = ToolArguments(
        tool_name=exp_cfg["expected_tool"], expected_args=exp_cfg["expected_args"]
    )

    p_trace = ExecutionTrace(
        trace_id="p-trace-3",
        input=data["traces"]["passing"]["input"],
        output=data["traces"]["passing"]["output"],
        steps=[
            TraceStep(
                name="lookup_user",
                step_type="tool",
                input={"user_id": 789, "include_deleted": False},
            )
        ],
    )
    assert exp.evaluate(p_trace).passed is True

    f_trace = ExecutionTrace(
        trace_id="f-trace-3",
        input=data["traces"]["failing"]["input"],
        output=data["traces"]["failing"]["output"],
        steps=[
            TraceStep(
                name="lookup_user",
                step_type="tool",
                input={"user_id": 789, "include_deleted": True},
            )
        ],
    )
    assert exp.evaluate(f_trace).passed is False


def test_fixture_output_regression_scenarios():
    """Verify output_regression.json fixture evaluates correctly."""
    data = _load_fixture("output_regression.json")
    exp = OutputEquals(expected=data["expectations"][0]["expected_output"])

    p_trace = ExecutionTrace(
        trace_id="p-trace-4",
        input=data["traces"]["passing"]["input"],
        output=data["traces"]["passing"]["output"],
    )
    assert exp.evaluate(p_trace).passed is True

    f_trace = ExecutionTrace(
        trace_id="f-trace-4",
        input=data["traces"]["failing"]["input"],
        output=data["traces"]["failing"]["output"],
    )
    assert exp.evaluate(f_trace).passed is False


# ==============================================================================
# 2. Baseline Transitions & Regression Semantics
# ==============================================================================


def test_baseline_manager_transitions():
    """Verify BaselineManager categorizes PASSING, FIXED, KNOWN_FAILURE, REGRESSION."""
    bm = BaselineManager()

    tc_pass = TestCase(id="tc-1", name="PassingTest", input="hi")
    tc_fail = TestCase(id="tc-2", name="FailingTest", input="bad")
    tc_reg = TestCase(id="tc-3", name="RegressingTest", input="was good")
    tc_fix = TestCase(id="tc-4", name="FixingTest", input="was bad")
    tc_new = TestCase(id="tc-5", name="NewTest", input="brand new")

    # Baseline:
    # tc-1: passed
    # tc-2: failed
    # tc-3: passed
    # tc-4: failed
    baseline_runs = [
        RunResult(
            test=tc_pass, trace=ExecutionTrace(trace_id="b1", input="hi"), passed=True
        ),
        RunResult(
            test=tc_fail, trace=ExecutionTrace(trace_id="b2", input="bad"), passed=False
        ),
        RunResult(
            test=tc_reg,
            trace=ExecutionTrace(trace_id="b3", input="was good"),
            passed=True,
        ),
        RunResult(
            test=tc_fix,
            trace=ExecutionTrace(trace_id="b4", input="was bad"),
            passed=False,
        ),
    ]
    bm.create_baseline(baseline_runs, name="ci_base")

    # Current PR runs:
    # tc-1: passed -> PASSING
    # tc-2: failed -> KNOWN_FAILURE
    # tc-3: failed -> REGRESSION
    # tc-4: passed -> FIXED
    # tc-5: passed -> NEW
    current_runs = [
        RunResult(
            test=tc_pass, trace=ExecutionTrace(trace_id="c1", input="hi"), passed=True
        ),
        RunResult(
            test=tc_fail, trace=ExecutionTrace(trace_id="c2", input="bad"), passed=False
        ),
        RunResult(
            test=tc_reg,
            trace=ExecutionTrace(trace_id="c3", input="was good"),
            passed=False,
        ),
        RunResult(
            test=tc_fix,
            trace=ExecutionTrace(trace_id="c4", input="was bad"),
            passed=True,
        ),
        RunResult(
            test=tc_new,
            trace=ExecutionTrace(trace_id="c5", input="brand new"),
            passed=True,
        ),
    ]

    summary = bm.compare(current_runs, baseline_name="ci_base")

    assert summary.total_tests == 5
    assert len(summary.passing) == 1
    assert summary.passing[0].test_id == "tc-1"
    assert summary.passing[0].status == ComparisonStatus.PASSING

    assert len(summary.known_failures) == 1
    assert summary.known_failures[0].test_id == "tc-2"
    assert summary.known_failures[0].status == ComparisonStatus.KNOWN_FAILURE

    assert len(summary.regressions) == 1
    assert summary.regressions[0].test_id == "tc-3"
    assert summary.regressions[0].status == ComparisonStatus.REGRESSION

    assert len(summary.fixed) == 1
    assert summary.fixed[0].test_id == "tc-4"
    assert summary.fixed[0].status == ComparisonStatus.FIXED

    assert len(summary.new_tests) == 1
    assert summary.new_tests[0].test_id == "tc-5"
    assert summary.new_tests[0].status == ComparisonStatus.NEW

    # Critical requirement: only regressions flag has_regressions=True
    assert summary.has_regressions is True


def test_known_failures_do_not_fail_baseline_comparison():
    """Verify that known failures (FAIL -> FAIL) do NOT flag has_regressions."""
    bm = BaselineManager()
    tc = TestCase(id="tc-known", name="KnownFailingTest", input="x")

    baseline_runs = [
        RunResult(test=tc, trace=ExecutionTrace(trace_id="b1", input="x"), passed=False)
    ]
    bm.create_baseline(baseline_runs, name="base")

    current_runs = [
        RunResult(test=tc, trace=ExecutionTrace(trace_id="c1", input="x"), passed=False)
    ]
    summary = bm.compare(current_runs, baseline_name="base")

    assert len(summary.known_failures) == 1
    assert len(summary.regressions) == 0
    assert summary.has_regressions is False


# ==============================================================================
# 3. CLI Machine-Readable & Markdown Report Generation
# ==============================================================================


def test_cli_report_json_and_markdown(tmp_path: Path):
    """Verify CLI test command exports structured JSON and markdown step summaries."""
    # Create simple agent
    agent_code = """
def run_agent(input_data):
    return {"output": "Hello, world!"}
"""
    agent_file = tmp_path / "my_agent.py"
    agent_file.write_text(agent_code)

    # Initialize airel project
    init_code = main(["init", "--dir", str(tmp_path)])
    assert init_code == 0

    # Remove starter sample_test.json so only our test runs
    sample_file = tmp_path / "tests" / "reliability" / "sample_test.json"
    if sample_file.exists():
        sample_file.unlink()

    # Write a test case
    tc_data = {
        "id": "tc-greet-1",
        "name": "Greeting Test",
        "input": "Greet me",
        "expectations": ["OutputContains: Hello"],
    }
    tc_path = tmp_path / "tests" / "reliability" / "greet.json"
    tc_path.write_text(json.dumps(tc_data))

    json_report = tmp_path / "reliability-report.json"
    md_report = tmp_path / "reliability-report.md"

    exit_code = main(
        [
            "test",
            "--dir",
            str(tmp_path),
            "--agent",
            "my_agent:run_agent",
            "--save-baseline",
            "--report-json",
            str(json_report),
            "--report-markdown",
            str(md_report),
        ]
    )
    assert exit_code == 0
    assert json_report.exists()
    assert md_report.exists()

    # Verify JSON structure
    report_content = json.loads(json_report.read_text())
    assert report_content["status"] == "passed"
    assert report_content["tests"] == 1
    assert report_content["passed"] == 1
    assert report_content["failed"] == 0
    assert report_content["reliability_regressions"] == 0

    # Verify Markdown structure
    md_content = md_report.read_text()
    assert "# aireliability Reliability Report" in md_content
    assert "Core Tests: PASS" in md_content
    assert "Scenarios: 1" in md_content


def test_cli_compare_report_json_and_markdown(tmp_path: Path):
    """Verify CLI compare command exports structured JSON and markdown reports."""
    # Agent 1: passing
    agent1_file = tmp_path / "agent1.py"
    agent1_file.write_text("def run(inp): return {'output': 'Hello'}")

    main(["init", "--dir", str(tmp_path)])
    sample_file = tmp_path / "tests" / "reliability" / "sample_test.json"
    if sample_file.exists():
        sample_file.unlink()

    tc_data = {
        "id": "tc-1",
        "name": "Test One",
        "input": "hi",
        "expectations": ["OutputContains: Hello"],
    }
    (tmp_path / "tests" / "reliability" / "test.json").write_text(json.dumps(tc_data))

    # Save baseline with agent 1
    main(
        [
            "test",
            "--dir",
            str(tmp_path),
            "--agent",
            "agent1:run",
            "--save-baseline",
        ]
    )

    # Agent 2: failing (regression)
    agent2_file = tmp_path / "agent2.py"
    agent2_file.write_text("def run(inp): return {'output': 'Bye'}")

    json_cmp = tmp_path / "cmp-report.json"
    md_cmp = tmp_path / "cmp-report.md"

    cmp_exit = main(
        [
            "compare",
            "default",
            "--dir",
            str(tmp_path),
            "--agent",
            "agent2:run",
            "--report-json",
            str(json_cmp),
            "--report-markdown",
            str(md_cmp),
        ]
    )
    assert cmp_exit == 1
    assert json_cmp.exists()
    assert md_cmp.exists()

    cmp_data = json.loads(json_cmp.read_text())
    assert cmp_data["status"] == "failed"
    assert cmp_data["regressions"] == 1

    cmp_md = md_cmp.read_text()
    assert "FAIL (Regressions detected)" in cmp_md
    assert "Test One" in cmp_md


# ==============================================================================
# 4. End-to-End PR Reliability Lifecycle Scenario
# ==============================================================================


def test_end_to_end_ci_reliability_lifecycle():
    """Verify complete PR CI reliability lifecycle:
    1. Main baseline: nominal agent passes test
    2. PR introduces behavioral bug
    3. aireliability runner detects failure
    4. Root cause analyzer identifies root cause
    5. Regression generator synthesizes minimal regression test
    6. Baseline comparison detects REGRESSION and fails CI
    7. Bug is resolved and fixed behavior passes
    """

    # 1. Main baseline
    class OrderAgent:
        def __init__(self, mode="correct"):
            self.mode = mode

        def __call__(self, inp: dict) -> dict:
            if self.mode == "correct":
                return {
                    "output": "Order 123 refunded.",
                    "tool_calls": [
                        {"tool": "get_order", "args": {"id": 123}},
                        {"tool": "cancel_order", "args": {"id": 123}},
                        {"tool": "refund_order", "args": {"id": 123}},
                    ],
                }
            elif self.mode == "buggy_order":
                # Bug: refund before cancel
                return {
                    "output": "Order 123 refunded prematurely.",
                    "tool_calls": [
                        {"tool": "get_order", "args": {"id": 123}},
                        {"tool": "refund_order", "args": {"id": 123}},
                        {"tool": "cancel_order", "args": {"id": 123}},
                    ],
                }

    tc = TestCase(
        id="refund-flow-001",
        name="Order Refund Flow",
        input={"action": "refund", "order_id": 123},
        expectations=["ToolOrder:get_order,cancel_order,refund_order"],
    )

    evaluator = ToolOrder(
        expected_order=["get_order", "cancel_order", "refund_order"], exact_match=True
    )

    nominal_adapter = CallableAdapter(agent=OrderAgent(mode="correct"))
    runner_main = ReliabilityRunner(
        agent=OrderAgent(mode="correct"),
        adapter=nominal_adapter,
        evaluators=[evaluator],
    )
    baseline_run = runner_main.run(tc)
    assert baseline_run.passed is True

    # Save to baseline
    bm = BaselineManager()
    bm.create_baseline([baseline_run], name="main")

    # 2. PR introduces behavioral bug
    buggy_adapter = CallableAdapter(agent=OrderAgent(mode="buggy_order"))
    runner_pr = ReliabilityRunner(
        agent=OrderAgent(mode="buggy_order"),
        adapter=buggy_adapter,
        evaluators=[evaluator],
    )
    pr_run = runner_pr.run(tc)

    # 3. aireliability detects failure
    assert pr_run.passed is False
    assert len(pr_run.failures) == 1
    failure = pr_run.failures[0]
    assert failure.category == "tool"

    # 4. Root cause analyzer diagnoses empirical root cause
    analyzer = RootCauseAnalyzer()
    diag = analyzer.diagnose(pr_run.trace, pr_run.failures, tc)
    assert diag.status == "FAIL"
    assert diag.primary_cause is not None
    assert diag.primary_cause.category.value == "tool"
    assert diag.primary_cause.type.value == "wrong_order"

    # 5. Regression generator synthesizes minimal regression test
    generator = RegressionGenerator()
    reg_test = generator.generate(failure, tc)
    assert reg_test is not None
    assert reg_test.source_failure_id == failure.failure_id

    # 6. Baseline comparison detects REGRESSION and triggers CI failure
    cmp_summary = bm.compare([pr_run], baseline_name="main")
    assert cmp_summary.has_regressions is True
    assert len(cmp_summary.regressions) == 1
    assert cmp_summary.regressions[0].status == ComparisonStatus.REGRESSION

    # 7. Bug is fixed in follow-up commit
    fixed_adapter = CallableAdapter(agent=OrderAgent(mode="correct"))
    runner_fixed = ReliabilityRunner(
        agent=OrderAgent(mode="correct"), adapter=fixed_adapter, evaluators=[evaluator]
    )
    fixed_run = runner_fixed.run(tc)
    assert fixed_run.passed is True

    # Compare fixed run against baseline
    cmp_fixed = bm.compare([fixed_run], baseline_name="main")
    assert cmp_fixed.has_regressions is False
    assert len(cmp_fixed.passing) == 1
    assert len(cmp_fixed.passing) == 1
