"""Core typing protocols for AI Reliability Engine."""

from typing import Any, Protocol, runtime_checkable

from aireliability.core.models import EvaluationResult, ExecutionTrace, TestCase


@runtime_checkable
class Traceable(Protocol):
    """Protocol for components or agents capable of emitting execution traces."""

    def to_trace(self) -> ExecutionTrace:
        """Convert or export current execution state to an ExecutionTrace."""
        ...


@runtime_checkable
class ExecutionAdapter(Protocol):
    """Protocol for executing an agent or workflow against a test case.

    Execution adapters isolate framework-specific or provider-specific agent invocation
    and capture standard ExecutionTrace instances.
    """

    def execute(
        self,
        agent: Any,
        test_case: TestCase,
    ) -> ExecutionTrace:
        """Execute an agent with inputs from a test case and produce an ExecutionTrace.

        Args:
            agent: The AI agent, chain, model, or callable to execute.
            test_case: The test case specification containing input and configuration.

        Returns:
            An ExecutionTrace representing the execution history and outcomes.
        """
        ...


@runtime_checkable
class Evaluator(Protocol):
    """Protocol defining trace evaluation components.

    Evaluators analyze an execution trace alongside test case expectations to produce
    an EvaluationResult.
    """

    name: str

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase,
    ) -> EvaluationResult:
        """Evaluate an execution trace against the given test case.

        Args:
            trace: The captured execution trace.
            test_case: The test case specification with expectations and inputs.

        Returns:
            An EvaluationResult indicating pass/fail status, scores, and details.
        """
        ...


@runtime_checkable
class Expectation(Protocol):
    """Protocol for deterministic expectations against execution traces or outputs.

    Expectations define verifiable conditions that can be evaluated to produce
    an EvaluationResult.
    """

    name: str

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        """Evaluate whether the execution trace satisfies this expectation.

        Args:
            trace: The captured execution trace.
            test_case: Optional test case specification.

        Returns:
            An EvaluationResult representing the outcome of checking the expectation.
        """
        ...
