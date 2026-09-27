"""Storage backend protocols and abstractions for AI Reliability Engine."""

from abc import ABC, abstractmethod
from typing import Any

from aireliability.core.models import (
    EvaluationResult,
    ExecutionTrace,
    FailureReport,
    RegressionTest,
    TestCase,
)
from aireliability.regression.baseline import BaselineEntry


class StorageBackend(ABC):
    """Abstract storage backend for persistence across AI Reliability Engine.

    Decouples storage engines (SQLite, PostgreSQL, etc.) from the core domain models.
    """

    # --- Lifecycle & Connection ---
    @abstractmethod
    def initialize(self) -> None:
        """Initialize storage schema, tables, and indices if they do not exist."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close connection and release underlying resources."""
        ...

    # --- Test Cases ---
    @abstractmethod
    def save_test_case(self, test_case: TestCase) -> None:
        """Persist or update a TestCase."""
        ...

    @abstractmethod
    def get_test_case(self, test_id: str) -> TestCase | None:
        """Retrieve a TestCase by ID."""
        ...

    @abstractmethod
    def list_test_cases(self, tags: list[str] | None = None) -> list[TestCase]:
        """List all test cases, optionally filtered by tags."""
        ...

    # --- Execution Traces ---
    @abstractmethod
    def save_trace(self, trace: ExecutionTrace) -> None:
        """Persist an ExecutionTrace."""
        ...

    @abstractmethod
    def get_trace(self, trace_id: str) -> ExecutionTrace | None:
        """Retrieve an ExecutionTrace by ID."""
        ...

    @abstractmethod
    def list_traces(
        self,
        test_id: str | None = None,
        limit: int = 100,
    ) -> list[ExecutionTrace]:
        """List execution traces, optionally filtered by test_id."""
        ...

    # --- Evaluations ---
    @abstractmethod
    def save_evaluations(
        self,
        trace_id: str,
        evaluations: list[EvaluationResult],
    ) -> None:
        """Persist evaluation results for an execution trace."""
        ...

    @abstractmethod
    def get_evaluations(self, trace_id: str) -> list[EvaluationResult]:
        """Retrieve all evaluations associated with a trace_id."""
        ...

    # --- Failure Reports ---
    @abstractmethod
    def save_failure(self, failure: FailureReport) -> None:
        """Persist a FailureReport."""
        ...

    @abstractmethod
    def get_failure(self, failure_id: str) -> FailureReport | None:
        """Retrieve a FailureReport by ID."""
        ...

    @abstractmethod
    def list_failures(
        self,
        category: str | None = None,
        trace_id: str | None = None,
        limit: int = 100,
    ) -> list[FailureReport]:
        """List failure reports with optional category/trace filtering."""
        ...

    # --- Regression Tests ---
    @abstractmethod
    def save_regression_test(self, regression_test: RegressionTest) -> None:
        """Persist a RegressionTest."""
        ...

    @abstractmethod
    def get_regression_test(self, regression_id: str) -> RegressionTest | None:
        """Retrieve a RegressionTest by ID."""
        ...

    @abstractmethod
    def list_regression_tests(
        self,
        source_failure_id: str | None = None,
    ) -> list[RegressionTest]:
        """List regression tests with optional failure ID filtering."""
        ...

    # --- Baselines ---
    @abstractmethod
    def save_baseline(
        self,
        name: str,
        entries: list[BaselineEntry],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Persist or update a named baseline snapshot."""
        ...

    @abstractmethod
    def get_baseline(self, name: str) -> dict[str, BaselineEntry]:
        """Retrieve all entries in a named baseline, keyed by test_id."""
        ...

    @abstractmethod
    def list_baselines(self) -> list[str]:
        """List the names of all saved baselines."""
        ...


__all__ = ["StorageBackend"]
