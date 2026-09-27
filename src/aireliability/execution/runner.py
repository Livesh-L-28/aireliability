"""Execution runner and tracing abstractions."""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from aireliability.core.models import (
    EvaluationResult,
    ExecutionStatus,
    ExecutionTrace,
    FailureReport,
    RunResult,
    StepType,
    TestCase,
    TraceStep,
)
from aireliability.core.protocols import Evaluator
from aireliability.failures.analyzer import FailureAnalyzer


class ReliabilityRunner:
    """Execution engine that runs an agent against a TestCase, captures an

    ExecutionTrace, executes configured evaluators, and compiles a comprehensive
    RunResult.
    """

    def __init__(
        self,
        agent: Callable[[Any], Any] | Any | None = None,
        evaluators: Sequence[Evaluator] | None = None,
        *,
        adapter: Any = None,
        failure_analyzer: FailureAnalyzer | None = None,
        suppress_agent_exceptions: bool = False,
        telemetry_collector: Any | None = None,
    ) -> None:
        """Initialize ReliabilityRunner.

        Args:
            agent: The AI agent or callable to run. Can be None if provided via adapter.
            evaluators: Sequence of evaluators/expectations to run on the trace.
            adapter: Optional ExecutionAdapter for custom agent invocations.
            failure_analyzer: Optional FailureAnalyzer instance.
            suppress_agent_exceptions: If True, agent exceptions will be captured in the
                trace and failure report without re-raising. If False (default), the
                exception is re-raised after trace capture.
            telemetry_collector: Optional TelemetryCollector (e.g.
                InMemoryTelemetryCollector, JsonTelemetryCollector) to record
                production telemetry traces.
        """
        if agent is None and adapter is None:
            raise ValueError(
                "Either an agent or an adapter must be provided to ReliabilityRunner."
            )

        self.agent = agent
        self.evaluators = list(evaluators or [])
        self.adapter = adapter
        self.failure_analyzer = failure_analyzer or FailureAnalyzer()
        self.suppress_agent_exceptions = suppress_agent_exceptions
        self.telemetry_collector = telemetry_collector

    def run(
        self,
        test_case: TestCase,
        steps: list[TraceStep] | None = None,
    ) -> RunResult:
        """Execute agent against test case, run evaluators, and produce RunResult.

        Args:
            test_case: The test case specification containing input and expectations.
            steps: Optional explicit trace steps supplied by caller or adapter.

        Returns:
            A RunResult containing the test case, trace, evaluation results, and status.
        """
        start_time = datetime.now(UTC)
        trace_steps: list[TraceStep] = list(steps or [])
        captured_output: Any = None
        status = ExecutionStatus.COMPLETED
        agent_exception: BaseException | None = None

        try:
            if self.adapter is not None:
                # Use provided execution adapter
                if self.agent is not None:
                    trace = self.adapter.execute(self.agent, test_case)
                else:
                    trace = self.adapter.execute(test_case=test_case)
                # Combine supplied steps if any
                if trace_steps:
                    trace = trace.model_copy(
                        update={"steps": list(trace.steps) + trace_steps}
                    )
            elif callable(self.agent):
                captured_output = self.agent(test_case.input)
                end_time = datetime.now(UTC)
                trace = ExecutionTrace(
                    test_id=test_case.id,
                    input=test_case.input,
                    output=captured_output,
                    status=ExecutionStatus.COMPLETED,
                    started_at=start_time,
                    completed_at=end_time,
                    steps=trace_steps,
                )
            elif hasattr(self.agent, "run") and callable(self.agent.run):
                captured_output = self.agent.run(test_case.input)
                end_time = datetime.now(UTC)
                trace = ExecutionTrace(
                    test_id=test_case.id,
                    input=test_case.input,
                    output=captured_output,
                    status=ExecutionStatus.COMPLETED,
                    started_at=start_time,
                    completed_at=end_time,
                    steps=trace_steps,
                )
            else:
                raise TypeError(
                    f"Agent of type {type(self.agent).__name__} is neither callable "
                    f"nor provides a .run() method."
                )
        except Exception as exc:
            end_time = datetime.now(UTC)
            agent_exception = exc
            status = ExecutionStatus.FAILED
            trace = ExecutionTrace(
                test_id=test_case.id,
                input=test_case.input,
                output={"error": str(exc), "error_type": type(exc).__name__},
                status=status,
                started_at=start_time,
                completed_at=end_time,
                steps=trace_steps,
                metadata={"error_details": str(exc)},
            )

        # Run evaluators
        evaluation_results: list[EvaluationResult] = []
        for evaluator in self.evaluators:
            try:
                res = evaluator.evaluate(trace, test_case)
                evaluation_results.append(res)
            except Exception as eval_exc:
                evaluation_results.append(
                    EvaluationResult(
                        evaluator=getattr(evaluator, "name", str(evaluator)),
                        passed=False,
                        score=0.0,
                        message=f"Evaluator error: {eval_exc}",
                        metadata={"error": str(eval_exc)},
                    )
                )

        # Build failure reports using the deterministic failure analyzer
        failure_reports: list[FailureReport] = (
            self.failure_analyzer.analyze_trace_failures(
                trace=trace,
                evaluation_results=evaluation_results,
                test_id=test_case.id,
            )
        )

        result = RunResult(
            test=test_case,
            trace=trace,
            evaluations=evaluation_results,
            failures=failure_reports,
        )

        if self.telemetry_collector is not None:
            try:
                from aireliability.telemetry.builder import TelemetryBuilder

                builder = TelemetryBuilder()
                tel_trace = builder.build_trace(result)
                self.telemetry_collector.record(tel_trace)
            except Exception:
                # Telemetry capture failure must never break execution
                pass

        if agent_exception is not None and not self.suppress_agent_exceptions:
            # Attach the generated RunResult to the exception for inspection if needed
            agent_exception.run_result = result  # type: ignore[attr-defined]
            raise agent_exception

        return result


class Runner:
    """Basic execution runner wrapper for capturing execution traces."""

    @staticmethod
    def run_callable(
        func: Callable[..., Any],
        *args: Any,
        task_name: str = "task_execution",
        test_id: str | None = None,
        **kwargs: Any,
    ) -> tuple[Any, ExecutionTrace]:
        """Execute a callable and return its result with an execution trace."""
        start_time = datetime.now(UTC)
        step_start = datetime.now(UTC)
        step = TraceStep(
            name=f"{task_name}_call",
            type=StepType.SYSTEM,
            input={
                "args": [str(a) for a in args],
                "kwargs": {k: str(v) for k, v in kwargs.items()},
            },
            started_at=step_start,
        )
        try:
            result = func(*args, **kwargs)
            step_end = datetime.now(UTC)
            completed_step = TraceStep(
                name=f"{task_name}_call",
                type=StepType.SYSTEM,
                input=step.input,
                output={"result": str(result)},
                started_at=step_start,
                completed_at=step_end,
            )
            trace_end = datetime.now(UTC)
            trace = ExecutionTrace(
                test_id=test_id,
                input={
                    "args": [str(a) for a in args],
                    "kwargs": {k: str(v) for k, v in kwargs.items()},
                },
                output={"result": str(result)},
                status=ExecutionStatus.COMPLETED,
                started_at=start_time,
                completed_at=trace_end,
                steps=[completed_step],
            )
            return result, trace
        except Exception as exc:
            step_end = datetime.now(UTC)
            failed_step = TraceStep(
                name=f"{task_name}_call",
                type=StepType.SYSTEM,
                input=step.input,
                output={"error": str(exc), "error_type": type(exc).__name__},
                started_at=step_start,
                completed_at=step_end,
            )
            trace_end = datetime.now(UTC)
            trace = ExecutionTrace(
                test_id=test_id,
                input={
                    "args": [str(a) for a in args],
                    "kwargs": {k: str(v) for k, v in kwargs.items()},
                },
                output={"error": str(exc)},
                status=ExecutionStatus.FAILED,
                started_at=start_time,
                completed_at=trace_end,
                steps=[failed_step],
            )
            raise
