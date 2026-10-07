"""Unit tests for package imports and core models."""

import aireliability
from aireliability.core import (
    AIReliabilityError,
    EvaluationError,
    EvaluationResult,
    Evaluator,
    ExecutionAdapter,
    ExecutionError,
    ExecutionStatus,
    ExecutionTrace,
    Expectation,
    FailureAnalysisError,
    FailureReport,
    FailureSeverity,
    RegressionTest,
    RegressionTestError,
    RunResult,
    StepType,
    StorageError,
    TestCase,
    Traceable,
    TraceStep,
)
from aireliability.evaluation import (
    AssertionResult,
    BaseExpectation,
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
from aireliability.execution import ReliabilityRunner, Runner
from aireliability.failures import (
    FailureAnalyzer,
    FailureCategory,
    FailureTaxonomy,
    FailureType,
)
from aireliability.regression import (
    BaselineManager,
    ComparisonStatus,
    RegressionGenerator,
    RegressionRunner,
)
from aireliability.storage import SQLiteStorage, StorageBackend


def test_package_import_and_version() -> None:
    """Verify that aireliability can be imported and has a valid version."""
    assert aireliability.__version__ == "1.4.0"


def test_core_models_instantiation() -> None:
    """Verify basic instantiation of core models."""
    step = TraceStep(name="step_1", input={"query": "test"})
    assert step.name == "step_1"
    assert step.input["query"] == "test"

    trace = ExecutionTrace(steps=[step])
    assert trace.trace_id.startswith("trace_")
    assert len(trace.steps) == 1
    assert trace.steps[0].name == "step_1"


def test_runner_execution() -> None:
    """Verify basic runner trace capture."""
    result, trace = Runner.run_callable(lambda x: x * 2, 21, task_name="doubler")
    assert result == 42
    assert len(trace.steps) == 1
    assert trace.steps[0].output == {"result": "42"}


def test_assertion_result() -> None:
    """Verify assertion result model."""
    res = AssertionResult(name="format_check", passed=True, message="Looks good")
    assert res.passed is True
    assert res.name == "format_check"


def test_exceptions_hierarchy() -> None:
    """Verify exception inheritance."""
    for exc in (
        ExecutionError,
        EvaluationError,
        FailureAnalysisError,
        RegressionTestError,
        StorageError,
    ):
        assert issubclass(exc, AIReliabilityError)


def test_protocols() -> None:
    """Verify protocols can be referenced."""
    assert isinstance(Traceable, type)
    assert isinstance(ExecutionAdapter, type)
    assert isinstance(Evaluator, type)
    assert isinstance(Expectation, type)
    assert isinstance(BaseExpectation, type)


def test_all_public_models_imported() -> None:
    """Verify all public models can be imported from aireliability root."""
    for cls in (
        TestCase,
        TraceStep,
        ExecutionTrace,
        EvaluationResult,
        FailureReport,
        RegressionTest,
        RunResult,
        StepType,
        ExecutionStatus,
        FailureSeverity,
        ExecutionAdapter,
        Evaluator,
        Expectation,
        BaseExpectation,
        ToolCalled,
        ToolNotCalled,
        ToolOrder,
        ToolArguments,
        OutputEquals,
        OutputContains,
        SchemaMatch,
        MaxLatency,
        MaxCost,
        ReliabilityRunner,
        Runner,
        FailureAnalyzer,
        FailureCategory,
        FailureTaxonomy,
        FailureType,
        RegressionGenerator,
        RegressionRunner,
        BaselineManager,
        ComparisonStatus,
        StorageBackend,
        SQLiteStorage,
        StorageError,
    ):
        assert hasattr(aireliability, cls.__name__)
