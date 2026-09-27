"""Unit tests for Phase 9 CLI (`airel`)."""

import json
import tempfile
from pathlib import Path

from aireliability.cli import main
from aireliability.core.models import (
    EvaluationResult,
    ExecutionTrace,
    FailureReport,
    FailureSeverity,
    RegressionTest,
    RunResult,
    TestCase,
)
from aireliability.storage import SQLiteStorage


def _setup_test_project(tmpdir: Path) -> None:
    """Helper to initialize a project structure in a temporary directory."""
    agent_code = """
def app(user_input: str) -> str:
    if user_input == "bad":
        return "wrong_output"
    return f"Hello, {user_input}!"
"""
    (tmpdir / "agent.py").write_text(agent_code.strip(), encoding="utf-8")

    # Run airel init
    exit_code = main(["init", "--dir", str(tmpdir)])
    assert exit_code == 0


def test_cli_init_creates_files_and_directories() -> None:
    """Test `airel init` command creates config and folders."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        code = main(["init", "--dir", str(tmpdir)])
        assert code == 0

        assert (tmpdir / "aireliability.json").is_file()
        assert (tmpdir / "tests/reliability").is_dir()
        assert (tmpdir / ".aireliability/aireliability.db").is_file()
        assert (tmpdir / "agent.py").is_file()


def test_cli_test_executes_passing_tests(capsys: object) -> None:
    """Test `airel test` runs successfully on passing tests and exits with 0."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        _setup_test_project(tmpdir)

        # The default sample test expects "Hello" in output for input "Alice"
        code = main(["test", "--dir", str(tmpdir)])
        assert code == 0


def test_cli_test_filters_by_name() -> None:
    """Test `airel test <name>` filters and runs single test."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        _setup_test_project(tmpdir)

        # Run with matching name
        code = main(["test", "sample_greeting", "--dir", str(tmpdir)])
        assert code == 0

        # Run with nonexistent name
        code_missing = main(["test", "nonexistent_test", "--dir", str(tmpdir)])
        assert code_missing == 2  # Configuration / arg error


def test_cli_test_detects_failure_exit_code_1() -> None:
    """Test `airel test` exits with 1 when a test fails."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        _setup_test_project(tmpdir)

        # Add a failing test case to tests/reliability
        failing_tc = {
            "id": "tc_failing",
            "name": "failing_greeting",
            "input": "bad",
            "expected_output": "Hello, bad!",
            "expectations": ["OutputEquals: Hello, bad!"],
        }
        (tmpdir / "tests/reliability/fail.json").write_text(
            json.dumps(failing_tc), encoding="utf-8"
        )

        code = main(["test", "failing_greeting", "--dir", str(tmpdir)])
        assert code == 1


def test_cli_failures_command() -> None:
    """Test `airel failures` displays failure reports."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        _setup_test_project(tmpdir)

        db_path = tmpdir / ".aireliability/aireliability.db"
        storage = SQLiteStorage(db_path)
        trace = ExecutionTrace(trace_id="tr_cli_fail")
        storage.save_trace(trace)
        fail = FailureReport(
            failure_id="fail_cli_1",
            trace_id="tr_cli_fail",
            category="tool",
            type="wrong_tool",
            severity=FailureSeverity.HIGH,
            message="Tool selection error",
        )
        storage.save_failure(fail)
        storage.close()

        code = main(["failures", "--dir", str(tmpdir)])
        assert code == 0


def test_cli_regressions_command() -> None:
    """Test `airel regressions` displays synthesized regression tests."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        _setup_test_project(tmpdir)

        db_path = tmpdir / ".aireliability/aireliability.db"
        storage = SQLiteStorage(db_path)
        tc = TestCase(name="cli_reg_tc", input="in", expected_output="out")
        reg_test = RegressionTest(
            id="reg_cli_1",
            name="reg_cli_test",
            source_failure_id="fail_cli_1",
            test_case=tc,
        )
        storage.save_regression_test(reg_test)
        storage.close()

        code = main(["regressions", "--dir", str(tmpdir)])
        assert code == 0


def test_cli_compare_command_detects_regression() -> None:
    """Test `airel compare` against baseline detects regressions and exits with 1."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        _setup_test_project(tmpdir)

        db_path = tmpdir / ".aireliability/aireliability.db"
        storage = SQLiteStorage(db_path)

        # Create baseline with a passing test
        tc = TestCase(
            id="tc_sample_greeting",
            name="sample_greeting",
            input="Alice",
            expected_output="Hello, Alice!",
            expectations=["OutputContains: Hello"],
        )
        run_res = RunResult(
            test=tc,
            trace=ExecutionTrace(test_id=tc.id),
            evaluations=[EvaluationResult(evaluator="check", passed=True)],
            failures=[],
            passed=True,
        )
        from aireliability.regression.baseline import BaselineEntry

        entry = BaselineEntry(
            test_id=tc.id,
            test_name=tc.name,
            passed=True,
            run_result=run_res,
        )
        storage.save_baseline("default", [entry])
        storage.close()

        # Update agent to return failing output
        bad_agent_code = """
def app(user_input: str) -> str:
    return "Goodbye!"
"""
        (tmpdir / "agent.py").write_text(bad_agent_code.strip(), encoding="utf-8")

        # Now running compare should detect regression (was passing, now failing)
        code = main(["compare", "--dir", str(tmpdir)])
        assert code == 1


def test_cli_uninitialized_project_exit_code_2() -> None:
    """Test running `airel test` on uninitialized directory returns exit code 2."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        code = main(["test", "--dir", str(tmpdir)])
        assert code == 2


def test_cli_test_ci_mode_and_regression_exit_code() -> None:
    """Test `airel test --ci` returns 0 when passing and non-zero (1) on regressions."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        _setup_test_project(tmpdir)

        # Baseline: Save initial passing state
        code_baseline = main(["test", "--save-baseline", "--dir", str(tmpdir)])
        assert code_baseline == 0

        # CI run with no regression should succeed (exit code 0)
        code_ci_pass = main(["test", "--ci", "--dir", str(tmpdir)])
        assert code_ci_pass == 0

        # Inject regression: change agent output to fail expectation
        broken_agent_code = """
def app(user_input: str) -> str:
    return "Goodbye, Alice!"
"""
        (tmpdir / "agent.py").write_text(broken_agent_code.strip(), encoding="utf-8")

        # CI run should now detect regression and return non-zero exit code (1)
        code_ci_fail = main(["test", "--ci", "--dir", str(tmpdir)])
        assert code_ci_fail == 1
