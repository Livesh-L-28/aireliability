"""Regression test suite execution and validation against agent and baselines."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from aireliability.core.models import (
    RegressionTest,
    RunResult,
    TraceStep,
)
from aireliability.core.protocols import Evaluator
from aireliability.execution.runner import ReliabilityRunner
from aireliability.regression.baseline import (
    BaselineComparisonSummary,
    BaselineManager,
    ComparisonResult,
)


@dataclass
class RegressionSuiteResult:
    """Consolidated outcome of running a suite of RegressionTests."""

    total_runs: int
    passed_count: int
    failed_count: int
    results: list[RunResult] = field(default_factory=list)
    regression_tests: list[RegressionTest] = field(default_factory=list)
    comparison_summary: BaselineComparisonSummary | None = None

    @property
    def all_passed(self) -> bool:
        """True if every regression test in the suite passed."""
        return self.failed_count == 0


class RegressionRunner:
    """Executes suites of RegressionTests and tracks regressions against baselines."""

    def __init__(
        self,
        agent: Any = None,
        evaluators: Sequence[Evaluator] | None = None,
        *,
        adapter: Any = None,
        baseline_manager: BaselineManager | None = None,
        suppress_agent_exceptions: bool = True,
        telemetry_collector: Any | None = None,
    ) -> None:
        """Initialize RegressionRunner.

        Args:
            agent: The AI agent or callable to run.
            evaluators: Evaluators/expectations to evaluate on each execution.
            adapter: Optional ExecutionAdapter.
            baseline_manager: Optional BaselineManager for automatic regression
                checking.
            suppress_agent_exceptions: If True (default for test suites), crashes are
                recorded as failures in RunResult rather than halting suite execution.
            telemetry_collector: Optional TelemetryCollector to record test telemetry.
        """
        self.runner = ReliabilityRunner(
            agent=agent,
            evaluators=evaluators,
            adapter=adapter,
            suppress_agent_exceptions=suppress_agent_exceptions,
            telemetry_collector=telemetry_collector,
        )
        self.baseline_manager = baseline_manager
        self.telemetry_collector = telemetry_collector

    def run_test(
        self,
        regression_test: RegressionTest,
        steps: list[TraceStep] | None = None,
    ) -> RunResult:
        """Execute a single RegressionTest.

        Args:
            regression_test: The regression test case to execute.
            steps: Optional explicit trace steps.

        Returns:
            The RunResult from executing the test case.
        """
        return self.runner.run(regression_test.test_case, steps=steps)

    def run_suite(
        self,
        regression_tests: list[RegressionTest],
        *,
        compare_baseline: str | None = None,
    ) -> RegressionSuiteResult:
        """Execute an entire suite of RegressionTests.

        Args:
            regression_tests: Sequence of regression tests to execute.
            compare_baseline: Optional baseline name to compare results against.

        Returns:
            A RegressionSuiteResult detailing all executions and baseline comparisons.
        """
        results: list[RunResult] = []
        for reg_test in regression_tests:
            run_res = self.run_test(reg_test)
            results.append(run_res)

        passed_count = sum(1 for r in results if r.passed)
        failed_count = len(results) - passed_count

        comparison_summary: BaselineComparisonSummary | None = None
        if compare_baseline and self.baseline_manager is not None:
            comparison_summary = self.baseline_manager.compare(
                current_results=results,
                baseline_name=compare_baseline,
            )

        return RegressionSuiteResult(
            total_runs=len(results),
            passed_count=passed_count,
            failed_count=failed_count,
            results=results,
            regression_tests=regression_tests,
            comparison_summary=comparison_summary,
        )

    async def run_suite_async(
        self,
        regression_tests: list[RegressionTest],
        *,
        max_concurrency: int = 5,
        test_timeout_seconds: float | None = 60.0,
        compare_baseline: str | None = None,
    ) -> RegressionSuiteResult:
        """Execute an entire suite of RegressionTests concurrently.

        Args:
            regression_tests: Sequence of regression tests to execute.
            max_concurrency: Maximum number of concurrent executions (default: 5).
            test_timeout_seconds: Timeout per individual test execution.
            compare_baseline: Optional baseline name to compare results against.

        Returns:
            A RegressionSuiteResult detailing all executions and baseline comparisons
            with deterministic test ordering preserved.
        """
        from aireliability.distributed.runner import AsyncReliabilityRunner

        async_runner = AsyncReliabilityRunner(
            agent=self.runner.agent,
            adapter=self.runner.adapter,
            evaluators=self.runner.evaluators,
            max_concurrency=max_concurrency,
            test_timeout_seconds=test_timeout_seconds,
            telemetry_collector=self.telemetry_collector,
        )

        test_cases = [rt.test_case for rt in regression_tests]
        summary = await async_runner.execute_many(test_cases)
        results = summary.results

        passed_count = sum(1 for r in results if r.passed)
        failed_count = len(results) - passed_count

        comparison_summary: BaselineComparisonSummary | None = None
        if compare_baseline and self.baseline_manager is not None:
            comparison_summary = self.baseline_manager.compare(
                current_results=results,
                baseline_name=compare_baseline,
            )

        return RegressionSuiteResult(
            total_runs=len(results),
            passed_count=passed_count,
            failed_count=failed_count,
            results=results,
            regression_tests=regression_tests,
            comparison_summary=comparison_summary,
        )

    def compare_against_baseline(
        self,
        run_results: list[RunResult],
        baseline_name: str = "default",
    ) -> BaselineComparisonSummary:
        """Compare a list of run results against a named baseline."""
        if self.baseline_manager is None:
            raise ValueError("BaselineManager was not configured on RegressionRunner.")
        return self.baseline_manager.compare(run_results, baseline_name=baseline_name)


__all__ = [
    "ComparisonResult",
    "RegressionRunner",
    "RegressionSuiteResult",
]
