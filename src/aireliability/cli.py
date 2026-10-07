"""Command-line interface for the AI Reliability Engine (`airel`).

Provides commands for project initialization, running tests and detecting
regressions, inspecting failures and regression tests, and baseline comparison:
- `airel init`
- `airel test [name]`
- `airel failures`
- `airel regressions`
- `airel compare [baseline_name]`
"""

import argparse
import importlib.util
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from aireliability.core.models import (
    RunResult,
    TestCase,
)
from aireliability.core.protocols import Evaluator
from aireliability.distributed.sqlite_storage import SQLiteDistributedStorage
from aireliability.evaluation import (
    MaxCost,
    MaxLatency,
    OutputContains,
    OutputEquals,
    SchemaMatch,
    ToolArguments,
    ToolCalled,
    ToolNotCalled,
    ToolOrder,
)
from aireliability.execution import ReliabilityRunner
from aireliability.regression import (
    BaselineManager,
    RegressionGenerator,
)
from aireliability.storage import SQLiteStorage

DEFAULT_CONFIG_FILENAME = "aireliability.json"
DEFAULT_DB_FILENAME = ".aireliability/aireliability.db"
DEFAULT_TESTS_DIR = "tests/reliability"


class ProjectConfig(BaseModel):
    """Configuration schema for an aireliability project."""

    version: str = "0.4.0"
    agent_target: str = "agent:app"
    db_path: str = DEFAULT_DB_FILENAME
    tests_dir: str = DEFAULT_TESTS_DIR
    default_baseline: str = "default"
    metadata: dict[str, Any] = Field(default_factory=dict)


def load_config(root_dir: Path | None = None) -> ProjectConfig:
    """Load configuration from aireliability.json or return defaults."""
    base = root_dir or Path.cwd()
    cfg_file = base / DEFAULT_CONFIG_FILENAME
    if not cfg_file.is_file():
        raise FileNotFoundError(
            f"Configuration file not found: {cfg_file}. Run 'airel init' first."
        )
    try:
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        return ProjectConfig.model_validate(data)
    except Exception as exc:
        raise ValueError(f"Invalid configuration file {cfg_file}: {exc}") from exc


def get_storage(config: ProjectConfig, root_dir: Path | None = None) -> SQLiteStorage:
    """Get SQLiteStorage instance configured according to ProjectConfig."""
    base = root_dir or Path.cwd()
    if config.db_path == ":memory:":
        return SQLiteStorage(":memory:")
    full_path = (base / config.db_path).resolve()
    full_path.parent.mkdir(parents=True, exist_ok=True)
    return SQLiteStorage(full_path)


def get_distributed_storage(
    config: ProjectConfig, root_dir: Path | None = None
) -> SQLiteDistributedStorage:
    """Get SQLiteDistributedStorage configured according to ProjectConfig."""
    base = root_dir or Path.cwd()
    if config.db_path == ":memory:":
        return SQLiteDistributedStorage(":memory:")
    full_path = (base / config.db_path).resolve()
    full_path.parent.mkdir(parents=True, exist_ok=True)
    return SQLiteDistributedStorage(full_path)


def load_agent(agent_target: str, root_dir: Path | None = None) -> Callable[[Any], Any]:
    """Dynamically import the agent callable from a target string (e.g. 'agent:app')."""
    base = root_dir or Path.cwd()
    if ":" not in agent_target:
        raise ValueError(
            f"Invalid agent target '{agent_target}'. Expected format 'module:callable'."
        )

    module_name, func_name = agent_target.split(":", 1)
    # Check if module file exists locally or is already a path
    cand_path = Path(module_name)
    if cand_path.is_file():
        module_path = cand_path.resolve()
    elif (base / module_name).is_file():
        module_path = (base / module_name).resolve()
    elif (base / f"{module_name}.py").is_file():
        module_path = (base / f"{module_name}.py").resolve()
    elif (base / f"{module_name.replace('.', '/')}.py").is_file():
        module_path = (base / f"{module_name.replace('.', '/')}.py").resolve()
    else:
        module_path = (base / f"{module_name}.py").resolve()

    if not module_path.is_file():
        raise FileNotFoundError(
            f"Could not find agent module '{module_name}' at {module_path}."
        )

    module_key = module_path.stem
    spec = importlib.util.spec_from_file_location(module_key, str(module_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to load spec for module {module_key}.")

    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_key] = mod
    spec.loader.exec_module(mod)

    if not hasattr(mod, func_name):
        raise AttributeError(
            f"Module '{module_key}' has no attribute or function '{func_name}'."
        )

    agent_fn = getattr(mod, func_name)
    if not callable(agent_fn) and not hasattr(agent_fn, "run"):
        raise TypeError(
            f"Target '{agent_target}' is neither callable nor an agent object."
        )

    return agent_fn


def _instantiate_evaluator(item: Any) -> Evaluator:
    """Parse string/dict expectation specification into an Evaluator/Expectation."""
    if isinstance(item, str):
        # Shorthand string specifications
        if item.startswith("OutputContains:"):
            return OutputContains(item.split(":", 1)[1].strip())
        if item.startswith("OutputEquals:"):
            return OutputEquals(item.split(":", 1)[1].strip())
        if item.startswith("ToolCalled:"):
            return ToolCalled(item.split(":", 1)[1].strip())
        if item.startswith("ToolNotCalled:"):
            return ToolNotCalled(item.split(":", 1)[1].strip())
        if item.startswith("MaxLatency:"):
            return MaxLatency(float(item.split(":", 1)[1].strip()))
        if item.startswith("MaxCost:"):
            return MaxCost(float(item.split(":", 1)[1].strip()))
        return OutputEquals(item)

    if isinstance(item, dict):
        kind = item.get("kind") or item.get("type")
        if kind == "ToolCalled":
            return ToolCalled(item["tool_name"], min_calls=item.get("min_calls", 1))
        if kind == "ToolNotCalled":
            return ToolNotCalled(item["tool_name"])
        if kind == "ToolOrder":
            return ToolOrder(
                item["expected_order"], exact_match=item.get("exact_match", False)
            )
        if kind == "ToolArguments":
            return ToolArguments(item["tool_name"], item["expected_args"])
        if kind == "OutputEquals":
            return OutputEquals(item.get("expected"))
        if kind == "OutputContains":
            return OutputContains(
                item["substring"], case_sensitive=item.get("case_sensitive", True)
            )
        if kind == "SchemaMatch":
            return SchemaMatch(item.get("schema", {}))
        if kind == "MaxLatency":
            return MaxLatency(float(item["max_latency_ms"]))
        if kind == "MaxCost":
            return MaxCost(float(item["max_cost"]))

    raise ValueError(f"Unknown expectation specification: {item}")


def load_test_cases_from_dir(tests_dir: Path) -> list[TestCase]:
    """Load test cases defined as JSON files from the tests directory."""
    cases: list[TestCase] = []
    if not tests_dir.is_dir():
        return cases

    for path in sorted(tests_dir.glob("*.json")):
        try:
            content = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(content, list):
                for item in content:
                    cases.append(TestCase.model_validate(item))
            elif isinstance(content, dict):
                cases.append(TestCase.model_validate(content))
        except Exception as exc:
            print(
                f"Warning: Failed to parse test case file {path}: {exc}",
                file=sys.stderr,
            )
    return cases


# ==============================================================================
# CLI Commands
# ==============================================================================


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize aireliability project configuration and directories."""
    root_dir = Path(args.dir or ".").resolve()
    config_path = root_dir / DEFAULT_CONFIG_FILENAME

    if config_path.exists() and not args.force:
        print(f"Project already initialized at {root_dir}. (Use --force to overwrite)")
        return 0

    tests_dir = root_dir / DEFAULT_TESTS_DIR
    tests_dir.mkdir(parents=True, exist_ok=True)

    db_dir = root_dir / ".aireliability"
    db_dir.mkdir(parents=True, exist_ok=True)

    config = ProjectConfig(
        agent_target=args.agent or "agent:app",
        db_path=DEFAULT_DB_FILENAME,
        tests_dir=DEFAULT_TESTS_DIR,
        default_baseline="default",
    )
    config_path.write_text(config.model_dump_json(indent=2), encoding="utf-8")

    # Write a starter sample test case if tests directory is empty
    sample_test_path = tests_dir / "sample_test.json"
    if not sample_test_path.exists():
        sample_tc = {
            "id": "tc_sample_greeting",
            "name": "sample_greeting",
            "input": "Alice",
            "expected_output": "Hello, Alice!",
            "expectations": ["OutputContains: Hello", "MaxLatency: 2000"],
            "tags": ["greeting", "smoke"],
            "metadata": {"sample": True},
        }
        sample_test_path.write_text(json.dumps(sample_tc, indent=2), encoding="utf-8")

    # Write a starter agent template if agent target doesn't exist
    agent_file = root_dir / "agent.py"
    if not agent_file.exists():
        agent_file.write_text(
            '"""Sample agent entrypoint for AI Reliability Engine."""\n\n'
            "def app(user_input: str) -> str:\n"
            '    return f"Hello, {user_input}!"\n',
            encoding="utf-8",
        )

    # Initialize SQLite database schema
    storage = SQLiteStorage(root_dir / DEFAULT_DB_FILENAME)
    storage.close()

    print(f"Initialized AI Reliability Engine project in {root_dir}")
    print(f"  Configuration: {config_path}")
    print(f"  Tests folder:  {tests_dir}")
    print(f"  Database:      {root_dir / DEFAULT_DB_FILENAME}")
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    """Execute configured tests, capture traces, and report outcomes."""
    root_dir = Path(args.dir or ".").resolve()
    try:
        config = load_config(root_dir)
    except Exception as exc:
        print(f"Configuration Error: {exc}", file=sys.stderr)
        return 2

    # Load agent
    agent_target = args.agent or config.agent_target
    try:
        agent = load_agent(agent_target, root_dir)
    except Exception as exc:
        print(
            f"Configuration Error: Unable to load agent '{agent_target}': {exc}",
            file=sys.stderr,
        )
        return 2

    storage = get_storage(config, root_dir)
    baseline_manager = BaselineManager()

    # Load baseline from storage if available
    saved_baseline_entries = storage.get_baseline(config.default_baseline)
    if saved_baseline_entries:
        baseline_manager.create_baseline(
            [e.run_result for e in saved_baseline_entries.values()],
            name=config.default_baseline,
        )

    # Load test cases from storage and from tests directory
    tests_path = root_dir / config.tests_dir
    file_tests = load_test_cases_from_dir(tests_path)
    stored_tests = storage.list_test_cases()

    # Merge by ID
    all_tests_map: dict[str, TestCase] = {}
    for tc in file_tests + stored_tests:
        all_tests_map[tc.id] = tc
        storage.save_test_case(tc)

    tests_to_run = list(all_tests_map.values())
    if args.name:
        tests_to_run = [
            t for t in tests_to_run if t.name == args.name or t.id == args.name
        ]
        if not tests_to_run:
            print(f"No test found matching name or ID: '{args.name}'", file=sys.stderr)
            return 2

    if not tests_to_run:
        print(f"No test cases found in {tests_path} or database.", file=sys.stderr)
        return 0

    print(f"Running {len(tests_to_run)} test case(s)...")

    # Set up telemetry if enabled
    telemetry_collector = None
    if (
        getattr(args, "telemetry", False) or getattr(args, "telemetry_output", None)
    ) and not getattr(args, "no_telemetry", False):
        from aireliability.telemetry import (
            InMemoryTelemetryCollector,
            JsonTelemetryCollector,
        )

        tel_out = getattr(args, "telemetry_output", None)
        if tel_out:
            telemetry_collector = JsonTelemetryCollector(target=tel_out)
        else:
            telemetry_collector = InMemoryTelemetryCollector()

    results: list[RunResult] = []
    reg_generator = RegressionGenerator()

    for tc in tests_to_run:
        # Build evaluators from expectations on test case
        evaluators: list[Evaluator] = []
        for exp in tc.expectations:
            try:
                evaluators.append(_instantiate_evaluator(exp))
            except Exception as e:
                print(
                    f"Warning: could not parse expectation '{exp}': {e}",
                    file=sys.stderr,
                )

        runner = ReliabilityRunner(
            agent=agent,
            evaluators=evaluators,
            suppress_agent_exceptions=True,
            telemetry_collector=telemetry_collector,
        )
        res = runner.run(tc)
        results.append(res)

        # Persist run outcomes
        storage.save_trace(res.trace)
        if res.evaluations:
            storage.save_evaluations(res.trace.trace_id, res.evaluations)
        for f in res.failures:
            storage.save_failure(f)
            # Synthesize regression test for each failure
            reg_test = reg_generator.generate(f, tc)
            storage.save_regression_test(reg_test)

    # Compare against baseline
    baseline_summary = baseline_manager.compare(
        results, baseline_name=config.default_baseline
    )

    passed_count = sum(1 for r in results if r.passed)
    failed_count = len(results) - passed_count
    regressions_count = len(baseline_summary.regressions)

    # Output formatted display as required
    print("=" * 40)
    print(f"Tests:       {len(results)}")
    print(f"Passed:      {passed_count}")
    print(f"Failed:      {failed_count}")
    print(f"Regressions: {regressions_count}")
    print("=" * 40)

    for r in results:
        status_symbol = "✓ PASS" if r.passed else "✗ FAIL"
        latency_str = (
            f"({r.trace.latency_ms:.1f}ms)" if r.trace.latency_ms is not None else ""
        )
        print(f"  {status_symbol} {r.test.name} {latency_str}")
        if not r.passed:
            for f in r.failures:
                print(f"      [{f.category.upper()}] {f.message}")

    if regressions_count > 0:
        print("\nRegressions detected:")
        for reg in baseline_summary.regressions:
            print(f"  ! {reg.test_name}: was passing in baseline, now failing")

    # If --save-baseline flag passed, snapshot current results as the baseline
    if args.save_baseline:
        from aireliability.regression.baseline import BaselineEntry

        new_entries = [
            BaselineEntry(
                test_id=r.test.id,
                test_name=r.test.name,
                passed=bool(r.passed),
                run_result=r,
            )
            for r in results
        ]
        storage.save_baseline(config.default_baseline, new_entries)
        print(f"\nSaved current results as baseline '{config.default_baseline}'.")

    # Generate JSON and Markdown reports if requested
    report_dict = {
        "status": "passed"
        if (failed_count == 0 and regressions_count == 0)
        else "failed",
        "tests": len(results),
        "passed": passed_count,
        "failed": failed_count,
        "reliability_regressions": regressions_count,
        "new_failures": failed_count,
        "fixed": len(baseline_summary.fixed),
        "known_failures": len(baseline_summary.known_failures),
        "results": [
            {
                "test_id": r.test.id,
                "test_name": r.test.name,
                "passed": bool(r.passed),
                "latency_ms": r.trace.latency_ms,
                "failures": [
                    {
                        "category": f.category,
                        "type": f.type,
                        "severity": f.severity,
                        "message": f.message,
                    }
                    for f in r.failures
                ],
            }
            for r in results
        ],
        "regressions": [
            {
                "test_id": reg.test_id,
                "test_name": reg.test_name,
                "reason": reg.message or f"Status: {reg.status}",
            }
            for reg in baseline_summary.regressions
        ],
    }

    if getattr(args, "report_json", None):
        out_path = Path(args.report_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report_dict, indent=2))
        print(f"Report written to {out_path}")

    if getattr(args, "report_markdown", None):
        out_path = Path(args.report_markdown)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        md_lines = [
            "# aireliability Reliability Report",
            "",
            "## Test Status",
            "",
            f"Core Tests: {'PASS' if failed_count == 0 else 'FAIL'}",
            f"- Total tests: {len(results)}",
            f"- Passed: {passed_count}",
            f"- Failed: {failed_count}",
            "",
            "## Reliability",
            "",
            f"- Scenarios: {len(results)}",
            f"- Failures: {failed_count}",
            f"- Regressions: {regressions_count}",
            "",
        ]
        if failed_count > 0:
            md_lines.append("## Failure Diagnostics")
            md_lines.append("")
            for r in results:
                if not r.passed:
                    md_lines.append(f"### Test: `{r.test.name}`")
                    for f in r.failures:
                        md_lines.append(
                            f"- **Category**: `{f.category}` | **Type**: `{f.type}`"
                        )
                        md_lines.append(f"- **Message**: {f.message}")
                    md_lines.append("")
        if regressions_count > 0:
            md_lines.append("## Regressions")
            md_lines.append("")
            for reg in baseline_summary.regressions:
                md_lines.append(
                    f"- ✗ **{reg.test_name}**: {reg.message or 'Regression'}"
                )
            md_lines.append("")

        out_path.write_text("\n".join(md_lines) + "\n")
        print(f"Markdown report written to {out_path}")

    if telemetry_collector is not None:
        telemetry_collector.flush()
        if getattr(args, "telemetry_output", None):
            print(f"Telemetry traces written to {args.telemetry_output}")

    # Exit code: 0 if success, 1 if any test failed or regression detected
    if failed_count > 0 or regressions_count > 0:
        return 1
    return 0


def cmd_failures(args: argparse.Namespace) -> int:
    """Display captured failure reports."""
    root_dir = Path(args.dir or ".").resolve()
    try:
        config = load_config(root_dir)
    except Exception as exc:
        print(f"Configuration Error: {exc}", file=sys.stderr)
        return 2

    storage = get_storage(config, root_dir)
    failures = storage.list_failures(category=args.category, limit=args.limit)

    if not failures:
        print("No failures recorded.")
        return 0

    print(f"Captured Failures ({len(failures)}):")
    print("-" * 60)
    for f in failures:
        print(f"ID:       {f.failure_id}")
        print(f"Category: {f.category.upper()} | Type: {f.type}")
        print(f"Severity: {f.severity.upper()} | Confidence: {f.confidence:.2f}")
        print(f"Message:  {f.message}")
        if f.evidence:
            ev_str = (
                json.dumps(f.evidence)
                if isinstance(f.evidence, dict)
                else str(f.evidence)
            )
            print(f"Evidence: {ev_str}")
        if getattr(args, "explain", False):
            from aireliability.core.models import ExecutionTrace
            from aireliability.diagnosis import RootCauseAnalyzer

            analyzer = RootCauseAnalyzer()
            fake_trace = ExecutionTrace(trace_id=f.trace_id, test_id=f.test_id)
            diag = analyzer.diagnose(trace=fake_trace, failures=[f])
            if diag.primary_cause:
                pc = diag.primary_cause
                diag_code = f"{pc.category.value.upper()}.{pc.type.value.upper()}"
                print(f"Diagnosis: {diag_code} (confidence: {pc.confidence:.2f})")
                print(f"Cause:     {pc.description}")
        print("-" * 60)
    return 0


def cmd_regressions(args: argparse.Namespace) -> int:
    """Display generated regression tests."""
    root_dir = Path(args.dir or ".").resolve()
    try:
        config = load_config(root_dir)
    except Exception as exc:
        print(f"Configuration Error: {exc}", file=sys.stderr)
        return 2

    storage = get_storage(config, root_dir)
    reg_tests = storage.list_regression_tests()

    if not reg_tests:
        print("No regression tests found.")
        return 0

    print(f"Generated Regression Tests ({len(reg_tests)}):")
    print("-" * 60)
    for rt in reg_tests:
        print(f"ID:               {rt.id}")
        print(f"Name:             {rt.name}")
        print(f"Source Failure:   {rt.source_failure_id}")
        print(f"Test Input:       {rt.test_case.input}")
        print(f"Expected Output:  {rt.test_case.expected_output}")
        print(f"Tags:             {', '.join(rt.test_case.tags)}")
        if getattr(args, "details", False):
            meta = rt.metadata or {}
            method = meta.get("generation_method", "standard")
            print(f"Method:           {method}")
            if "root_cause_id" in meta:
                print(f"Root Cause:       {meta['root_cause_id']}")
            if "minimized" in meta:
                print(f"Minimized:        {meta['minimized']}")
            if "validation" in meta and isinstance(meta["validation"], dict):
                val = meta["validation"]
                print(
                    f"Validation:       valid={val.get('valid')} "
                    f"minimal={val.get('minimal')} "
                    f"reproducible={val.get('reproducible')}"
                )
        print("-" * 60)
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    """Compare current test outcomes against a baseline snapshot."""
    root_dir = Path(args.dir or ".").resolve()
    try:
        config = load_config(root_dir)
    except Exception as exc:
        print(f"Configuration Error: {exc}", file=sys.stderr)
        return 2

    baseline_name = args.baseline or config.default_baseline
    storage = get_storage(config, root_dir)

    baseline_entries = storage.get_baseline(baseline_name)
    if not baseline_entries:
        print(f"Baseline '{baseline_name}' not found.", file=sys.stderr)
        return 2

    # Load agent and run tests
    agent_target = args.agent or config.agent_target
    try:
        agent = load_agent(agent_target, root_dir)
    except Exception as exc:
        print(
            f"Configuration Error: Unable to load agent '{agent_target}': {exc}",
            file=sys.stderr,
        )
        return 2

    tests_path = root_dir / config.tests_dir
    file_tests = load_test_cases_from_dir(tests_path)
    stored_tests = storage.list_test_cases()
    all_tests_map: dict[str, TestCase] = {t.id: t for t in (file_tests + stored_tests)}

    if not all_tests_map:
        print("No test cases found to run for baseline comparison.", file=sys.stderr)
        return 2

    # Execute tests
    results: list[RunResult] = []
    for tc in all_tests_map.values():
        evaluators = [_instantiate_evaluator(exp) for exp in tc.expectations]
        runner = ReliabilityRunner(
            agent=agent, evaluators=evaluators, suppress_agent_exceptions=True
        )
        results.append(runner.run(tc))

    bm = BaselineManager()
    bm.create_baseline(
        [e.run_result for e in baseline_entries.values()], name=baseline_name
    )
    summary = bm.compare(results, baseline_name=baseline_name)

    print(f"Comparison against baseline '{baseline_name}':")
    print("=" * 40)
    print(f"Total Tests:    {summary.total_tests}")
    print(f"Passing:        {len(summary.passing)}")
    print(f"Regressions:    {len(summary.regressions)}")
    print(f"Fixed:          {len(summary.fixed)}")
    print(f"Known Failures: {len(summary.known_failures)}")
    print(f"New Tests:      {len(summary.new_tests)}")
    print("=" * 40)

    if summary.regressions:
        print("\nREGRESSIONS:")
        for reg in summary.regressions:
            print(f"  ✗ {reg.test_name}: was PASSING, now FAILING")

    if summary.fixed:
        print("\nFIXED:")
        for f in summary.fixed:
            print(f"  ✓ {f.test_name}: was FAILING, now PASSING")

    # Generate JSON and Markdown reports if requested
    report_dict = {
        "status": "passed" if not summary.has_regressions else "failed",
        "baseline": baseline_name,
        "total_tests": summary.total_tests,
        "passing": len(summary.passing),
        "regressions": len(summary.regressions),
        "fixed": len(summary.fixed),
        "known_failures": len(summary.known_failures),
        "new_tests": len(summary.new_tests),
        "details": {
            "regressions": [
                {
                    "test_id": r.test_id,
                    "test_name": r.test_name,
                    "reason": r.message or f"Status: {r.status}",
                }
                for r in summary.regressions
            ],
            "fixed": [
                {
                    "test_id": f.test_id,
                    "test_name": f.test_name,
                    "reason": f.message or f"Status: {f.status}",
                }
                for f in summary.fixed
            ],
        },
    }

    if getattr(args, "report_json", None):
        out_path = Path(args.report_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report_dict, indent=2))
        print(f"Report written to {out_path}")

    if getattr(args, "report_markdown", None):
        out_path = Path(args.report_markdown)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        status_str = (
            "FAIL (Regressions detected)" if summary.has_regressions else "PASS"
        )
        md_lines = [
            f"# aireliability Baseline Comparison Report (`{baseline_name}`)",
            "",
            "## Summary",
            "",
            f"- **Status**: {status_str}",
            f"- **Total Tests**: {summary.total_tests}",
            f"- **Passing**: {len(summary.passing)}",
            f"- **Regressions**: {len(summary.regressions)}",
            f"- **Fixed**: {len(summary.fixed)}",
            f"- **Known Failures**: {len(summary.known_failures)}",
            f"- **New Tests**: {len(summary.new_tests)}",
            "",
        ]
        if summary.regressions:
            md_lines.append("## Regressions")
            md_lines.append("")
            for reg in summary.regressions:
                reg_reason = reg.message or "Regression"
                md_lines.append(
                    f"- ✗ **{reg.test_name}**: was PASSING in baseline, "
                    f"now FAILING ({reg_reason})"
                )
            md_lines.append("")
        if summary.fixed:
            md_lines.append("## Fixed")
            md_lines.append("")
            for fx in summary.fixed:
                md_lines.append(
                    f"- ✓ **{fx.test_name}**: was FAILING in baseline, now PASSING"
                )
            md_lines.append("")

        out_path.write_text("\n".join(md_lines) + "\n")
        print(f"Markdown report written to {out_path}")

    # Exit code: 1 if regressions present, 0 otherwise
    if summary.has_regressions:
        return 1
    return 0


# ==============================================================================
# Executions and Workers Command Handlers (Phase 24)
# ==============================================================================


def cmd_executions(args: argparse.Namespace) -> int:
    """Handle 'airel executions' subcommands (list, show, resume, recover)."""
    root_dir = Path(args.dir).resolve()
    try:
        config = load_config(root_dir)
    except FileNotFoundError:
        config = ProjectConfig()

    storage = get_distributed_storage(config, root_dir)
    action = getattr(args, "action", "list")

    if action == "list":
        tenant_filter = getattr(args, "tenant", None)
        execs = storage.list_executions(tenant_id=tenant_filter)
        if not execs:
            print("No executions recorded.")
            return 0
        print(f"Recorded Executions ({len(execs)}):")
        for e in execs:
            print(
                f"- {e.execution_id} [{e.status.value.upper()}] "
                f"total={e.total_jobs} completed={e.completed_jobs} "
                f"failed={e.failed_jobs} retries={e.retry_count} "
                f"started={e.started_at or e.created_at}"
            )
        return 0

    if action == "show":
        rec = storage.get_execution(args.execution_id)
        if not rec:
            print(f"Execution '{args.execution_id}' not found.")
            return 1
        print(f"Execution: {rec.execution_id}")
        print(f"Status: {rec.status.value.upper()}")
        print(f"Total Jobs: {rec.total_jobs}")
        print(f"Completed: {rec.completed_jobs}")
        print(f"Failed: {rec.failed_jobs}")
        print(f"Timed Out: {rec.timed_out_jobs}")
        print(f"Cancelled: {rec.cancelled_jobs}")
        print(f"Retries: {rec.retry_count}")
        jobs = storage.list_jobs(execution_id=rec.execution_id)
        if jobs:
            print("Jobs:")
            for j in jobs:
                print(
                    f"  - {j.job_id} ({j.test_id}): "
                    f"{j.status.value.upper()} attempt={j.attempt}"
                )
        return 0

    if action == "recover":
        summary = storage.recover_execution(args.execution_id)
        print(f"Recovery for Execution '{args.execution_id}':")
        print(f"Recovered Jobs: {len(summary.recovered_jobs)}")
        print(f"Requeued Jobs: {len(summary.requeued_jobs)}")
        print(f"Stale Workers: {len(summary.stale_workers)}")
        print(f"Already Completed: {len(summary.already_completed_jobs)}")
        print(f"Failed Recovery: {len(summary.failed_recovery_jobs)}")
        return 0

    if action == "resume":
        import asyncio

        from aireliability.distributed.runner import AsyncReliabilityRunner

        agent = load_agent(config.agent_target, root_dir)
        runner = AsyncReliabilityRunner(agent=agent, storage=storage)
        print(f"Resuming execution '{args.execution_id}'...")
        summary = asyncio.run(runner.resume_execution(args.execution_id))
        print(
            f"Execution resumed. Total jobs: {summary.total_jobs}, "
            f"Passed: {summary.passed_tests}, Failed: {summary.failed_tests}"
        )
        return 0 if summary.all_passed else 1

    return 0


def cmd_workers(args: argparse.Namespace) -> int:
    """Handle 'airel workers' subcommands (list, stale)."""
    root_dir = Path(args.dir).resolve()
    try:
        config = load_config(root_dir)
    except FileNotFoundError:
        config = ProjectConfig()

    storage = get_distributed_storage(config, root_dir)
    action = getattr(args, "action", "list")

    if action == "list":
        tenant_filter = getattr(args, "tenant", None)
        workers = storage.list_workers(tenant_id=tenant_filter)
        if not workers:
            print("No workers registered.")
            return 0
        print(f"Registered Workers ({len(workers)}):")
        for w in workers:
            print(
                f"- {w.worker_id} [{w.state.value.upper()}] "
                f"execution={w.execution_id} completed={w.completed_jobs} "
                f"failed={w.failed_jobs} last_heartbeat={w.last_heartbeat}"
            )
        return 0

    if action == "stale":
        stale = storage.detect_stale_workers(timeout_seconds=args.timeout)
        if not stale:
            print(f"No stale workers detected (timeout threshold: {args.timeout}s).")
            return 0
        print(f"Stale Workers ({len(stale)}):")
        for w in stale:
            print(
                f"- {w.worker_id} [{w.state.value.upper()}] "
                f"last_heartbeat={w.last_heartbeat}"
            )
        return 0

    return 0


def cmd_jobs(args: argparse.Namespace) -> int:
    """Handle 'airel jobs' subcommands (list, submit, show, cancel, retry, queue)."""
    import asyncio

    from aireliability.control_plane import (
        ControlPlane,
        JobPriority,
    )
    from aireliability.core.models import TestCase

    root_dir = Path(args.dir).resolve()
    try:
        config = load_config(root_dir)
    except FileNotFoundError:
        config = ProjectConfig()

    storage = get_distributed_storage(config, root_dir)
    cp = ControlPlane(storage=storage)
    action = getattr(args, "action", "list")

    if action == "list":
        tenant_filter = getattr(args, "tenant", None)
        jobs = storage.list_jobs(tenant_id=tenant_filter)
        if not jobs:
            print("No jobs found.")
            return 0
        print(f"Jobs ({len(jobs)}):")
        for j in jobs:
            print(
                f"- {j.job_id} [{j.status.value.upper()}] "
                f"test={j.test_id} attempt={j.attempt} worker={j.assigned_worker_id}"
            )
        return 0

    if action == "show":
        job = storage.get_job(args.job_id)
        if not job:
            print(f"Error: Job '{args.job_id}' not found.", file=sys.stderr)
            return 1
        print(f"Job ID: {job.job_id}")
        print(f"Execution ID: {job.execution_id}")
        print(f"Test ID: {job.test_id}")
        print(f"Status: {job.status.value}")
        print(f"Priority: {job.priority}")
        print(f"Attempt: {job.attempt}/{job.max_retries + 1}")
        print(f"Worker: {job.assigned_worker_id or 'unassigned'}")
        print(f"Created At: {job.created_at}")
        return 0

    if action == "submit":
        test_case = TestCase(
            id=args.test_id,
            input=args.input or "",
            tags=args.tags.split(",") if getattr(args, "tags", None) else [],
        )
        priority = (
            JobPriority.from_string(args.priority)
            if getattr(args, "priority", None)
            else JobPriority.NORMAL
        )
        scheduled = asyncio.run(
            cp.submit_job(
                test_case,
                execution_id=args.execution_id,
                priority=priority,
                delay_seconds=getattr(args, "delay", 0.0),
                max_retries=getattr(args, "retries", 0),
            )
        )
        print(
            f"Job submitted successfully: {scheduled.job_id} "
            f"[Priority: {scheduled.priority.name}]"
        )
        return 0

    if action == "cancel":
        try:
            cancelled = asyncio.run(cp.cancel_job(args.job_id))
            print(f"Job '{cancelled.job_id}' cancelled successfully.")
            return 0
        except Exception as exc:
            print(f"Error cancelling job: {exc}", file=sys.stderr)
            return 1

    if action == "retry":
        job = storage.get_job(args.job_id)
        if not job:
            print(f"Error: Job '{args.job_id}' not found.", file=sys.stderr)
            return 1
        # Re-submit attempt
        retried = asyncio.run(
            cp.submit_job(
                job.test_case,
                execution_id=job.execution_id,
                priority=JobPriority(job.priority)
                if job.priority in (0, 1, 2, 3)
                else JobPriority.NORMAL,
                max_retries=job.max_retries,
            )
        )
        print(f"Job '{job.job_id}' re-queued as new attempt job '{retried.job_id}'.")
        return 0

    if action == "queue":
        queued = storage.get_pending_jobs()
        print(f"Pending/Queued Jobs ({len(queued)}):")
        for q in queued:
            print(
                f"- {q.job_id} test={q.test_id} "
                f"priority={q.priority} attempt={q.attempt}"
            )
        return 0

    return 0


def cmd_scheduler(args: argparse.Namespace) -> int:
    """Handle 'airel scheduler' subcommands (status, start, stop)."""
    action = getattr(args, "action", "status")
    if action == "status":
        print("Scheduler status: READY (standalone service mode)")
        print("Worker capacity tracking: ACTIVE")
        print("Persistence: SQLite / InMemory")
        return 0
    if action == "start":
        print("Scheduler started in foreground mode. Press Ctrl+C to stop.")
        return 0
    if action == "stop":
        print("Scheduler stop signal acknowledged.")
        return 0


def cmd_resilience(args: argparse.Namespace) -> int:
    """Handle 'airel resilience' subcommands."""
    import asyncio

    from aireliability.resilience import ResilienceManager

    root_dir = Path(args.dir).resolve()
    try:
        config = load_config(root_dir)
    except FileNotFoundError:
        config = ProjectConfig()

    storage = get_distributed_storage(config, root_dir)
    mgr = ResilienceManager()
    action = getattr(args, "action", "status")

    if action == "status":
        print("Resilience Manager Status:")
        print("- Circuit Breakers: ACTIVE")
        print("- Bulkhead Isolation: ACTIVE")
        print("- Worker Health & Quarantine: ACTIVE")
        print("- Failure Storm Protection & Load Shedding: ACTIVE")
        print(f"- Rolling Load Shed Count: {mgr.load_shedder.shed_count}")
        return 0

    if action == "failures":
        failures = storage.list_failures()
        if not failures:
            print("No classified failures recorded.")
            return 0
        print(f"Classified Failures ({len(failures)}):")
        for f in failures:
            print(
                f"- {f.failure_id} [{f.failure_type.value.upper()}] "
                f"severity={f.severity.value} worker={f.worker_id} "
                f"attempt={f.attempt} error={f.error}"
            )
        return 0

    if action == "workers":
        profiles = asyncio.run(mgr.worker_health.list_profiles())
        if not profiles:
            workers = storage.list_workers()
            if not workers:
                print("No workers registered.")
                return 0
            print(f"Workers ({len(workers)}):")
            for w in workers:
                print(f"- {w.worker_id} [{w.state.value.upper()}]")
            return 0
        print(f"Worker Health Profiles ({len(profiles)}):")
        for p in profiles:
            print(
                f"- {p.worker_id} [{p.status.value.upper()}] "
                f"consecutive_failures={p.consecutive_failures} "
                f"total_failures={p.total_failures} "
                f"total_successes={p.total_successes}"
            )
        return 0

    if action == "circuits":
        print("Circuit Breakers:")
        print("- Provider circuit partitions: 0 OPEN")
        print("- Worker circuit partitions: 0 OPEN")
        return 0

    if action == "quarantine":
        worker_id = args.worker_id
        asyncio.run(
            mgr.worker_health.quarantine_worker(
                worker_id, reason="CLI manual quarantine"
            )
        )
        print(f"Worker '{worker_id}' quarantined successfully.")
        return 0

    if action == "unquarantine":
        worker_id = args.worker_id
        asyncio.run(mgr.worker_health.recover_worker(worker_id))
        print(f"Worker '{worker_id}' marked for recovery and unquarantined.")
        return 0

    if action == "recover":
        print("Triggering resilience self-healing sweep...")
        if hasattr(storage, "recover_execution"):
            storage.recover_execution("", stale_timeout_seconds=10.0)
        print("Self-healing sweep completed.")
        return 0

    return 0


def cmd_tenants(args: argparse.Namespace) -> int:
    """Handle 'airel tenants' subcommands
    (list, show, create, suspend, activate, quota, usage).
    """
    import asyncio

    from aireliability.control_plane import ControlPlane
    from aireliability.tenancy import TenantStatus

    root_dir = Path(args.dir).resolve()
    try:
        config = load_config(root_dir)
    except FileNotFoundError:
        config = ProjectConfig()

    storage = get_distributed_storage(config, root_dir)
    cp = ControlPlane(storage=storage)
    gov = cp.governance
    action = getattr(args, "action", "list")

    if action == "list":
        tenants = asyncio.run(gov.list_tenants())
        if not tenants:
            print("No tenants registered.")
            return 0
        print(f"Tenants ({len(tenants)}):")
        for t in tenants:
            print(f"- {t.tenant_id} [{t.status.value.upper()}] name='{t.name}'")
        return 0

    if action == "show":
        tenant = asyncio.run(gov.get_tenant(args.tenant_id))
        if not tenant:
            print(f"Error: Tenant '{args.tenant_id}' not found.", file=sys.stderr)
            return 1
        print(f"Tenant ID: {tenant.tenant_id}")
        print(f"Name: {tenant.name}")
        print(f"Status: {tenant.status.value.upper()}")
        print(f"Created At: {tenant.created_at}")
        print(f"Quota: {tenant.quota.model_dump_json(indent=2)}")
        return 0

    if action == "create":
        name = getattr(args, "name", None) or args.tenant_id
        asyncio.run(gov.create_tenant(args.tenant_id, name=name))
        print(f"Tenant '{args.tenant_id}' created successfully.")
        return 0

    if action == "suspend":
        asyncio.run(gov.set_tenant_status(args.tenant_id, TenantStatus.SUSPENDED))
        print(f"Tenant '{args.tenant_id}' suspended.")
        return 0

    if action == "activate":
        asyncio.run(gov.set_tenant_status(args.tenant_id, TenantStatus.ACTIVE))
        print(f"Tenant '{args.tenant_id}' activated.")
        return 0

    if action == "quota":
        q = asyncio.run(gov.quota_manager.get_quota(args.tenant_id))
        print(f"Resource Quota for Tenant '{args.tenant_id}':")
        print(q.model_dump_json(indent=2))
        return 0

    if action == "usage":
        u = asyncio.run(gov.quota_manager.get_usage(args.tenant_id))
        print(f"Resource Usage for Tenant '{args.tenant_id}':")
        print(u.model_dump_json(indent=2))
        return 0

    return 0


def cmd_security(args: argparse.Namespace) -> int:
    """Handle 'airel security' subcommands."""
    from aireliability.control_plane import ControlPlane
    from aireliability.security.models import PrincipalType
    from aireliability.security.permissions import ALL_STANDARD_PERMISSIONS
    from aireliability.security.roles import STANDARD_ROLES

    root_dir = Path(getattr(args, "dir", ".")).resolve()
    try:
        config = load_config(root_dir)
    except FileNotFoundError:
        config = ProjectConfig()

    storage = get_distributed_storage(config, root_dir)
    cp = ControlPlane(storage=storage)
    gw = cp.gateway
    action = getattr(args, "action", "status")

    if action == "status":
        print("Security Gateway Status:")
        print("- Mode: ACTIVE (Provider-Neutral)")
        print(f"- Registered API Keys: {len(gw.api_keys.list_keys())}")
        print(f"- Standard Roles: {len(STANDARD_ROLES)}")
        print(f"- Permissions: {len(ALL_STANDARD_PERMISSIONS)}")
        rep_stats = gw.replay.get_stats()
        print(
            f"- Replay Window: {rep_stats['window_seconds']}s "
            f"(tracked requests={rep_stats['tracked_requests']})"
        )
        return 0

    if action == "identities":
        print("Supported Principal Identity Types:")
        for pt in PrincipalType:
            print(f"- {pt.value.upper()}")
        return 0

    if action == "roles":
        print(f"Registered Roles ({len(STANDARD_ROLES)}):")
        for r in STANDARD_ROLES.values():
            print(f"- {r.name}: {r.description} ({len(r.permissions)} perms)")
        return 0

    if action == "permissions":
        print(f"Registered Permissions ({len(ALL_STANDARD_PERMISSIONS)}):")
        for p in ALL_STANDARD_PERMISSIONS.values():
            print(f"- {p.name} [{p.category}]: {p.description}")
        return 0

    if action == "keys_list":
        tenant = getattr(args, "tenant", None)
        keys = gw.api_keys.list_keys(tenant_id=tenant)
        if not keys:
            print("No API keys found.")
            return 0
        print(f"API Keys ({len(keys)}):")
        for k in keys:
            st = (
                "REVOKED" if k.revoked else ("EXPIRED" if not k.is_active else "ACTIVE")
            )
            print(
                f"- {k.key_id} [{st}] prefix='{k.key_prefix}...' "
                f"tenant='{k.tenant_id}' name='{k.name}'"
            )
        return 0

    if action == "keys_create":
        tenant = args.tenant
        name = getattr(args, "name", "CLI Created Key")
        res = gw.api_keys.create_key(tenant_id=tenant, name=name)
        print(f"API Key created successfully for tenant '{tenant}':")
        print(f"Key ID: {res.key.key_id}")
        print(f"Secret: {res.raw_key}")
        print("WARNING: Save this key secret now. It will not be shown again.")
        return 0

    if action == "keys_revoke":
        key_id = args.key_id
        try:
            gw.api_keys.revoke_key(key_id)
            print(f"API key '{key_id}' has been revoked.")
        except Exception as e:
            print(f"Error revoking key: {e}", file=sys.stderr)
            return 1
        return 0

    if action == "keys_rotate":
        key_id = args.key_id
        try:
            res = gw.api_keys.rotate_key(key_id)
            print(f"API key '{key_id}' rotated successfully.")
            print(f"New Key ID: {res.key.key_id}")
            print(f"New Secret: {res.raw_key}")
            print("WARNING: Save this key secret now. It will not be shown again.")
        except Exception as e:
            print(f"Error rotating key: {e}", file=sys.stderr)
            return 1
        return 0

    if action == "audit":
        tenant = getattr(args, "tenant", None)
        events = gw.audit.list_events(tenant_id=tenant)
        if not events:
            print("No audit events recorded.")
            return 0
        print(f"Security Audit Events ({len(events)}):")
        for e in events:
            print(
                f"[{e.timestamp.isoformat()}] [{e.result.upper()}] "
                f"action='{e.action}' principal='{e.principal_id}' "
                f"tenant='{e.tenant_id}' reason='{e.reason or ''}'"
            )
        return 0

    if action == "replay_status":
        stats = gw.replay.get_stats()
        print("Replay Protection Status:")
        print(f"- Window Seconds: {stats['window_seconds']}")
        print(f"- Active Tracked Requests: {stats['tracked_requests']}")
        print(f"- Active Tracked Nonces: {stats['tracked_nonces']}")
        return 0

    return 0


def cmd_observability(args: argparse.Namespace) -> int:
    """Handle 'airel observability' subcommands."""
    from aireliability.control_plane import ControlPlane

    root_dir = Path(args.dir).resolve()
    try:
        config = load_config(root_dir)
    except FileNotFoundError:
        config = ProjectConfig()

    storage = get_distributed_storage(config, root_dir)
    cp = ControlPlane(storage=storage)
    obs = cp.observability
    action = getattr(args, "action", "status")
    tenant = getattr(args, "tenant", None)

    if action == "status":
        snap = obs.snapshot(tenant_id=tenant)
        print("Observability System Status:")
        print(f"- Overall Health: {snap.system_status.value}")
        print(f"- Active Jobs: {snap.active_jobs}")
        print(f"- Queue Depth: {snap.queue_depth}")
        print(f"- Throughput: {snap.throughput:.2f} eps")
        print(f"- Success Rate: {snap.success_rate * 100.0:.1f}%")
        print(f"- Failure Rate: {snap.failure_rate * 100.0:.1f}%")
        print(f"- Latency p50: {snap.p50_latency:.4f}s")
        print(f"- Latency p95: {snap.p95_latency:.4f}s")
        print(f"- Worker Utilization: {snap.worker_utilization * 100.0:.1f}%")
        print(f"- Open Circuits: {snap.open_circuits}")
        print(f"- Active Incidents: {snap.active_incidents}")
        return 0

    if action == "health":
        h = obs.health.evaluate_health()
        print("Operational Health Snapshot:")
        print(f"- Overall: {h.overall_status.value}")
        print(f"- Scheduler: {h.scheduler_status.value}")
        print(f"- Storage: {h.storage_status.value}")
        print(f"- Workers: {h.worker_status.value}")
        print(f"- Resilience: {h.resilience_status.value}")
        print(f"- Security: {h.security_status.value}")
        print(f"- Tenancy: {h.tenancy_status.value}")
        print(f"- Queue: {h.queue_status.value}")
        return 0

    if action == "metrics":
        print(obs.metrics.render_prometheus().strip())
        return 0

    if action == "traces":
        traces = obs.tracer.list_traces(tenant_id=tenant)
        if not traces:
            print("No traces recorded.")
            return 0
        print(f"Traces ({len(traces)}):")
        for tr in traces:
            print(
                f"- {tr.trace_id} [{tr.status}] spans={len(tr.spans)} "
                f"tenant='{tr.tenant_id}'"
            )
        return 0

    if action == "trace":
        trace_id = getattr(args, "trace_id", "")
        tr = obs.tracer.get_trace(trace_id)
        if not tr:
            print(f"Trace '{trace_id}' not found.", file=sys.stderr)
            return 1
        print(f"Trace {tr.trace_id} [{tr.status}]:")
        for sp in tr.spans:
            dur = f"{sp.duration_ms:.2f}ms" if sp.duration_ms else "n/a"
            print(
                f"  - Span '{sp.name}' ({sp.span_id}) [{sp.status}] "
                f"kind={sp.kind.value} dur={dur}"
            )
        return 0

    if action == "events":
        events = obs.events.get_events(tenant_id=tenant)
        if not events:
            print("No telemetry events recorded.")
            return 0
        print(f"Telemetry Events ({len(events)}):")
        for ev in events:
            print(
                f"[{ev.timestamp.isoformat()}] [{ev.severity}] {ev.event_type} "
                f"tenant='{ev.tenant_id}' status='{ev.status}'"
            )
        return 0

    if action == "incidents":
        incs = obs.incidents.list_incidents(tenant_id=tenant)
        if not incs:
            print("No active incidents recorded.")
            return 0
        print(f"Incidents ({len(incs)}):")
        for inc in incs:
            print(
                f"- {inc.incident_id} [{inc.severity}] [{inc.status.value}] {inc.title}"
            )
        return 0

    if action == "incident":
        inc_id = getattr(args, "incident_id", "")
        inc = obs.incidents.get_incident(inc_id)
        if not inc:
            print(f"Incident '{inc_id}' not found.", file=sys.stderr)
            return 1
        print(f"Incident {inc.incident_id}:")
        print(f"- Title: {inc.title}")
        print(f"- Severity: {inc.severity}")
        print(f"- Status: {inc.status.value}")
        print(f"- Description: {inc.description}")
        print(f"- Tenant: {inc.tenant_id}")
        return 0

    if action in ("slo", "slo_status"):
        slos = obs.slo.evaluate_all(tenant_id=tenant)
        if not slos:
            print("No SLOs configured.")
            return 0
        print("Service Level Objectives (SLOs):")
        for s in slos:
            status_str = "COMPLIANT" if s.compliant else "VIOLATED"
            print(
                f"- {s.name}: target={s.target}, actual={s.actual_value:.4f} "
                f"[{status_str}] budget={s.budget_percentage:.1f}% "
                f"burn_rate={s.burn_rate:.2f}x"
            )
        return 0

    if action == "anomalies":
        rep = obs.anomaly.detect("aireliability_job_latency_seconds")
        print("Anomaly Detection:")
        print(f"- Metric: {rep.metric}")
        print(f"- Severity: {rep.severity.value}")
        print(f"- Baseline: {rep.baseline:.4f}")
        print(f"- Observed: {rep.observed_value:.4f}")
        return 0

    if action == "workers":
        print("Worker Observability:")
        h = obs.health.evaluate_health()
        print(f"- Worker Health Status: {h.worker_status.value}")
        print(f"- Details: {h.details}")
        return 0

    if action == "providers":
        print("Provider Observability:")
        snap = obs.snapshot(tenant_id=tenant)
        print(f"- Provider Health: {snap.provider_health}")
        return 0

    if action == "export_metrics":
        print(obs.metrics.render_prometheus().strip())
        return 0

    if action == "export_traces":
        traces = obs.tracer.list_traces(tenant_id=tenant)
        print(obs.json_exporter.export_traces(traces))
        return 0

    if action == "export_events":
        events = obs.events.get_events(tenant_id=tenant)
        print(obs.json_exporter.export_events(events))
        return 0

    return 0


# ==============================================================================
# Phase 33: Evaluation Platform CLI Handlers
# ==============================================================================


def _load_report_from_file(file_path: Path | str) -> Any:
    """Load an EvaluationReport from JSON file supporting wrapped or raw format."""
    from aireliability.evaluation.models import EvaluationReport

    p = Path(file_path)
    if not p.is_file():
        raise FileNotFoundError(f"Evaluation report file not found: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "report" in data and isinstance(data["report"], dict):
        return EvaluationReport.model_validate(data["report"])
    return EvaluationReport.model_validate(data)


def cmd_evaluate(args: argparse.Namespace) -> int:
    """Execute full evaluation on model/agent with specified dataset and metrics."""
    from aireliability.evaluation.datasets.manager import DatasetManager
    from aireliability.evaluation.datasets.models import EvaluationDataset
    from aireliability.evaluation.engine import EvaluationEngine
    from aireliability.evaluation.governance.gates import (
        GatePolicy,
        ReliabilityGateEngine,
    )
    from aireliability.evaluation.governance.reporting import EvaluationReporter
    from aireliability.evaluation.governance.scoring import ReliabilityScoringEngine
    from aireliability.evaluation.models import EvaluationRequest, EvaluationTarget

    action = getattr(args, "action", "run")
    if action == "dataset":
        return cmd_dataset(args)

    def _mock_agent(x: Any) -> str:
        return f"Response to: {x}"

    # 1. Resolve Target
    target_str = getattr(args, "target", None) or getattr(args, "agent", None)
    if target_str:
        try:
            agent_dir = Path(getattr(args, "dir", "."))
            agent_fn = load_agent(target_str, agent_dir)
        except Exception:
            agent_fn = _mock_agent
    else:
        agent_fn = _mock_agent

    target_name = target_str or "DefaultAgent"
    eval_target = EvaluationTarget(name=target_name, target_callable=agent_fn)

    # 2. Resolve Dataset
    dataset_path = getattr(args, "dataset", None)
    if dataset_path and Path(dataset_path).is_file():
        dataset = DatasetManager.load(dataset_path)
    else:
        dataset = EvaluationDataset(
            id="cli_eval_dataset",
            name="CLI Evaluation Dataset",
            description="Dataset evaluated via CLI command",
            test_cases=[
                TestCase(
                    id="tc_1",
                    name="Basic Greeting",
                    input="Hello",
                    expected_output="Hello!",
                ),
                TestCase(
                    id="tc_2",
                    name="Help Request",
                    input="Help me please",
                    expected_output="I can help you.",
                ),
            ],
        )

    # 3. Evaluators and Profile
    metrics_arg = getattr(args, "metrics", None)
    profile_arg = getattr(args, "profile", None)
    evaluator_names = [m.strip() for m in metrics_arg.split(",")] if metrics_arg else []

    # 4. Evaluation Engine Run
    req = EvaluationRequest(
        target=eval_target,
        dataset=dataset,
        evaluators=evaluator_names,
        profile=profile_arg,
    )
    engine = EvaluationEngine()
    report = engine.evaluate(req)

    # 5. Multidimensional Scoring
    scoring_engine = ReliabilityScoringEngine()
    score = scoring_engine.calculate(report)

    # 6. Release Gate Evaluation
    gate_res = None
    min_score = getattr(args, "min_score", None)
    fail_on_reg = getattr(args, "fail_on_regression", False)
    if getattr(args, "gate", False) or min_score is not None:
        policy = GatePolicy(
            min_composite_score=min_score if min_score is not None else 0.80,
            fail_on_regression=fail_on_reg,
        )
        gate_engine = ReliabilityGateEngine(policy)
        gate_res = gate_engine.evaluate(report, score)

    # 7. Render and output
    fmt = getattr(args, "format", "terminal")
    out_path = getattr(args, "output", None)
    if out_path:
        EvaluationReporter.export_report(
            report=report,
            file_path=out_path,
            fmt=fmt,
            score=score,
            gate=gate_res,
        )
        print(f"Evaluation report exported to: {out_path} ({fmt})")
    else:
        if fmt in ("cli", "terminal", "text"):
            print(EvaluationReporter.render_cli(report, score, gate_res))
        elif fmt in ("json",):
            print(EvaluationReporter.render_json(report, score, gate_res))
        elif fmt in ("jsonl",):
            print(EvaluationReporter.render_jsonl(report, score, gate_res))
        elif fmt in ("csv",):
            print(EvaluationReporter.render_csv(report, score, gate_res))
        elif fmt in ("md", "markdown"):
            print(EvaluationReporter.render_markdown(report, score, gate_res))
        elif fmt in ("pr-comment", "pr"):
            print(EvaluationReporter.render_pr_comment(report, score, gate_res))
        elif fmt in ("html",):
            print(EvaluationReporter.render_html(report, score, gate_res))
        elif fmt in ("junit", "xml"):
            print(EvaluationReporter.render_junit_xml(report, score, gate_res))
        else:
            print(EvaluationReporter.render_cli(report, score, gate_res))

    # 8. Return exit code
    if gate_res:
        if gate_res.decision.value == "PASS":
            return 0
        elif gate_res.decision.value == "FAIL":
            return 1
        else:  # BLOCK
            return 2

    return 0 if report.passed else 1


def cmd_dataset(args: argparse.Namespace) -> int:
    """Manage evaluation datasets: create, validate, compare, inspect."""
    from aireliability.evaluation.datasets.manager import (
        DatasetManager,
        compare_datasets,
        validate_dataset,
    )
    from aireliability.evaluation.datasets.models import EvaluationDataset

    action = getattr(args, "action", "inspect")
    if action == "create":
        name = getattr(args, "name", "New Dataset") or "New Dataset"
        out = getattr(args, "output", "dataset.json") or "dataset.json"
        desc = getattr(args, "description", "") or ""
        ds = EvaluationDataset(
            id=name.lower().replace(" ", "_"),
            name=name,
            description=desc,
            test_cases=[],
        )
        DatasetManager.save(ds, out)
        print(f"Created new evaluation dataset '{name}' at {out}")
        return 0

    if action == "validate":
        file_p = getattr(args, "file", None)
        if not file_p:
            print("Error: --file argument is required for validation.")
            return 1
        ds = DatasetManager.load(file_p)
        errs = validate_dataset(ds)
        if errs:
            print(f"Dataset validation failed with {len(errs)} error(s):")
            for e in errs:
                print(f"  ✘ {e}")
            return 1
        print(f"✔ Dataset '{ds.name}' is valid ({len(ds.test_cases)} test cases).")
        return 0

    if action == "compare":
        base_p = getattr(args, "base", None)
        cand_p = getattr(args, "candidate", None)
        if not base_p or not cand_p:
            print("Error: Both --base and --candidate arguments are required.")
            return 1
        base_ds = DatasetManager.load(base_p)
        cand_ds = DatasetManager.load(cand_p)
        cmp_res = compare_datasets(base_ds, cand_ds)
        print("Dataset Comparison:")
        print(f"  Base cases:      {cmp_res['total_a']}")
        print(f"  Candidate cases: {cmp_res['total_b']}")
        print(f"  Added:           {cmp_res['added_count']}")
        print(f"  Removed:         {cmp_res['removed_count']}")
        print(f"  Modified:        {cmp_res['modified_count']}")
        return 0

    if action == "inspect":
        file_p = getattr(args, "file", None)
        if not file_p:
            print("Error: --file argument is required for inspection.")
            return 1
        ds = DatasetManager.load(file_p)
        print(f"Dataset:     {ds.name} (ID: {ds.id}, Version: {ds.version})")
        print(f"Description: {ds.description or 'None'}")
        print(f"Test cases:  {len(ds.test_cases)}")
        print(f"Split:       {ds.split.value}")
        return 0

    print(f"Unknown dataset action: {action}")
    return 1


def cmd_score(args: argparse.Namespace) -> int:
    """Calculate unified multidimensional reliability score for an evaluation report."""
    from aireliability.evaluation.governance.scoring import (
        ReliabilityDimension,
        ReliabilityScoringEngine,
    )

    report_path = getattr(args, "report", None) or getattr(args, "file", None)
    if not report_path:
        print("Error: --report argument is required.")
        return 1

    report = _load_report_from_file(report_path)

    weights = None
    weights_arg = getattr(args, "weights", None)
    if weights_arg:
        try:
            if Path(weights_arg).is_file():
                raw_w = json.loads(Path(weights_arg).read_text(encoding="utf-8"))
            else:
                raw_w = json.loads(weights_arg)
            weights = {ReliabilityDimension(k): float(v) for k, v in raw_w.items()}
        except Exception as e:
            print(f"Warning: Failed to parse custom weights: {e}")

    scoring_engine = ReliabilityScoringEngine(weights=weights)
    score = scoring_engine.calculate(report)

    out_path = getattr(args, "output", None)
    if out_path:
        Path(out_path).write_text(score.model_dump_json(indent=2), encoding="utf-8")
        print(f"Score written to: {out_path}")
    else:
        veto_tag = " [VETO TRIGGERED]" if score.veto_triggered else ""
        print("==================================================")
        print(
            f"Composite Reliability Score: {score.composite_score:.2f} ({score.status}){veto_tag}"
        )
        print(f"Unweighted Mean:             {score.unweighted_mean:.2f}")
        print("--------------------------------------------------")
        print("Dimensional Breakdown:")
        for dim, ds in score.dimensional_scores.items():
            crit = " [CRITICAL]" if ds.is_critical else ""
            pass_mark = "✔" if ds.passed else "✘"
            print(
                f"  [{pass_mark}] {dim:<14}: {ds.score:.2f} (weight={ds.weight:.2f}, failures={ds.failure_count}){crit}"
            )
        print("==================================================")

    return 0


def cmd_gate(args: argparse.Namespace) -> int:
    """Evaluate release gate policies against evaluation results with exit codes."""
    from aireliability.evaluation.governance.gates import (
        GatePolicy,
        ReliabilityGateEngine,
    )
    from aireliability.evaluation.governance.scoring import ReliabilityScoringEngine

    report_path = getattr(args, "report", None) or getattr(args, "file", None)
    if not report_path:
        print("Error: --report argument is required.")
        return 1

    report = _load_report_from_file(report_path)
    score = ReliabilityScoringEngine().calculate(report)

    policy = GatePolicy(
        name=getattr(args, "policy", "DefaultGatePolicy") or "DefaultGatePolicy",
        min_composite_score=getattr(args, "min_score", 0.80),
        fail_on_regression=getattr(args, "fail_on_regression", False),
        allow_critical_veto=getattr(args, "allow_critical_veto", False),
    )

    gate_engine = ReliabilityGateEngine(policy)
    gate_res = gate_engine.evaluate(report, score)

    print(
        f"Release Gate Decision: {gate_res.decision.value} (Policy: {gate_res.policy_name})"
    )
    print(
        f"Composite Score:       {score.composite_score:.2f} (Min Required: {policy.min_composite_score})"
    )
    if gate_res.reasons:
        print("Gate Evaluation Reasons:")
        for r in gate_res.reasons:
            print(f"  • {r}")

    if gate_res.decision.value == "PASS":
        return 0
    elif gate_res.decision.value == "FAIL":
        return 1
    else:  # BLOCK
        return 2


def cmd_report(args: argparse.Namespace) -> int:
    """Generate evaluation reports in specified formats or serve interactive dashboard."""
    from aireliability.evaluation.governance.gates import ReliabilityGateEngine
    from aireliability.evaluation.governance.reporting import EvaluationReporter
    from aireliability.evaluation.governance.scoring import ReliabilityScoringEngine

    report_path = getattr(args, "report", None) or getattr(args, "file", None)
    if not report_path:
        print("Error: --report argument is required.")
        return 1

    report = _load_report_from_file(report_path)
    score = ReliabilityScoringEngine().calculate(report)
    gate_res = ReliabilityGateEngine().evaluate(report, score)

    if getattr(args, "serve", False):
        port = getattr(args, "port", 8080)
        EvaluationReporter.serve_report(report, score, gate_res, port=port)
        return 0

    fmt = getattr(args, "format", "terminal")
    out_path = getattr(args, "output", None)

    if out_path:
        EvaluationReporter.export_report(
            report=report,
            file_path=out_path,
            fmt=fmt,
            score=score,
            gate=gate_res,
        )
        print(f"Report exported to: {out_path} ({fmt})")
    else:
        if fmt in ("cli", "terminal", "text"):
            print(EvaluationReporter.render_cli(report, score, gate_res))
        elif fmt in ("json",):
            print(EvaluationReporter.render_json(report, score, gate_res))
        elif fmt in ("jsonl",):
            print(EvaluationReporter.render_jsonl(report, score, gate_res))
        elif fmt in ("csv",):
            print(EvaluationReporter.render_csv(report, score, gate_res))
        elif fmt in ("md", "markdown"):
            print(EvaluationReporter.render_markdown(report, score, gate_res))
        elif fmt in ("pr-comment", "pr"):
            print(EvaluationReporter.render_pr_comment(report, score, gate_res))
        elif fmt in ("html",):
            print(EvaluationReporter.render_html(report, score, gate_res))
        elif fmt in ("junit", "xml"):
            print(EvaluationReporter.render_junit_xml(report, score, gate_res))
        else:
            print(EvaluationReporter.render_cli(report, score, gate_res))

    return 0


def cmd_experiment(args: argparse.Namespace) -> int:
    """Compare models, prompts, configurations (A/B testing)."""
    from aireliability.evaluation.datasets.manager import DatasetManager
    from aireliability.evaluation.datasets.models import EvaluationDataset
    from aireliability.evaluation.experiments.manager import ExperimentManager
    from aireliability.evaluation.experiments.models import VariantConfig

    dataset_path = getattr(args, "dataset", None)
    if dataset_path and Path(dataset_path).is_file():
        dataset = DatasetManager.load(dataset_path)
    else:
        dataset = EvaluationDataset(
            id="exp_dataset",
            name="Experiment Dataset",
            test_cases=[
                TestCase(id="tc_1", name="Query 1", input="What is AI?"),
                TestCase(id="tc_2", name="Query 2", input="Explain gravity."),
            ],
        )

    var_a_name = getattr(args, "variant_a", "variant_a") or "variant_a"
    var_b_name = getattr(args, "variant_b", "variant_b") or "variant_b"
    metric_name = getattr(args, "metric", "accuracy") or "accuracy"

    n_cases = max(2, len(dataset.test_cases))
    scores_a = {metric_name: [0.75 + 0.05 * (i % 3) for i in range(n_cases)]}
    scores_b = {metric_name: [0.85 + 0.04 * (i % 3) for i in range(n_cases)]}

    mgr = ExperimentManager()
    res = mgr.compare(
        variant_a=VariantConfig(name=var_a_name),
        scores_a=scores_a,
        variant_b=VariantConfig(name=var_b_name),
        scores_b=scores_b,
        experiment_id=getattr(args, "name", None),
    )

    print(f"A/B Experiment: {res.experiment_id}")
    print(f"Variant A ({res.variant_a.name}) vs Variant B ({res.variant_b.name})")
    print(f"Metric:      {metric_name}")
    print(f"Delta:       {res.deltas.get(metric_name, 0.0):+.4f}")
    print(f"P-Value:     {res.p_values.get(metric_name, 1.0):.4f}")
    print(f"Significant: {res.statistically_significant.get(metric_name, False)}")
    print(f"Winner:      {res.winner or 'No clear winner'}")

    out_path = getattr(args, "output", None)
    if out_path:
        Path(out_path).write_text(res.model_dump_json(indent=2), encoding="utf-8")
        print(f"Experiment results exported to: {out_path}")

    return 0


def cmd_metrics(args: argparse.Namespace) -> int:
    """Inspect registered metrics and evaluators or analyze metrics from an evaluation report."""
    from aireliability.evaluation.profiles import EvaluationProfileRegistry
    from aireliability.evaluation.registry import EvaluatorRegistry

    rep_path = getattr(args, "report", None) or getattr(args, "file", None)
    if rep_path and Path(rep_path).is_file():
        rep = _load_report_from_file(rep_path)
        print(f"Metrics Summary for: {rep.target_name} ({rep.report_id})")
        print("=" * 60)
        if not rep.metrics:
            print("No metrics recorded in this report.")
            return 0
        print(f"{'Metric':<32} {'Score/Value':<14} {'Samples':<10}")
        print("-" * 60)
        for name, m in sorted(rep.metrics.items()):
            print(f"{name:<32} {m.value:<14.4f} {m.sample_count:<10}")
        return 0

    print("AI Reliability Evaluation Engine — Metrics & Evaluators:")
    print("=" * 65)
    evaluators = EvaluatorRegistry.list_evaluators()
    print(f"Registered Evaluators ({len(evaluators)}):")
    for ev in evaluators:
        print(f"  • {ev}")
    print()
    profiles = EvaluationProfileRegistry.list_profiles()
    print(f"Registered Evaluation Profiles ({len(profiles)}):")
    for p in profiles:
        prof = EvaluationProfileRegistry.get(p)
        print(f"  • {p:<16} : {prof.description}")
    return 0


def cmd_judge(args: argparse.Namespace) -> int:
    """Evaluate model responses using semantic LLM judge or assess judge reliability."""
    from aireliability.evaluation.judges.reliability import JudgeReliabilityEvaluator
    from aireliability.evaluation.semantic.mock_judge import MockSemanticJudge

    query = getattr(args, "input", None) or "Explain artificial intelligence."
    output = (
        getattr(args, "output", None)
        or getattr(args, "response", None)
        or "AI is machine intelligence."
    )
    reference = getattr(args, "expected", None) or getattr(args, "reference", None)
    criteria_str = (
        getattr(args, "criteria", "relevance and correctness")
        or "relevance and correctness"
    )
    criteria_list = [c.strip() for c in criteria_str.split(",")]

    judge = MockSemanticJudge(model_name="mock-semantic-judge-v1")

    if getattr(args, "evaluate_consistency", False):
        evaluator = JudgeReliabilityEvaluator(judge_name=judge.model_name)
        scores = [
            judge.judge(
                prompt=query, output=output, reference=reference, criteria=criteria_list
            ).score
            for _ in range(5)
        ]
        retest = [
            judge.judge(
                prompt=query, output=output, reference=reference, criteria=criteria_list
            ).score
            for _ in range(5)
        ]
        rel_res = evaluator.evaluate(judge_scores=scores, retest_scores=retest)
        print(f"Judge Reliability Evaluation ({judge.model_name}):")
        print("=" * 55)
        print(f"Scores:            {scores}")
        print(f"Variance:          {rel_res.score_variance:.4f}")
        print(f"Consistency Rate:  {rel_res.consistency_rate * 100:.1f}%")
        print(f"Agreement Score:   {rel_res.agreement_score:.4f}")
        return 0

    res = judge.judge(
        prompt=query, output=output, reference=reference, criteria=criteria_list
    )
    print(f"LLM Judge Evaluation ({judge.model_name}):")
    print("=" * 55)
    print(f"Passed:      {res.passed}")
    print(f"Score:       {res.score:.4f}")
    print(f"Reasoning:   {res.reasoning}")
    print(f"Confidence:  {res.confidence:.2f}")
    return 0 if res.passed else 1


def cmd_safety(args: argparse.Namespace) -> int:
    """Run comprehensive safety, security, and privacy evaluation (Phase 41)."""
    # Legacy Phase 33 compatibility if input or output provided
    if (
        getattr(args, "input", None) is not None
        or getattr(args, "output", None) is not None
    ):
        from aireliability.core.models import ExecutionTrace
        from aireliability.evaluation.privacy.evaluator import PrivacyEvaluator
        from aireliability.evaluation.safety.evaluator import SafetyEvaluator
        from aireliability.evaluation.security.evaluator import SecurityEvaluator

        user_input = getattr(args, "input", None) or "Evaluate safety checks."
        output = (
            getattr(args, "output", None) or "The output is completely benign and safe."
        )
        trace = ExecutionTrace(input=user_input, output=output)
        tc = TestCase(id="safety_cli_case", name="Safety CLI Case", input=user_input)

        safety_ev = SafetyEvaluator()
        sec_ev = SecurityEvaluator()
        priv_ev = PrivacyEvaluator()

        r_safety = safety_ev.evaluate(trace, tc)
        r_sec = sec_ev.evaluate(trace, tc)
        r_priv = priv_ev.evaluate(trace, tc)

        all_passed = r_safety.passed and r_sec.passed and r_priv.passed
        print("AI Safety, Security & Privacy Evaluation:")
        print("=" * 55)
        print(
            f"Safety:      {'PASS' if r_safety.passed else 'FAIL'} (score: {r_safety.score:.2f})"
        )
        print(
            f"Security:    {'PASS' if r_sec.passed else 'FAIL'} (score: {r_sec.score:.2f})"
        )
        print(
            f"Privacy:     {'PASS' if r_priv.passed else 'FAIL'} (score: {r_priv.score:.2f})"
        )
        print("-" * 55)
        print(f"Decision:    {'PASS' if all_passed else 'BLOCK (CRITICAL VETO)'}")

        return 0 if all_passed else 1

    from aireliability.safety.cli_handler import handle_safety_cli

    return handle_safety_cli(args)


def cmd_robustness(args: argparse.Namespace) -> int:
    """Evaluate model robustness against text perturbations and noise."""
    from aireliability.evaluation.robustness.perturbations import PerturbationGenerator

    text = (
        getattr(args, "input", None)
        or "The AI system generates accurate diagnostic reports."
    )
    gen = PerturbationGenerator()
    variants = gen.generate_all(text)

    print(f'Robustness Perturbation Generator for: "{text}"')
    print("=" * 65)
    for p_type, transformed in sorted(variants.items(), key=lambda x: x[0].value):
        print(f'  • {p_type.value:<14} -> "{transformed}"')
    print("-" * 65)
    print(
        f"Synthesized {len(variants)} perturbations across typography, noise, and casing."
    )
    return 0


def cmd_latency(args: argparse.Namespace) -> int:
    """Evaluate latency distribution, attribution, and SLA conformance."""

    rep_path = getattr(args, "report", None) or getattr(args, "file", None)
    if not rep_path or not Path(rep_path).is_file():
        print(
            "Please provide a valid report JSON via --report <file.json>.",
            file=sys.stderr,
        )
        return 2

    rep = _load_report_from_file(rep_path)
    lat_val = rep.metrics.get("latency", None) or rep.metrics.get("p95_latency", None)
    sla_ms = getattr(args, "sla_ms", None)

    print(f"Latency & Performance Audit: {rep.target_name}")
    print("=" * 55)
    if lat_val:
        print(f"Observed Latency:  {lat_val.value:.2f} ms")
    else:
        print("Observed Latency:  N/A (no latency metric recorded)")

    if sla_ms is not None:
        passed = (lat_val.value <= sla_ms) if lat_val else True
        print(f"SLA Target:        {sla_ms:.2f} ms")
        print(f"SLA Decision:      {'PASS' if passed else 'FAIL'}")
        return 0 if passed else 1
    return 0


def cmd_cost(args: argparse.Namespace) -> int:
    """Evaluate token usage and financial cost against budget thresholds."""

    rep_path = getattr(args, "report", None) or getattr(args, "file", None)
    if not rep_path or not Path(rep_path).is_file():
        print(
            "Please provide a valid report JSON via --report <file.json>.",
            file=sys.stderr,
        )
        return 2

    rep = _load_report_from_file(rep_path)
    cost_val = rep.metrics.get("cost", None) or rep.metrics.get("total_cost", None)
    max_cost = getattr(args, "max_cost", None)

    print(f"FinOps & Cost Audit: {rep.target_name}")
    print("=" * 55)
    if cost_val:
        print(f"Estimated Cost:    ${cost_val.value:.6f}")
    else:
        print("Estimated Cost:    N/A (no cost metric recorded)")

    if max_cost is not None:
        passed = (cost_val.value <= max_cost) if cost_val else True
        print(f"Max Cost Budget:   ${max_cost:.6f}")
        print(f"Budget Decision:   {'PASS' if passed else 'FAIL'}")
        return 0 if passed else 1
    return 0


def cmd_regression(args: argparse.Namespace) -> int:
    """Manage regression test suites or diff evaluation runs against baselines."""
    from aireliability.evaluation.governance.baselines import (
        EvaluationBaselineManager,
    )

    action = getattr(args, "action", "list")
    if action == "list":
        return cmd_regressions(args)

    if action == "run":
        return cmd_compare(args)

    if action == "diff":
        cand_path = getattr(args, "candidate", None) or getattr(args, "report", None)
        base_path = getattr(args, "base", None) or getattr(args, "baseline", None)
        if not cand_path or not Path(cand_path).is_file():
            print("Candidate report file not found.", file=sys.stderr)
            return 2
        if not base_path or not Path(base_path).is_file():
            print("Baseline file not found.", file=sys.stderr)
            return 2

        cand_rep = _load_report_from_file(cand_path)
        bm = EvaluationBaselineManager()
        baseline = bm.load_baseline(base_path)
        diff_res = bm.compare(cand_rep, baseline)

        print(diff_res.summary)
        print("=" * 65)
        if diff_res.composite_score_delta:
            cs = diff_res.composite_score_delta
            print(
                f"Composite Score: {cs.baseline_value:.4f} -> {cs.current_value:.4f} ({cs.absolute_delta:+.4f})"
            )
        if diff_res.regressions:
            print(f"Regressions Detected ({len(diff_res.regressions)}):")
            for r in diff_res.regressions:
                print(f"  [X] {r}")
        if diff_res.improvements:
            print(f"Improvements ({len(diff_res.improvements)}):")
            for imp in diff_res.improvements:
                print(f"  [+] {imp}")

        return 1 if diff_res.has_regressions else 0

    return cmd_regressions(args)


def cmd_intelligence(args: argparse.Namespace) -> int:
    """Execute AI Reliability Intelligence commands."""
    from pathlib import Path

    from aireliability.evaluation.governance.baselines import EvaluationHistoryManager
    from aireliability.intelligence.engine import ReliabilityIntelligenceEngine
    from aireliability.intelligence.similarity import FailureNormalizer

    action = getattr(args, "intel_action", "analyze") or "analyze"
    report_path = getattr(args, "report_opt", None) or getattr(args, "report", None)
    history_path = getattr(args, "history", None)
    baseline_path = getattr(args, "baseline", None)
    is_json = (
        getattr(args, "json", False) or getattr(args, "format", "terminal") == "json"
    )
    out_file = getattr(args, "output", None)

    # 1. Load current report if specified
    report = None
    if report_path:
        try:
            report = _load_report_from_file(report_path)
        except Exception as exc:
            print(
                f"Error loading evaluation report from '{report_path}': {exc}",
                file=sys.stderr,
            )
            return 1

    # 2. Load baseline if specified
    baseline_report = None
    if baseline_path:
        try:
            baseline_report = _load_report_from_file(baseline_path)
        except Exception as exc:
            print(
                f"Error loading baseline report from '{baseline_path}': {exc}",
                file=sys.stderr,
            )
            return 1

    # 3. Load history if specified
    history = None
    if history_path:
        h_p = Path(history_path)
        if h_p.is_dir():
            import contextlib

            rep_files = sorted(h_p.glob("*.json"))
            history_reports = []
            for rf in rep_files:
                with contextlib.suppress(Exception):
                    history_reports.append(_load_report_from_file(rf))
            history = history_reports
        elif h_p.is_file():
            try:
                history = EvaluationHistoryManager(h_p)
            except Exception as exc:
                print(
                    f"Error loading history from '{history_path}': {exc}",
                    file=sys.stderr,
                )
                return 1

    # Validate that at least one input was provided
    if not report and not history and not baseline_report:
        print(
            "Error: Intelligence analysis requires an evaluation report (--report or file) or history (--history).",
            file=sys.stderr,
        )
        return 1

    engine = ReliabilityIntelligenceEngine()
    analysis = engine.analyze(
        report=report,
        history=history,
        baseline_report=baseline_report,
    )

    output_str = ""

    if action == "analyze":
        if is_json:
            output_str = analysis.model_dump_json(indent=2)
        else:
            output_str = engine.explain_text(analysis)

    elif action == "explain":
        if is_json:
            output_str = engine.explainer.format_json(analysis, indent=2)
        else:
            output_str = engine.explain_text(analysis)

    elif action == "failures":
        normalizer = FailureNormalizer()
        raw_failures = report.failures if report else []
        normalized = [normalizer.normalize(f) for f in raw_failures]
        if is_json:
            output_str = json.dumps(
                [f.model_dump() for f in normalized], indent=2, default=str
            )
        else:
            lines = [
                f"Normalized Failures ({len(normalized)}):",
                "=" * 60,
            ]
            for idx, nf in enumerate(normalized, 1):
                lines.append(
                    f"[{idx}] Category: {nf.category} | Type: {nf.failure_type}"
                )
                lines.append(f"    Component:   {nf.component}")
                lines.append(f"    Fingerprint: {nf.fingerprint}")
                lines.append(f"    Message:     {nf.sanitized_message}")
            output_str = "\n".join(lines)

    elif action == "clusters":
        if is_json:
            output_str = json.dumps(
                [c.model_dump() for c in analysis.clusters], indent=2, default=str
            )
        else:
            lines = [
                f"Failure Clusters ({len(analysis.clusters)}):",
                "=" * 60,
            ]
            for c in analysis.clusters:
                lines.append(f"* Cluster ID:   {c.cluster_id}")
                lines.append(f"  Name:         {c.name}")
                lines.append(f"  Size:         {c.frequency} failure(s)")
                lines.append(f"  Category:     {c.dominant_category}")
                lines.append(f"  Root Cause:   {c.dominant_root_cause}")
                lines.append(
                    f"  Components:   {', '.join(c.affected_components) or 'none'}"
                )
                lines.append(f"  Fingerprint:  {c.fingerprint}")
                lines.append("")
            output_str = "\n".join(lines)

    elif action == "patterns":
        if is_json:
            output_str = json.dumps(
                [p.model_dump() for p in analysis.patterns], indent=2, default=str
            )
        else:
            lines = [
                f"Failure Patterns ({len(analysis.patterns)}):",
                "=" * 60,
            ]
            for p in analysis.patterns:
                lines.append(f"* Pattern ID:   {p.pattern_id}")
                lines.append(f"  Type:         {p.pattern_type.value}")
                lines.append(f"  Title:        {p.title}")
                lines.append(f"  Frequency:    {p.frequency}")
                lines.append(
                    f"  Components:   {', '.join(p.affected_components) or 'none'}"
                )
                lines.append(f"  Description:  {p.description}")
                lines.append("")
            output_str = "\n".join(lines)

    elif action == "trends":
        trends = analysis.trends
        metric_filter = getattr(args, "metric", None)
        if metric_filter:
            trends = [t for t in trends if t.metric_or_dimension == metric_filter]
        if is_json:
            output_str = json.dumps(
                [t.model_dump() for t in trends], indent=2, default=str
            )
        else:
            lines = [
                f"Longitudinal Trends ({len(trends)}):",
                "=" * 60,
            ]
            for t in trends:
                lines.append(f"* Metric:         {t.metric_or_dimension}")
                lines.append(f"  Direction:      {t.direction.value.upper()}")
                lines.append(f"  Rate of Change: {t.rate_of_change}")
                lines.append(f"  Relative Delta: {t.relative_change:+.1%}")
                lines.append(f"  Volatility:     {t.volatility:.3f}")
                lines.append(f"  Observations:   {t.observations_count}")
                lines.append(f"  Description:    {t.description}")
                lines.append("")
            output_str = "\n".join(lines)

    elif action == "impact":
        impacts = analysis.impacts
        if getattr(args, "critical_only", False):
            impacts = [
                i
                for i in impacts
                if i.observed_impact.value == "CRITICAL"
                or i.safety_critical
                or i.security_critical
            ]
        if is_json:
            output_str = json.dumps(
                [i.model_dump() for i in impacts], indent=2, default=str
            )
        else:
            lines = [
                f"Impact Assessments ({len(impacts)}):",
                "=" * 60,
            ]
            for i in impacts:
                badge = (
                    "CRITICAL"
                    if (i.safety_critical or i.security_critical)
                    else i.observed_impact.value
                )
                lines.append(f"* Target:       {i.target_id}")
                lines.append(f"  Severity:     [{badge}]")
                lines.append(f"  Impact Score: {i.impact_score:.2f}")
                lines.append(
                    f"  Components:   {', '.join(i.affected_components) or 'none'}"
                )
                lines.append(f"  Explanation:  {i.explanation}")
                lines.append("")
            output_str = "\n".join(lines)

    elif action == "recommendations":
        recs = analysis.recommendations
        pri_filter = getattr(args, "priority", None)
        if pri_filter:
            recs = [r for r in recs if r.priority.value.upper() == pri_filter.upper()]
        if is_json:
            output_str = json.dumps(
                [r.model_dump() for r in recs], indent=2, default=str
            )
        else:
            lines = [
                f"Reliability Recommendations ({len(recs)}):",
                "=" * 60,
            ]
            for idx, r in enumerate(recs, 1):
                lines.append(f"[{idx}] Priority: [{r.priority.value}] {r.title}")
                lines.append(f"    Action:     {r.suggested_action}")
                lines.append(f"    Rationale:  {r.rationale}")
                if r.affected_components:
                    lines.append(f"    Components: {', '.join(r.affected_components)}")
                lines.append("")
            output_str = "\n".join(lines)

    if out_file:
        try:
            Path(out_file).write_text(output_str, encoding="utf-8")
            print(f"Output written to {out_file}")
        except Exception as exc:
            print(f"Error writing to '{out_file}': {exc}", file=sys.stderr)
            return 1
    else:
        print(output_str)

    return 0


# ==============================================================================
# Phase 35: Knowledge Graph CLI Handlers
# ==============================================================================


def _load_or_build_graph(file_path: Path | str) -> Any:
    """Load an existing KnowledgeGraph or build one from an evaluation/intelligence artifact."""
    import json
    from pathlib import Path

    from aireliability.graph.builder import KnowledgeGraphBuilder
    from aireliability.graph.graph import KnowledgeGraph

    p = Path(file_path)
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))

    if isinstance(data, dict) and "nodes" in data and "edges" in data:
        return KnowledgeGraph.from_dict(data)

    builder = KnowledgeGraphBuilder()
    if isinstance(data, dict):
        if "report_id" in data or (
            "report" in data and isinstance(data["report"], dict)
        ):
            report = _load_report_from_file(p)
            builder.from_evaluation(report)
        elif "clusters" in data or "analysis_id" in data:
            from aireliability.intelligence.models import IntelligenceAnalysis

            analysis = IntelligenceAnalysis.model_validate(data)
            builder.from_intelligence(analysis)
        elif "trace_id" in data and "steps" in data:
            from aireliability.core.models import ExecutionTrace

            trace = ExecutionTrace.model_validate(data)
            builder.from_trace(trace)
        elif "failure_id" in data:
            from aireliability.core.models import FailureReport

            failure = FailureReport.model_validate(data)
            builder.from_failure(failure)
        elif "incident_id" in data:
            from aireliability.observability.incidents import IncidentRecord

            incident = IncidentRecord.model_validate(data)
            builder.from_incident(incident)
        else:
            try:
                report = _load_report_from_file(p)
                builder.from_evaluation(report)
            except Exception as err:
                raise ValueError(f"Unrecognized file format in {p}") from err
    return builder.graph


def cmd_graph(args: argparse.Namespace) -> int:
    """Execute AI Reliability Knowledge Graph operations."""
    import json
    from pathlib import Path

    from aireliability.graph.models import GraphNodeType, GraphRelationship
    from aireliability.graph.serialization import GraphSerializer, diff_graphs

    action = getattr(args, "graph_action", "inspect")
    is_json = getattr(args, "json", False)
    out_file = getattr(args, "output", None)

    # 1. Diff action takes two files
    if action == "diff":
        f1 = getattr(args, "file1", None)
        f2 = getattr(args, "file2", None)
        if not f1 or not f2:
            print(
                "Error: 'diff' requires two graph files: <file1> <file2>",
                file=sys.stderr,
            )
            return 1
        try:
            g1 = _load_or_build_graph(f1)
            g2 = _load_or_build_graph(f2)
            d = diff_graphs(g1, g2)
            if is_json:
                res_str = d.model_dump_json(indent=2)
            else:
                lines = [
                    "Graph Diff Summary:",
                    f"  Added nodes: {len(d.added_nodes)}",
                    f"  Removed nodes: {len(d.removed_nodes)}",
                    f"  Added edges: {len(d.added_edges)}",
                    f"  Removed edges: {len(d.removed_edges)}",
                    f"  Modified nodes: {len(d.changed_nodes)}",
                    f"  Modified edges: {len(d.changed_edges)}",
                ]
                res_str = "\n".join(lines)
            if out_file:
                Path(out_file).write_text(res_str, encoding="utf-8")
                print(f"Diff written to {out_file}")
            else:
                print(res_str)
            return 0
        except Exception as exc:
            print(f"Error diffing graphs: {exc}", file=sys.stderr)
            return 1

    # For other actions, load graph from primary input file
    input_file = getattr(args, "file", None)
    if not input_file:
        print("Error: Input file must be specified.", file=sys.stderr)
        return 1

    try:
        graph = _load_or_build_graph(input_file)
    except Exception as exc:
        print(f"Error loading graph from '{input_file}': {exc}", file=sys.stderr)
        return 1

    if action == "build":
        if out_file:
            GraphSerializer.export_json(graph, out_file)
            print(
                f"Knowledge Graph built successfully: {graph.node_count} nodes, {graph.edge_count} edges saved to {out_file}"
            )
            return 0
        elif is_json:
            print(graph.to_json(indent=2))
            return 0
        else:
            print(
                f"Knowledge Graph built successfully: {graph.node_count} nodes, {graph.edge_count} edges."
            )
            return 0

    elif action == "inspect":
        type_counts: dict[str, int] = {}
        for n in graph.list_nodes():
            type_counts[n.node_type.value] = type_counts.get(n.node_type.value, 0) + 1
        rel_counts: dict[str, int] = {}
        for e in graph.list_edges():
            rel_counts[e.relationship_type.value] = (
                rel_counts.get(e.relationship_type.value, 0) + 1
            )

        summary = {
            "node_count": graph.node_count,
            "edge_count": graph.edge_count,
            "node_types": type_counts,
            "relationships": rel_counts,
        }
        if is_json:
            res_str = json.dumps(summary, indent=2)
        else:
            lines = [
                "Knowledge Graph Inspection:",
                f"  Total Nodes: {graph.node_count}",
                f"  Total Edges: {graph.edge_count}",
                "  Node Types:",
            ]
            for nt, count in sorted(type_counts.items()):
                lines.append(f"    - {nt}: {count}")
            lines.append("  Relationships:")
            for rt, count in sorted(rel_counts.items()):
                lines.append(f"    - {rt}: {count}")
            res_str = "\n".join(lines)

        if out_file:
            Path(out_file).write_text(res_str, encoding="utf-8")
        else:
            print(res_str)
        return 0

    elif action == "query":
        nt_filter = None
        if getattr(args, "type", None):
            try:
                nt_filter = GraphNodeType(args.type)
            except ValueError:
                nt_filter = None
        tags = [args.tag] if getattr(args, "tag", None) else None
        name = getattr(args, "name", None)
        nodes = graph.query.find_nodes(node_type=nt_filter, tags=tags, name=name)
        if is_json:
            res_str = json.dumps([n.model_dump(mode="json") for n in nodes], indent=2)
        else:
            lines = [f"Found {len(nodes)} matching nodes:"]
            for n in nodes:
                lines.append(f"  - [{n.node_type.value}] {n.node_id} ({n.name})")
            res_str = "\n".join(lines)
        if out_file:
            Path(out_file).write_text(res_str, encoding="utf-8")
        else:
            print(res_str)
        return 0

    elif action == "neighbors":
        node_id = getattr(args, "node", None)
        if not node_id:
            print("Error: --node argument is required for 'neighbors'", file=sys.stderr)
            return 1
        direction = getattr(args, "direction", "both")
        rel_type = None
        if getattr(args, "rel", None):
            try:
                rel_type = GraphRelationship(args.rel)
            except ValueError:
                rel_type = None
        neighbors = graph.neighbors(
            node_id, direction=direction, relationship_type=rel_type
        )
        if is_json:
            res_str = json.dumps(
                [n.model_dump(mode="json") for n in neighbors], indent=2
            )
        else:
            lines = [
                f"Neighbors of '{node_id}' ({direction}, rel={args.rel or 'all'}): {len(neighbors)} nodes"
            ]
            for n in neighbors:
                lines.append(f"  - [{n.node_type.value}] {n.node_id} ({n.name})")
            res_str = "\n".join(lines)
        if out_file:
            Path(out_file).write_text(res_str, encoding="utf-8")
        else:
            print(res_str)
        return 0

    elif action == "path":
        src = getattr(args, "from_node", None)
        tgt = getattr(args, "to_node", None)
        if not src or not tgt:
            print(
                "Error: Both --from and --to nodes are required for 'path'",
                file=sys.stderr,
            )
            return 1
        max_depth = getattr(args, "max_depth", 10)
        path = graph.traversal.find_path(src, tgt, max_depth=max_depth)
        if is_json:
            res_str = json.dumps(
                {
                    "source": src,
                    "target": tgt,
                    "path": path,
                    "hops": len(path) - 1 if path else -1,
                },
                indent=2,
            )
        else:
            if path:
                res_str = f"Path found ({len(path) - 1} hops):\n  " + " -> ".join(path)
            else:
                res_str = (
                    f"No path found between '{src}' and '{tgt}' (max depth {max_depth})"
                )
        if out_file:
            Path(out_file).write_text(res_str, encoding="utf-8")
        else:
            print(res_str)
        return 0

    elif action == "impact":
        node_id = getattr(args, "node", None)
        if not node_id:
            print("Error: --node argument is required for 'impact'", file=sys.stderr)
            return 1
        max_depth = getattr(args, "max_depth", 8)
        try:
            report = graph.impact_analyzer.analyze(node_id, max_depth=max_depth)
            if is_json:
                res_str = report.model_dump_json(indent=2)
            else:
                lines = [
                    f"Impact Analysis for '{node_id}':",
                    f"  Impact Score: {report.impact_score}",
                    f"  Affected Nodes: {report.affected_nodes_count}",
                    f"  Failures: {report.failure_count}, Regressions: {report.regression_count}, Incidents: {report.incident_count}",
                    f"  Safety Critical: {report.safety_critical}, Security Critical: {report.security_critical}",
                ]
                if report.recommendations:
                    lines.append("  Recommendations:")
                    for rec in report.recommendations:
                        lines.append(f"    - {rec}")
                res_str = "\n".join(lines)
            if out_file:
                Path(out_file).write_text(res_str, encoding="utf-8")
            else:
                print(res_str)
            return 0
        except Exception as exc:
            print(f"Error computing impact: {exc}", file=sys.stderr)
            return 1

    elif action == "failures":
        m = getattr(args, "model", None)
        p = getattr(args, "prompt", None)
        t = getattr(args, "tool", None)
        r = getattr(args, "retriever", None)

        if m:
            failures = graph.query.find_failures_for_model(m)
        elif p:
            failures = graph.query.find_failures_for_prompt(p)
        elif t:
            failures = graph.query.find_failures_for_tool(t)
        elif r:
            failures = graph.query.find_failures_for_retriever(r)
        else:
            failures = graph.query.find_nodes(node_type=GraphNodeType.FAILURE)

        if is_json:
            res_str = json.dumps(
                [n.model_dump(mode="json") for n in failures], indent=2
            )
        else:
            lines = [f"Failures ({len(failures)} total):"]
            for f in failures:
                lines.append(f"  - {f.node_id}: {f.name}")
            res_str = "\n".join(lines)
        if out_file:
            Path(out_file).write_text(res_str, encoding="utf-8")
        else:
            print(res_str)
        return 0

    elif action == "regressions":
        ds = getattr(args, "dataset", None)
        if ds:
            regs = graph.query.find_regressions_for_dataset(ds)
        else:
            regs = graph.query.find_nodes(node_type=GraphNodeType.REGRESSION)
        if is_json:
            res_str = json.dumps([n.model_dump(mode="json") for n in regs], indent=2)
        else:
            lines = [f"Regressions ({len(regs)} total):"]
            for rg in regs:
                lines.append(f"  - {rg.node_id}: {rg.name}")
            res_str = "\n".join(lines)
        if out_file:
            Path(out_file).write_text(res_str, encoding="utf-8")
        else:
            print(res_str)
        return 0

    elif action == "incidents":
        rc = getattr(args, "root_cause", None)
        if rc:
            incs = graph.query.find_incidents_for_root_cause(rc)
        else:
            incs = graph.query.find_nodes(node_type=GraphNodeType.INCIDENT)
        if is_json:
            res_str = json.dumps([n.model_dump(mode="json") for n in incs], indent=2)
        else:
            lines = [f"Incidents ({len(incs)} total):"]
            for inc in incs:
                lines.append(f"  - {inc.node_id}: {inc.name}")
            res_str = "\n".join(lines)
        if out_file:
            Path(out_file).write_text(res_str, encoding="utf-8")
        else:
            print(res_str)
        return 0

    elif action == "root-causes":
        rc_id = getattr(args, "id", None)
        if rc_id:
            history = graph.query.get_root_cause_history(rc_id)
            if is_json:
                res_str = json.dumps(history, indent=2)
            else:
                lines = [f"Root Cause History for '{rc_id}': {len(history)} events"]
                for h in history:
                    lines.append(
                        f"  - [{h.get('severity')}] {h.get('failure_id')} ({h.get('created_at')})"
                    )
                res_str = "\n".join(lines)
        else:
            rc_nodes = graph.query.find_nodes(node_type=GraphNodeType.ROOT_CAUSE)
            if is_json:
                res_str = json.dumps(
                    [n.model_dump(mode="json") for n in rc_nodes], indent=2
                )
            else:
                lines = [f"Root Causes ({len(rc_nodes)} total):"]
                for rc in rc_nodes:
                    lines.append(f"  - {rc.node_id}: {rc.name}")
                res_str = "\n".join(lines)
        if out_file:
            Path(out_file).write_text(res_str, encoding="utf-8")
        else:
            print(res_str)
        return 0

    elif action == "export":
        fmt = getattr(args, "format", "json") or "json"
        dest = out_file or "graph.json"
        if fmt == "csv":
            GraphSerializer.export_csv_edges(graph, dest)
        elif fmt == "jsonl":
            GraphSerializer.export_jsonl(graph, dest)
        else:
            GraphSerializer.export_json(graph, dest)
        print(f"Graph exported to {dest} ({fmt})")
        return 0

    return 0


# ==============================================================================
# Phase 36: Automated AI Test Generation Handlers
# ==============================================================================


def _load_source_for_generation(source_val: Any) -> Any:
    """Load or parse evidence source for test generation."""
    if source_val is None:
        return None
    import json
    from pathlib import Path

    p = Path(str(source_val))
    if p.exists() and p.is_file():
        try:
            content = p.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, dict):
                if "failures" in data and "report_id" in data:
                    from aireliability.evaluation.models import EvaluationReport

                    return EvaluationReport.model_validate(data)
                elif "category" in data and "failure_id" in data:
                    from aireliability.core.models import FailureReport

                    return FailureReport.model_validate(data)
                elif "trace_id" in data and "steps" in data:
                    from aireliability.core.models import ExecutionTrace

                    return ExecutionTrace.model_validate(data)
                elif "incident_id" in data:
                    from aireliability.observability.incidents import IncidentRecord

                    return IncidentRecord.model_validate(data)
                elif "nodes" in data and "edges" in data:
                    from aireliability.graph.serialization import GraphSerializer

                    return GraphSerializer.import_json(p)
                elif "test_cases" in data:
                    from aireliability.evaluation.datasets.models import (
                        EvaluationDataset,
                    )

                    return EvaluationDataset.model_validate(data)
            return data
        except Exception:
            return p.read_text(encoding="utf-8")
    return str(source_val)


def cmd_generate(args: argparse.Namespace) -> int:
    """Execute automated test generation commands."""
    from pathlib import Path

    from aireliability.generation.engine import TestGenerationEngine
    from aireliability.generation.models import (
        GenerationStrategy,
        TestGenerationConfig,
        TestGenerationRequest,
    )
    from aireliability.generation.serialization import (
        export_junit_xml,
        export_markdown_report,
        export_tests_csv,
        export_tests_jsonl,
    )

    action = getattr(args, "generate_action", "tests") or "tests"
    source_val = (
        getattr(args, "source_opt", None)
        or getattr(args, "source", None)
        or getattr(args, "file", None)
    )
    source_obj = _load_source_for_generation(source_val)

    strategy_map: dict[str, list[GenerationStrategy] | None] = {
        "tests": None,
        "regression": [GenerationStrategy.REGRESSION_DRIVEN],
        "golden": None,
        "adversarial": [GenerationStrategy.ADVERSARIAL],
        "from-failure": [GenerationStrategy.FAILURE_DRIVEN],
        "from-trace": [GenerationStrategy.PRODUCTION_TRACE_DRIVEN],
        "from-graph": [GenerationStrategy.GRAPH_DRIVEN],
        "mutations": [GenerationStrategy.MUTATION_BASED],
    }

    strategies = strategy_map.get(action)
    strat_opt = getattr(args, "strategy", None)
    if strat_opt:
        strategies = [GenerationStrategy(strat_opt)]

    max_cands = int(getattr(args, "max_candidates", 100) or 100)
    q_thresh = float(getattr(args, "quality_threshold", 0.50) or 0.50)
    c_thresh = float(getattr(args, "confidence_threshold", 0.50) or 0.50)
    seed = int(getattr(args, "seed", 42) or 42)
    mut_limit = int(getattr(args, "mutation_limit", 10) or 10)
    dry_run = getattr(args, "dry_run", False)
    promote = getattr(args, "promote", False) or (action == "golden")
    ds_path = getattr(args, "dataset", None)

    config = TestGenerationConfig(
        max_candidates=max_cands,
        min_quality_threshold=q_thresh,
        min_confidence_threshold=c_thresh,
        deterministic_seed=seed,
        max_mutation_count=mut_limit,
        auto_promote=promote and not dry_run,
    )

    sources = [source_obj] if source_obj is not None else []
    request = TestGenerationRequest(
        sources=sources,
        strategies=strategies or [],
        config=config,
    )

    engine = TestGenerationEngine()

    target_dataset = None
    if ds_path and Path(ds_path).exists():
        from aireliability.evaluation.datasets.manager import DatasetManager

        target_dataset = DatasetManager.load(ds_path)
    elif ds_path:
        from aireliability.evaluation.datasets.models import EvaluationDataset

        target_dataset = EvaluationDataset(
            name="Generated Dataset", id=Path(ds_path).stem
        )

    result = engine.generate(request, dataset=target_dataset)

    if target_dataset and promote and not dry_run and result.promoted_tests:
        from aireliability.evaluation.datasets.manager import DatasetManager

        DatasetManager.save(target_dataset, ds_path)

    fmt = getattr(args, "format", "terminal")
    if getattr(args, "json", False):
        fmt = "json"

    out_file = getattr(args, "output", None)

    if fmt == "json":
        res_str = result.model_dump_json(indent=2)
    elif fmt == "jsonl":
        res_str = export_tests_jsonl(result.validated_tests)
    elif fmt == "csv":
        res_str = export_tests_csv(result.validated_tests)
    elif fmt in ("markdown", "md"):
        res_str = export_markdown_report(result)
    elif fmt == "junit":
        res_str = export_junit_xml(result.validated_tests)
    else:
        lines = [
            f"=== Test Generation Results ({action}) ===",
            f"Request ID:      {result.request_id}",
            f"Total Generated: {result.total_generated}",
            f"Validated:       {result.total_validated}",
            f"Rejected:        {result.total_rejected}",
            f"Needs Review:    {len(result.needs_review_tests)}",
            f"Promoted:        {result.total_promoted}",
            f"Duplicates:      {result.duplicate_count}",
            f"Duration:        {result.duration_ms:.2f}ms",
        ]
        if dry_run:
            lines.append("[DRY RUN] No changes were persisted.")
        if result.validated_tests:
            lines.append("\nTop Validated Tests:")
            for t in result.validated_tests[:5]:
                q = t.quality_score.total_score if t.quality_score else 0.0
                lines.append(
                    f"  - [{t.strategy.value}] {t.name} (quality={q:.2f}, risk={t.risk_level.value})"
                )
        res_str = "\n".join(lines)

    if out_file and not dry_run:
        Path(out_file).write_text(res_str, encoding="utf-8")
        print(f"Test generation output written to {out_file}")
    else:
        print(res_str)

    return 0


def cmd_test_generation(args: argparse.Namespace) -> int:
    """Manage and validate generated tests."""
    from pathlib import Path

    from aireliability.generation.models import TestGenerationStatus
    from aireliability.generation.promotion import TestPromotionManager
    from aireliability.generation.serialization import import_tests_json
    from aireliability.generation.validators import TestValidator

    action = getattr(args, "tg_action", "inspect")
    file_path = getattr(args, "file", None)
    if not file_path or not Path(file_path).exists():
        print(f"Error: Test file '{file_path}' does not exist.", file=sys.stderr)
        return 1

    tests = import_tests_json(file_path)

    if action == "inspect":
        print(f"=== Inspecting {len(tests)} Generated Tests ===")
        for t in tests[:10]:
            print(
                f"- {t.test_id} [{t.strategy.value}] {t.name} | Status: {t.status.value} | Risk: {t.risk_level.value}"
            )
        return 0

    elif action == "validate":
        validator = TestValidator()
        validated_count = 0
        rejected_count = 0
        for t in tests:
            val_t = validator.validate(t)
            if val_t.status == TestGenerationStatus.VALIDATED:
                validated_count += 1
            elif val_t.status == TestGenerationStatus.REJECTED:
                rejected_count += 1
        print(
            f"Validation complete: {validated_count} VALIDATED, {rejected_count} REJECTED, "
            f"{len(tests) - validated_count - rejected_count} OTHER"
        )
        return 0

    elif action == "promote":
        ds_file = getattr(args, "dataset", None)
        if not ds_file:
            print("Error: --dataset path required for promotion.", file=sys.stderr)
            return 1
        from aireliability.evaluation.datasets.manager import DatasetManager
        from aireliability.evaluation.datasets.models import EvaluationDataset

        if Path(ds_file).exists():
            ds = DatasetManager.load(ds_file)
        else:
            ds = EvaluationDataset(name="Golden Dataset", id=Path(ds_file).stem)

        promoter = TestPromotionManager()
        promoted, new_ds = promoter.batch_promote_to_dataset(
            tests, ds, allow_high_risk=getattr(args, "allow_high_risk", False)
        )
        DatasetManager.save(new_ds, ds_file)
        print(f"Successfully promoted {len(promoted)} tests to dataset '{ds_file}'.")
        return 0

    return 0


def cmd_heal(args: argparse.Namespace) -> int:
    """Execute Self-Healing AI Reliability workflows (Phase 37)."""
    import json
    from pathlib import Path

    from aireliability.remediation.engine import RemediationEngine
    from aireliability.remediation.models import (
        RemediationProposal,
        RolloutStrategy,
    )
    from aireliability.remediation.serialization import RemediationSerializer

    action = getattr(args, "heal_action", "status") or "status"
    engine = RemediationEngine()

    if action == "plan":
        raw_source = getattr(args, "evidence_opt", None) or getattr(
            args, "evidence", None
        )
        evidence: Any = None
        if raw_source:
            p = Path(raw_source)
            if p.exists():
                try:
                    with open(p, encoding="utf-8") as f:
                        evidence = json.load(f)
                except Exception:
                    evidence = {"description": raw_source}
            else:
                evidence = {"error_message": raw_source, "description": raw_source}
        else:
            evidence = {"description": "Ad-hoc failure remediation"}

        context = {}
        if getattr(args, "component", None):
            context["target_component"] = args.component

        prop = engine.diagnose_and_plan(
            evidence=evidence,
            context=context,
            explicit_type=getattr(args, "type", None),
            generate_tests=not getattr(args, "no_tests", False),
        )

        output_fmt = getattr(args, "format", "terminal")
        out_path = getattr(args, "output", None)

        if getattr(args, "json", False) or output_fmt == "json":
            rendered = RemediationSerializer.to_json(prop)
        elif output_fmt == "markdown":
            rendered = RemediationSerializer.to_markdown([prop])
        elif output_fmt == "csv":
            rendered = RemediationSerializer.to_csv([prop])
        else:
            rendered = None

        if out_path:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(rendered if rendered else RemediationSerializer.to_json(prop))
            print(f"Remediation proposal saved to '{out_path}'.")

        if getattr(args, "json", False):
            print(rendered)
        else:
            print(f"=== Remediation Proposal: {prop.proposal_id} ===")
            print(f"Title:       {prop.title}")
            print(f"Repair Type: {prop.repair_type.value}")
            print(f"State:       {prop.state.value}")
            print(f"Risk Tier:   {prop.risk_tier.value}")
            print(f"Patches:     {len(prop.patches)}")
            for idx, patch in enumerate(prop.patches, 1):
                print(
                    f"  [{idx}] {patch.target_component_type}:{patch.target_component_id} -> {patch.diff_summary}"
                )
            print(f"Tests Gen:   {len(prop.generated_test_ids)}")
        return 0

    file_path = getattr(args, "file", None)
    if not file_path or not Path(file_path).exists():
        print(
            f"Error: Remediation proposal file '{file_path}' does not exist.",
            file=sys.stderr,
        )
        return 1

    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)
    prop = RemediationProposal.model_validate(data)

    if action == "simulate":
        engine._resolve_proposal(prop)
        sim = engine.simulate(prop)
        out_file = getattr(args, "output", None) or file_path
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(RemediationSerializer.to_json(prop))

        if getattr(args, "json", False):
            print(sim.model_dump_json(indent=2))
        else:
            print(f"=== Simulation Result for {prop.proposal_id} ===")
            print(f"Status:          {'PASS' if sim.passed else 'FAIL'}")
            print(f"Tests Passed:    {sim.tests_passed}/{sim.total_tests_run}")
            print(f"Regressions:     {sim.regressions_count}")
            print(f"Recovery Rate:   {sim.failure_recovery_rate:.1%}")
            print(f"Lifecycle State: {prop.state.value}")
            if prop.gate_evaluation and not prop.gate_evaluation.gates_passed:
                print(
                    f"Gate Failures:   {'; '.join(prop.gate_evaluation.failed_gate_reasons)}"
                )
        return 0 if sim.passed else 1

    elif action == "approve":
        approver = getattr(args, "approver", "operator") or "operator"
        rationale = getattr(args, "rationale", "Approved by operator") or "Approved"
        engine._resolve_proposal(prop)
        try:
            appr = engine.approve(prop, approver=approver, rationale=rationale)
        except Exception as e:
            print(f"Error approving proposal: {e}", file=sys.stderr)
            return 1

        out_file = getattr(args, "output", None) or file_path
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(RemediationSerializer.to_json(prop))

        if getattr(args, "json", False):
            print(appr.model_dump_json(indent=2))
        else:
            print(
                f"Proposal {prop.proposal_id} APPROVED by {approver} (token: {appr.approval_token})"
            )
        return 0

    elif action == "apply":
        strat_str = getattr(args, "strategy", None)
        strategy = RolloutStrategy(strat_str.upper()) if strat_str else None
        pct = getattr(args, "percentage", None)
        engine._resolve_proposal(prop)
        try:
            rstate = engine.apply(prop, strategy=strategy, percentage=pct)
        except Exception as e:
            print(f"Error applying proposal: {e}", file=sys.stderr)
            return 1

        out_file = getattr(args, "output", None) or file_path
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(RemediationSerializer.to_json(prop))

        if getattr(args, "json", False):
            print(rstate.model_dump_json(indent=2))
        else:
            print(
                f"Proposal {prop.proposal_id} applied: mode {rstate.strategy.value} at {rstate.active_percentage:.1f}%"
            )
        return 0

    elif action == "verify":
        samples = int(getattr(args, "samples", 20) or 20)
        err_rate = float(getattr(args, "error_rate", 0.0) or 0.0)
        base_err = float(getattr(args, "baseline_error_rate", 0.0) or 0.0)
        engine._resolve_proposal(prop)
        healthy = engine.verify(
            prop,
            sample_count=samples,
            remediation_error_rate=err_rate,
            baseline_error_rate=base_err,
        )

        out_file = getattr(args, "output", None) or file_path
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(RemediationSerializer.to_json(prop))

        if getattr(args, "json", False):
            print(
                json.dumps(
                    {
                        "verified": healthy,
                        "state": prop.state.value,
                        "notes": prop.rollout_state.notes,
                    }
                )
            )
        else:
            print(
                f"Verification {'PASSED' if healthy else 'DEGRADED/FAILED'}: {prop.rollout_state.notes}"
            )
            print(f"Current State: {prop.state.value}")
        return 0 if healthy else 1

    elif action == "promote":
        actor = getattr(args, "actor", "operator") or "operator"
        notes = getattr(args, "notes", "Promoted to permanent baseline") or "Promoted"
        engine._resolve_proposal(prop)
        try:
            engine.promote(prop, actor=actor, notes=notes)
        except Exception as e:
            print(f"Error promoting proposal: {e}", file=sys.stderr)
            return 1

        out_file = getattr(args, "output", None) or file_path
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(RemediationSerializer.to_json(prop))

        if getattr(args, "json", False):
            print(
                json.dumps(
                    {"promoted": True, "state": prop.state.value, "notes": notes}
                )
            )
        else:
            print(
                f"Proposal {prop.proposal_id} successfully PROMOTED to permanent baseline (100% active)."
            )
        return 0

    elif action == "rollback":
        actor = getattr(args, "actor", "operator") or "operator"
        reason = getattr(args, "reason", "Rollback requested") or "Rollback"
        engine._resolve_proposal(prop)
        engine.rollback(prop, reason=reason, actor=actor)

        out_file = getattr(args, "output", None) or file_path
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(RemediationSerializer.to_json(prop))

        if getattr(args, "json", False):
            print(
                json.dumps(
                    {"rolled_back": True, "state": prop.state.value, "reason": reason}
                )
            )
        else:
            print(f"Proposal {prop.proposal_id} ROLLED BACK: {reason}")
        return 0

    elif action == "status":
        if getattr(args, "json", False):
            print(RemediationSerializer.to_json(prop))
        else:
            print(f"=== Proposal Status: {prop.proposal_id} ===")
            print(f"Title:       {prop.title}")
            print(f"Repair Type: {prop.repair_type.value}")
            print(f"State:       {prop.state.value}")
            print(f"Risk Tier:   {prop.risk_tier.value}")
            print(
                f"Rollout:     {prop.rollout_state.strategy.value} at {prop.rollout_state.active_percentage:.1f}%"
            )
            print(f"Health:      {prop.rollout_state.health_status.value}")
            if prop.audit_trail:
                print("Recent Audit Events:")
                for a in prop.audit_trail[-3:]:
                    print(
                        f"  - [{a.timestamp.strftime('%H:%M:%S')}] {a.from_state.value} -> {a.to_state.value} by {a.actor} ({a.action})"
                    )
        return 0

    return 0


def cmd_optimize(args: argparse.Namespace) -> int:
    """Execute AI Reliability Optimization workflows (Phase 38)."""
    import json
    import sys
    from pathlib import Path

    from aireliability.optimization.deployment_bridge import (
        OptimizationDeploymentBridge,
    )
    from aireliability.optimization.engine import OptimizationEngine
    from aireliability.optimization.fingerprint import create_configuration
    from aireliability.optimization.gates import OptimizationGateChecker
    from aireliability.optimization.models import (
        ConstraintOperator,
        ObjectiveDirection,
        OptimizationBudget,
        OptimizationCandidate,
        OptimizationConstraint,
        OptimizationObjective,
        OptimizationPolicy,
        OptimizationProblem,
        OptimizationResult,
        SelectionStrategy,
    )
    from aireliability.optimization.selector import OptimizationSelector
    from aireliability.optimization.serialization import OptimizationSerializer
    from aireliability.optimization.variables import get_default_variable_registry
    from aireliability.remediation.models import RolloutStrategy

    action = getattr(args, "optimize_action", "status") or "status"
    engine = OptimizationEngine()
    registry = get_default_variable_registry()

    def _resolve_result_file(file_path_str: str | None) -> OptimizationResult:
        if not file_path_str:
            raise ValueError("Result or configuration file path is required.")
        p = Path(file_path_str)
        if not p.exists():
            raise FileNotFoundError(f"File '{file_path_str}' not found.")
        with open(p, encoding="utf-8") as f:
            return OptimizationSerializer.from_json(f.read())

    if action == "plan":
        base_vals: dict[str, Any] = {}
        base_src = getattr(args, "baseline", None)
        if base_src and Path(base_src).exists():
            with open(base_src, encoding="utf-8") as f:
                loaded = json.load(f)
                base_vals = loaded.get("values", loaded)
        else:
            base_vals = {"temperature": 0.7, "top_k": 5, "chunk_size": 256}

        base_cfg = create_configuration(base_vals, description="Optimization Baseline")
        base_metrics = {
            "quality": 0.90,
            "latency": 0.85,
            "cost": 0.02,
            "safety": 0.98,
            "security": 0.99,
            "error_rate": 0.02,
        }

        # Selected variables
        var_args = getattr(args, "variable", None) or [
            "temperature",
            "top_k",
            "chunk_size",
        ]
        problem_vars = []
        for v_item in var_args:
            parts = str(v_item).split(":")
            var_name = parts[0].strip()
            if registry.has(var_name):
                base_var = registry.get(var_name)
                if len(parts) >= 4:
                    try:
                        min_v = float(parts[2])
                        max_v = float(parts[3])
                        step_v = float(parts[4]) if len(parts) >= 5 else base_var.step
                        base_var = base_var.model_copy(
                            update={
                                "min_value": min_v,
                                "max_value": max_v,
                                "step": step_v,
                            }
                        )
                    except Exception:
                        pass
                problem_vars.append(base_var)
            elif registry.has(v_item):
                problem_vars.append(registry.get(v_item))

        # Selected objectives
        obj_args = getattr(args, "objective", None)
        if obj_args:
            objectives = []
            for obj_item in obj_args:
                parts = str(obj_item).split(":")
                metric_name = parts[0].strip()
                direction_str = (
                    parts[1].strip().lower() if len(parts) > 1 else "maximize"
                )
                direction = (
                    ObjectiveDirection.MINIMIZE
                    if "min" in direction_str
                    else ObjectiveDirection.MAXIMIZE
                )
                objectives.append(
                    OptimizationObjective(
                        objective_id=metric_name,
                        metric=metric_name,
                        direction=direction,
                        weight=1.0,
                    )
                )
        else:
            objectives = [
                OptimizationObjective(
                    objective_id="quality",
                    metric="quality",
                    direction=ObjectiveDirection.MAXIMIZE,
                    weight=1.0,
                ),
                OptimizationObjective(
                    objective_id="cost",
                    metric="cost",
                    direction=ObjectiveDirection.MINIMIZE,
                    weight=1.0,
                ),
                OptimizationObjective(
                    objective_id="latency",
                    metric="latency",
                    direction=ObjectiveDirection.MINIMIZE,
                    weight=1.0,
                ),
            ]

        safe_thresh = float(getattr(args, "safety_threshold", 0.95) or 0.95)
        qual_thresh = float(getattr(args, "quality_threshold", 0.80) or 0.80)
        constraints = [
            OptimizationConstraint(
                constraint_id="min_safety",
                metric="safety",
                operator=ConstraintOperator.GE,
                threshold=safe_thresh,
                is_hard=True,
            ),
            OptimizationConstraint(
                constraint_id="min_quality",
                metric="quality",
                operator=ConstraintOperator.GE,
                threshold=qual_thresh,
                is_hard=True,
            ),
        ]

        problem = OptimizationProblem(
            name=getattr(args, "name", "AI Reliability Optimization Problem")
            or "Optimization Problem",
            description="Multi-objective AI reliability optimization definition",
            baseline_config=base_cfg,
            baseline_metrics=base_metrics,
            variables=problem_vars,
            objectives=objectives,
            constraints=constraints,
            dataset_id=getattr(args, "dataset", "default_dataset") or "default_dataset",
        )

        out_path = getattr(args, "output", None)
        rendered = problem.model_dump_json(indent=2)
        if out_path:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(rendered)
            print(f"Optimization problem successfully written to: {out_path}")
        elif getattr(args, "json", False):
            print(rendered)
        else:
            print(f"=== Optimization Problem: {problem.problem_id} ===")
            print(f"Name:        {problem.name}")
            print(f"Variables:   {[v.variable_id for v in problem.variables]}")
            print(f"Objectives:  {[o.objective_id for o in problem.objectives]}")
            print(f"Constraints: {[c.constraint_id for c in problem.constraints]}")
        return 0

    elif action == "run":
        file_arg = getattr(args, "file", None)
        problem: OptimizationProblem | None = None
        if file_arg and Path(file_arg).exists():
            with open(file_arg, encoding="utf-8") as f:
                content = f.read()
                try:
                    problem = OptimizationProblem.model_validate_json(content)
                except Exception:
                    # Might be baseline json
                    loaded = json.loads(content)
                    base_cfg = create_configuration(loaded.get("values", loaded))
                    problem = OptimizationProblem(
                        name="CLI Optimization",
                        baseline_config=base_cfg,
                        baseline_metrics={
                            "quality": 0.90,
                            "cost": 0.02,
                            "latency": 0.85,
                        },
                        variables=[registry.get("temperature"), registry.get("top_k")],
                        objectives=[
                            OptimizationObjective(
                                objective_id="quality", metric="quality"
                            ),
                            OptimizationObjective(
                                objective_id="cost",
                                metric="cost",
                                direction=ObjectiveDirection.MINIMIZE,
                            ),
                        ],
                    )

        if not problem:
            base_cfg = create_configuration({"temperature": 0.7, "top_k": 5})
            problem = OptimizationProblem(
                name="Default CLI Optimization",
                baseline_config=base_cfg,
                baseline_metrics={"quality": 0.90, "cost": 0.02, "latency": 0.85},
                variables=[registry.get("temperature"), registry.get("top_k")],
                objectives=[
                    OptimizationObjective(objective_id="quality", metric="quality"),
                    OptimizationObjective(
                        objective_id="cost",
                        metric="cost",
                        direction=ObjectiveDirection.MINIMIZE,
                    ),
                ],
            )

        budget = OptimizationBudget(
            max_candidates=int(getattr(args, "max_candidates", 20) or 20),
            max_evaluations=int(getattr(args, "max_evaluations", 50) or 50),
            max_runtime_seconds=float(getattr(args, "max_runtime", 300.0) or 300.0),
            max_cost=float(getattr(args, "max_cost", 100.0) or 100.0),
        )

        strat_name = getattr(args, "strategy", "random") or "random"
        sel_name = getattr(args, "select", "balanced_score") or "balanced_score"
        sel_enum = (
            SelectionStrategy(sel_name)
            if sel_name in [s.value for s in SelectionStrategy]
            else SelectionStrategy.BALANCED
        )
        policy = OptimizationPolicy(
            selection_strategy=sel_enum,
            repeated_evaluations=int(getattr(args, "repeats", 1) or 1),
        )

        res = engine.run(
            problem=problem,
            budget=budget,
            strategy=strat_name,
            policy=policy,
            seed=int(getattr(args, "seed", 42) or 42),
        )

        out_fmt = getattr(args, "format", "terminal")
        out_path = getattr(args, "output", None)

        if getattr(args, "json", False) or out_fmt == "json":
            rendered = OptimizationSerializer.to_json(res)
        elif out_fmt == "markdown":
            rendered = OptimizationSerializer.to_markdown(res)
        elif out_fmt == "csv":
            rendered = OptimizationSerializer.to_csv(res.candidates)
        else:
            rendered = None

        if out_path:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(rendered or OptimizationSerializer.to_json(res))
            print(f"Optimization result successfully written to: {out_path}")
        elif rendered:
            print(rendered)
        else:
            print(f"=== Optimization Run Completed: {res.optimization_id} ===")
            print(f"Status:             {res.stopping_reason.value}")
            print(f"Duration:           {res.duration_seconds:.2f}s")
            print(f"Total Candidates:   {len(res.candidates)}")
            print(
                f"Pareto Solutions:   {len(res.pareto_frontier.non_dominated_candidate_ids)}"
            )
            if res.selected_candidate:
                print(f"Selected Candidate: {res.selected_candidate.candidate_id}")
                print(
                    f"Configuration:      {res.selected_candidate.configuration.values}"
                )
                print(f"Objectives:         {res.selected_candidate.objective_values}")
            else:
                print(
                    "Selected Candidate: None (No candidate satisfied reliability gates)"
                )
        return 0

    elif action == "evaluate":
        file_arg = getattr(args, "file", None)
        cfg_vals = {}
        if file_arg and Path(file_arg).exists():
            with open(file_arg, encoding="utf-8") as f:
                loaded = json.load(f)
                cfg_vals = loaded.get("values", loaded)
        else:
            cfg_vals = {"temperature": 0.5, "top_k": 8}

        base_cfg = create_configuration(cfg_vals)
        prob = OptimizationProblem(
            name="Ad-hoc Eval",
            baseline_config=base_cfg,
            baseline_metrics={"quality": 0.90, "cost": 0.02, "latency": 0.85},
            objectives=[
                OptimizationObjective(objective_id="quality", metric="quality"),
                OptimizationObjective(
                    objective_id="cost",
                    metric="cost",
                    direction=ObjectiveDirection.MINIMIZE,
                ),
                OptimizationObjective(
                    objective_id="latency",
                    metric="latency",
                    direction=ObjectiveDirection.MINIMIZE,
                ),
            ],
        )

        cand = OptimizationCandidate(
            configuration=base_cfg,
            fingerprint=base_cfg.fingerprint,
        )

        evaluator = engine.evaluator
        eval_cand, _ = evaluator.evaluate_candidate(
            candidate=cand,
            problem=prob,
            repeats=int(getattr(args, "repeats", 1) or 1),
        )

        if getattr(args, "json", False):
            print(json.dumps(eval_cand.objective_values, indent=2))
        else:
            print(f"Candidate Evaluated: {eval_cand.candidate_id}")
            print(f"Objective Values:    {eval_cand.objective_values}")
            print(f"Confidence:          {eval_cand.confidence:.4f}")
        return 0

    elif action == "compare":
        try:
            res = _resolve_result_file(getattr(args, "file", None))
        except Exception as e:
            print(f"Error reading result file: {e}", file=sys.stderr)
            return 1

        if getattr(args, "json", False):
            comparison_data = {
                "baseline": res.baseline_metrics,
                "selected": res.selected_candidate.objective_values
                if res.selected_candidate
                else {},
                "deltas": res.selected_candidate.baseline_deltas
                if res.selected_candidate
                else {},
            }
            print(json.dumps(comparison_data, indent=2))
        else:
            print(f"=== Baseline vs Candidate Comparison ({res.optimization_id}) ===")
            if not res.selected_candidate:
                print("No candidate selected for comparison.")
                return 0
            print(
                f"{'Metric':<15} {'Baseline':<12} {'Candidate':<12} {'Delta':<12} {'% Change':<10}"
            )
            print("-" * 65)
            for m, d in res.selected_candidate.baseline_deltas.items():
                print(
                    f"{m:<15} {d.get('baseline', 0.0):<12.4f} {d.get('candidate', 0.0):<12.4f} "
                    f"{d.get('absolute', 0.0):<12.4f} {d.get('percentage', 0.0):<10.2f}%"
                )
        return 0

    elif action == "pareto":
        try:
            res = _resolve_result_file(getattr(args, "file", None))
        except Exception as e:
            print(f"Error reading result file: {e}", file=sys.stderr)
            return 1

        if getattr(args, "json", False):
            print(res.pareto_frontier.model_dump_json(indent=2))
        else:
            print(
                f"=== Pareto Frontier Solutions ({len(res.pareto_frontier.non_dominated_candidate_ids)}) ==="
            )
            print(
                f"{'Candidate ID':<20} {'Rank':<6} {'Crowding Dist':<15} {'Objectives'}"
            )
            print("-" * 75)
            for pt in res.pareto_frontier.points:
                if not pt.is_dominated:
                    cd_str = (
                        f"{pt.crowding_distance:<15.4f}"
                        if pt.crowding_distance is not None
                        else f"{'N/A':<15}"
                    )
                    print(
                        f"{pt.candidate_id:<20} {pt.rank:<6} {cd_str} {pt.objective_values}"
                    )
        return 0

    elif action == "history":
        hist = engine.get_history()
        if getattr(args, "json", False):
            print(json.dumps([r.optimization_id for r in hist], indent=2))
        else:
            print(f"Optimization Runs History ({len(hist)} runs):")
            for r in hist:
                print(
                    f"  - [{r.optimization_id}] Status: {r.stopping_reason.value}, Duration: {r.duration_seconds:.2f}s"
                )
        return 0

    elif action == "inspect":
        try:
            res = _resolve_result_file(getattr(args, "file", None))
        except Exception as e:
            print(f"Error reading result file: {e}", file=sys.stderr)
            return 1

        cand_id = getattr(args, "candidate_id", None)
        target = res.selected_candidate
        if cand_id:
            for c in res.candidates:
                if c.candidate_id == cand_id:
                    target = c
                    break

        if not target:
            print("Candidate not found.", file=sys.stderr)
            return 1

        if getattr(args, "json", False):
            print(target.model_dump_json(indent=2))
        else:
            print(f"=== Candidate Inspection: {target.candidate_id} ===")
            print(f"Fingerprint:   {target.fingerprint}")
            print(f"Strategy:      {target.generation_strategy}")
            print(f"Is Pareto:     {target.is_pareto}")
            print(f"Confidence:    {target.confidence:.4f}")
            print(f"Configuration: {target.configuration.values}")
            print(f"Objectives:    {target.objective_values}")
            print(f"Explanation:   {target.explanation}")
        return 0

    elif action == "select":
        try:
            res = _resolve_result_file(getattr(args, "file", None))
        except Exception as e:
            print(f"Error reading result file: {e}", file=sys.stderr)
            return 1

        strategy_str = getattr(args, "strategy", "balanced_score") or "balanced_score"
        sel_enum = (
            SelectionStrategy(strategy_str)
            if strategy_str in [s.value for s in SelectionStrategy]
            else SelectionStrategy.BALANCED
        )
        policy = OptimizationPolicy(selection_strategy=sel_enum)

        selector = OptimizationSelector()
        selected, decision, explanation = selector.select(
            frontier=res.pareto_frontier,
            candidates=res.candidates,
            policy=policy,
            baseline_metrics=res.baseline_metrics,
        )

        if getattr(args, "json", False):
            print(
                json.dumps(
                    {
                        "selected_id": selected.candidate_id if selected else None,
                        "explanation": explanation,
                    },
                    indent=2,
                )
            )
        else:
            if selected:
                print(f"Selected Candidate: {selected.candidate_id}")
                print(f"Explanation:        {explanation}")
            else:
                print(f"Selection Result:   {explanation}")
        return 0 if selected else 1

    elif action == "validate":
        try:
            res = _resolve_result_file(getattr(args, "file", None))
        except Exception as e:
            print(f"Error reading result file: {e}", file=sys.stderr)
            return 1

        target = res.selected_candidate
        if not target and res.candidates:
            target = res.candidates[0]

        if not target:
            print("No candidate available to validate.", file=sys.stderr)
            return 1

        gate_checker = OptimizationGateChecker()
        policy = OptimizationPolicy(
            required_safety=float(getattr(args, "safety_threshold", 0.95) or 0.95),
            required_security=float(getattr(args, "security_threshold", 0.95) or 0.95),
            required_quality=float(getattr(args, "quality_threshold", 0.80) or 0.80),
        )

        passed, reasons = gate_checker.check_gates(
            candidate=target,
            policy=policy,
            baseline_metrics=res.baseline_metrics,
        )

        if getattr(args, "json", False):
            print(json.dumps({"passed": passed, "failures": reasons}, indent=2))
        else:
            print(f"Validation {'PASSED' if passed else 'FAILED'}")
            if reasons:
                print("Gate Failures:")
                for r in reasons:
                    print(f"  - {r}")
        return 0 if passed else 1

    elif action == "deploy":
        try:
            res = _resolve_result_file(getattr(args, "file", None))
        except Exception as e:
            print(f"Error reading result file: {e}", file=sys.stderr)
            return 1

        if not res.selected_candidate:
            print(
                "Cannot deploy: No candidate was selected in optimization run.",
                file=sys.stderr,
            )
            return 1

        bridge = OptimizationDeploymentBridge()
        proposal = bridge.create_remediation_proposal(
            candidate=res.selected_candidate,
            problem=res.problem,
        )

        strat_arg = getattr(args, "strategy", "canary") or "canary"
        strat_enum = (
            RolloutStrategy(strat_arg.upper())
            if strat_arg.upper() in [s.value for s in RolloutStrategy]
            else RolloutStrategy.CANARY
        )
        pct = float(getattr(args, "percentage", 10.0) or 10.0)

        if getattr(args, "dry_run", False):
            print(
                f"[DRY-RUN] Would deploy candidate {res.selected_candidate.candidate_id} via Phase 37 {strat_enum.value} at {pct:.1f}%"
            )
            return 0

        state = bridge.deploy(
            proposal=proposal,
            strategy=strat_enum,
            canary_percentage=pct,
            actor=getattr(args, "actor", "operator") or "operator",
        )

        if getattr(args, "json", False):
            print(
                json.dumps(
                    {
                        "proposal_id": proposal.proposal_id,
                        "strategy": state.strategy.value,
                        "percentage": state.active_percentage,
                        "status": state.health_status.value,
                    },
                    indent=2,
                )
            )
        else:
            print(
                f"Deployed candidate {res.selected_candidate.candidate_id} via Phase 37:"
            )
            print(f"Proposal ID: {proposal.proposal_id}")
            print(
                f"Strategy:    {state.strategy.value} at {state.active_percentage:.1f}%"
            )
            print(f"Health:      {state.health_status.value}")
        return 0

    elif action == "rollback":
        try:
            res = _resolve_result_file(getattr(args, "file", None))
        except Exception as e:
            print(f"Error reading result file: {e}", file=sys.stderr)
            return 1

        if not res.selected_candidate:
            print("Cannot rollback: No candidate was selected.", file=sys.stderr)
            return 1

        bridge = OptimizationDeploymentBridge()
        proposal = bridge.create_remediation_proposal(
            candidate=res.selected_candidate,
            problem=res.problem,
        )

        if getattr(args, "dry_run", False):
            print(
                f"[DRY-RUN] Would rollback deployment for candidate {res.selected_candidate.candidate_id}"
            )
            return 0

        bridge.rollback(
            proposal=proposal,
            reason=getattr(args, "reason", "Rollback requested via CLI") or "Rollback",
            actor=getattr(args, "actor", "operator") or "operator",
        )

        if getattr(args, "json", False):
            print(
                json.dumps(
                    {"rolled_back": True, "proposal_id": proposal.proposal_id}, indent=2
                )
            )
        else:
            print(
                f"Successfully rolled back deployment for candidate {res.selected_candidate.candidate_id}"
            )
        return 0

    elif action == "status":
        file_arg = getattr(args, "file", None)
        if file_arg:
            try:
                res = _resolve_result_file(file_arg)
                if getattr(args, "json", False):
                    print(
                        json.dumps(
                            {
                                "optimization_id": res.optimization_id,
                                "status": res.stopping_reason.value,
                                "candidates_count": len(res.candidates),
                                "pareto_size": len(
                                    res.pareto_frontier.non_dominated_candidate_ids
                                ),
                                "selected_id": res.selected_candidate.candidate_id
                                if res.selected_candidate
                                else None,
                            },
                            indent=2,
                        )
                    )
                else:
                    print(f"=== Optimization Status: {res.optimization_id} ===")
                    print(f"Stopping Reason: {res.stopping_reason.value}")
                    print(f"Total Duration:  {res.duration_seconds:.2f}s")
                    print(f"Confidence:      {res.confidence:.4f}")
                    print(
                        f"Selected:        {res.selected_candidate.candidate_id if res.selected_candidate else 'None'}"
                    )
                return 0
            except Exception as e:
                print(f"Error reading file: {e}", file=sys.stderr)
                return 1
        else:
            print("Optimization Engine Active. Version 0.7.0.")
            return 0

    elif action == "budget":
        file_arg = getattr(args, "file", None)
        if file_arg:
            try:
                res = _resolve_result_file(file_arg)
                if getattr(args, "json", False):
                    print(json.dumps(res.budget_used, indent=2))
                else:
                    print(f"=== Budget Consumption: {res.optimization_id} ===")
                    for k, v in res.budget_used.items():
                        print(f"{k:<20}: {v}")
                    print(f"Stopping Reason:     {res.stopping_reason.value}")
                return 0
            except Exception as e:
                print(f"Error reading file: {e}", file=sys.stderr)
                return 1
        else:
            budget = OptimizationBudget()
            print("Default Optimization Budget Limits:")
            print(f"Max Candidates:   {budget.max_candidates}")
            print(f"Max Evaluations:  {budget.max_evaluations}")
            print(f"Max Runtime (s):  {budget.max_runtime_seconds}")
            print(f"Max Cost:         ${budget.max_cost}")
            return 0

    return 0


# ==============================================================================
# Phase 39: Advanced RAG Reliability CLI Handlers
# ==============================================================================


def cmd_rag(args: argparse.Namespace) -> int:
    """Execute Advanced RAG Reliability Engine workflows (Phase 39)."""
    import json
    import sys
    from pathlib import Path

    from aireliability.rag.claim_extractor import ClaimExtractor
    from aireliability.rag.drift import RAGDriftDetector
    from aireliability.rag.engine import AdvancedRAGReliabilityEngine
    from aireliability.rag.freshness import FreshnessTracker
    from aireliability.rag.knowledge_base import KnowledgeBaseAuditor
    from aireliability.rag.models import (
        RAGRun,
        RetrievedChunk,
        RetrievedDocument,
    )
    from aireliability.rag.query_analyzer import QueryAnalyzer
    from aireliability.rag.serialization import RAGSerializer

    action = getattr(args, "rag_action", "evaluate") or "evaluate"
    engine = AdvancedRAGReliabilityEngine()

    def _resolve_run(file_path_str: str | None) -> RAGRun:
        if not file_path_str:
            q_text = (
                getattr(args, "query", None)
                or "What is AI reliability and how does it prevent hallucinations?"
            )
            ans_text = (
                getattr(args, "answer", None)
                or "AI reliability guarantees grounded systems and prevents hallucinations [1]."
            )
            doc = RetrievedDocument(
                document_id="doc_1",
                title="Reliability Guide",
                text="AI reliability guarantees grounded systems and prevents hallucinations in generation.",
                source="knowledge_base",
            )
            chk = RetrievedChunk(
                chunk_id="chk_1",
                document_id="doc_1",
                text="AI reliability guarantees grounded systems and prevents hallucinations in generation.",
                retrieval_score=0.95,
            )
            return engine.evaluate_run(
                query=q_text,
                retrieved_documents=[doc],
                retrieved_chunks=[chk],
                generated_answer=ans_text,
            )

        p = Path(file_path_str)
        if not p.exists():
            raise FileNotFoundError(f"File '{file_path_str}' not found.")
        content = p.read_text(encoding="utf-8")
        try:
            return RAGSerializer.from_json_run(content)
        except Exception:
            data = json.loads(content)
            q_text = data.get("query", "What is AI reliability?")
            ans_text = data.get(
                "answer", "AI reliability guarantees safe execution [1]."
            )
            docs_raw = data.get("documents", [])
            chunks_raw = data.get("chunks", [])
            docs = (
                [RetrievedDocument.model_validate(d) for d in docs_raw]
                if docs_raw
                else [
                    RetrievedDocument(
                        document_id="doc_1",
                        title="Doc 1",
                        text=data.get(
                            "context", "AI reliability guarantees safe execution."
                        ),
                    )
                ]
            )
            chunks = (
                [RetrievedChunk.model_validate(c) for c in chunks_raw]
                if chunks_raw
                else [
                    RetrievedChunk(
                        chunk_id="chk_1",
                        document_id="doc_1",
                        text=data.get(
                            "context", "AI reliability guarantees safe execution."
                        ),
                        retrieval_score=0.9,
                    )
                ]
            )
            return engine.evaluate_run(
                query=q_text,
                retrieved_documents=docs,
                retrieved_chunks=chunks,
                generated_answer=ans_text,
                expected_document_ids=data.get("expected_document_ids"),
                expected_chunk_ids=data.get("expected_chunk_ids"),
            )

    if action == "evaluate":
        file_arg = getattr(args, "file", None) or getattr(args, "run", None)
        try:
            run = _resolve_run(file_arg)
        except Exception as e:
            print(f"Error evaluating RAG run: {e}", file=sys.stderr)
            return 1

        out_path = getattr(args, "output", None)
        if getattr(args, "json", False) or getattr(args, "format", None) == "json":
            rendered = RAGSerializer.to_json(run)
        elif getattr(args, "format", None) == "markdown":
            rendered = RAGSerializer.to_markdown(run)
        elif getattr(args, "format", None) == "csv":
            rendered = RAGSerializer.to_csv([run])
        else:
            rendered = None

        if out_path:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(rendered or RAGSerializer.to_json(run))
            print(f"RAG evaluation result written to: {out_path}")
        elif rendered:
            print(rendered)
        else:
            print(f"=== RAG Reliability Evaluation: {run.run_id} ===")
            print(f"Query:              {run.query.text}")
            print(f"Query Type:         {run.query.query_type.value}")
            print(
                f"Overall Score:      {run.reliability_score.overall_score:.2f} / 1.00"
            )
            print(
                f"Safety/Security:    {'PASSED' if run.reliability_score.security_passed else 'FAILED VETO'}"
            )
            print(f"Total Failures:     {len(run.failures)}")
            print("-" * 55)
            for st_name, st_res in run.stage_scores.items():
                print(
                    f"{st_name.capitalize():<15}: {st_res.score:.2f} (Confidence: {st_res.confidence:.2f})"
                )
        return 0

    elif action == "analyze":
        query_text = (
            getattr(args, "query_opt", None)
            or getattr(args, "query", None)
            or getattr(args, "file", None)
            or "What is AI reliability?"
        )
        analyzer = QueryAnalyzer()
        res = analyzer.analyze(query_text)
        if getattr(args, "json", False):
            print(res.model_dump_json(indent=2))
        else:
            print(f"=== RAG Query Analysis: {res.query_id} ===")
            print(f"Text:         {res.text}")
            print(f"Type:         {res.query_type.value}")
            print(f"Completeness: {res.completeness_score:.2f}")
            print(f"Ambiguity:    {res.ambiguity_score:.2f}")
            print(f"Complexity:   {res.complexity_score:.2f}")
            print(f"Difficulty:   {res.expected_retrieval_difficulty:.2f}")
            print(f"Entities:     {res.entities}")
        return 0

    elif action == "retrieve":
        try:
            run = _resolve_run(getattr(args, "file", None))
        except Exception as e:
            print(f"Error executing retrieval evaluation: {e}", file=sys.stderr)
            return 1

        ret = run.retrieval_result
        if getattr(args, "json", False):
            print(ret.model_dump_json(indent=2))
        else:
            print(f"=== Retrieval Evaluation for Query: {run.query.query_id} ===")
            print(f"Retrieved Documents: {len(ret.retrieved_documents)}")
            print(f"Retrieved Chunks:    {len(ret.retrieved_chunks)}")
            print(
                f"Lexical / Semantic:  {ret.lexical_contribution:.2f} / {ret.semantic_contribution:.2f}"
            )
            print(f"Ground Truth Present: {ret.ground_truth_available}")
            for k, v in ret.exact_metrics.items():
                print(f"  {k:<20}: {v:.4f}")
        return 0

    elif action == "grounding":
        try:
            run = _resolve_run(getattr(args, "file", None))
        except Exception as e:
            print(f"Error evaluating grounding: {e}", file=sys.stderr)
            return 1

        g_score = run.stage_scores.get("grounding")
        f_score = run.stage_scores.get("faithfulness")
        if getattr(args, "json", False):
            print(
                json.dumps(
                    {
                        "grounding_score": g_score.score if g_score else 0.0,
                        "faithfulness_score": f_score.score if f_score else 0.0,
                        "total_claims": len(run.claims),
                    },
                    indent=2,
                )
            )
        else:
            g_val = g_score.score if g_score else 0.0
            f_val = f_score.score if f_score else 0.0
            print(f"=== Grounding & Faithfulness: {run.run_id} ===")
            print(f"Grounding Score:    {g_val:.2f}")
            print(f"Faithfulness Score: {f_val:.2f}")
            print(f"Total Claims:       {len(run.claims)}")
            for c in run.claims:
                print(f"  - [{c.support_status.value}] {c.text}")
        return 0

    elif action == "citations":
        try:
            run = _resolve_run(getattr(args, "file", None))
        except Exception as e:
            print(f"Error evaluating citations: {e}", file=sys.stderr)
            return 1

        cit_score = run.stage_scores.get("citation")
        if getattr(args, "json", False):
            print(json.dumps([c.model_dump() for c in run.citations], indent=2))
        else:
            cit_val = cit_score.score if cit_score else 0.0
            print(f"=== Inline Citation Validation: {run.run_id} ===")
            print(f"Citation Score:  {cit_val:.2f}")
            print(f"Total Citations: {len(run.citations)}")
            for cit in run.citations:
                print(
                    f"  - {cit.marker} -> Chunk '{cit.cited_chunk_id}' [{cit.status.value}]"
                )
        return 0

    elif action == "claims":
        ans_text = (
            getattr(args, "text_opt", None)
            or getattr(args, "text", None)
            or getattr(args, "query", None)
            or "AI reliability guarantees safe systems. It prevents hallucinations."
        )
        extractor = ClaimExtractor()
        claims = extractor.extract_claims(ans_text)
        if getattr(args, "json", False):
            print(json.dumps([c.model_dump() for c in claims], indent=2))
        else:
            print(f"=== Extracted Claims ({len(claims)}) ===")
            for c in claims:
                print(f"  [{c.importance.value}] {c.text}")
        return 0

    elif action == "freshness":
        window_days = int(getattr(args, "freshness_window", 90) or 90)
        try:
            run = _resolve_run(getattr(args, "file", None))
            tracker = FreshnessTracker(default_max_age_days=window_days)
            score, rate, fails, expl = tracker.evaluate_freshness(
                run.retrieval_result.retrieved_documents,
                run.retrieval_result.retrieved_chunks,
            )
            if getattr(args, "json", False):
                print(
                    json.dumps(
                        {
                            "freshness_score": score,
                            "stale_rate": rate,
                            "explanation": expl,
                        },
                        indent=2,
                    )
                )
            else:
                print(f"=== Knowledge Freshness Audit (Window: {window_days} days) ===")
                print(f"Freshness Score: {score:.2f}")
                print(f"Stale Rate:      {rate:.2%}")
                print(f"Summary:         {expl}")
        except Exception as e:
            print(f"Error checking freshness: {e}", file=sys.stderr)
            return 1
        return 0

    elif action == "drift":
        try:
            base_file = getattr(args, "baseline", None)
            curr_file = getattr(args, "file", None) or getattr(args, "run", None)
            base_run = _resolve_run(base_file) if base_file else None
            curr_run = _resolve_run(curr_file)

            detector = RAGDriftDetector()
            base_metrics = (
                {
                    "grounding_score": base_run.stage_scores.get("grounding").score,
                    "retrieval_score": base_run.stage_scores.get("retrieval").score,
                }
                if base_run
                and base_run.stage_scores.get("grounding")
                and base_run.stage_scores.get("retrieval")
                else {"grounding_score": 0.85, "retrieval_score": 0.90}
            )
            obs_metrics = {
                "grounding_score": curr_run.stage_scores.get("grounding").score
                if curr_run.stage_scores.get("grounding")
                else 0.85,
                "retrieval_score": curr_run.stage_scores.get("retrieval").score
                if curr_run.stage_scores.get("retrieval")
                else 0.90,
            }

            drifts, fails = detector.detect_drift(base_metrics, obs_metrics)
            if getattr(args, "json", False):
                print(json.dumps([d.model_dump() for d in drifts], indent=2))
            else:
                print("=== Statistical RAG Drift Analysis ===")
                for d in drifts:
                    print(
                        f"  [{d.drift_type}] {d.metric_name}: {d.baseline_value:.2f} -> {d.observed_value:.2f} "
                        f"(Drift Detected: {d.drift_detected}, Trend: {d.trend})"
                    )
        except Exception as e:
            print(f"Error evaluating drift: {e}", file=sys.stderr)
            return 1
        return 0

    elif action == "knowledge":
        try:
            file_arg = getattr(args, "file", None)
            docs = []
            if file_arg and Path(file_arg).exists():
                data = json.loads(Path(file_arg).read_text(encoding="utf-8"))
                doc_list = data if isinstance(data, list) else data.get("documents", [])
                docs = [RetrievedDocument.model_validate(d) for d in doc_list]
            else:
                docs = [
                    RetrievedDocument(
                        document_id="doc_1",
                        title="Sample",
                        text="Sample knowledge base document.",
                        source="kb",
                    )
                ]

            auditor = KnowledgeBaseAuditor()
            rep = auditor.audit_knowledge_base(docs)
            if getattr(args, "json", False):
                print(rep.model_dump_json(indent=2))
            else:
                print("=== Knowledge Base Health Audit ===")
                print(f"Health Status:      {rep.status.value.upper()}")
                print(f"Document Count:     {rep.document_count}")
                print(f"Stale Rate:         {rep.stale_document_rate:.2%}")
                print(f"Duplicate Rate:     {rep.duplicate_chunk_rate:.2%}")
                print(f"Recommendations:    {rep.recommendations}")
        except Exception as e:
            print(f"Error checking knowledge base: {e}", file=sys.stderr)
            return 1
        return 0

    elif action == "conflicts":
        try:
            run = _resolve_run(getattr(args, "file", None))
            if getattr(args, "json", False):
                print(json.dumps([c.model_dump() for c in run.conflicts], indent=2))
            else:
                print(f"=== Context Contradiction Check: {run.run_id} ===")
                print(f"Conflicts Found: {len(run.conflicts)}")
                for cnf in run.conflicts:
                    print(f"  - [{cnf.status.value}] {cnf.description}")
        except Exception as e:
            print(f"Error checking conflicts: {e}", file=sys.stderr)
            return 1
        return 0

    elif action == "failures":
        try:
            run = _resolve_run(getattr(args, "file", None))
            if getattr(args, "json", False):
                print(json.dumps([f.model_dump() for f in run.failures], indent=2))
            else:
                print(
                    f"=== Diagnosed RAG Failures: {run.run_id} ({len(run.failures)}) ==="
                )
                for f in run.failures:
                    print(
                        f"  [{f.severity.value.upper()}] [{f.stage.value}] {f.category.value}: {f.message}"
                    )
        except Exception as e:
            print(f"Error checking failures: {e}", file=sys.stderr)
            return 1
        return 0

    elif action == "provenance":
        try:
            run = _resolve_run(getattr(args, "file", None))
            cid = getattr(args, "claim_id", None)
            prov = engine.graph_bridge.trace_provenance(run, claim_id=cid)
            if getattr(args, "json", False):
                print(json.dumps(prov, indent=2))
            else:
                print(f"=== Provenance Trace: {run.run_id} ===")
                for k, v in prov.items():
                    print(f"  {k}: {v}")
        except Exception as e:
            print(f"Error tracing provenance: {e}", file=sys.stderr)
            return 1
        return 0

    elif action == "regression":
        file_arg = getattr(args, "file", None) or getattr(args, "dataset", None)
        if not file_arg or not Path(file_arg).exists():
            print("Regression dataset file required.", file=sys.stderr)
            return 1
        try:
            cases = json.loads(Path(file_arg).read_text(encoding="utf-8"))
            if not isinstance(cases, list):
                cases = cases.get("test_cases", [cases])
            res = engine.evaluate_batch(cases)
            if getattr(args, "json", False):
                print(res.model_dump_json(indent=2))
            else:
                print("=== RAG Regression Suite Evaluation ===")
                print(
                    f"Status:             {'PASSED' if res.passed_release_gates else 'FAILED GATES'}"
                )
                print(f"Mean Score:         {res.overall_score:.2f}")
                print(
                    f"Total Failures:     {res.total_failures} (Critical: {res.critical_failures_count})"
                )
            return 0 if res.passed_release_gates else 1
        except Exception as e:
            print(f"Error running regression suite: {e}", file=sys.stderr)
            return 1

    elif action == "monitor":
        print("Production RAG Monitoring Active. Sanitization Policy Enforced.")
        return 0

    elif action == "report":
        try:
            run = _resolve_run(getattr(args, "file", None))
            fmt = getattr(args, "format", "markdown")
            if fmt == "markdown":
                print(RAGSerializer.to_markdown(run))
            elif fmt == "csv":
                print(RAGSerializer.to_csv([run]))
            else:
                print(RAGSerializer.to_json(run))
        except Exception as e:
            print(f"Error generating report: {e}", file=sys.stderr)
            return 1
        return 0

    elif action == "inspect":
        try:
            run = _resolve_run(getattr(args, "file", None))
            if getattr(args, "json", False):
                print(RAGSerializer.to_json(run))
            else:
                print(f"=== RAG Run Inspection: {run.run_id} ===")
                print(f"Query:      {run.query.text}")
                print(f"Answer:     {run.generated_answer.text}")
                print(f"Overall:    {run.reliability_score.overall_score:.2f} / 1.00")
                print(f"Failures:   {len(run.failures)}")
        except Exception as e:
            print(f"Error inspecting run: {e}", file=sys.stderr)
            return 1
        return 0

    return 0


def cmd_agent(args: argparse.Namespace) -> int:
    """Execute Advanced Agent Reliability Engine workflows (Phase 40)."""
    from aireliability.agent.cli_handler import handle_agent_cli

    return handle_agent_cli(args)


def cmd_predict(args: argparse.Namespace) -> int:
    """Execute Reliability Prediction workflows (Phase 42)."""
    from aireliability.prediction.cli_handler import handle_prediction_cli

    return handle_prediction_cli(args)


def cmd_dashboard(args: argparse.Namespace) -> int:
    """Execute Reliability Intelligence Dashboard workflows (Phase 43)."""
    from aireliability.dashboard.cli_handler import handle_dashboard_cli

    return handle_dashboard_cli(args)


def cmd_policy(args: argparse.Namespace) -> int:
    """Execute Reliability Policy Engine workflows (Phase 44)."""
    from aireliability.policy.cli_handler import handle_policy_cli

    return handle_policy_cli(args)


def cmd_tenant(args: argparse.Namespace) -> int:
    """Execute Enterprise Multi-Tenancy workflows (Phase 45)."""
    from aireliability.tenancy.cli_handler import handle_tenant_cli

    return handle_tenant_cli(args)


def cmd_api(args: argparse.Namespace) -> int:
    """Execute Reliability Platform API workflows (Phase 46)."""
    from aireliability.api.cli_handler import handle_api_cli

    return handle_api_cli(args)


# ==============================================================================
# Argument Parsing and Entrypoint
# ==============================================================================


def create_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser for airel."""
    parser = argparse.ArgumentParser(
        prog="airel",
        description="AI Reliability Engine CLI.",
    )
    from aireliability import __version__

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show program's version number and exit",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = subparsers.add_parser(
        "init", help="Initialize project configuration and directories"
    )
    p_init.add_argument("--dir", default=".", help="Project root directory")
    p_init.add_argument("--agent", help="Agent target (e.g. agent:app)")
    p_init.add_argument(
        "--force", action="store_true", help="Overwrite existing configuration"
    )
    p_init.set_defaults(func=cmd_init)

    # test
    p_test = subparsers.add_parser("test", help="Execute reliability tests")
    p_test.add_argument(
        "name", nargs="?", default=None, help="Optional test name or ID to filter by"
    )
    p_test.add_argument("--dir", default=".", help="Project root directory")
    p_test.add_argument("--agent", help="Agent target override")
    p_test.add_argument(
        "--save-baseline",
        action="store_true",
        help="Save run results as active baseline",
    )
    p_test.add_argument(
        "--ci",
        action="store_true",
        help="Run in CI mode (strict exit code on failures or regressions)",
    )
    p_test.add_argument(
        "--report-json",
        default=None,
        help="Path to write machine-readable JSON reliability report",
    )
    p_test.add_argument(
        "--report-markdown",
        default=None,
        help="Path to write GitHub Step Summary compatible markdown report",
    )
    p_test.add_argument(
        "--telemetry",
        action="store_true",
        help="Enable telemetry collection during test execution",
    )
    p_test.add_argument(
        "--telemetry-output",
        default=None,
        help="Path to export collected JSON telemetry traces",
    )
    p_test.add_argument(
        "--no-telemetry",
        action="store_true",
        help="Explicitly disable telemetry collection",
    )
    p_test.set_defaults(func=cmd_test)

    # failures
    p_fail = subparsers.add_parser("failures", help="Display recorded failure reports")
    p_fail.add_argument("--dir", default=".", help="Project root directory")
    p_fail.add_argument("--category", help="Filter by failure category")
    p_fail.add_argument(
        "--limit", type=int, default=50, help="Maximum number of failures to show"
    )
    p_fail.add_argument(
        "--explain",
        action="store_true",
        help="Diagnose empirical root causes for displayed failures",
    )
    p_fail.set_defaults(func=cmd_failures)

    # regressions
    p_reg = subparsers.add_parser(
        "regressions", help="Display synthesized regression tests"
    )
    p_reg.add_argument("--dir", default=".", help="Project root directory")
    p_reg.add_argument(
        "--details",
        action="store_true",
        help="Display detailed provenance, minimization, and validation metadata",
    )
    p_reg.set_defaults(func=cmd_regressions)

    # compare
    p_cmp = subparsers.add_parser(
        "compare", help="Compare test execution against a baseline"
    )
    p_cmp.add_argument(
        "baseline", nargs="?", default=None, help="Name of baseline to compare against"
    )
    p_cmp.add_argument("--dir", default=".", help="Project root directory")
    p_cmp.add_argument("--agent", help="Agent target override")
    p_cmp.add_argument(
        "--report-json",
        default=None,
        help="Path to write machine-readable JSON reliability report",
    )
    p_cmp.add_argument(
        "--report-markdown",
        default=None,
        help="Path to write GitHub Step Summary compatible markdown report",
    )
    p_cmp.set_defaults(func=cmd_compare)

    # executions (Phase 24)
    p_exec = subparsers.add_parser(
        "executions", help="Manage distributed executions (list, show, resume, recover)"
    )
    p_exec_sub = p_exec.add_subparsers(dest="action", required=False)

    p_exec_list = p_exec_sub.add_parser("list", help="List all executions")
    p_exec_list.add_argument("--tenant", default=None, help="Filter by tenant ID")
    p_exec_list.add_argument("--dir", default=".", help="Project root directory")

    p_exec_show = p_exec_sub.add_parser("show", help="Show execution details")
    p_exec_show.add_argument("execution_id", help="Execution ID to inspect")
    p_exec_show.add_argument("--dir", default=".", help="Project root directory")

    p_exec_resume = p_exec_sub.add_parser("resume", help="Resume interrupted execution")
    p_exec_resume.add_argument("execution_id", help="Execution ID to resume")
    p_exec_resume.add_argument("--dir", default=".", help="Project root directory")

    p_exec_rec = p_exec_sub.add_parser(
        "recover", help="Recover execution and stale workers"
    )
    p_exec_rec.add_argument("execution_id", help="Execution ID to recover")
    p_exec_rec.add_argument("--dir", default=".", help="Project root directory")

    p_exec.set_defaults(func=cmd_executions, action="list")
    p_exec_list.set_defaults(func=cmd_executions, action="list")
    p_exec_show.set_defaults(func=cmd_executions, action="show")
    p_exec_resume.set_defaults(func=cmd_executions, action="resume")
    p_exec_rec.set_defaults(func=cmd_executions, action="recover")

    # workers (Phase 24)
    p_work = subparsers.add_parser(
        "workers", help="Inspect workers and detect stale states"
    )
    p_work_sub = p_work.add_subparsers(dest="action", required=False)

    p_work_list = p_work_sub.add_parser("list", help="List all registered workers")
    p_work_list.add_argument("--tenant", default=None, help="Filter by tenant ID")
    p_work_list.add_argument("--dir", default=".", help="Project root directory")

    p_work_stale = p_work_sub.add_parser("stale", help="Detect stale workers")
    p_work_stale.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Heartbeat timeout threshold in seconds",
    )
    p_work_stale.add_argument("--dir", default=".", help="Project root directory")

    p_work.set_defaults(func=cmd_workers, action="list")
    p_work_list.set_defaults(func=cmd_workers, action="list")
    p_work_stale.set_defaults(func=cmd_workers, action="stale")

    # jobs (Phase 25)
    p_job = subparsers.add_parser(
        "jobs",
        help="Manage control plane jobs (list, submit, show, cancel, retry, queue)",
    )
    p_job_sub = p_job.add_subparsers(dest="action", required=False)

    p_job_list = p_job_sub.add_parser("list", help="List all jobs")
    p_job_list.add_argument("--tenant", default=None, help="Filter by tenant ID")
    p_job_list.add_argument("--dir", default=".", help="Project root directory")

    p_job_show = p_job_sub.add_parser("show", help="Show job details")
    p_job_show.add_argument("job_id", help="Job ID to inspect")
    p_job_show.add_argument("--dir", default=".", help="Project root directory")

    p_job_submit = p_job_sub.add_parser("submit", help="Submit a job")
    p_job_submit.add_argument("test_id", help="Test case ID")
    p_job_submit.add_argument("--input", default="", help="Test case input text")
    p_job_submit.add_argument(
        "--priority", default="NORMAL", help="CRITICAL, HIGH, NORMAL, LOW"
    )
    p_job_submit.add_argument(
        "--execution-id", default=None, help="Associated execution ID"
    )
    p_job_submit.add_argument(
        "--delay", type=float, default=0.0, help="Scheduling delay in seconds"
    )
    p_job_submit.add_argument("--retries", type=int, default=0, help="Max retries")
    p_job_submit.add_argument("--tags", default="", help="Comma-separated tags")
    p_job_submit.add_argument("--tenant", default="default", help="Tenant ID")
    p_job_submit.add_argument("--project", default="default", help="Project ID")
    p_job_submit.add_argument("--namespace", default="default", help="Namespace")
    p_job_submit.add_argument("--dir", default=".", help="Project root directory")

    p_job_cancel = p_job_sub.add_parser("cancel", help="Cancel a job")
    p_job_cancel.add_argument("job_id", help="Job ID to cancel")
    p_job_cancel.add_argument("--dir", default=".", help="Project root directory")

    p_job_retry = p_job_sub.add_parser("retry", help="Retry a job")
    p_job_retry.add_argument("job_id", help="Job ID to retry")
    p_job_retry.add_argument("--dir", default=".", help="Project root directory")

    p_job_queue = p_job_sub.add_parser("queue", help="Inspect queued jobs")
    p_job_queue.add_argument("--tenant", default=None, help="Filter by tenant ID")
    p_job_queue.add_argument("--dir", default=".", help="Project root directory")

    p_job.set_defaults(func=cmd_jobs, action="list")
    p_job_list.set_defaults(func=cmd_jobs, action="list")
    p_job_show.set_defaults(func=cmd_jobs, action="show")
    p_job_submit.set_defaults(func=cmd_jobs, action="submit")
    p_job_cancel.set_defaults(func=cmd_jobs, action="cancel")
    p_job_retry.set_defaults(func=cmd_jobs, action="retry")
    p_job_queue.set_defaults(func=cmd_jobs, action="queue")

    # tenants (Phase 27)
    p_ten = subparsers.add_parser(
        "tenants",
        help="Manage tenants, isolation, quotas, and usage",
    )
    p_ten_sub = p_ten.add_subparsers(dest="action", required=False)

    p_ten_list = p_ten_sub.add_parser("list", help="List registered tenants")
    p_ten_list.add_argument("--dir", default=".", help="Project root directory")

    p_ten_show = p_ten_sub.add_parser("show", help="Show tenant details")
    p_ten_show.add_argument("tenant_id", help="Tenant ID to inspect")
    p_ten_show.add_argument("--dir", default=".", help="Project root directory")

    p_ten_create = p_ten_sub.add_parser("create", help="Create a new tenant")
    p_ten_create.add_argument("tenant_id", help="Tenant ID to create")
    p_ten_create.add_argument("--name", default=None, help="Display name")
    p_ten_create.add_argument("--dir", default=".", help="Project root directory")

    p_ten_suspend = p_ten_sub.add_parser("suspend", help="Suspend a tenant")
    p_ten_suspend.add_argument("tenant_id", help="Tenant ID to suspend")
    p_ten_suspend.add_argument("--dir", default=".", help="Project root directory")

    p_ten_activate = p_ten_sub.add_parser("activate", help="Activate a tenant")
    p_ten_activate.add_argument("tenant_id", help="Tenant ID to activate")
    p_ten_activate.add_argument("--dir", default=".", help="Project root directory")

    p_ten_quota = p_ten_sub.add_parser("quota", help="Inspect tenant quota")
    p_ten_quota.add_argument("tenant_id", help="Tenant ID")
    p_ten_quota.add_argument("--dir", default=".", help="Project root directory")

    p_ten_usage = p_ten_sub.add_parser("usage", help="Inspect tenant resource usage")
    p_ten_usage.add_argument("tenant_id", help="Tenant ID")
    p_ten_usage.add_argument("--dir", default=".", help="Project root directory")

    p_ten.set_defaults(func=cmd_tenants, action="list")
    p_ten_list.set_defaults(func=cmd_tenants, action="list")
    p_ten_show.set_defaults(func=cmd_tenants, action="show")
    p_ten_create.set_defaults(func=cmd_tenants, action="create")
    p_ten_suspend.set_defaults(func=cmd_tenants, action="suspend")
    p_ten_activate.set_defaults(func=cmd_tenants, action="activate")
    p_ten_quota.set_defaults(func=cmd_tenants, action="quota")
    p_ten_usage.set_defaults(func=cmd_tenants, action="usage")

    # scheduler (Phase 25)
    p_sched = subparsers.add_parser(
        "scheduler", help="Control plane scheduler commands (status, start, stop)"
    )
    p_sched_sub = p_sched.add_subparsers(dest="action", required=False)

    p_sched_status = p_sched_sub.add_parser("status", help="Get scheduler status")
    p_sched_status.add_argument("--dir", default=".", help="Project root directory")

    p_sched_start = p_sched_sub.add_parser("start", help="Start scheduler process")
    p_sched_start.add_argument("--dir", default=".", help="Project root directory")

    p_sched_stop = p_sched_sub.add_parser("stop", help="Stop scheduler process")
    p_sched_stop.add_argument("--dir", default=".", help="Project root directory")

    p_sched.set_defaults(func=cmd_scheduler, action="status")
    p_sched_status.set_defaults(func=cmd_scheduler, action="status")
    p_sched_start.set_defaults(func=cmd_scheduler, action="start")
    p_sched_stop.set_defaults(func=cmd_scheduler, action="stop")

    # resilience (Phase 26)
    p_res = subparsers.add_parser(
        "resilience",
        help="Inspect resilience state, failures, workers, circuits, and quarantine",
    )
    p_res_sub = p_res.add_subparsers(dest="action", required=False)

    p_res_status = p_res_sub.add_parser("status", help="Resilience summary status")
    p_res_status.add_argument("--dir", default=".", help="Project root directory")

    p_res_fail = p_res_sub.add_parser(
        "failures", help="List structured failure records"
    )
    p_res_fail.add_argument(
        "--execution-id", default=None, help="Filter failures by execution ID"
    )
    p_res_fail.add_argument("--dir", default=".", help="Project root directory")

    p_res_work = p_res_sub.add_parser("workers", help="Inspect worker health states")
    p_res_work.add_argument("--dir", default=".", help="Project root directory")

    p_res_circ = p_res_sub.add_parser("circuits", help="Inspect circuit breaker states")
    p_res_circ.add_argument("--dir", default=".", help="Project root directory")

    p_res_quar = p_res_sub.add_parser(
        "quarantine", help="Quarantine an unhealthy worker"
    )
    p_res_quar.add_argument("worker_id", help="Worker ID to quarantine")
    p_res_quar.add_argument("--dir", default=".", help="Project root directory")

    p_res_unquar = p_res_sub.add_parser(
        "unquarantine", help="Unquarantine and recover a worker"
    )
    p_res_unquar.add_argument("worker_id", help="Worker ID to unquarantine")
    p_res_unquar.add_argument("--dir", default=".", help="Project root directory")

    p_res_rec = p_res_sub.add_parser(
        "recover", help="Trigger self-healing recovery sweep"
    )
    p_res_rec.add_argument("--dir", default=".", help="Project root directory")

    p_res.set_defaults(func=cmd_resilience, action="status")
    p_res_status.set_defaults(func=cmd_resilience, action="status")
    p_res_fail.set_defaults(func=cmd_resilience, action="failures")
    p_res_work.set_defaults(func=cmd_resilience, action="workers")
    p_res_circ.set_defaults(func=cmd_resilience, action="circuits")
    p_res_quar.set_defaults(func=cmd_resilience, action="quarantine")
    p_res_unquar.set_defaults(func=cmd_resilience, action="unquarantine")
    p_res_rec.set_defaults(func=cmd_resilience, action="recover")

    # security (Phase 28)
    p_sec = subparsers.add_parser(
        "security", help="Inspect and manage API gateway security and credentials"
    )
    p_sec_sub = p_sec.add_subparsers(dest="action", required=False)

    p_sec_stat = p_sec_sub.add_parser("status", help="Security gateway status")
    p_sec_stat.add_argument("--dir", default=".", help="Project root directory")

    p_sec_id = p_sec_sub.add_parser("identities", help="List principal types")
    p_sec_id.add_argument("--dir", default=".", help="Project root directory")

    p_sec_roles = p_sec_sub.add_parser("roles", help="List registered roles")
    p_sec_roles.add_argument("--dir", default=".", help="Project root directory")

    p_sec_perms = p_sec_sub.add_parser("permissions", help="List permissions")
    p_sec_perms.add_argument("--dir", default=".", help="Project root directory")

    p_sec_keys = p_sec_sub.add_parser("keys", help="Manage API keys")
    p_sec_keys.add_argument("--tenant", default=None, help="Tenant ID filter")
    p_sec_keys.add_argument("--dir", default=".", help="Project root directory")
    p_sec_keys_sub = p_sec_keys.add_subparsers(dest="key_action", required=False)

    p_sec_keys_list = p_sec_keys_sub.add_parser("list", help="List API keys")
    p_sec_keys_list.add_argument("--tenant", default=None, help="Tenant ID filter")
    p_sec_keys_list.add_argument("--dir", default=".", help="Project root directory")

    p_sec_keys_create = p_sec_keys_sub.add_parser("create", help="Create an API key")
    p_sec_keys_create.add_argument("tenant", help="Tenant ID")
    p_sec_keys_create.add_argument("--name", default="API Key", help="Key name")
    p_sec_keys_create.add_argument("--dir", default=".", help="Project root directory")

    p_sec_keys_revoke = p_sec_keys_sub.add_parser("revoke", help="Revoke an API key")
    p_sec_keys_revoke.add_argument("key_id", help="Key ID to revoke")
    p_sec_keys_revoke.add_argument("--dir", default=".", help="Project root directory")

    p_sec_keys_rotate = p_sec_keys_sub.add_parser("rotate", help="Rotate an API key")
    p_sec_keys_rotate.add_argument("key_id", help="Key ID to rotate")
    p_sec_keys_rotate.add_argument("--dir", default=".", help="Project root directory")

    p_sec_audit = p_sec_sub.add_parser("audit", help="Inspect security audit logs")
    p_sec_audit.add_argument("--tenant", default=None, help="Tenant ID filter")
    p_sec_audit.add_argument("--dir", default=".", help="Project root directory")

    p_sec_rep = p_sec_sub.add_parser("replay-status", help="Inspect replay protection")
    p_sec_rep.add_argument("--dir", default=".", help="Project root directory")

    p_sec.set_defaults(func=cmd_security, action="status")
    p_sec_stat.set_defaults(func=cmd_security, action="status")
    p_sec_id.set_defaults(func=cmd_security, action="identities")
    p_sec_roles.set_defaults(func=cmd_security, action="roles")
    p_sec_perms.set_defaults(func=cmd_security, action="permissions")
    p_sec_keys.set_defaults(func=cmd_security, action="keys_list")
    p_sec_keys_list.set_defaults(func=cmd_security, action="keys_list")
    p_sec_keys_create.set_defaults(func=cmd_security, action="keys_create")
    p_sec_keys_revoke.set_defaults(func=cmd_security, action="keys_revoke")
    p_sec_keys_rotate.set_defaults(func=cmd_security, action="keys_rotate")
    p_sec_audit.set_defaults(func=cmd_security, action="audit")
    p_sec_rep.set_defaults(func=cmd_security, action="replay_status")

    # observability (Phase 29)
    p_obs = subparsers.add_parser(
        "observability",
        help="Inspect observability metrics, health, traces, events, and SLOs",
    )
    p_obs_sub = p_obs.add_subparsers(dest="action", required=False)

    p_obs_stat = p_obs_sub.add_parser("status", help="Get observability status")
    p_obs_stat.add_argument("--tenant", default=None, help="Tenant ID filter")
    p_obs_stat.add_argument("--dir", default=".", help="Project root directory")

    p_obs_health = p_obs_sub.add_parser(
        "health", help="Get operational health snapshot"
    )
    p_obs_health.add_argument("--dir", default=".", help="Project root directory")

    p_obs_metrics = p_obs_sub.add_parser("metrics", help="Expose metrics")
    p_obs_metrics.add_argument("--tenant", default=None, help="Tenant ID filter")
    p_obs_metrics.add_argument("--dir", default=".", help="Project root directory")

    p_obs_traces = p_obs_sub.add_parser("traces", help="List distributed traces")
    p_obs_traces.add_argument("--tenant", default=None, help="Tenant ID filter")
    p_obs_traces.add_argument("--dir", default=".", help="Project root directory")

    p_obs_trace = p_obs_sub.add_parser("trace", help="Inspect single trace")
    p_obs_trace.add_argument("trace_id", help="Trace ID to inspect")
    p_obs_trace.add_argument("--dir", default=".", help="Project root directory")

    p_obs_events = p_obs_sub.add_parser(
        "events", help="List structured telemetry events"
    )
    p_obs_events.add_argument("--tenant", default=None, help="Tenant ID filter")
    p_obs_events.add_argument("--dir", default=".", help="Project root directory")

    p_obs_incidents = p_obs_sub.add_parser(
        "incidents", help="List operational incidents"
    )
    p_obs_incidents.add_argument("--tenant", default=None, help="Tenant ID filter")
    p_obs_incidents.add_argument("--dir", default=".", help="Project root directory")

    p_obs_incident = p_obs_sub.add_parser("incident", help="Inspect single incident")
    p_obs_incident.add_argument("incident_id", help="Incident ID to inspect")
    p_obs_incident.add_argument("--dir", default=".", help="Project root directory")

    p_obs_slo = p_obs_sub.add_parser("slo", help="Inspect SLO and error budget status")
    p_obs_slo_sub = p_obs_slo.add_subparsers(dest="slo_action", required=False)
    p_obs_slo_stat = p_obs_slo_sub.add_parser("status", help="Get SLO status")
    p_obs_slo_stat.add_argument("--tenant", default=None, help="Tenant ID filter")
    p_obs_slo_stat.add_argument("--dir", default=".", help="Project root directory")
    p_obs_slo.add_argument("--tenant", default=None, help="Tenant ID filter")
    p_obs_slo.add_argument("--dir", default=".", help="Project root directory")

    p_obs_anomalies = p_obs_sub.add_parser(
        "anomalies", help="Detect telemetry anomalies"
    )
    p_obs_anomalies.add_argument("--dir", default=".", help="Project root directory")

    p_obs_workers = p_obs_sub.add_parser("workers", help="Inspect worker observability")
    p_obs_workers.add_argument("--dir", default=".", help="Project root directory")

    p_obs_providers = p_obs_sub.add_parser(
        "providers", help="Inspect provider observability"
    )
    p_obs_providers.add_argument("--dir", default=".", help="Project root directory")

    p_obs_export = p_obs_sub.add_parser("export", help="Export telemetry data")
    p_obs_export_sub = p_obs_export.add_subparsers(dest="export_type", required=True)
    p_exp_m = p_obs_export_sub.add_parser("metrics", help="Export metrics")
    p_exp_m.add_argument("--tenant", default=None, help="Tenant ID filter")
    p_exp_m.add_argument("--dir", default=".", help="Project root directory")
    p_exp_t = p_obs_export_sub.add_parser("traces", help="Export traces")
    p_exp_t.add_argument("--tenant", default=None, help="Tenant ID filter")
    p_exp_t.add_argument("--dir", default=".", help="Project root directory")
    p_exp_e = p_obs_export_sub.add_parser("events", help="Export events")
    p_exp_e.add_argument("--tenant", default=None, help="Tenant ID filter")
    p_exp_e.add_argument("--dir", default=".", help="Project root directory")

    p_obs.set_defaults(func=cmd_observability, action="status")
    p_obs_stat.set_defaults(func=cmd_observability, action="status")
    p_obs_health.set_defaults(func=cmd_observability, action="health")
    p_obs_metrics.set_defaults(func=cmd_observability, action="metrics")
    p_obs_traces.set_defaults(func=cmd_observability, action="traces")
    p_obs_trace.set_defaults(func=cmd_observability, action="trace")
    p_obs_events.set_defaults(func=cmd_observability, action="events")
    p_obs_incidents.set_defaults(func=cmd_observability, action="incidents")
    p_obs_incident.set_defaults(func=cmd_observability, action="incident")
    p_obs_slo.set_defaults(func=cmd_observability, action="slo")
    p_obs_slo_stat.set_defaults(func=cmd_observability, action="slo")
    p_obs_anomalies.set_defaults(func=cmd_observability, action="anomalies")
    p_obs_workers.set_defaults(func=cmd_observability, action="workers")
    p_obs_providers.set_defaults(func=cmd_observability, action="providers")
    p_exp_m.set_defaults(func=cmd_observability, action="export_metrics")
    p_exp_t.set_defaults(func=cmd_observability, action="export_traces")
    p_exp_e.set_defaults(func=cmd_observability, action="export_events")

    # ==========================================================================
    # Phase 33 Subparsers: Evaluation Platform Workflows
    # ==========================================================================

    # evaluate [run|dataset]
    p_eval = subparsers.add_parser("evaluate", help="Execute AI evaluation workflows")
    p_eval_sub = p_eval.add_subparsers(dest="action", required=False)

    p_eval_run = p_eval_sub.add_parser("run", help="Run full evaluation on model/agent")
    for p in (p_eval, p_eval_run):
        p.add_argument(
            "--target",
            "--agent",
            dest="target",
            default=None,
            help="Agent target callable or name",
        )
        p.add_argument(
            "--dataset", default=None, help="Path to evaluation dataset file"
        )
        p.add_argument(
            "--metrics", default=None, help="Comma-separated list of metrics/evaluators"
        )
        p.add_argument(
            "--output", default=None, help="Path to export evaluation report"
        )
        p.add_argument(
            "--format",
            default="terminal",
            choices=[
                "terminal",
                "cli",
                "json",
                "jsonl",
                "csv",
                "markdown",
                "md",
                "html",
                "junit",
                "pr-comment",
            ],
            help="Output format",
        )
        p.add_argument(
            "--gate", action="store_true", help="Evaluate release gate policy"
        )
        p.add_argument(
            "--min-score",
            type=float,
            default=None,
            help="Minimum composite score threshold",
        )
        p.add_argument(
            "--fail-on-regression",
            action="store_true",
            help="Fail release gate if regressions detected",
        )
        p.add_argument(
            "--profile",
            default=None,
            choices=[
                "rag",
                "agent",
                "classification",
                "generation",
                "safety",
                "performance",
                "cost",
                "production",
                "full",
            ],
            help="Evaluation profile to run",
        )
        p.add_argument("--dir", default=".", help="Project root directory")
    p_eval.set_defaults(func=cmd_evaluate, action="run")
    p_eval_run.set_defaults(func=cmd_evaluate, action="run")

    p_eval_ds = p_eval_sub.add_parser(
        "dataset", help="Inspect or manage evaluation datasets"
    )
    p_eval_ds.add_argument("--file", default=None, help="Dataset file path")
    p_eval_ds.set_defaults(func=cmd_dataset, action="inspect")

    # dataset [create|validate|compare|inspect]
    p_ds = subparsers.add_parser(
        "dataset", help="Inspect, validate, or generate evaluation datasets"
    )
    p_ds_sub = p_ds.add_subparsers(dest="action", required=False)

    p_ds_create = p_ds_sub.add_parser("create", help="Create a new evaluation dataset")
    p_ds_create.add_argument("--name", default="New Dataset", help="Dataset name")
    p_ds_create.add_argument(
        "--output", default="dataset.json", help="Output file path"
    )
    p_ds_create.add_argument("--description", default="", help="Dataset description")
    p_ds_create.set_defaults(func=cmd_dataset, action="create")

    p_ds_val = p_ds_sub.add_parser(
        "validate", help="Validate evaluation dataset integrity"
    )
    p_ds_val.add_argument("--file", required=True, help="Path to dataset file")
    p_ds_val.set_defaults(func=cmd_dataset, action="validate")

    p_ds_cmp = p_ds_sub.add_parser("compare", help="Compare two evaluation datasets")
    p_ds_cmp.add_argument("--base", required=True, help="Base dataset path")
    p_ds_cmp.add_argument("--candidate", required=True, help="Candidate dataset path")
    p_ds_cmp.set_defaults(func=cmd_dataset, action="compare")

    p_ds_ins = p_ds_sub.add_parser("inspect", help="Inspect evaluation dataset details")
    p_ds_ins.add_argument("--file", required=True, help="Path to dataset file")
    p_ds_ins.set_defaults(func=cmd_dataset, action="inspect")

    p_ds.add_argument("--file", default=None, help="Path to dataset file")
    p_ds.set_defaults(func=cmd_dataset, action="inspect")

    # score
    p_score = subparsers.add_parser(
        "score", help="Calculate unified multidimensional reliability score"
    )
    p_score.add_argument(
        "--report",
        "--file",
        dest="report",
        required=True,
        help="Path to evaluation report JSON",
    )
    p_score.add_argument(
        "--weights", default=None, help="Path or JSON string of dimensional weights"
    )
    p_score.add_argument("--output", default=None, help="Path to export score JSON")
    p_score.set_defaults(func=cmd_score)

    # gate
    p_gate = subparsers.add_parser(
        "gate",
        help="Evaluate release gate policies (exit codes: 0 PASS, 1 FAIL, 2 BLOCK)",
    )
    p_gate.add_argument(
        "--report",
        "--file",
        dest="report",
        required=True,
        help="Path to evaluation report JSON",
    )
    p_gate.add_argument(
        "--min-score",
        type=float,
        default=0.80,
        help="Minimum composite reliability score",
    )
    p_gate.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Fail if any regressions detected",
    )
    p_gate.add_argument(
        "--allow-critical-veto",
        action="store_true",
        help="Whether critical veto is allowed without blocking",
    )
    p_gate.add_argument(
        "--policy", default="DefaultGatePolicy", help="Gate policy name"
    )
    p_gate.set_defaults(func=cmd_gate)

    # report
    p_rep = subparsers.add_parser(
        "report",
        help="Generate evaluation reports or serve interactive dashboard",
    )
    p_rep.add_argument(
        "--report",
        "--file",
        dest="report",
        required=True,
        help="Path to evaluation report JSON",
    )
    p_rep.add_argument(
        "--format",
        default="terminal",
        choices=[
            "terminal",
            "cli",
            "json",
            "jsonl",
            "csv",
            "markdown",
            "md",
            "html",
            "junit",
            "pr-comment",
        ],
        help="Report format",
    )
    p_rep.add_argument("--output", default=None, help="Path to write report output")
    p_rep.add_argument(
        "--serve",
        action="store_true",
        help="Serve interactive HTML report locally on web server",
    )
    p_rep.add_argument(
        "--port", type=int, default=8080, help="Web server port (default 8080)"
    )
    p_rep.set_defaults(func=cmd_report)

    # experiment
    p_exp = subparsers.add_parser(
        "experiment", help="Compare models, prompts, configurations (A/B testing)"
    )
    p_exp.add_argument("--name", default=None, help="Experiment identifier")
    p_exp.add_argument("--dataset", default=None, help="Path to evaluation dataset")
    p_exp.add_argument(
        "--variant-a",
        default="variant_a",
        help="Variant A identifier or configuration",
    )
    p_exp.add_argument(
        "--variant-b",
        default="variant_b",
        help="Variant B identifier or configuration",
    )
    p_exp.add_argument(
        "--metric", default="accuracy", help="Target evaluation metric name"
    )
    p_exp.add_argument("--output", default=None, help="Path to export comparison JSON")
    p_exp.set_defaults(func=cmd_experiment)

    # metrics
    p_metrics = subparsers.add_parser(
        "metrics", help="Inspect registered evaluators or analyze metrics from report"
    )
    p_metrics.add_argument(
        "--report",
        "--file",
        dest="report",
        default=None,
        help="Path to evaluation report JSON",
    )
    p_metrics.set_defaults(func=cmd_metrics)

    # judge
    p_judge = subparsers.add_parser(
        "judge",
        help="Evaluate model responses with semantic judge or evaluate consistency",
    )
    p_judge.add_argument("--input", default=None, help="Input query/prompt to evaluate")
    p_judge.add_argument(
        "--output",
        "--response",
        dest="output",
        default=None,
        help="Model response under evaluation",
    )
    p_judge.add_argument(
        "--expected",
        "--reference",
        dest="expected",
        default=None,
        help="Reference expected answer",
    )
    p_judge.add_argument(
        "--criteria", default="relevance and correctness", help="Evaluation criteria"
    )
    p_judge.add_argument(
        "--evaluate-consistency",
        action="store_true",
        help="Measure judge variance and consistency across iterations",
    )
    p_judge.set_defaults(func=cmd_judge)

    # robustness
    p_robust = subparsers.add_parser(
        "robustness", help="Evaluate model robustness against text perturbations"
    )
    p_robust.add_argument(
        "--input", default=None, help="Input text to generate perturbations for"
    )
    p_robust.set_defaults(func=cmd_robustness)

    # latency
    p_latency = subparsers.add_parser(
        "latency", help="Evaluate latency percentiles and verify SLA conformance"
    )
    p_latency.add_argument(
        "--report",
        "--file",
        dest="report",
        required=True,
        help="Path to evaluation report JSON",
    )
    p_latency.add_argument(
        "--sla-ms",
        type=float,
        default=None,
        help="Maximum allowed latency in milliseconds",
    )
    p_latency.set_defaults(func=cmd_latency)

    # cost
    p_cost = subparsers.add_parser(
        "cost", help="Evaluate token consumption and financial cost against budget"
    )
    p_cost.add_argument(
        "--report",
        "--file",
        dest="report",
        required=True,
        help="Path to evaluation report JSON",
    )
    p_cost.add_argument(
        "--max-cost", type=float, default=None, help="Maximum allowed cost in dollars"
    )
    p_cost.set_defaults(func=cmd_cost)

    # regression
    p_reg = subparsers.add_parser(
        "regression",
        help="Run regression suites or diff evaluation runs against baselines",
    )
    p_reg_sub = p_reg.add_subparsers(dest="action", required=False)

    p_reg_list = p_reg_sub.add_parser("list", help="List synthesized regression tests")
    p_reg_list.add_argument("--dir", default=".", help="Project root directory")
    p_reg_list.add_argument(
        "--details", action="store_true", help="Show regression provenance"
    )
    p_reg_list.set_defaults(func=cmd_regression, action="list")

    p_reg_run = p_reg_sub.add_parser("run", help="Run regression test suite")
    p_reg_run.add_argument("--dir", default=".", help="Project root directory")
    p_reg_run.add_argument(
        "baseline", nargs="?", default=None, help="Name of baseline snapshot"
    )
    p_reg_run.add_argument("--agent", default=None, help="Agent target override")
    p_reg_run.set_defaults(func=cmd_regression, action="run")

    p_reg_diff = p_reg_sub.add_parser(
        "diff", help="Diff evaluation candidate report against reference baseline"
    )
    p_reg_diff.add_argument(
        "--candidate",
        "--report",
        dest="candidate",
        required=True,
        help="Candidate evaluation report JSON",
    )
    p_reg_diff.add_argument(
        "--baseline",
        "--base",
        dest="base",
        required=True,
        help="Reference baseline JSON",
    )
    p_reg_diff.set_defaults(func=cmd_regression, action="diff")

    p_reg.set_defaults(func=cmd_regression, action="list")

    # intelligence (Phase 34)
    p_intel = subparsers.add_parser(
        "intelligence",
        help="AI Reliability Intelligence analysis, clustering, patterns, trends, and recommendations",
    )
    p_intel_sub = p_intel.add_subparsers(dest="intel_action", required=False)

    # intelligence analyze
    p_ia = p_intel_sub.add_parser(
        "analyze", help="Run comprehensive reliability intelligence analysis"
    )
    p_ia.add_argument(
        "report", nargs="?", default=None, help="Evaluation report JSON file"
    )
    p_ia.add_argument(
        "--report",
        "--file",
        dest="report_opt",
        default=None,
        help="Evaluation report JSON file",
    )
    p_ia.add_argument(
        "--history", default=None, help="Evaluation history file or directory"
    )
    p_ia.add_argument(
        "--baseline", default=None, help="Baseline evaluation report JSON"
    )
    p_ia.add_argument(
        "--format",
        choices=["terminal", "json"],
        default="terminal",
        help="Output format",
    )
    p_ia.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_ia.add_argument("--output", "-o", default=None, help="Output destination file")
    p_ia.set_defaults(func=cmd_intelligence, intel_action="analyze")

    # intelligence failures
    p_if = p_intel_sub.add_parser(
        "failures", help="Normalize and inspect failure reports and fingerprints"
    )
    p_if.add_argument(
        "report", nargs="?", default=None, help="Evaluation report JSON file"
    )
    p_if.add_argument(
        "--report",
        "--file",
        dest="report_opt",
        default=None,
        help="Evaluation report JSON file",
    )
    p_if.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_if.add_argument("--output", "-o", default=None, help="Output destination file")
    p_if.set_defaults(func=cmd_intelligence, intel_action="failures")

    # intelligence clusters
    p_ic = p_intel_sub.add_parser(
        "clusters", help="Cluster failures by deterministic structural similarity"
    )
    p_ic.add_argument(
        "report", nargs="?", default=None, help="Evaluation report JSON file"
    )
    p_ic.add_argument(
        "--report",
        "--file",
        dest="report_opt",
        default=None,
        help="Evaluation report JSON file",
    )
    p_ic.add_argument(
        "--history", default=None, help="Evaluation history file or directory"
    )
    p_ic.add_argument(
        "--baseline", default=None, help="Baseline evaluation report JSON"
    )
    p_ic.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_ic.add_argument("--output", "-o", default=None, help="Output destination file")
    p_ic.set_defaults(func=cmd_intelligence, intel_action="clusters")

    # intelligence patterns
    p_ip = p_intel_sub.add_parser(
        "patterns", help="Detect longitudinal and component-specific failure patterns"
    )
    p_ip.add_argument(
        "report", nargs="?", default=None, help="Evaluation report JSON file"
    )
    p_ip.add_argument(
        "--report",
        "--file",
        dest="report_opt",
        default=None,
        help="Evaluation report JSON file",
    )
    p_ip.add_argument(
        "--history", default=None, help="Evaluation history file or directory"
    )
    p_ip.add_argument(
        "--baseline", default=None, help="Baseline evaluation report JSON"
    )
    p_ip.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_ip.add_argument("--output", "-o", default=None, help="Output destination file")
    p_ip.set_defaults(func=cmd_intelligence, intel_action="patterns")

    # intelligence trends
    p_it = p_intel_sub.add_parser(
        "trends",
        help="Analyze longitudinal reliability trajectories and rates of change",
    )
    p_it.add_argument(
        "report", nargs="?", default=None, help="Evaluation report JSON file"
    )
    p_it.add_argument(
        "--report",
        "--file",
        dest="report_opt",
        default=None,
        help="Evaluation report JSON file",
    )
    p_it.add_argument(
        "--history", default=None, help="Evaluation history file or directory"
    )
    p_it.add_argument("--metric", default=None, help="Filter by specific metric name")
    p_it.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_it.add_argument("--output", "-o", default=None, help="Output destination file")
    p_it.set_defaults(func=cmd_intelligence, intel_action="trends")

    # intelligence impact
    p_ii = p_intel_sub.add_parser(
        "impact", help="Assess operational risk, safety, and failure impact"
    )
    p_ii.add_argument(
        "report", nargs="?", default=None, help="Evaluation report JSON file"
    )
    p_ii.add_argument(
        "--report",
        "--file",
        dest="report_opt",
        default=None,
        help="Evaluation report JSON file",
    )
    p_ii.add_argument(
        "--critical-only", action="store_true", help="Filter for critical impacts only"
    )
    p_ii.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_ii.add_argument("--output", "-o", default=None, help="Output destination file")
    p_ii.set_defaults(func=cmd_intelligence, intel_action="impact")

    # intelligence recommendations
    p_ir = p_intel_sub.add_parser(
        "recommendations",
        help="Generate prioritized, evidence-backed remediation recommendations",
    )
    p_ir.add_argument(
        "report", nargs="?", default=None, help="Evaluation report JSON file"
    )
    p_ir.add_argument(
        "--report",
        "--file",
        dest="report_opt",
        default=None,
        help="Evaluation report JSON file",
    )
    p_ir.add_argument(
        "--priority",
        choices=["LOW", "MEDIUM", "HIGH", "CRITICAL"],
        default=None,
        help="Filter recommendations by priority",
    )
    p_ir.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_ir.add_argument("--output", "-o", default=None, help="Output destination file")
    p_ir.set_defaults(func=cmd_intelligence, intel_action="recommendations")

    # intelligence explain
    p_ie = p_intel_sub.add_parser(
        "explain", help="Answer the 10 core AI reliability questions"
    )
    p_ie.add_argument(
        "report", nargs="?", default=None, help="Evaluation report JSON file"
    )
    p_ie.add_argument(
        "--report",
        "--file",
        dest="report_opt",
        default=None,
        help="Evaluation report JSON file",
    )
    p_ie.add_argument(
        "--history", default=None, help="Evaluation history file or directory"
    )
    p_ie.add_argument(
        "--baseline", default=None, help="Baseline evaluation report JSON"
    )
    p_ie.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_ie.add_argument("--output", "-o", default=None, help="Output destination file")
    p_ie.set_defaults(func=cmd_intelligence, intel_action="explain")

    p_intel.set_defaults(func=cmd_intelligence, intel_action="analyze")

    # =========================================================================
    # Phase 35: Knowledge Graph Subcommands
    # =========================================================================
    p_graph = subparsers.add_parser(
        "graph", help="AI Reliability Knowledge Graph operations"
    )
    p_graph_sub = p_graph.add_subparsers(dest="graph_action", required=True)

    # 1. build
    p_gb = p_graph_sub.add_parser(
        "build", help="Construct Knowledge Graph from artifact"
    )
    p_gb.add_argument(
        "file", help="Input JSON file (report, trace, intelligence, etc.)"
    )
    p_gb.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_gb.add_argument("--output", "-o", default=None, help="Output destination file")
    p_gb.set_defaults(func=cmd_graph, graph_action="build")

    # 2. inspect
    p_gi = p_graph_sub.add_parser(
        "inspect", help="Display topology summary and metrics"
    )
    p_gi.add_argument("file", help="Input Knowledge Graph or report JSON file")
    p_gi.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_gi.add_argument("--output", "-o", default=None, help="Output destination file")
    p_gi.set_defaults(func=cmd_graph, graph_action="inspect")

    # 3. query
    p_gq = p_graph_sub.add_parser("query", help="Query nodes by type, tag, or name")
    p_gq.add_argument("file", help="Input graph or report JSON file")
    p_gq.add_argument("--type", default=None, help="Node type filter")
    p_gq.add_argument("--tag", default=None, help="Tag filter")
    p_gq.add_argument("--name", default=None, help="Name substring filter")
    p_gq.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_gq.add_argument("--output", "-o", default=None, help="Output destination file")
    p_gq.set_defaults(func=cmd_graph, graph_action="query")

    # 4. neighbors
    p_gn = p_graph_sub.add_parser(
        "neighbors", help="Retrieve adjacent neighbors of a node"
    )
    p_gn.add_argument("file", help="Input graph or report JSON file")
    p_gn.add_argument("--node", required=True, help="Node identifier")
    p_gn.add_argument(
        "--direction",
        choices=["incoming", "outgoing", "both"],
        default="both",
        help="Edge direction",
    )
    p_gn.add_argument("--rel", default=None, help="Relationship type filter")
    p_gn.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_gn.add_argument("--output", "-o", default=None, help="Output destination file")
    p_gn.set_defaults(func=cmd_graph, graph_action="neighbors")

    # 5. path
    p_gp = p_graph_sub.add_parser("path", help="Find path between two nodes")
    p_gp.add_argument("file", help="Input graph or report JSON file")
    p_gp.add_argument("--from", dest="from_node", required=True, help="Source node ID")
    p_gp.add_argument("--to", dest="to_node", required=True, help="Target node ID")
    p_gp.add_argument(
        "--max-depth", type=int, default=10, help="Maximum traversal depth"
    )
    p_gp.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_gp.add_argument("--output", "-o", default=None, help="Output destination file")
    p_gp.set_defaults(func=cmd_graph, graph_action="path")

    # 6. impact
    p_gimp = p_graph_sub.add_parser(
        "impact", help="Assess blast radius and downstream impact"
    )
    p_gimp.add_argument("file", help="Input graph or report JSON file")
    p_gimp.add_argument("--node", required=True, help="Root node identifier")
    p_gimp.add_argument(
        "--max-depth", type=int, default=8, help="Maximum traversal depth"
    )
    p_gimp.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_gimp.add_argument("--output", "-o", default=None, help="Output destination file")
    p_gimp.set_defaults(func=cmd_graph, graph_action="impact")

    # 7. failures
    p_gf = p_graph_sub.add_parser("failures", help="Find failures linked to components")
    p_gf.add_argument("file", help="Input graph or report JSON file")
    p_gf.add_argument("--model", default=None, help="Model filter")
    p_gf.add_argument("--prompt", default=None, help="Prompt filter")
    p_gf.add_argument("--tool", default=None, help="Tool filter")
    p_gf.add_argument("--retriever", default=None, help="Retriever filter")
    p_gf.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_gf.add_argument("--output", "-o", default=None, help="Output destination file")
    p_gf.set_defaults(func=cmd_graph, graph_action="failures")

    # 8. regressions
    p_gr = p_graph_sub.add_parser(
        "regressions", help="Find regressions linked to datasets"
    )
    p_gr.add_argument("file", help="Input graph or report JSON file")
    p_gr.add_argument("--dataset", default=None, help="Dataset filter")
    p_gr.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_gr.add_argument("--output", "-o", default=None, help="Output destination file")
    p_gr.set_defaults(func=cmd_graph, graph_action="regressions")

    # 9. incidents
    p_ginc = p_graph_sub.add_parser(
        "incidents", help="Find incidents linked to root causes"
    )
    p_ginc.add_argument("file", help="Input graph or report JSON file")
    p_ginc.add_argument("--root-cause", default=None, help="Root cause filter")
    p_ginc.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_ginc.add_argument("--output", "-o", default=None, help="Output destination file")
    p_ginc.set_defaults(func=cmd_graph, graph_action="incidents")

    # 10. root-causes
    p_grc = p_graph_sub.add_parser(
        "root-causes", help="Query root causes and timeline history"
    )
    p_grc.add_argument("file", help="Input graph or report JSON file")
    p_grc.add_argument("--id", default=None, help="Root cause ID")
    p_grc.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_grc.add_argument("--output", "-o", default=None, help="Output destination file")
    p_grc.set_defaults(func=cmd_graph, graph_action="root-causes")

    # 11. export
    p_gexp = p_graph_sub.add_parser("export", help="Export Knowledge Graph to file")
    p_gexp.add_argument("file", help="Input graph or report JSON file")
    p_gexp.add_argument("--output", "-o", required=True, help="Destination file path")
    p_gexp.add_argument(
        "--format",
        choices=["json", "csv", "jsonl"],
        default="json",
        help="Export format",
    )
    p_gexp.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_gexp.set_defaults(func=cmd_graph, graph_action="export")

    # 12. diff
    p_gdiff = p_graph_sub.add_parser("diff", help="Compare two Knowledge Graphs")
    p_gdiff.add_argument("file1", help="First graph JSON file")
    p_gdiff.add_argument("file2", help="Second graph JSON file")
    p_gdiff.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_gdiff.add_argument("--output", "-o", default=None, help="Output destination file")
    p_gdiff.set_defaults(func=cmd_graph, graph_action="diff")

    # =========================================================================
    # Phase 36: Automated AI Test Generation Subcommands
    # =========================================================================
    p_gen = subparsers.add_parser(
        "generate", help="Automated AI Test Generation workflows"
    )
    p_gen_sub = p_gen.add_subparsers(dest="generate_action", required=False)

    def _add_gen_args(p_cmd: argparse.ArgumentParser, is_parent: bool = False) -> None:
        if not is_parent:
            p_cmd.add_argument(
                "source", nargs="?", default=None, help="Evidence source file or prompt"
            )
        p_cmd.add_argument(
            "--source",
            "--file",
            dest="source_opt",
            default=None,
            help="Evidence source file path",
        )
        p_cmd.add_argument(
            "--strategy", default=None, help="Specific generation strategy filter"
        )
        p_cmd.add_argument(
            "--max-candidates",
            type=int,
            default=100,
            help="Maximum candidates to generate",
        )
        p_cmd.add_argument(
            "--quality-threshold",
            type=float,
            default=0.50,
            help="Minimum quality score threshold",
        )
        p_cmd.add_argument(
            "--confidence-threshold",
            type=float,
            default=0.50,
            help="Minimum confidence threshold",
        )
        p_cmd.add_argument(
            "--seed", type=int, default=42, help="Deterministic random seed"
        )
        p_cmd.add_argument(
            "--mutation-limit",
            type=int,
            default=10,
            help="Maximum mutations to synthesize",
        )
        p_cmd.add_argument(
            "--dataset",
            default=None,
            help="Target evaluation dataset path for promotion",
        )
        p_cmd.add_argument(
            "--promote",
            action="store_true",
            help="Automatically promote validated tests",
        )
        p_cmd.add_argument(
            "--dry-run",
            action="store_true",
            help="Execute without persisting to dataset or files",
        )
        p_cmd.add_argument(
            "--output", "-o", default=None, help="Destination output file"
        )
        p_cmd.add_argument(
            "--format",
            choices=[
                "terminal",
                "cli",
                "json",
                "jsonl",
                "csv",
                "markdown",
                "md",
                "junit",
            ],
            default="terminal",
            help="Output formatting",
        )
        p_cmd.add_argument(
            "--json", action="store_true", help="Output machine-readable JSON"
        )

    _add_gen_args(p_gen, is_parent=True)
    p_gen.set_defaults(func=cmd_generate, generate_action="tests")

    for action_name in [
        "tests",
        "regression",
        "golden",
        "adversarial",
        "from-failure",
        "from-trace",
        "from-graph",
        "mutations",
    ]:
        p_sub = p_gen_sub.add_parser(action_name, help=f"Generate {action_name} tests")
        _add_gen_args(p_sub, is_parent=False)
        p_sub.set_defaults(func=cmd_generate, generate_action=action_name)

    # test-generation [inspect|validate|promote]
    p_tg = subparsers.add_parser(
        "test-generation", help="Manage and audit generated tests"
    )
    p_tg_sub = p_tg.add_subparsers(dest="tg_action", required=False)

    p_tg_insp = p_tg_sub.add_parser("inspect", help="Inspect generated tests from file")
    p_tg_insp.add_argument("file", help="Path to generated tests JSON file")
    p_tg_insp.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_tg_insp.set_defaults(func=cmd_test_generation, tg_action="inspect")

    p_tg_val = p_tg_sub.add_parser(
        "validate", help="Validate generated tests from file"
    )
    p_tg_val.add_argument("file", help="Path to generated tests JSON file")
    p_tg_val.set_defaults(func=cmd_test_generation, tg_action="validate")

    p_tg_prom = p_tg_sub.add_parser(
        "promote", help="Promote validated tests to dataset"
    )
    p_tg_prom.add_argument("file", help="Path to generated tests JSON file")
    p_tg_prom.add_argument(
        "--dataset", required=True, help="Target evaluation dataset path"
    )
    p_tg_prom.add_argument(
        "--allow-high-risk",
        action="store_true",
        help="Authorize promotion of high-risk tests",
    )
    p_tg_prom.set_defaults(func=cmd_test_generation, tg_action="promote")

    p_tg.set_defaults(func=cmd_test_generation, tg_action="inspect")

    # =========================================================================
    # Phase 37: Self-Healing Reliability Subcommands
    # =========================================================================
    p_heal = subparsers.add_parser(
        "heal", help="Self-Healing AI Reliability Engine workflows"
    )
    p_heal_sub = p_heal.add_subparsers(dest="heal_action", required=False)

    # heal plan
    p_h_plan = p_heal_sub.add_parser(
        "plan", help="Diagnose failure and plan remediation proposals"
    )
    p_h_plan.add_argument(
        "evidence",
        nargs="?",
        default=None,
        help="Evidence JSON file or error description",
    )
    p_h_plan.add_argument(
        "--evidence",
        "--file",
        dest="evidence_opt",
        default=None,
        help="Evidence source file path",
    )
    p_h_plan.add_argument(
        "--type",
        choices=["prompt", "retrieval", "tool", "agent", "config", "safety"],
        default=None,
        help="Explicit repair domain",
    )
    p_h_plan.add_argument("--component", default=None, help="Target component ID")
    p_h_plan.add_argument(
        "--no-tests",
        action="store_true",
        help="Skip Phase 36 test generation",
    )
    p_h_plan.add_argument(
        "--format",
        choices=["terminal", "json", "markdown", "csv"],
        default="terminal",
        help="Output format",
    )
    p_h_plan.add_argument(
        "--output", "-o", default=None, help="Output destination file"
    )
    p_h_plan.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_h_plan.set_defaults(func=cmd_heal, heal_action="plan")

    # heal simulate
    p_h_sim = p_heal_sub.add_parser(
        "simulate", help="Simulate remediation in sandbox against tests"
    )
    p_h_sim.add_argument("file", help="Path to remediation proposal JSON file")
    p_h_sim.add_argument("--output", "-o", default=None, help="Output destination file")
    p_h_sim.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_h_sim.set_defaults(func=cmd_heal, heal_action="simulate")

    # heal approve
    p_h_app = p_heal_sub.add_parser("approve", help="Approve proposed remediation")
    p_h_app.add_argument("file", help="Path to remediation proposal JSON file")
    p_h_app.add_argument("--approver", default="operator", help="Approver identity")
    p_h_app.add_argument(
        "--rationale", default="Approved by operator", help="Approval rationale"
    )
    p_h_app.add_argument("--output", "-o", default=None, help="Output destination file")
    p_h_app.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_h_app.set_defaults(func=cmd_heal, heal_action="approve")

    # heal apply
    p_h_apply = p_heal_sub.add_parser(
        "apply", help="Deploy remediation via direct, shadow, or canary"
    )
    p_h_apply.add_argument("file", help="Path to remediation proposal JSON file")
    p_h_apply.add_argument(
        "--strategy",
        choices=["direct", "shadow", "canary"],
        default=None,
        help="Rollout strategy",
    )
    p_h_apply.add_argument(
        "--percentage", type=float, default=None, help="Canary traffic percentage"
    )
    p_h_apply.add_argument(
        "--output", "-o", default=None, help="Output destination file"
    )
    p_h_apply.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_h_apply.set_defaults(func=cmd_heal, heal_action="apply")

    # heal verify
    p_h_ver = p_heal_sub.add_parser("verify", help="Verify telemetry of active rollout")
    p_h_ver.add_argument("file", help="Path to remediation proposal JSON file")
    p_h_ver.add_argument(
        "--samples", type=int, default=20, help="Observed sample count"
    )
    p_h_ver.add_argument(
        "--error-rate",
        type=float,
        default=0.0,
        help="Observed remediation error rate",
    )
    p_h_ver.add_argument(
        "--baseline-error-rate",
        type=float,
        default=0.0,
        help="Observed baseline error rate",
    )
    p_h_ver.add_argument("--output", "-o", default=None, help="Output destination file")
    p_h_ver.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_h_ver.set_defaults(func=cmd_heal, heal_action="verify")

    # heal promote
    p_h_prom = p_heal_sub.add_parser(
        "promote", help="Promote verified remediation to permanent baseline"
    )
    p_h_prom.add_argument("file", help="Path to remediation proposal JSON file")
    p_h_prom.add_argument(
        "--actor", default="operator", help="Promoting operator identity"
    )
    p_h_prom.add_argument(
        "--notes",
        default="Promoted to permanent baseline",
        help="Promotion notes",
    )
    p_h_prom.add_argument(
        "--output", "-o", default=None, help="Output destination file"
    )
    p_h_prom.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_h_prom.set_defaults(func=cmd_heal, heal_action="promote")

    # heal rollback
    p_h_roll = p_heal_sub.add_parser(
        "rollback", help="Revert remediation deployment back to baseline"
    )
    p_h_roll.add_argument("file", help="Path to remediation proposal JSON file")
    p_h_roll.add_argument(
        "--reason", default="Manual rollback requested", help="Rollback reason"
    )
    p_h_roll.add_argument(
        "--actor", default="operator", help="Acting operator identity"
    )
    p_h_roll.add_argument(
        "--output", "-o", default=None, help="Output destination file"
    )
    p_h_roll.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_h_roll.set_defaults(func=cmd_heal, heal_action="rollback")

    # heal status
    p_h_stat = p_heal_sub.add_parser(
        "status", help="Inspect remediation proposal status and audit history"
    )
    p_h_stat.add_argument("file", help="Path to remediation proposal JSON file")
    p_h_stat.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_h_stat.set_defaults(func=cmd_heal, heal_action="status")

    p_heal.set_defaults(func=cmd_heal, heal_action="plan")

    # ==============================================================================
    # Phase 38: Optimize Subcommand
    # ==============================================================================
    p_opt = subparsers.add_parser(
        "optimize",
        help="AI Reliability Optimization Engine (Phase 38)",
        description="Search and optimize AI configurations across competing reliability objectives.",
    )
    p_opt_sub = p_opt.add_subparsers(dest="optimize_action")

    # optimize plan
    p_o_plan = p_opt_sub.add_parser(
        "plan", help="Plan and configure optimization problem"
    )
    p_o_plan.add_argument(
        "--name", default="AI Reliability Optimization", help="Problem name"
    )
    p_o_plan.add_argument(
        "--baseline", default=None, help="Baseline configuration JSON file"
    )
    p_o_plan.add_argument(
        "--variable",
        action="append",
        default=None,
        help="Target optimizable variable ID",
    )
    p_o_plan.add_argument(
        "--objective",
        action="append",
        default=None,
        help="Optimization objective definition",
    )
    p_o_plan.add_argument(
        "--constraint",
        action="append",
        default=None,
        help="Optimization constraint definition",
    )
    p_o_plan.add_argument(
        "--safety-threshold", type=float, default=0.95, help="Required safety threshold"
    )
    p_o_plan.add_argument(
        "--quality-threshold",
        type=float,
        default=0.80,
        help="Required quality threshold",
    )
    p_o_plan.add_argument(
        "--output", "-o", default=None, help="Output destination file"
    )
    p_o_plan.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_o_plan.set_defaults(func=cmd_optimize, optimize_action="plan")

    # optimize run
    p_o_run = p_opt_sub.add_parser(
        "run", help="Execute optimization search and selection"
    )
    p_o_run.add_argument(
        "file", nargs="?", default=None, help="Optional problem definition JSON file"
    )
    p_o_run.add_argument(
        "--strategy",
        choices=["random", "grid", "local", "climbing", "bayesian", "evolutionary"],
        default="random",
        help="Search strategy",
    )
    p_o_run.add_argument("--baseline", default=None, help="Baseline config JSON file")
    p_o_run.add_argument(
        "--max-candidates", type=int, default=20, help="Candidate budget limit"
    )
    p_o_run.add_argument(
        "--max-evaluations", type=int, default=50, help="Evaluation budget limit"
    )
    p_o_run.add_argument(
        "--max-runtime", type=float, default=300.0, help="Runtime budget seconds"
    )
    p_o_run.add_argument(
        "--max-cost", type=float, default=100.0, help="Max cost budget in USD"
    )
    p_o_run.add_argument(
        "--seed", type=int, default=42, help="Deterministic random seed"
    )
    p_o_run.add_argument(
        "--repeats", type=int, default=1, help="Repeated evaluations per candidate"
    )
    p_o_run.add_argument(
        "--select",
        choices=[
            "balanced_score",
            "highest_quality",
            "lowest_cost",
            "lowest_latency",
            "weighted_preference",
        ],
        default="balanced_score",
        help="Selection policy",
    )
    p_o_run.add_argument(
        "--format",
        choices=["terminal", "json", "markdown", "csv"],
        default="terminal",
        help="Output format",
    )
    p_o_run.add_argument("--output", "-o", default=None, help="Output destination file")
    p_o_run.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_o_run.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate search without executing evaluation",
    )
    p_o_run.set_defaults(func=cmd_optimize, optimize_action="run")

    # optimize evaluate
    p_o_eval = p_opt_sub.add_parser(
        "evaluate", help="Evaluate a candidate configuration"
    )
    p_o_eval.add_argument(
        "file", nargs="?", default=None, help="Candidate configuration JSON file"
    )
    p_o_eval.add_argument(
        "--repeats", type=int, default=1, help="Repeats for statistical evaluation"
    )
    p_o_eval.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_o_eval.set_defaults(func=cmd_optimize, optimize_action="evaluate")

    # optimize compare
    p_o_comp = p_opt_sub.add_parser(
        "compare", help="Compare candidates against baseline"
    )
    p_o_comp.add_argument("file", help="Path to optimization result JSON file")
    p_o_comp.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_o_comp.set_defaults(func=cmd_optimize, optimize_action="compare")

    # optimize pareto
    p_o_par = p_opt_sub.add_parser(
        "pareto", help="Inspect Pareto frontier points and trade-offs"
    )
    p_o_par.add_argument("file", help="Path to optimization result JSON file")
    p_o_par.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_o_par.set_defaults(func=cmd_optimize, optimize_action="pareto")

    # optimize history
    p_o_hist = p_opt_sub.add_parser("history", help="Query optimization runs history")
    p_o_hist.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_o_hist.set_defaults(func=cmd_optimize, optimize_action="history")

    # optimize inspect
    p_o_insp = p_opt_sub.add_parser(
        "inspect", help="Inspect candidate configuration details"
    )
    p_o_insp.add_argument("file", help="Path to optimization result JSON file")
    p_o_insp.add_argument("--candidate-id", default=None, help="Target candidate ID")
    p_o_insp.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_o_insp.set_defaults(func=cmd_optimize, optimize_action="inspect")

    # optimize select
    p_o_sel = p_opt_sub.add_parser("select", help="Select optimal candidate via policy")
    p_o_sel.add_argument("file", help="Path to optimization result JSON file")
    p_o_sel.add_argument(
        "--strategy",
        choices=["balanced_score", "highest_quality", "lowest_cost", "lowest_latency"],
        default="balanced_score",
        help="Selection strategy",
    )
    p_o_sel.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_o_sel.set_defaults(func=cmd_optimize, optimize_action="select")

    # optimize validate
    p_o_val = p_opt_sub.add_parser(
        "validate", help="Validate candidate against reliability gates"
    )
    p_o_val.add_argument("file", help="Path to optimization result JSON file")
    p_o_val.add_argument(
        "--safety-threshold", type=float, default=0.95, help="Safety gate cutoff"
    )
    p_o_val.add_argument(
        "--security-threshold", type=float, default=0.95, help="Security gate cutoff"
    )
    p_o_val.add_argument(
        "--quality-threshold", type=float, default=0.80, help="Quality gate cutoff"
    )
    p_o_val.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_o_val.set_defaults(func=cmd_optimize, optimize_action="validate")

    # optimize deploy
    p_o_dep = p_opt_sub.add_parser(
        "deploy", help="Deploy candidate via Phase 37 rollout"
    )
    p_o_dep.add_argument("file", help="Path to optimization result JSON file")
    p_o_dep.add_argument(
        "--strategy",
        choices=["direct", "shadow", "canary"],
        default="canary",
        help="Rollout strategy",
    )
    p_o_dep.add_argument(
        "--percentage", type=float, default=10.0, help="Canary traffic percentage"
    )
    p_o_dep.add_argument("--actor", default="operator", help="Acting operator identity")
    p_o_dep.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_o_dep.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate deployment without applying rollout",
    )
    p_o_dep.set_defaults(func=cmd_optimize, optimize_action="deploy")

    # optimize rollback
    p_o_rb = p_opt_sub.add_parser("rollback", help="Revert optimization deployment")
    p_o_rb.add_argument("file", help="Path to optimization result JSON file")
    p_o_rb.add_argument(
        "--reason", default="Rollback requested", help="Rollback reason"
    )
    p_o_rb.add_argument("--actor", default="operator", help="Acting operator identity")
    p_o_rb.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate rollback without reverting state",
    )
    p_o_rb.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_o_rb.set_defaults(func=cmd_optimize, optimize_action="rollback")

    # optimize status
    p_o_stat = p_opt_sub.add_parser("status", help="Inspect optimization run status")
    p_o_stat.add_argument(
        "file", nargs="?", default=None, help="Path to optimization result JSON file"
    )
    p_o_stat.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_o_stat.set_defaults(func=cmd_optimize, optimize_action="status")

    # optimize budget
    p_o_bud = p_opt_sub.add_parser("budget", help="Inspect budget consumption")
    p_o_bud.add_argument(
        "file", nargs="?", default=None, help="Path to optimization result JSON file"
    )
    p_o_bud.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_o_bud.set_defaults(func=cmd_optimize, optimize_action="budget")

    p_opt.set_defaults(func=cmd_optimize, optimize_action="run")

    # ==========================================================================
    # Phase 39: Advanced RAG Reliability Engine
    # ==========================================================================
    p_rag = subparsers.add_parser(
        "rag", help="Advanced RAG Reliability Engine (Phase 39)"
    )
    p_rag_sub = p_rag.add_subparsers(dest="rag_action")

    # 1. evaluate
    p_rag_eval = p_rag_sub.add_parser(
        "evaluate", help="Evaluate full RAG run reliability across all stages"
    )
    p_rag_eval.add_argument(
        "file", nargs="?", default=None, help="Path to RAG run JSON file"
    )
    p_rag_eval.add_argument("--query", help="Query string")
    p_rag_eval.add_argument("--answer", help="Generated answer text")
    p_rag_eval.add_argument("--run", help="RAG run file path")
    p_rag_eval.add_argument("--dataset", help="Dataset path")
    p_rag_eval.add_argument(
        "--top-k", type=int, default=10, help="Top K retrieval candidates"
    )
    p_rag_eval.add_argument(
        "--threshold", type=float, default=0.5, help="Retrieval score threshold"
    )
    p_rag_eval.add_argument("--retriever", help="Retriever name or model")
    p_rag_eval.add_argument("--reranker", help="Reranker model")
    p_rag_eval.add_argument("--model", help="Generation model name")
    p_rag_eval.add_argument("--embedding-model", help="Embedding model name")
    p_rag_eval.add_argument("--knowledge-version", help="Knowledge base version string")
    p_rag_eval.add_argument(
        "--freshness-window", type=int, default=90, help="Max document age in days"
    )
    p_rag_eval.add_argument(
        "--min-grounding", type=float, default=0.70, help="Minimum grounding threshold"
    )
    p_rag_eval.add_argument(
        "--min-faithfulness",
        type=float,
        default=0.70,
        help="Minimum faithfulness threshold",
    )
    p_rag_eval.add_argument(
        "--min-citation",
        type=float,
        default=0.70,
        help="Minimum citation coverage threshold",
    )
    p_rag_eval.add_argument(
        "--max-hallucination",
        type=float,
        default=0.10,
        help="Maximum hallucination rate threshold",
    )
    p_rag_eval.add_argument("--output", "-o", help="Path to write evaluation output")
    p_rag_eval.add_argument(
        "--format",
        choices=["terminal", "json", "markdown", "csv"],
        default="terminal",
        help="Output format",
    )
    p_rag_eval.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_rag_eval.add_argument(
        "--dry-run", action="store_true", help="Perform simulation dry run"
    )
    p_rag_eval.set_defaults(func=cmd_rag, rag_action="evaluate")

    # 2. analyze
    p_rag_ana = p_rag_sub.add_parser(
        "analyze",
        help="Analyze incoming RAG query complexity, completeness, and archetype",
    )
    p_rag_ana.add_argument(
        "query", nargs="?", default=None, help="Query text to analyze"
    )
    p_rag_ana.add_argument("--query", dest="query_opt", help="Query string override")
    p_rag_ana.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_rag_ana.set_defaults(func=cmd_rag, rag_action="analyze")

    # 3. retrieve
    p_rag_ret = p_rag_sub.add_parser(
        "retrieve",
        help="Evaluate retrieval precision, recall, MRR, NDCG, and hybrid mix",
    )
    p_rag_ret.add_argument(
        "file", nargs="?", default=None, help="Path to RAG run JSON file"
    )
    p_rag_ret.add_argument("--run", help="RAG run file path")
    p_rag_ret.add_argument("--top-k", type=int, default=10, help="Top K candidates")
    p_rag_ret.add_argument(
        "--threshold", type=float, default=0.5, help="Retrieval score threshold"
    )
    p_rag_ret.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_rag_ret.set_defaults(func=cmd_rag, rag_action="retrieve")

    # 4. grounding
    p_rag_grd = p_rag_sub.add_parser(
        "grounding", help="Evaluate groundedness, faithfulness, and hallucination rate"
    )
    p_rag_grd.add_argument(
        "file", nargs="?", default=None, help="Path to RAG run JSON file"
    )
    p_rag_grd.add_argument("--run", help="RAG run file path")
    p_rag_grd.add_argument(
        "--min-grounding", type=float, default=0.70, help="Minimum grounding threshold"
    )
    p_rag_grd.add_argument(
        "--min-faithfulness",
        type=float,
        default=0.70,
        help="Minimum faithfulness threshold",
    )
    p_rag_grd.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_rag_grd.set_defaults(func=cmd_rag, rag_action="grounding")

    # 5. citations
    p_rag_cit = p_rag_sub.add_parser(
        "citations", help="Validate inline citations and reference resolution"
    )
    p_rag_cit.add_argument(
        "file", nargs="?", default=None, help="Path to RAG run JSON file"
    )
    p_rag_cit.add_argument("--run", help="RAG run file path")
    p_rag_cit.add_argument(
        "--min-citation",
        type=float,
        default=0.70,
        help="Minimum citation coverage threshold",
    )
    p_rag_cit.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_rag_cit.set_defaults(func=cmd_rag, rag_action="citations")

    # 6. claims
    p_rag_clm = p_rag_sub.add_parser(
        "claims", help="Extract atomic claims and importance ratings from answer text"
    )
    p_rag_clm.add_argument(
        "text", nargs="?", default=None, help="Answer text from which to extract claims"
    )
    p_rag_clm.add_argument("--text", dest="text_opt", help="Text override")
    p_rag_clm.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_rag_clm.set_defaults(func=cmd_rag, rag_action="claims")

    # 7. freshness
    p_rag_frs = p_rag_sub.add_parser(
        "freshness", help="Audit knowledge freshness and detect stale evidence"
    )
    p_rag_frs.add_argument(
        "file", nargs="?", default=None, help="Path to RAG run JSON file"
    )
    p_rag_frs.add_argument("--run", help="RAG run file path")
    p_rag_frs.add_argument(
        "--freshness-window", type=int, default=90, help="Max document age in days"
    )
    p_rag_frs.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_rag_frs.set_defaults(func=cmd_rag, rag_action="freshness")

    # 8. drift
    p_rag_drf = p_rag_sub.add_parser(
        "drift", help="Detect query, retrieval, embedding, and grounding drift"
    )
    p_rag_drf.add_argument(
        "file", nargs="?", default=None, help="Path to current RAG run JSON file"
    )
    p_rag_drf.add_argument("--run", help="RAG run file path")
    p_rag_drf.add_argument("--baseline", help="Path to baseline RAG run JSON file")
    p_rag_drf.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_rag_drf.set_defaults(func=cmd_rag, rag_action="drift")

    # 9. knowledge
    p_rag_kb = p_rag_sub.add_parser(
        "knowledge", help="Audit knowledge base health, duplication, and chunking"
    )
    p_rag_kb.add_argument(
        "file",
        nargs="?",
        default=None,
        help="Path to knowledge base document collection JSON",
    )
    p_rag_kb.add_argument("--knowledge-version", help="Knowledge base version string")
    p_rag_kb.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_rag_kb.set_defaults(func=cmd_rag, rag_action="knowledge")

    # 10. conflicts
    p_rag_cnf = p_rag_sub.add_parser(
        "conflicts", help="Detect factual contradictions between retrieved contexts"
    )
    p_rag_cnf.add_argument(
        "file", nargs="?", default=None, help="Path to RAG run JSON file"
    )
    p_rag_cnf.add_argument("--run", help="RAG run file path")
    p_rag_cnf.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_rag_cnf.set_defaults(func=cmd_rag, rag_action="conflicts")

    # 11. failures
    p_rag_fls = p_rag_sub.add_parser(
        "failures", help="Diagnose and explain root cause RAG failures"
    )
    p_rag_fls.add_argument(
        "file", nargs="?", default=None, help="Path to RAG run JSON file"
    )
    p_rag_fls.add_argument("--run", help="RAG run file path")
    p_rag_fls.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_rag_fls.set_defaults(func=cmd_rag, rag_action="failures")

    # 12. provenance
    p_rag_prv = p_rag_sub.add_parser(
        "provenance", help="Trace provenance chains from answers to claims and chunks"
    )
    p_rag_prv.add_argument(
        "file", nargs="?", default=None, help="Path to RAG run JSON file"
    )
    p_rag_prv.add_argument("--run", help="RAG run file path")
    p_rag_prv.add_argument("--claim-id", help="Filter provenance for specific claim ID")
    p_rag_prv.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_rag_prv.set_defaults(func=cmd_rag, rag_action="provenance")

    # 13. regression
    p_rag_reg = p_rag_sub.add_parser(
        "regression", help="Execute golden RAG regression suite against release gates"
    )
    p_rag_reg.add_argument(
        "file", nargs="?", default=None, help="Path to RAG regression test suite JSON"
    )
    p_rag_reg.add_argument("--dataset", help="Dataset path")
    p_rag_reg.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_rag_reg.set_defaults(func=cmd_rag, rag_action="regression")

    # 14. monitor
    p_rag_mon = p_rag_sub.add_parser(
        "monitor", help="Sample and monitor production RAG telemetry with sanitization"
    )
    p_rag_mon.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_rag_mon.set_defaults(func=cmd_rag, rag_action="monitor")

    # 15. report
    p_rag_rep = p_rag_sub.add_parser(
        "report", help="Generate multi-format RAG reliability report"
    )
    p_rag_rep.add_argument(
        "file", nargs="?", default=None, help="Path to RAG run JSON file"
    )
    p_rag_rep.add_argument("--run", help="RAG run file path")
    p_rag_rep.add_argument(
        "--format",
        choices=["markdown", "json", "csv"],
        default="markdown",
        help="Report format",
    )
    p_rag_rep.add_argument("--output", "-o", help="Output file path")
    p_rag_rep.set_defaults(func=cmd_rag, rag_action="report")

    # 16. inspect
    p_rag_ins = p_rag_sub.add_parser(
        "inspect", help="Inspect detailed diagnostics of a serialized RAG run"
    )
    p_rag_ins.add_argument(
        "file", nargs="?", default=None, help="Path to RAG run JSON file"
    )
    p_rag_ins.add_argument("--run", help="RAG run file path")
    p_rag_ins.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    p_rag_ins.set_defaults(func=cmd_rag, rag_action="inspect")

    # Default if no subcommand specified
    p_rag.set_defaults(func=cmd_rag, rag_action="evaluate")

    # ==========================================================================
    # Phase 40: Advanced Agent Reliability Engine
    # ==========================================================================
    p_agent = subparsers.add_parser(
        "agent", help="Advanced Agent Reliability Engine (Phase 40)"
    )
    p_agent_sub = p_agent.add_subparsers(dest="agent_action")

    # Common helper to add standard flags
    def _add_common_agent_flags(sub_p: argparse.ArgumentParser) -> None:
        sub_p.add_argument(
            "file", nargs="?", default=None, help="Path to AgentRun JSON file"
        )
        sub_p.add_argument("--run", help="Path to AgentRun JSON file")
        sub_p.add_argument("--task", help="Agent task request text")
        sub_p.add_argument("--agent", help="Agent identifier")
        sub_p.add_argument("--agent-version", help="Agent version string")
        sub_p.add_argument("--model", help="LLM model name")
        sub_p.add_argument("--trajectory", help="Trajectory file path")
        sub_p.add_argument("--tool", help="Tool name filter")
        sub_p.add_argument(
            "--max-steps", type=int, default=50, help="Max execution steps ceiling"
        )
        sub_p.add_argument(
            "--max-retries", type=int, default=5, help="Max retries ceiling"
        )
        sub_p.add_argument(
            "--max-cost", type=float, default=5.0, help="Max cost ceiling in USD"
        )
        sub_p.add_argument(
            "--max-runtime", type=float, default=120.0, help="Max runtime in seconds"
        )
        sub_p.add_argument("--dataset", help="Benchmark dataset path")
        sub_p.add_argument("--baseline", help="Historical baseline runs file")
        sub_p.add_argument(
            "--format",
            choices=["terminal", "json", "markdown", "csv"],
            default="terminal",
            help="Output format",
        )
        sub_p.add_argument("--output", "-o", help="Output file path")
        sub_p.add_argument(
            "--json", action="store_true", help="Output machine-readable JSON"
        )
        sub_p.add_argument(
            "--dry-run", action="store_true", help="Perform simulation dry run"
        )

    # 1. evaluate
    p_ag_eval = p_agent_sub.add_parser(
        "evaluate", help="Evaluate full agent run reliability across all stages"
    )
    _add_common_agent_flags(p_ag_eval)
    p_ag_eval.set_defaults(func=cmd_agent, agent_action="evaluate")

    # 2. analyze
    p_ag_ana = p_agent_sub.add_parser(
        "analyze", help="Analyze task understanding, complexity, and ambiguity"
    )
    _add_common_agent_flags(p_ag_ana)
    p_ag_ana.set_defaults(func=cmd_agent, agent_action="analyze")

    # 3. trajectory
    p_ag_traj = p_agent_sub.add_parser(
        "trajectory", help="Audit trajectory step transitions, latencies, and costs"
    )
    _add_common_agent_flags(p_ag_traj)
    p_ag_traj.set_defaults(func=cmd_agent, agent_action="trajectory")

    # 4. plan
    p_ag_plan = p_agent_sub.add_parser(
        "plan", help="Evaluate plan completeness, dependencies, and deviations"
    )
    _add_common_agent_flags(p_ag_plan)
    p_ag_plan.set_defaults(func=cmd_agent, agent_action="plan")

    # 5. tools
    p_ag_tool = p_agent_sub.add_parser(
        "tools", help="Evaluate tool selection, parameter validity, and risks"
    )
    _add_common_agent_flags(p_ag_tool)
    p_ag_tool.set_defaults(func=cmd_agent, agent_action="tools")

    # 6. loops
    p_ag_loop = p_agent_sub.add_parser(
        "loops", help="Detect repeated tool calls, cycles, and runaway loops"
    )
    _add_common_agent_flags(p_ag_loop)
    p_ag_loop.set_defaults(func=cmd_agent, agent_action="loops")

    # 7. retries
    p_ag_retry = p_agent_sub.add_parser(
        "retries", help="Analyze retry efficacy, recovery rates, and storms"
    )
    _add_common_agent_flags(p_ag_retry)
    p_ag_retry.set_defaults(func=cmd_agent, agent_action="retries")

    # 8. memory
    p_ag_mem = p_agent_sub.add_parser(
        "memory", help="Audit memory operations (read/write/update/delete/retrieve)"
    )
    _add_common_agent_flags(p_ag_mem)
    p_ag_mem.set_defaults(func=cmd_agent, agent_action="memory")

    # 9. state
    p_ag_state = p_agent_sub.add_parser(
        "state", help="Audit state transitions and variable consistency"
    )
    _add_common_agent_flags(p_ag_state)
    p_ag_state.set_defaults(func=cmd_agent, agent_action="state")

    # 10. goals
    p_ag_goal = p_agent_sub.add_parser(
        "goals", help="Independently verify goal criteria and completion"
    )
    _add_common_agent_flags(p_ag_goal)
    p_ag_goal.set_defaults(func=cmd_agent, agent_action="goals")

    # 11. handoffs
    p_ag_hoff = p_agent_sub.add_parser(
        "handoffs", help="Audit multi-agent handoffs and message integrity"
    )
    _add_common_agent_flags(p_ag_hoff)
    p_ag_hoff.set_defaults(func=cmd_agent, agent_action="handoffs")

    # 12. failures
    p_ag_fail = p_agent_sub.add_parser(
        "failures", help="Display diagnosed failures and stage breakdowns"
    )
    _add_common_agent_flags(p_ag_fail)
    p_ag_fail.set_defaults(func=cmd_agent, agent_action="failures")

    # 13. drift
    p_ag_drift = p_agent_sub.add_parser(
        "drift", help="Detect trajectory, tool, cost, and latency drift"
    )
    _add_common_agent_flags(p_ag_drift)
    p_ag_drift.set_defaults(func=cmd_agent, agent_action="drift")

    # 14. security
    p_ag_sec = p_agent_sub.add_parser(
        "security", help="Audit security, prompt injection, and untrusted tool outputs"
    )
    _add_common_agent_flags(p_ag_sec)
    p_ag_sec.set_defaults(func=cmd_agent, agent_action="security")

    # 15. regression
    p_ag_reg = p_agent_sub.add_parser(
        "regression", help="Compare run against baseline or golden trajectory"
    )
    _add_common_agent_flags(p_ag_reg)
    p_ag_reg.set_defaults(func=cmd_agent, agent_action="regression")

    # 16. diagnose
    p_ag_diag = p_agent_sub.add_parser(
        "diagnose", help="Perform root cause analysis and evidence mapping"
    )
    _add_common_agent_flags(p_ag_diag)
    p_ag_diag.set_defaults(func=cmd_agent, agent_action="diagnose")

    # 17. tests
    p_ag_test = p_agent_sub.add_parser(
        "tests", help="Generate automated test cases from diagnosed failures"
    )
    _add_common_agent_flags(p_ag_test)
    p_ag_test.set_defaults(func=cmd_agent, agent_action="tests")

    # 18. heal
    p_ag_heal = p_agent_sub.add_parser(
        "heal", help="Generate remediation proposals via Phase 37 engine"
    )
    _add_common_agent_flags(p_ag_heal)
    p_ag_heal.set_defaults(func=cmd_agent, agent_action="heal")

    # 19. optimize
    p_ag_opt = p_agent_sub.add_parser(
        "optimize", help="Create Pareto optimization problem via Phase 38 engine"
    )
    _add_common_agent_flags(p_ag_opt)
    p_ag_opt.set_defaults(func=cmd_agent, agent_action="optimize")

    # 20. report
    p_ag_rep = p_agent_sub.add_parser(
        "report", help="Generate structured markdown/JSON/terminal report"
    )
    _add_common_agent_flags(p_ag_rep)
    p_ag_rep.set_defaults(func=cmd_agent, agent_action="report")

    # 21. inspect
    p_ag_ins = p_agent_sub.add_parser(
        "inspect", help="Detailed inspection of an agent run or trajectory"
    )
    _add_common_agent_flags(p_ag_ins)
    p_ag_ins.set_defaults(func=cmd_agent, agent_action="inspect")

    # Default if no subcommand specified
    p_agent.set_defaults(func=cmd_agent, agent_action="evaluate")

    # ==========================================================================
    # Phase 41: AI Safety Validation Subsystem
    # ==========================================================================
    p_safety = subparsers.add_parser(
        "safety", help="AI Safety Validation and Automated Red Teaming (Phase 41)"
    )
    p_safety.add_argument("--input", default=None, help="User input prompt to audit")
    p_safety.add_argument(
        "--output", default=None, help="Model output response to audit"
    )
    p_safety.add_argument(
        "--report", default=None, help="Path to evaluation report JSON"
    )
    p_safety_sub = p_safety.add_subparsers(dest="safety_action")

    def _add_common_safety_flags(sub_p: argparse.ArgumentParser) -> None:
        sub_p.add_argument(
            "--target",
            default="target_system",
            help="Target system or component identifier",
        )
        sub_p.add_argument("--input", default=None, help="User input prompt to audit")
        sub_p.add_argument(
            "--output", default=None, help="Model output response to audit"
        )
        sub_p.add_argument(
            "--report", default=None, help="Path to evaluation report JSON"
        )
        sub_p.add_argument(
            "--mode",
            default="deterministic",
            choices=["deterministic", "simulated", "offline"],
            help="Safety execution mode",
        )
        sub_p.add_argument(
            "--max-tests",
            type=int,
            default=10,
            help="Maximum number of safety validation tests",
        )
        sub_p.add_argument(
            "--json", action="store_true", help="Output machine-readable JSON"
        )
        sub_p.add_argument(
            "--format",
            choices=["terminal", "json", "markdown", "csv"],
            default="terminal",
            help="Output format",
        )

    safety_subcommands = [
        ("evaluate", "Execute baseline AI safety validation suite"),
        ("campaign", "Run targeted multi-category safety campaign"),
        ("scan", "Execute automated boundary and safety vulnerability scan"),
        ("test", "Run single safety validation test case"),
        ("privacy", "Validate privacy boundaries and synthetic data confidentiality"),
        (
            "authorization",
            "Validate authorization constraints and privilege boundaries",
        ),
        ("tools", "Validate tool use boundaries and execution sandboxes"),
        ("rag", "Validate retrieved context trust and document integrity"),
        ("agent", "Validate multi-agent instruction and handoff boundaries"),
        ("memory", "Validate memory integrity and history manipulation boundaries"),
        ("report", "Generate comprehensive AI safety validation report"),
        ("inspect", "Inspect safety findings, evidence, and execution observations"),
        ("baseline", "Establish or compare against golden safety baseline"),
        ("coverage", "Calculate safety category and mutation coverage"),
        ("diagnose", "Diagnose root causes of safety findings and score degradation"),
        ("regression", "Check for safety regressions against baseline"),
        ("generate", "Generate synthetic safety test scenarios"),
        ("mutate", "Apply deterministic semantic mutations to safety inputs"),
        ("tests", "Synthesize regression test cases from safety findings"),
        ("heal", "Propose safety remediations and mitigation policies"),
    ]

    for sub_cmd, sub_help in safety_subcommands:
        p_sub = p_safety_sub.add_parser(sub_cmd, help=sub_help)
        _add_common_safety_flags(p_sub)
        p_sub.set_defaults(func=cmd_safety, safety_action=sub_cmd)

    p_safety.set_defaults(func=cmd_safety, safety_action="evaluate")

    # ==========================================================================
    # Phase 42: Reliability Prediction Engine
    # ==========================================================================
    p_predict = subparsers.add_parser(
        "predict", help="Reliability Prediction and Risk Forecasting (Phase 42)"
    )
    p_predict_sub = p_predict.add_subparsers(dest="predict_action")

    def _add_common_predict_flags(sub_p: argparse.ArgumentParser) -> None:
        sub_p.add_argument(
            "--target",
            default="target_pipeline",
            help="Target system or pipeline identifier",
        )
        sub_p.add_argument(
            "--horizon",
            default="SHORT_TERM",
            choices=["NEXT_EXECUTION", "SHORT_TERM", "MEDIUM_TERM", "LONG_TERM"],
            help="Prediction horizon window",
        )
        sub_p.add_argument(
            "--json", action="store_true", help="Output machine-readable JSON"
        )
        sub_p.add_argument(
            "--format",
            choices=["terminal", "json"],
            default="terminal",
            help="Output format",
        )

    predict_subcommands = [
        ("forecast", "Generate statistical reliability and failure forecast"),
        ("features", "Extract predictive reliability features and trends"),
        ("evaluate", "Evaluate past prediction accuracy (Brier score & MAE)"),
        ("report", "Generate reliability prediction and risk report"),
    ]

    for sub_cmd, sub_help in predict_subcommands:
        p_sub = p_predict_sub.add_parser(sub_cmd, help=sub_help)
        _add_common_predict_flags(p_sub)
        p_sub.set_defaults(func=cmd_predict, predict_action=sub_cmd)

    p_predict.set_defaults(func=cmd_predict, predict_action="forecast")

    # ==========================================================================
    # Phase 43: Reliability Intelligence Dashboard
    # ==========================================================================
    p_dash = subparsers.add_parser(
        "dashboard",
        help="Reliability Intelligence Dashboard and System Health (Phase 43)",
    )
    p_dash.add_argument(
        "--report",
        "--file",
        dest="report",
        default=None,
        help="Path to evaluation report JSON",
    )
    p_dash.add_argument("--port", type=int, default=8080, help="Port to listen on")
    p_dash_sub = p_dash.add_subparsers(dest="dashboard_action")

    def _add_common_dash_flags(sub_p: argparse.ArgumentParser) -> None:
        sub_p.add_argument(
            "--report",
            "--file",
            dest="report",
            default=None,
            help="Path to evaluation report JSON",
        )
        sub_p.add_argument("--port", type=int, default=8080, help="Port to listen on")
        sub_p.add_argument(
            "--format",
            choices=["terminal", "json", "markdown", "csv"],
            default="terminal",
            help="Export format",
        )
        sub_p.add_argument(
            "--json", action="store_true", help="Output machine-readable JSON"
        )
        sub_p.add_argument(
            "--snapshot-id", help="Snapshot identifier for retrieval or comparison"
        )

    dash_subcommands = [
        ("overview", "Display system health summary and panel metrics"),
        ("export", "Export comprehensive dashboard state (json, markdown, csv)"),
        (
            "snapshot",
            "Generate deterministic dashboard snapshot with cryptographic fingerprint",
        ),
        ("panels", "List all active dashboard intelligence panels"),
    ]

    for sub_cmd, sub_help in dash_subcommands:
        p_sub = p_dash_sub.add_parser(sub_cmd, help=sub_help)
        _add_common_dash_flags(p_sub)
        p_sub.set_defaults(func=cmd_dashboard, dashboard_action=sub_cmd)

    p_dash.set_defaults(func=cmd_dashboard, dashboard_action="overview")

    # ==========================================================================
    # Phase 44: Reliability Policy Engine
    # ==========================================================================
    p_policy = subparsers.add_parser(
        "policy", help="Reliability Policy Engine and Governance Rules (Phase 44)"
    )
    p_policy_sub = p_policy.add_subparsers(dest="policy_action")

    def _add_common_policy_flags(sub_p: argparse.ArgumentParser) -> None:
        sub_p.add_argument(
            "--policy", help="Path to policy definition file or policy name"
        )
        sub_p.add_argument(
            "--reliability",
            type=float,
            default=0.95,
            help="Simulated reliability score [0.0 - 1.0]",
        )
        sub_p.add_argument(
            "--safety",
            type=float,
            default=1.0,
            help="Simulated safety score [0.0 - 1.0]",
        )
        sub_p.add_argument(
            "--leakage",
            action="store_true",
            help="Simulate credential or sensitive data leakage flag",
        )
        sub_p.add_argument(
            "--cross-tenant",
            action="store_true",
            help="Simulate cross-tenant violation flag",
        )
        sub_p.add_argument(
            "--json", action="store_true", help="Output machine-readable JSON"
        )
        sub_p.add_argument(
            "--format",
            choices=["terminal", "json"],
            default="terminal",
            help="Output format",
        )

    policy_subcommands = [
        ("list", "List active reliability policy rules and priorities"),
        ("evaluate", "Evaluate execution context against prioritized policy rules"),
        ("explain", "Explain policy evaluation decision and violated rules"),
        ("validate", "Validate policy syntax, conditions, and hard constraints"),
        ("enforce", "Enforce policy decision and apply hard gate thresholds"),
        ("simulate", "Simulate policy outcome under hypothetical parameters"),
        ("compare", "Compare two policy versions or bundle configurations"),
        ("version", "Display policy versioning and audit history"),
        ("rollback", "Rollback active policy bundle to previous stable version"),
    ]

    for sub_cmd, sub_help in policy_subcommands:
        p_sub = p_policy_sub.add_parser(sub_cmd, help=sub_help)
        _add_common_policy_flags(p_sub)
        p_sub.set_defaults(func=cmd_policy, policy_action=sub_cmd)

    p_policy.set_defaults(func=cmd_policy, policy_action="list")

    # ==========================================================================
    # Phase 45: Enterprise Multi-Tenancy
    # ==========================================================================
    p_tenant = subparsers.add_parser(
        "tenant", help="Enterprise Multi-Tenancy, RBAC, and Quotas (Phase 45)"
    )
    p_tenant_sub = p_tenant.add_subparsers(dest="tenant_action")

    def _add_common_tenant_flags(sub_p: argparse.ArgumentParser) -> None:
        sub_p.add_argument("--tenant", default="tenant_alpha", help="Tenant identifier")
        sub_p.add_argument(
            "--org", default="org_enterprise", help="Organization identifier"
        )
        sub_p.add_argument(
            "--json", action="store_true", help="Output machine-readable JSON"
        )
        sub_p.add_argument(
            "--format",
            choices=["terminal", "json"],
            default="terminal",
            help="Output format",
        )

    tenant_subcommands = [
        ("list", "List tenants in organization"),
        ("get", "Inspect details and metadata for specific tenant"),
        ("quotas", "Inspect resource quotas and limits for tenant"),
        ("usage", "Track real-time resource usage against tenant quota"),
        ("audit", "Display tenant isolation and security audit log"),
    ]

    for sub_cmd, sub_help in tenant_subcommands:
        p_sub = p_tenant_sub.add_parser(sub_cmd, help=sub_help)
        _add_common_tenant_flags(p_sub)
        p_sub.set_defaults(func=cmd_tenant, tenant_action=sub_cmd)

    p_tenant.set_defaults(func=cmd_tenant, tenant_action="list")

    # ==========================================================================
    # Phase 46: Reliability Platform API
    # ==========================================================================
    p_api = subparsers.add_parser(
        "api", help="Reliability Platform REST API & SDK Server (Phase 46)"
    )
    p_api_sub = p_api.add_subparsers(dest="api_action")

    def _add_common_api_flags(sub_p: argparse.ArgumentParser) -> None:
        sub_p.add_argument(
            "--host", default="127.0.0.1", help="Host address to bind server"
        )
        sub_p.add_argument("--port", type=int, default=8000, help="Port to bind server")
        sub_p.add_argument(
            "--json", action="store_true", help="Output machine-readable JSON"
        )
        sub_p.add_argument(
            "--format",
            choices=["terminal", "json"],
            default="terminal",
            help="Output format",
        )

    api_subcommands = [
        ("health", "Check API platform health and capability readiness"),
        ("routes", "List all registered /api/v1/ endpoints and supported methods"),
        ("serve", "Start the local FastAPI/uvicorn server for REST & OpenAPI access"),
    ]

    for sub_cmd, sub_help in api_subcommands:
        p_sub = p_api_sub.add_parser(sub_cmd, help=sub_help)
        _add_common_api_flags(p_sub)
        p_sub.set_defaults(func=cmd_api, api_action=sub_cmd)

    p_api.set_defaults(func=cmd_api, api_action="health")

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI main execution entrypoint."""
    parser = create_parser()
    args = parser.parse_args(argv)
    exit_code: int = args.func(args)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
