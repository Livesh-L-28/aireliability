"""Core package for AI Reliability Engine."""

from aireliability.core.exceptions import (
    AIReliabilityError,
    EvaluationError,
    ExecutionError,
    FailureAnalysisError,
    RegressionTestError,
    StorageError,
)
from aireliability.core.models import (
    EvaluationResult,
    ExecutionStatus,
    ExecutionTrace,
    FailureReport,
    FailureSeverity,
    RegressionTest,
    RunResult,
    StepType,
    TestCase,
    TraceStep,
)
from aireliability.core.protocols import (
    Evaluator,
    ExecutionAdapter,
    Expectation,
    Traceable,
)

__all__ = [
    "AIReliabilityError",
    "EvaluationError",
    "EvaluationResult",
    "Evaluator",
    "ExecutionAdapter",
    "ExecutionError",
    "ExecutionStatus",
    "ExecutionTrace",
    "Expectation",
    "FailureAnalysisError",
    "FailureReport",
    "FailureSeverity",
    "RegressionTest",
    "RegressionTestError",
    "RunResult",
    "StepType",
    "StorageError",
    "TestCase",
    "TraceStep",
    "Traceable",
]
