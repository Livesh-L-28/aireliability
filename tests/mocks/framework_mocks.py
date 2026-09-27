"""Mock implementations of LangGraph and LangChain objects for deterministic testing.

Allows testing LangGraphAdapter and LangChainAdapter with full event lifecycle,
tool calls, streaming, errors, and output normalization without network or paid APIs.
"""

import json
from collections.abc import AsyncIterator, Iterator
from typing import Any


class MockAIMessage:
    """Mock LangChain / LangGraph AIMessage with optional tool_calls."""

    def __init__(
        self,
        content: str = "",
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> None:
        self.type = "ai"
        self.content = content
        self.tool_calls = tool_calls or []


class MockToolMessage:
    """Mock LangChain / LangGraph ToolMessage representing a tool execution result."""

    def __init__(self, content: Any, name: str = "tool") -> None:
        self.type = "tool"
        self.name = name
        self.content = content


class MockLangGraphApp:
    """Mock compiled LangGraph StateGraph application.

    Simulates stream() and invoke() behaviors with tool calling sequences.
    """

    def __init__(
        self,
        tool_sequence: list[tuple[str, dict[str, Any], Any]] | None = None,
        final_output: str = "Success",
        should_error: bool = False,
        error_message: str = "Graph execution error",
    ) -> None:
        self.tool_sequence = tool_sequence or []
        self.final_output = final_output
        self.should_error = should_error
        self.error_message = error_message

    def invoke(self, state: dict[str, Any], config: Any = None) -> dict[str, Any]:
        """Simulate synchronous graph invocation."""
        if self.should_error:
            raise RuntimeError(self.error_message)

        messages: list[Any] = []
        for name, args, res in self.tool_sequence:
            messages.append(
                MockAIMessage(
                    content="",
                    tool_calls=[{"name": name, "args": args}],
                )
            )
            messages.append(MockToolMessage(content=res, name=name))

        messages.append(MockAIMessage(content=self.final_output))
        return {
            "messages": messages,
            "output": self.final_output,
        }

    def stream(
        self, state: dict[str, Any], config: Any = None
    ) -> Iterator[dict[str, Any]]:
        """Simulate streaming node chunks."""
        if self.should_error:
            raise RuntimeError(self.error_message)

        # Emit node chunks
        for idx, (name, args, res) in enumerate(self.tool_sequence):
            node_name = f"node_{idx + 1}"
            yield {
                node_name: {
                    "messages": [
                        MockAIMessage(
                            content="",
                            tool_calls=[{"name": name, "args": args}],
                        ),
                        MockToolMessage(content=res, name=name),
                    ]
                }
            }

        yield {
            "output_node": {
                "messages": [MockAIMessage(content=self.final_output)],
                "output": self.final_output,
            }
        }

    async def ainvoke(
        self, state: dict[str, Any], config: Any = None
    ) -> dict[str, Any]:
        """Simulate async graph invocation."""
        return self.invoke(state, config)

    async def astream(
        self, state: dict[str, Any], config: Any = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Simulate async streaming."""
        for chunk in self.stream(state, config):
            yield chunk


class MockLangChainRunnable:
    """Mock LangChain Runnable supporting callbacks via config."""

    def __init__(
        self,
        tool_sequence: list[tuple[str, dict[str, Any], Any]] | None = None,
        final_output: str = "Chain finished",
        should_error: bool = False,
        error_message: str = "Chain execution error",
    ) -> None:
        self.tool_sequence = tool_sequence or []
        self.final_output = final_output
        self.should_error = should_error
        self.error_message = error_message

    def invoke(self, input_val: Any, config: dict[str, Any] | None = None) -> Any:
        """Simulate Runnable.invoke triggering callbacks."""
        callbacks = (config or {}).get("callbacks", [])

        if self.should_error:
            for cb in callbacks:
                if hasattr(cb, "on_chain_error"):
                    cb.on_chain_error(RuntimeError(self.error_message))
            raise RuntimeError(self.error_message)

        for name, args, res in self.tool_sequence:
            for cb in callbacks:
                if hasattr(cb, "on_tool_start"):
                    cb.on_tool_start(
                        serialized={"name": name},
                        input_str="",
                        inputs=args,
                    )
                if hasattr(cb, "on_tool_end"):
                    cb.on_tool_end(output=res)

        return {"output": self.final_output}

    async def ainvoke(
        self, input_val: Any, config: dict[str, Any] | None = None
    ) -> Any:
        """Simulate async Runnable.ainvoke."""
        return self.invoke(input_val, config)


class MockOpenAICompletion:
    """Mock ChatCompletion response object with choices, tool calls, and usage."""

    def __init__(
        self,
        content: str | None = "Response text",
        tool_calls: list[dict[str, Any]] | None = None,
        model: str = "gpt-4o",
        finish_reason: str = "stop",
        prompt_tokens: int | None = 15,
        completion_tokens: int | None = 25,
        total_tokens: int | None = 40,
        cached_tokens: int | None = None,
    ) -> None:
        self.model = model
        self.choices = [
            MockChoice(
                content=content,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
            )
        ]
        self.usage = MockUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cached_tokens=cached_tokens,
        )


class MockChoice:
    def __init__(
        self,
        content: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        finish_reason: str = "stop",
    ) -> None:
        self.message = MockMessage(content=content, tool_calls=tool_calls)
        self.finish_reason = finish_reason


class MockMessage:
    def __init__(
        self,
        content: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> None:
        self.role = "assistant"
        self.content = content
        self.tool_calls = [MockToolCall(tc) for tc in (tool_calls or [])]


class MockToolCall:
    def __init__(self, data: dict[str, Any]) -> None:
        self.id = data.get("id", "call_123")
        self.type = "function"
        fn = data.get("function", {})
        self.function = MockFunction(
            name=fn.get("name", data.get("name", "")),
            arguments=fn.get("arguments", data.get("arguments", "{}")),
        )


class MockFunction:
    def __init__(self, name: str, arguments: Any) -> None:
        self.name = name
        self.arguments = (
            arguments if isinstance(arguments, str) else json.dumps(arguments)
        )


class MockUsage:
    def __init__(
        self,
        prompt_tokens: int | None = 10,
        completion_tokens: int | None = 20,
        total_tokens: int | None = 30,
        cached_tokens: int | None = None,
    ) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens
        if cached_tokens is not None:
            self.prompt_tokens_details = {"cached_tokens": cached_tokens}
        else:
            self.prompt_tokens_details = None


class MockStreamChunk:
    """Mock streaming chunk from chat.completions.create(stream=True)."""

    def __init__(
        self,
        content: str | None = None,
        tool_call_delta: dict[str, Any] | None = None,
        finish_reason: str | None = None,
        model: str = "gpt-4o",
        usage: dict[str, Any] | None = None,
    ) -> None:
        self.model = model
        self.choices = [
            MockChunkChoice(
                content=content,
                tool_call_delta=tool_call_delta,
                finish_reason=finish_reason,
            )
        ]
        self.usage = usage


class MockChunkChoice:
    def __init__(
        self,
        content: str | None = None,
        tool_call_delta: dict[str, Any] | None = None,
        finish_reason: str | None = None,
    ) -> None:
        self.delta = MockChunkDelta(content=content, tool_call_delta=tool_call_delta)
        self.finish_reason = finish_reason


class MockChunkDelta:
    def __init__(
        self,
        content: str | None = None,
        tool_call_delta: dict[str, Any] | None = None,
    ) -> None:
        self.content = content
        self.tool_calls = [tool_call_delta] if tool_call_delta else None


class MockOpenAIClient:
    """Mock client replicating `client.chat.completions.create(...)`."""

    def __init__(
        self,
        response: Any = None,
        should_error: bool = False,
        error_message: str = "API Rate Limit Exceeded",
        stream_chunks: list[Any] | None = None,
    ) -> None:
        self.response = response or MockOpenAICompletion()
        self.should_error = should_error
        self.error_message = error_message
        self.stream_chunks = stream_chunks
        self.call_history: list[dict[str, Any]] = []

    @property
    def chat(self) -> Any:
        return self

    @property
    def completions(self) -> Any:
        return self

    def create(self, **kwargs: Any) -> Any:
        self.call_history.append(kwargs)
        if self.should_error:
            raise RuntimeError(self.error_message)
        if kwargs.get("stream", False) and self.stream_chunks is not None:
            return iter(self.stream_chunks)
        return self.response

    async def acreate(self, **kwargs: Any) -> Any:
        return self.create(**kwargs)


__all__ = [
    "MockAIMessage",
    "MockLangChainRunnable",
    "MockLangGraphApp",
    "MockOpenAIClient",
    "MockOpenAICompletion",
    "MockStreamChunk",
    "MockToolMessage",
]
