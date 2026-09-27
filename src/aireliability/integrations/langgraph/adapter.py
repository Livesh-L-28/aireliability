"""LangGraph adapter implementation for observing compiled state graphs."""

from collections.abc import Sequence
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
    BaseAdapter,
    ToolCallRecord,
)


class LangGraphAdapter(BaseAdapter):
    """Adapter for executing and observing LangGraph StateGraph instances.

    Normalizes:
    - Node execution events (node start/end) -> StepType.AGENT or StepType.CUSTOM
    - ToolMessage / AIMessage.tool_calls -> ToolCallRecord -> StepType.TOOL
    - Graph outputs -> trace.output
    - Exceptions -> normalized ExecutionStatus.FAILED with error telemetry

    Never exposes LangGraph-specific objects directly to core evaluators.
    """

    def __init__(
        self,
        graph: Any = None,
        *,
        suppress_exceptions: bool = False,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize LangGraphAdapter.

        Args:
            graph: Optional pre-compiled LangGraph application.
            suppress_exceptions: If True, failures produce a failed ExecutionTrace.
            config: Optional LangGraph invocation config (e.g. recursion_limit).
        """
        self.default_graph = graph
        self.suppress_exceptions = suppress_exceptions
        self.config = config or {}

    def execute(
        self,
        agent: Any = None,
        test_case: TestCase | None = None,
    ) -> ExecutionTrace:
        """Execute a LangGraph compiled graph and produce an ExecutionTrace.

        Args:
            agent: The compiled graph instance. If None, uses self.default_graph.
            test_case: The TestCase specification containing input.

        Returns:
            An ExecutionTrace with normalized tool steps, timing, and outputs.
        """
        effective_graph = agent if agent is not None else self.default_graph
        effective_test_case = test_case

        if effective_test_case is None and isinstance(agent, TestCase):
            effective_test_case = agent
            effective_graph = self.default_graph

        if effective_test_case is None:
            raise ValueError("A TestCase must be provided to execute.")

        if effective_graph is None:
            raise TypeError("No LangGraph graph or runnable provided to execute.")

        start_time = datetime.now(UTC)
        steps: list[TraceStep] = []
        status = ExecutionStatus.COMPLETED
        raw_output: Any = None
        error_details: dict[str, Any] = {}

        try:
            # LangGraph apps provide .invoke(input, config=...) or stream()
            input_data = self._format_graph_input(effective_test_case.input)

            if hasattr(effective_graph, "stream") and callable(effective_graph.stream):
                # Using stream allows capturing node-by-node execution states
                stream_chunks: list[dict[str, Any]] = []
                for chunk in effective_graph.stream(input_data, config=self.config):
                    stream_chunks.append(chunk)
                    # Extract node-level transitions and tool messages from chunk
                    node_steps = self._extract_steps_from_chunk(chunk)
                    steps.extend(node_steps)

                # Determine final state from last stream chunk or invoke return
                raw_output = stream_chunks[-1] if stream_chunks else {}
            elif hasattr(effective_graph, "invoke") and callable(
                effective_graph.invoke
            ):
                raw_output = effective_graph.invoke(input_data, config=self.config)
                steps.extend(self._extract_steps_from_state(raw_output))
            elif callable(effective_graph):
                raw_output = effective_graph(input_data)
                steps.extend(self._extract_steps_from_state(raw_output))
            else:
                raise TypeError(
                    f"Target '{type(effective_graph).__name__}' does not provide "
                    ".invoke() or .stream()."
                )

        except Exception as exc:
            status = ExecutionStatus.FAILED
            error_details = {
                "error": str(exc),
                "error_type": type(exc).__name__,
                "framework": "langgraph",
            }
            raw_output = error_details
            if not self.suppress_exceptions:
                end_time = datetime.now(UTC)
                lat_ms = (end_time - start_time).total_seconds() * 1000.0
                trace = ExecutionTrace(
                    test_id=effective_test_case.id,
                    input=effective_test_case.input,
                    output=raw_output,
                    status=status,
                    started_at=start_time,
                    completed_at=end_time,
                    latency_ms=max(0.0, lat_ms),
                    steps=steps,
                    metadata=error_details,
                )
                exc.execution_trace = trace  # type: ignore[attr-defined]
                raise exc

        end_time = datetime.now(UTC)
        lat_ms = (end_time - start_time).total_seconds() * 1000.0
        final_output = self._normalize_graph_output(raw_output)

        return ExecutionTrace(
            test_id=effective_test_case.id,
            input=effective_test_case.input,
            output=final_output,
            status=status,
            started_at=start_time,
            completed_at=end_time,
            latency_ms=max(0.0, lat_ms),
            steps=steps,
            metadata=error_details,
        )

    async def aexecute(
        self,
        agent: Any = None,
        test_case: TestCase | None = None,
    ) -> ExecutionTrace:
        """Asynchronously execute a LangGraph compiled graph via .ainvoke."""
        effective_graph = agent if agent is not None else self.default_graph
        effective_test_case = test_case

        if effective_test_case is None and isinstance(agent, TestCase):
            effective_test_case = agent
            effective_graph = self.default_graph

        if effective_test_case is None:
            raise ValueError("A TestCase must be provided to execute.")
        if effective_graph is None:
            raise TypeError("No LangGraph graph or runnable provided to execute.")

        start_time = datetime.now(UTC)
        steps: list[TraceStep] = []
        status = ExecutionStatus.COMPLETED
        raw_output: Any = None
        error_details: dict[str, Any] = {}

        try:
            input_data = self._format_graph_input(effective_test_case.input)
            if hasattr(effective_graph, "astream") and callable(
                effective_graph.astream
            ):
                stream_chunks: list[dict[str, Any]] = []
                async for chunk in effective_graph.astream(
                    input_data, config=self.config
                ):
                    stream_chunks.append(chunk)
                    steps.extend(self._extract_steps_from_chunk(chunk))
                raw_output = stream_chunks[-1] if stream_chunks else {}
            elif hasattr(effective_graph, "ainvoke") and callable(
                effective_graph.ainvoke
            ):
                raw_output = await effective_graph.ainvoke(
                    input_data, config=self.config
                )
                steps.extend(self._extract_steps_from_state(raw_output))
            else:
                # Fallback to sync execution in worker thread
                return await super().aexecute(effective_graph, effective_test_case)

        except Exception as exc:
            status = ExecutionStatus.FAILED
            error_details = {
                "error": str(exc),
                "error_type": type(exc).__name__,
                "framework": "langgraph",
            }
            raw_output = error_details
            if not self.suppress_exceptions:
                end_time = datetime.now(UTC)
                lat_ms = (end_time - start_time).total_seconds() * 1000.0
                trace = ExecutionTrace(
                    test_id=effective_test_case.id,
                    input=effective_test_case.input,
                    output=raw_output,
                    status=status,
                    started_at=start_time,
                    completed_at=end_time,
                    latency_ms=max(0.0, lat_ms),
                    steps=steps,
                    metadata=error_details,
                )
                exc.execution_trace = trace  # type: ignore[attr-defined]
                raise exc

        end_time = datetime.now(UTC)
        lat_ms = (end_time - start_time).total_seconds() * 1000.0
        final_output = self._normalize_graph_output(raw_output)

        return ExecutionTrace(
            test_id=effective_test_case.id,
            input=effective_test_case.input,
            output=final_output,
            status=status,
            started_at=start_time,
            completed_at=end_time,
            latency_ms=max(0.0, lat_ms),
            steps=steps,
            metadata=error_details,
        )

    def _format_graph_input(self, tc_input: Any) -> Any:
        """Format test case input into the dictionary or state structure."""
        if isinstance(tc_input, dict):
            return tc_input
        # If input is a raw string, wrap in common LangGraph message / query convention
        return {"input": tc_input}

    def _extract_steps_from_chunk(self, chunk: dict[str, Any]) -> list[TraceStep]:
        """Extract tool calls and steps from a stream chunk."""
        steps: list[TraceStep] = []
        if not isinstance(chunk, dict):
            return steps

        for node_name, state_update in chunk.items():
            # Check for messages in state update
            if isinstance(state_update, dict):
                extracted = self._extract_steps_from_state(state_update)
                if extracted:
                    steps.extend(extracted)
                else:
                    # Generic node step if no tool messages found
                    steps.append(
                        TraceStep(
                            type=StepType.AGENT,
                            name=str(node_name),
                            input=state_update.get("input"),
                            output=state_update.get("output"),
                            metadata={"node": str(node_name)},
                        )
                    )
        return steps

    def _extract_steps_from_state(self, state: Any) -> list[TraceStep]:
        """Extract tool calls from state dictionary."""
        steps: list[TraceStep] = []
        if not isinstance(state, dict):
            return steps

        # Check for 'messages' list (common LangChain / LangGraph pattern)
        messages = state.get("messages", [])
        if isinstance(messages, Sequence) and not isinstance(messages, (str, bytes)):
            # Look for AIMessage with tool_calls or ToolMessage
            for msg in messages:
                # 1. AIMessage with tool_calls
                tool_calls = getattr(msg, "tool_calls", None)
                if tool_calls is None and isinstance(msg, dict):
                    tool_calls = msg.get("tool_calls")

                if isinstance(tool_calls, (list, tuple)):
                    for tc in tool_calls:
                        name = (
                            tc.get("name")
                            if isinstance(tc, dict)
                            else getattr(tc, "name", "")
                        )
                        args = (
                            tc.get("args")
                            if isinstance(tc, dict)
                            else getattr(tc, "args", {})
                        )
                        if name:
                            rec = ToolCallRecord(
                                name=str(name),
                                arguments=args if isinstance(args, dict) else {},
                                status="completed",
                            )
                            steps.append(rec.to_trace_step())

                # 2. ToolMessage representing tool result
                msg_type = getattr(msg, "type", None) or (
                    msg.get("type") if isinstance(msg, dict) else None
                )
                if msg_type == "tool" or msg.__class__.__name__ == "ToolMessage":
                    tool_name = getattr(msg, "name", None) or (
                        msg.get("name") if isinstance(msg, dict) else "tool"
                    )
                    content = getattr(msg, "content", None) or (
                        msg.get("content") if isinstance(msg, dict) else None
                    )
                    # Check if matching prior tool step to enrich result
                    matched = False
                    for existing_step in reversed(steps):
                        if (
                            existing_step.type == StepType.TOOL
                            and existing_step.name == tool_name
                            and existing_step.output is None
                        ):
                            # Enrich existing record
                            object.__setattr__(existing_step, "output", content)
                            matched = True
                            break
                    if not matched:
                        rec = ToolCallRecord(
                            name=str(tool_name),
                            arguments={},
                            result=content,
                            status="completed",
                        )
                        steps.append(rec.to_trace_step())

        # Also check for explicit 'tool_calls' in state
        if "tool_calls" in state and isinstance(state["tool_calls"], (list, tuple)):
            for tc in state["tool_calls"]:
                t_name = (
                    tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                )
                t_args = (
                    tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                )
                t_res = (
                    tc.get("result")
                    if isinstance(tc, dict)
                    else getattr(tc, "result", None)
                )
                if t_name:
                    rec = ToolCallRecord(
                        name=str(t_name),
                        arguments=t_args if isinstance(t_args, dict) else {},
                        result=t_res,
                    )
                    steps.append(rec.to_trace_step())

        return steps

    def _normalize_graph_output(self, raw_output: Any) -> Any:
        """Extract user-facing text from graph state dictionary."""
        if isinstance(raw_output, dict):
            # Check for common final output keys directly
            if "output" in raw_output:
                return raw_output["output"]
            if "response" in raw_output:
                return raw_output["response"]
            if "answer" in raw_output:
                return raw_output["answer"]
            if "messages" in raw_output and raw_output["messages"]:
                last_msg = raw_output["messages"][-1]
                content = getattr(last_msg, "content", None)
                if content is not None:
                    return content
                if isinstance(last_msg, dict) and "content" in last_msg:
                    return last_msg["content"]

            # If raw_output is a stream chunk keyed by node name
            for val in raw_output.values():
                if isinstance(val, dict):
                    inner_normalized = self._normalize_graph_output(val)
                    if inner_normalized is not val:
                        return inner_normalized

        return raw_output


__all__ = ["LangGraphAdapter"]
