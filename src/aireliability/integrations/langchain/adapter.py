"""LangChain execution adapter using standardized BaseCallbackHandler."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

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


class ReliabilityCallbackHandler:
    """Standard LangChain callback handler capturing tools, chains, and errors.

    Duck-types LangChain's BaseCallbackHandler without requiring LangChain installed
    at import time.
    """

    def __init__(self) -> None:
        self.steps: list[TraceStep] = []
        self._active_tools: dict[str, dict[str, Any]] = {}

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID | str | None = None,
        parent_run_id: UUID | str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Capture tool start event."""
        tool_name = (
            serialized.get("name") if isinstance(serialized, dict) else str(serialized)
        )
        t_id = str(run_id) if run_id is not None else tool_name

        args: dict[str, Any] = {}
        if inputs is not None and isinstance(inputs, dict):
            args = inputs
        elif input_str:
            args = {"input": input_str}

        self._active_tools[t_id] = {
            "name": tool_name,
            "arguments": args,
            "started_at": datetime.now(UTC),
            "metadata": metadata or {},
        }

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID | str | None = None,
        parent_run_id: UUID | str | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Capture tool completion and record normalized ToolCallRecord."""
        t_id = str(run_id) if run_id is not None else None
        active = self._active_tools.pop(t_id, None) if t_id else None

        if active is None and self._active_tools:
            # Fall back to the most recently opened tool if run_id was omitted
            _, active = self._active_tools.popitem()

        if active:
            now = datetime.now(UTC)
            start = active["started_at"]
            duration = (now - start).total_seconds() * 1000.0

            rec = ToolCallRecord(
                name=active["name"],
                arguments=active["arguments"],
                result=output,
                started_at=start,
                completed_at=now,
                duration_ms=max(0.0, duration),
                status="completed",
                metadata=active.get("metadata", {}),
            )
            self.steps.append(rec.to_trace_step())
        else:
            # Record isolated tool end
            rec = ToolCallRecord(
                name="tool",
                arguments={},
                result=output,
                status="completed",
            )
            self.steps.append(rec.to_trace_step())

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID | str | None = None,
        **kwargs: Any,
    ) -> None:
        """Capture tool error event."""
        t_id = str(run_id) if run_id is not None else None
        active = self._active_tools.pop(t_id, None) if t_id else None
        name = active["name"] if active else "tool"
        args = active["arguments"] if active else {}

        rec = ToolCallRecord(
            name=name,
            arguments=args,
            result={"error": str(error), "error_type": type(error).__name__},
            status="failed",
            metadata={"error": str(error)},
        )
        self.steps.append(rec.to_trace_step())

    def on_chain_error(self, error: BaseException, **kwargs: Any) -> None:
        """Capture chain-level execution error."""
        self.steps.append(
            TraceStep(
                type=StepType.AGENT,
                name="chain_error",
                output={"error": str(error), "error_type": type(error).__name__},
                metadata={"error": str(error)},
            )
        )


class LangChainAdapter(BaseAdapter):
    """Adapter for executing and observing LangChain Runnable or Chain instances.

    Uses LangChain's official callback mechanism (`config={"callbacks": [...]}`) rather
    than monkey-patching internal classes.
    """

    def __init__(
        self,
        chain: Any = None,
        *,
        suppress_exceptions: bool = False,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize LangChainAdapter.

        Args:
            chain: Optional default LangChain Runnable or AgentExecutor.
            suppress_exceptions: If True, failures produce a failed ExecutionTrace.
            config: Optional base invocation config dictionary.
        """
        self.default_chain = chain
        self.suppress_exceptions = suppress_exceptions
        self.config = config or {}

    def execute(
        self,
        agent: Any = None,
        test_case: TestCase | None = None,
    ) -> ExecutionTrace:
        """Execute a LangChain runnable and capture an ExecutionTrace with callbacks."""
        effective_chain = agent if agent is not None else self.default_chain
        effective_test_case = test_case

        if effective_test_case is None and isinstance(agent, TestCase):
            effective_test_case = agent
            effective_chain = self.default_chain

        if effective_test_case is None:
            raise ValueError("A TestCase must be provided to execute.")
        if effective_chain is None:
            raise TypeError("No LangChain runnable or agent provided to execute.")

        handler = ReliabilityCallbackHandler()
        run_config = dict(self.config)
        existing_callbacks = list(run_config.get("callbacks", []))
        existing_callbacks.append(handler)
        run_config["callbacks"] = existing_callbacks

        start_time = datetime.now(UTC)
        status = ExecutionStatus.COMPLETED
        raw_output: Any = None
        error_details: dict[str, Any] = {}

        try:
            # LangChain Runnable Protocol: .invoke(input, config=...)
            if hasattr(effective_chain, "invoke") and callable(effective_chain.invoke):
                raw_output = effective_chain.invoke(
                    effective_test_case.input, config=run_config
                )
            elif hasattr(effective_chain, "run") and callable(effective_chain.run):
                # Legacy Chain.run(input, callbacks=...)
                try:
                    raw_output = effective_chain.run(
                        effective_test_case.input, callbacks=[handler]
                    )
                except TypeError:
                    raw_output = effective_chain.run(effective_test_case.input)
            elif callable(effective_chain):
                raw_output = effective_chain(effective_test_case.input)
            else:
                raise TypeError(
                    f"Target '{type(effective_chain).__name__}' does not support "
                    ".invoke() or .run()."
                )

        except Exception as exc:
            status = ExecutionStatus.FAILED
            error_details = {
                "error": str(exc),
                "error_type": type(exc).__name__,
                "framework": "langchain",
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
                    steps=handler.steps,
                    metadata=error_details,
                )
                exc.execution_trace = trace  # type: ignore[attr-defined]
                raise exc

        end_time = datetime.now(UTC)
        lat_ms = (end_time - start_time).total_seconds() * 1000.0
        final_output = self._normalize_chain_output(raw_output)

        return ExecutionTrace(
            test_id=effective_test_case.id,
            input=effective_test_case.input,
            output=final_output,
            status=status,
            started_at=start_time,
            completed_at=end_time,
            latency_ms=max(0.0, lat_ms),
            steps=handler.steps,
            metadata=error_details,
        )

    async def aexecute(
        self,
        agent: Any = None,
        test_case: TestCase | None = None,
    ) -> ExecutionTrace:
        """Asynchronously execute a LangChain runnable via .ainvoke."""
        effective_chain = agent if agent is not None else self.default_chain
        effective_test_case = test_case

        if effective_test_case is None and isinstance(agent, TestCase):
            effective_test_case = agent
            effective_chain = self.default_chain

        if effective_test_case is None:
            raise ValueError("A TestCase must be provided to execute.")
        if effective_chain is None:
            raise TypeError("No LangChain runnable or agent provided to execute.")

        handler = ReliabilityCallbackHandler()
        run_config = dict(self.config)
        existing_callbacks = list(run_config.get("callbacks", []))
        existing_callbacks.append(handler)
        run_config["callbacks"] = existing_callbacks

        start_time = datetime.now(UTC)
        status = ExecutionStatus.COMPLETED
        raw_output: Any = None
        error_details: dict[str, Any] = {}

        try:
            if hasattr(effective_chain, "ainvoke") and callable(
                effective_chain.ainvoke
            ):
                raw_output = await effective_chain.ainvoke(
                    effective_test_case.input, config=run_config
                )
            else:
                return await super().aexecute(effective_chain, effective_test_case)

        except Exception as exc:
            status = ExecutionStatus.FAILED
            error_details = {
                "error": str(exc),
                "error_type": type(exc).__name__,
                "framework": "langchain",
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
                    steps=handler.steps,
                    metadata=error_details,
                )
                exc.execution_trace = trace  # type: ignore[attr-defined]
                raise exc

        end_time = datetime.now(UTC)
        lat_ms = (end_time - start_time).total_seconds() * 1000.0
        final_output = self._normalize_chain_output(raw_output)

        return ExecutionTrace(
            test_id=effective_test_case.id,
            input=effective_test_case.input,
            output=final_output,
            status=status,
            started_at=start_time,
            completed_at=end_time,
            latency_ms=max(0.0, lat_ms),
            steps=handler.steps,
            metadata=error_details,
        )

    def _normalize_chain_output(self, raw_output: Any) -> Any:
        """Extract output payload from common LangChain dictionary wrappers."""
        if isinstance(raw_output, dict):
            if "output" in raw_output:
                return raw_output["output"]
            if "text" in raw_output:
                return raw_output["text"]
            if "content" in raw_output:
                return raw_output["content"]
        # Check AIMessage-like object
        content = getattr(raw_output, "content", None)
        if content is not None:
            return content
        return raw_output


__all__ = [
    "LangChainAdapter",
    "ReliabilityCallbackHandler",
]
