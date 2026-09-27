"""Callable execution adapter for standard Python functions and agent objects."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from aireliability.core.models import (
    ExecutionStatus,
    ExecutionTrace,
    StepType,
    TestCase,
    TraceStep,
)
from aireliability.execution.adapters.base import (
    AgentEventType,
    BaseAdapter,
    ExecutionEvent,
    ToolCallRecord,
)


class CallableAdapter(BaseAdapter):
    """Adapter executing ordinary Python callables or agent objects.

    Supports:
    1. Direct execution via adapter.execute(agent, test_case)
    2. Bound execution where agent is passed in constructor: adapter.execute(test_case)
       or adapter.execute(agent=None, test_case=test_case)
    3. Tool-aware execution: handles agents returning structured events, tool calls,
       or agents equipped with an execution history/events attribute.
    """

    def __init__(
        self,
        agent: Callable[..., Any] | Any | None = None,
        *,
        suppress_exceptions: bool = False,
        extract_steps_hook: Callable[[Any, Any], list[TraceStep]] | None = None,
    ) -> None:
        """Initialize CallableAdapter.

        Args:
            agent: Optional default agent or callable to bind.
            suppress_exceptions: If True, caught exceptions produce a failed trace
                rather than re-raising.
            extract_steps_hook: Optional hook (agent, result) -> list[TraceStep] to
                extract custom steps from arbitrary agent execution objects.
        """
        self.default_agent = agent
        self.suppress_exceptions = suppress_exceptions
        self.extract_steps_hook = extract_steps_hook

    def execute(
        self,
        agent: Any = None,
        test_case: TestCase | None = None,
    ) -> ExecutionTrace:
        """Execute an agent or callable against a test case.

        Supports both signature patterns:
        - execute(agent, test_case)
        - execute(test_case=test_case) when agent was provided in __init__
        - execute(test_case) when agent was provided in __init__

        Args:
            agent: The callable or agent object. If None, uses self.default_agent.
            test_case: The TestCase containing input data.

        Returns:
            An ExecutionTrace capturing start/end timestamps, latency, status, output,
            and discrete steps.
        """
        effective_agent = agent if agent is not None else self.default_agent
        effective_test_case = test_case

        # Handle the case where test_case was passed as first positional arg
        if effective_test_case is None and isinstance(agent, TestCase):
            effective_test_case = agent
            effective_agent = self.default_agent

        if effective_test_case is None:
            raise ValueError("A TestCase must be provided to execute.")

        if effective_agent is None:
            raise TypeError("No agent or callable provided to execute.")

        start_time = datetime.now(UTC)
        steps: list[TraceStep] = []
        raw_output: Any = None
        status = ExecutionStatus.COMPLETED
        error_details: dict[str, Any] | None = None

        try:
            # Execute the agent
            if callable(effective_agent):
                raw_output = effective_agent(effective_test_case.input)
            elif hasattr(effective_agent, "run") and callable(effective_agent.run):
                raw_output = effective_agent.run(effective_test_case.input)
            elif hasattr(effective_agent, "invoke") and callable(
                effective_agent.invoke
            ):
                raw_output = effective_agent.invoke(effective_test_case.input)
            else:
                agent_type = type(effective_agent).__name__
                raise TypeError(
                    f"Agent of type {agent_type} is neither callable "
                    "nor implements .run() or .invoke()."
                )

            # Extract steps if agent provides structured tool records or events
            steps = self._extract_steps(effective_agent, raw_output)

        except Exception as exc:
            status = ExecutionStatus.FAILED
            error_details = {
                "error": str(exc),
                "error_type": type(exc).__name__,
            }
            raw_output = error_details
            if not self.suppress_exceptions:
                end_time = datetime.now(UTC)
                # Compute latency
                latency_ms = (end_time - start_time).total_seconds() * 1000.0
                trace = ExecutionTrace(
                    test_id=effective_test_case.id,
                    input=effective_test_case.input,
                    output=raw_output,
                    status=status,
                    started_at=start_time,
                    completed_at=end_time,
                    latency_ms=max(0.0, latency_ms),
                    steps=steps,
                    metadata={"error": str(exc), "error_type": type(exc).__name__},
                )
                exc.execution_trace = trace  # type: ignore[attr-defined]
                raise exc

        end_time = datetime.now(UTC)
        latency_ms = (end_time - start_time).total_seconds() * 1000.0

        # Unwrap output if agent returned a dict containing output and steps/events
        final_output = self._normalize_output(raw_output)

        metadata: dict[str, Any] = {}
        if error_details:
            metadata.update(error_details)

        return ExecutionTrace(
            test_id=effective_test_case.id,
            input=effective_test_case.input,
            output=final_output,
            status=status,
            started_at=start_time,
            completed_at=end_time,
            latency_ms=max(0.0, latency_ms),
            steps=steps,
            metadata=metadata,
        )

    def _extract_steps(self, agent: Any, result: Any) -> list[TraceStep]:
        """Extract TraceSteps from agent attributes, custom hook, or returned result."""
        steps: list[TraceStep] = []

        # 1. Custom hook if defined
        if self.extract_steps_hook is not None:
            try:
                hook_steps = self.extract_steps_hook(agent, result)
                if hook_steps:
                    return hook_steps
            except Exception:
                pass

        # 2. Inspect agent for tool_calls, events, or steps attributes
        for attr in ("tool_calls", "tools_called", "tool_history"):
            if hasattr(agent, attr):
                val = getattr(agent, attr)
                if isinstance(val, (list, tuple)):
                    for item in val:
                        step = self._to_trace_step(item)
                        if step:
                            steps.append(step)
                if steps:
                    return steps

        for attr in ("events", "execution_events", "history"):
            if hasattr(agent, attr):
                val = getattr(agent, attr)
                if isinstance(val, (list, tuple)):
                    for item in val:
                        step = self._to_trace_step(item)
                        if step:
                            steps.append(step)
                if steps:
                    return steps

        # 3. Inspect result if result is a dictionary containing tool calls or steps
        if isinstance(result, dict):
            for key in ("tool_calls", "tools", "steps"):
                if key in result and isinstance(result[key], (list, tuple)):
                    for item in result[key]:
                        step = self._to_trace_step(item)
                        if step:
                            steps.append(step)
                    if steps:
                        return steps

            for key in ("events", "history"):
                if key in result and isinstance(result[key], (list, tuple)):
                    for item in result[key]:
                        step = self._to_trace_step(item)
                        if step:
                            steps.append(step)
                    if steps:
                        return steps

        return steps

    def _to_trace_step(self, item: Any) -> TraceStep | None:
        """Convert arbitrary tool call or event representations into a TraceStep."""
        if isinstance(item, TraceStep):
            return item

        if isinstance(item, ToolCallRecord):
            return item.to_trace_step()

        if isinstance(item, ExecutionEvent):
            step_type = (
                StepType.TOOL
                if item.type
                in (
                    AgentEventType.TOOL_CALL,
                    AgentEventType.TOOL_RESULT,
                )
                else (
                    StepType.LLM
                    if item.type == AgentEventType.LLM_CALL
                    else (
                        StepType.RETRIEVAL
                        if item.type == AgentEventType.RETRIEVAL
                        else (
                            StepType.MEMORY
                            if item.type
                            in (
                                AgentEventType.MEMORY_READ,
                                AgentEventType.MEMORY_WRITE,
                            )
                            else StepType.CUSTOM
                        )
                    )
                )
            )
            return TraceStep(
                type=step_type,
                name=item.name or str(item.type),
                input=item.payload.get("input")
                or item.payload.get("arguments")
                or item.payload,
                output=item.payload.get("output") or item.payload.get("result"),
                started_at=item.timestamp,
                metadata=item.metadata,
            )

        if isinstance(item, dict):
            # Formats like {"tool": "name", "arguments": {...}, "result": {...}}
            tool_name = item.get("name") or item.get("tool") or item.get("tool_name")
            if tool_name:
                args = (
                    item.get("arguments") or item.get("input") or item.get("args") or {}
                )
                output = item.get("result") or item.get("output")
                duration = item.get("duration_ms") or item.get("duration")
                started_at = item.get("started_at")
                completed_at = item.get("completed_at")
                return TraceStep(
                    type=StepType.TOOL,
                    name=str(tool_name),
                    input=args,
                    output=output,
                    duration_ms=float(duration) if duration is not None else None,
                    started_at=started_at
                    if isinstance(started_at, datetime)
                    else datetime.now(UTC),
                    completed_at=completed_at
                    if isinstance(completed_at, datetime)
                    else None,
                    metadata=item.get("metadata", {}),
                )

        return None

    def _normalize_output(self, raw_output: Any) -> Any:
        """Return unwrapped output if wrapped in an envelope dictionary."""
        if isinstance(raw_output, dict):
            if "output" in raw_output and any(
                k in raw_output for k in ("steps", "tool_calls", "tools", "events")
            ):
                return raw_output["output"]
            if "response" in raw_output and any(
                k in raw_output for k in ("steps", "tool_calls", "tools", "events")
            ):
                return raw_output["response"]
        return raw_output
