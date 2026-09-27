"""Base adapter interface and event model for AI agent execution observation."""

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from aireliability.core.models import ExecutionTrace, StepType, TestCase, TraceStep


class AgentEventType(StrEnum):
    """Event types emitted during agent execution."""

    AGENT_STARTED = "agent_started"
    AGENT_FINISHED = "agent_finished"
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    RETRIEVAL = "retrieval"
    MEMORY_READ = "memory_read"
    MEMORY_WRITE = "memory_write"
    ERROR = "error"
    # Phase 21: Model execution and streaming events
    MODEL_CALL_START = "model_call_start"
    MODEL_CALL_END = "model_call_end"
    MODEL_CALL_ERROR = "model_call_error"
    STREAM_START = "stream_start"
    STREAM_CHUNK = "stream_chunk"
    STREAM_END = "stream_end"


class ExecutionEvent(BaseModel):
    """Structured event capturing a discrete action or transition in agent execution."""

    model_config = ConfigDict(frozen=True)

    type: AgentEventType
    name: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelUsage(BaseModel):
    """Token usage and resource consumption reported by a model provider."""

    model_config = ConfigDict(frozen=True)

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_tokens: int | None = None

    def to_dict(self) -> dict[str, int]:
        """Convert non-None usage counts to standard token_usage dictionary."""
        usage: dict[str, int] = {}
        if self.input_tokens is not None:
            usage["prompt_tokens"] = self.input_tokens
            usage["input_tokens"] = self.input_tokens
        if self.output_tokens is not None:
            usage["completion_tokens"] = self.output_tokens
            usage["output_tokens"] = self.output_tokens
        if self.total_tokens is not None:
            usage["total_tokens"] = self.total_tokens
        if self.cached_tokens is not None:
            usage["cached_tokens"] = self.cached_tokens
        return usage


class ToolCallRecord(BaseModel):
    """Framework-independent representation of a tool invocation."""

    model_config = ConfigDict(frozen=True)

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    call_id: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    duration_ms: float | None = None
    status: str = "completed"
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_trace_step(self) -> TraceStep:
        """Convert this tool call record into an aireliability TraceStep."""
        step_meta = {**self.metadata, "status": self.status}
        if self.call_id is not None:
            step_meta["call_id"] = self.call_id
        return TraceStep(
            type=StepType.TOOL,
            name=self.name,
            input=self.arguments,
            output=self.result,
            started_at=self.started_at,
            completed_at=self.completed_at,
            duration_ms=self.duration_ms,
            metadata=step_meta,
        )


class ModelCallRecord(BaseModel):
    """Framework-independent representation of a model invocation or completion."""

    model_config = ConfigDict(frozen=True)

    model: str
    provider: str = "generic"
    input: Any = None
    output: Any = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    duration_ms: float | None = None
    status: str = "completed"
    error: str | None = None
    attempt: int = 1
    usage: ModelUsage | None = None
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_trace_step(self) -> TraceStep:
        """Convert this model call record into an aireliability TraceStep."""
        meta = {
            **self.metadata,
            "provider": self.provider,
            "status": self.status,
            "attempt": self.attempt,
        }
        if self.error is not None:
            meta["error"] = self.error
        if self.usage is not None:
            meta["usage"] = self.usage.model_dump(exclude_none=True)

        return TraceStep(
            type=StepType.LLM,
            name=self.model,
            input=self.input,
            output=self.output,
            started_at=self.started_at,
            completed_at=self.completed_at,
            duration_ms=self.duration_ms,
            metadata=meta,
        )


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
class AsyncExecutionAdapter(Protocol):
    """Protocol for asynchronously executing an agent against a test case."""

    async def aexecute(
        self,
        agent: Any,
        test_case: TestCase,
    ) -> ExecutionTrace:
        """Asynchronously execute an agent and produce an ExecutionTrace."""
        ...


class BaseAdapter(ABC):
    """Abstract base class for execution adapters providing common utilities."""

    @abstractmethod
    def execute(
        self,
        agent: Any,
        test_case: TestCase,
    ) -> ExecutionTrace:
        """Execute the agent against the test case and produce an ExecutionTrace."""
        ...

    async def aexecute(
        self,
        agent: Any,
        test_case: TestCase,
    ) -> ExecutionTrace:
        """Asynchronously execute the agent against the test case.

        Default implementation runs the synchronous execute method.
        Subclasses with native async event hooks may override this.
        """
        import asyncio

        return await asyncio.to_thread(self.execute, agent, test_case)


class ProviderAdapter(BaseAdapter):
    """Base adapter for provider-neutral model and tool execution observation.

    Provides common sanitization, timing, event recording, and normalization
    utilities across model provider integrations without exposing provider SDK objects.
    """

    def __init__(
        self,
        *,
        provider: str = "generic",
        suppress_exceptions: bool = False,
        sanitize_keys: bool = True,
    ) -> None:
        self.provider = provider
        self.suppress_exceptions = suppress_exceptions
        self.sanitize_keys = sanitize_keys

    @staticmethod
    def sanitize_metadata(meta: dict[str, Any]) -> dict[str, Any]:
        """Strip sensitive credentials such as api keys and bearer tokens."""
        if not isinstance(meta, dict):
            return meta

        sensitive_substrs = (
            "api_key",
            "apikey",
            "token",
            "secret",
            "password",
            "authorization",
            "bearer",
            "cookie",
        )
        cleaned: dict[str, Any] = {}
        for k, v in meta.items():
            k_lower = str(k).lower()
            if any(s in k_lower for s in sensitive_substrs):
                cleaned[k] = "[REDACTED]"
            elif isinstance(v, dict):
                cleaned[k] = ProviderAdapter.sanitize_metadata(v)
            else:
                cleaned[k] = v
        return cleaned


__all__ = [
    "AgentEventType",
    "AsyncExecutionAdapter",
    "BaseAdapter",
    "ExecutionAdapter",
    "ExecutionEvent",
    "ModelCallRecord",
    "ModelUsage",
    "ProviderAdapter",
    "ToolCallRecord",
]
