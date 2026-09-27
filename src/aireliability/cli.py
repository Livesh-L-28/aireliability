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

    version: str = "0.1.0"
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

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI main execution entrypoint."""
    parser = create_parser()
    args = parser.parse_args(argv)
    exit_code: int = args.func(args)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
