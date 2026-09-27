"""In-memory baseline management and comparison for test and regression tracking."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from aireliability.core.models import RunResult


class ComparisonStatus(StrEnum):
    """Status indicating how a current test outcome compares against a baseline."""

    REGRESSION = "regression"  # previously passed, now failing
    FIXED = "fixed"  # previously failing, now passing
    KNOWN_FAILURE = "known_failure"  # previously failing, still failing
    PASSING = "passing"  # previously passing, still passing
    NEW = "new"  # not present in baseline


@dataclass(frozen=True)
class BaselineEntry:
    """Historical baseline record for a single test case."""

    test_id: str
    test_name: str
    passed: bool
    run_result: RunResult
    captured_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ComparisonResult:
    """Detailed comparison between a current run result and baseline."""

    test_id: str
    test_name: str
    status: ComparisonStatus
    current_passed: bool
    baseline_passed: bool | None
    current_run: RunResult
    baseline_entry: BaselineEntry | None = None
    message: str = ""


@dataclass
class BaselineComparisonSummary:
    """Aggregated comparison report of a full test suite against baseline."""

    total_tests: int
    regressions: list[ComparisonResult] = field(default_factory=list)
    fixed: list[ComparisonResult] = field(default_factory=list)
    known_failures: list[ComparisonResult] = field(default_factory=list)
    passing: list[ComparisonResult] = field(default_factory=list)
    new_tests: list[ComparisonResult] = field(default_factory=list)

    @property
    def has_regressions(self) -> bool:
        """Return True if any regressions were detected."""
        return len(self.regressions) > 0


class BaselineManager:
    """Manages baseline snapshots and compares current runs against baselines."""

    def __init__(self) -> None:
        self._baselines: dict[str, dict[str, BaselineEntry]] = {}
        self._active_baseline_name: str = "default"

    def create_baseline(
        self,
        results: list[RunResult],
        name: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, BaselineEntry]:
        """Create or replace a baseline from a list of test RunResults.

        Args:
            results: List of RunResults representing the reference state.
            name: Identifier for the baseline (defaults to 'default').
            metadata: Optional metadata for the baseline snapshot.

        Returns:
            Dictionary mapping test_id to BaselineEntry.
        """
        baseline_store: dict[str, BaselineEntry] = {}
        meta = metadata or {}
        now = datetime.now(UTC)

        for res in results:
            entry = BaselineEntry(
                test_id=res.test.id,
                test_name=res.test.name,
                passed=bool(res.passed),
                run_result=res,
                captured_at=now,
                metadata=meta,
            )
            baseline_store[res.test.id] = entry

        self._baselines[name] = baseline_store
        self._active_baseline_name = name
        return baseline_store

    def get_baseline(self, name: str = "default") -> dict[str, BaselineEntry]:
        """Retrieve a baseline by name."""
        return dict(self._baselines.get(name, {}))

    def list_baselines(self) -> list[str]:
        """List all available baseline names."""
        return list(self._baselines.keys())

    def compare_single(
        self,
        current_result: RunResult,
        baseline_name: str = "default",
    ) -> ComparisonResult:
        """Compare a single RunResult against the baseline.

        Returns:
            ComparisonResult with status REGRESSION, FIXED, KNOWN_FAILURE,
            PASSING, or NEW.
        """
        baseline = self._baselines.get(baseline_name, {})
        test_id = current_result.test.id
        test_name = current_result.test.name
        current_passed = bool(current_result.passed)

        if test_id not in baseline:
            # Also try matching by test name if id is ephemeral
            matched_by_name = next(
                (entry for entry in baseline.values() if entry.test_name == test_name),
                None,
            )
            if matched_by_name is not None:
                entry = matched_by_name
            else:
                return ComparisonResult(
                    test_id=test_id,
                    test_name=test_name,
                    status=ComparisonStatus.NEW,
                    current_passed=current_passed,
                    baseline_passed=None,
                    current_run=current_result,
                    baseline_entry=None,
                    message=f"Test '{test_name}' is not in baseline '{baseline_name}'.",
                )
        else:
            entry = baseline[test_id]

        prev_passed = entry.passed

        if prev_passed and not current_passed:
            status = ComparisonStatus.REGRESSION
            msg = (
                f"REGRESSION: Test '{test_name}' was previously passing "
                f"and is now failing!"
            )
        elif not prev_passed and current_passed:
            status = ComparisonStatus.FIXED
            msg = (
                f"FIXED: Test '{test_name}' was previously failing and is now passing."
            )
        elif not prev_passed and not current_passed:
            status = ComparisonStatus.KNOWN_FAILURE
            msg = (
                f"KNOWN FAILURE: Test '{test_name}' was failing in baseline "
                f"and continues to fail."
            )
        else:
            status = ComparisonStatus.PASSING
            msg = f"PASSING: Test '{test_name}' remains passing."

        return ComparisonResult(
            test_id=test_id,
            test_name=test_name,
            status=status,
            current_passed=current_passed,
            baseline_passed=prev_passed,
            current_run=current_result,
            baseline_entry=entry,
            message=msg,
        )

    def compare(
        self,
        current_results: list[RunResult],
        baseline_name: str = "default",
    ) -> BaselineComparisonSummary:
        """Compare a full suite of RunResults against a baseline.

        Returns:
            BaselineComparisonSummary categorizing all results into regressions,
            fixed, known_failures, passing, and new.
        """
        summary = BaselineComparisonSummary(total_tests=len(current_results))

        for res in current_results:
            cmp_res = self.compare_single(res, baseline_name=baseline_name)
            match cmp_res.status:
                case ComparisonStatus.REGRESSION:
                    summary.regressions.append(cmp_res)
                case ComparisonStatus.FIXED:
                    summary.fixed.append(cmp_res)
                case ComparisonStatus.KNOWN_FAILURE:
                    summary.known_failures.append(cmp_res)
                case ComparisonStatus.PASSING:
                    summary.passing.append(cmp_res)
                case ComparisonStatus.NEW:
                    summary.new_tests.append(cmp_res)

        return summary


__all__ = [
    "BaselineComparisonSummary",
    "BaselineEntry",
    "BaselineManager",
    "ComparisonResult",
    "ComparisonStatus",
]
