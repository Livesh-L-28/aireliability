"""OpenAI-compatible execution adapter for AI Reliability Engine.

Provides normalized trace capture for OpenAI-compatible chat completion APIs,
local LLM servers (vLLM, Ollama, LiteLLM, llama.cpp), and OpenAI SDK clients
without requiring the OpenAI SDK as a mandatory dependency.
"""

import inspect
import json
import time
from collections.abc import AsyncIterator, Callable, Iterator
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
    ExecutionEvent,
    ModelCallRecord,
    ModelUsage,
    ProviderAdapter,
    ToolCallRecord,
)


class OpenAICompatibleAdapter(ProviderAdapter):
    """Execution adapter for OpenAI-compatible model completions and tool calling.

    Normalizes:
    - Model completions (model, content, finish_reason) -> ModelCallRecord / TraceStep
    - Tool calls (name, arguments JSON/dict, call_id) -> ToolCallRecord
    - Tool results -> enriched into matching tool steps
    - Token usage (prompt/input, completion/output, total, cached) -> ModelUsage
    - Streaming responses (chunk-by-chunk delta aggregation)
    - Retry events and attempt counts
    - Latency measurements (using monotonic clock)
    - Error details (sanitized, non-crashing execution trace)

    Does NOT require `openai` installed at import time. Works directly with SDK client
    instances, callable functions, dictionaries, or mocked completion objects.
    """

    def __init__(
        self,
        client: Any = None,
        *,
        model: str | None = None,
        provider: str = "openai_compatible",
        suppress_exceptions: bool = False,
        sanitize_keys: bool = True,
        tool_executor: Callable[[str, dict[str, Any]], Any] | None = None,
        default_params: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            provider=provider,
            suppress_exceptions=suppress_exceptions,
            sanitize_keys=sanitize_keys,
        )
        self.client = client
        self.default_model = model
        self.tool_executor = tool_executor
        self.default_params = default_params or {}

    def execute(
        self,
        agent: Any = None,
        test_case: TestCase | None = None,
    ) -> ExecutionTrace:
        """Execute an OpenAI-compatible agent/client and produce an ExecutionTrace."""
        effective_client = agent if agent is not None else self.client
        effective_test_case = test_case

        if effective_test_case is None and isinstance(agent, TestCase):
            effective_test_case = agent
            effective_client = self.client

        if effective_test_case is None:
            raise ValueError("A TestCase must be provided to execute.")

        start_wall = datetime.now(UTC)
        t0 = time.perf_counter()

        steps: list[TraceStep] = []
        events: list[ExecutionEvent] = []
        status = ExecutionStatus.COMPLETED
        final_output: Any = None
        error_details: dict[str, Any] = {}
        token_usage_dict: dict[str, int] = {}
        attempts = 0

        # Format prompt / messages
        input_payload = self._format_input(effective_test_case.input)

        try:
            attempts += 1
            events.append(
                ExecutionEvent(
                    type=AgentEventType.MODEL_CALL_START,
                    name="model_call",
                    timestamp=datetime.now(UTC),
                    payload={"attempt": attempts},
                )
            )

            raw_response = self._invoke_target(effective_client, input_payload)

            # Check if response is a streaming generator/iterator
            if inspect.isgenerator(raw_response) or hasattr(raw_response, "__next__"):
                raw_response = self._consume_stream(raw_response, events)

            # Normalize completion object / dict
            model_record, tool_records, final_output = self._normalize_response(
                raw_response,
                input_payload=input_payload,
                attempt=attempts,
            )

            # Record model step
            steps.append(model_record.to_trace_step())

            # If tools were invoked and a tool executor was provided, execute tools
            for tr in tool_records:
                if self.tool_executor is not None:
                    t_res = self.tool_executor(tr.name, tr.arguments)
                    enriched_tr = ToolCallRecord(
                        name=tr.name,
                        arguments=tr.arguments,
                        result=t_res,
                        call_id=tr.call_id,
                        started_at=tr.started_at,
                        completed_at=datetime.now(UTC),
                        status="completed",
                        metadata=tr.metadata,
                    )
                    steps.append(enriched_tr.to_trace_step())
                else:
                    steps.append(tr.to_trace_step())

            # Usage
            if model_record.usage is not None:
                token_usage_dict = model_record.usage.to_dict()

            events.append(
                ExecutionEvent(
                    type=AgentEventType.MODEL_CALL_END,
                    name="model_call",
                    timestamp=datetime.now(UTC),
                    payload={"attempt": attempts, "status": "completed"},
                )
            )

        except Exception as exc:
            status = ExecutionStatus.FAILED
            err_msg = str(exc)
            err_type = type(exc).__name__
            error_details = {
                "error": err_msg,
                "error_type": err_type,
                "provider": self.provider,
                "attempt": attempts,
            }
            events.append(
                ExecutionEvent(
                    type=AgentEventType.MODEL_CALL_ERROR,
                    name="model_call",
                    timestamp=datetime.now(UTC),
                    payload=error_details,
                )
            )
            final_output = error_details

            # Record failed model step if none exists
            if not steps:
                failed_model_step = TraceStep(
                    type=StepType.LLM,
                    name=self.default_model or "model",
                    input=input_payload,
                    output=error_details,
                    metadata={"status": "failed", "error": err_msg},
                )
                steps.append(failed_model_step)

            if not self.suppress_exceptions:
                t1 = time.perf_counter()
                end_wall = datetime.now(UTC)
                duration_ms = (t1 - t0) * 1000.0
                trace = ExecutionTrace(
                    test_id=effective_test_case.id,
                    input=effective_test_case.input,
                    output=final_output,
                    status=status,
                    started_at=start_wall,
                    completed_at=end_wall,
                    latency_ms=max(0.0, duration_ms),
                    steps=steps,
                    token_usage=token_usage_dict,
                    metadata=self.sanitize_metadata(error_details)
                    if self.sanitize_keys
                    else error_details,
                )
                exc.execution_trace = trace  # type: ignore[attr-defined]
                raise exc

        t1 = time.perf_counter()
        end_wall = datetime.now(UTC)
        duration_ms = (t1 - t0) * 1000.0

        trace_meta = {
            "provider": self.provider,
            "attempts": attempts,
            **error_details,
        }
        if self.sanitize_keys:
            trace_meta = self.sanitize_metadata(trace_meta)

        return ExecutionTrace(
            test_id=effective_test_case.id,
            input=effective_test_case.input,
            output=final_output,
            status=status,
            started_at=start_wall,
            completed_at=end_wall,
            latency_ms=max(0.0, duration_ms),
            steps=steps,
            token_usage=token_usage_dict,
            metadata=trace_meta,
        )

    async def aexecute(
        self,
        agent: Any = None,
        test_case: TestCase | None = None,
    ) -> ExecutionTrace:
        """Asynchronously execute an OpenAI-compatible agent/client."""
        effective_client = agent if agent is not None else self.client
        effective_test_case = test_case

        if effective_test_case is None and isinstance(agent, TestCase):
            effective_test_case = agent
            effective_client = self.client

        if effective_test_case is None:
            raise ValueError("A TestCase must be provided to execute.")

        start_wall = datetime.now(UTC)
        t0 = time.perf_counter()

        steps: list[TraceStep] = []
        events: list[ExecutionEvent] = []
        status = ExecutionStatus.COMPLETED
        final_output: Any = None
        error_details: dict[str, Any] = {}
        token_usage_dict: dict[str, int] = {}
        attempts = 0

        input_payload = self._format_input(effective_test_case.input)

        try:
            attempts += 1
            events.append(
                ExecutionEvent(
                    type=AgentEventType.MODEL_CALL_START,
                    name="model_call",
                    timestamp=datetime.now(UTC),
                    payload={"attempt": attempts},
                )
            )

            raw_response = await self._ainvoke_target(effective_client, input_payload)

            if hasattr(raw_response, "__aiter__"):
                raw_response = await self._aconsume_stream(raw_response, events)

            model_record, tool_records, final_output = self._normalize_response(
                raw_response,
                input_payload=input_payload,
                attempt=attempts,
            )

            steps.append(model_record.to_trace_step())

            for tr in tool_records:
                if self.tool_executor is not None:
                    if inspect.iscoroutinefunction(self.tool_executor):
                        t_res = await self.tool_executor(tr.name, tr.arguments)
                    else:
                        t_res = self.tool_executor(tr.name, tr.arguments)
                    enriched_tr = ToolCallRecord(
                        name=tr.name,
                        arguments=tr.arguments,
                        result=t_res,
                        call_id=tr.call_id,
                        started_at=tr.started_at,
                        completed_at=datetime.now(UTC),
                        status="completed",
                        metadata=tr.metadata,
                    )
                    steps.append(enriched_tr.to_trace_step())
                else:
                    steps.append(tr.to_trace_step())

            if model_record.usage is not None:
                token_usage_dict = model_record.usage.to_dict()

            events.append(
                ExecutionEvent(
                    type=AgentEventType.MODEL_CALL_END,
                    name="model_call",
                    timestamp=datetime.now(UTC),
                    payload={"attempt": attempts, "status": "completed"},
                )
            )

        except Exception as exc:
            status = ExecutionStatus.FAILED
            err_msg = str(exc)
            err_type = type(exc).__name__
            error_details = {
                "error": err_msg,
                "error_type": err_type,
                "provider": self.provider,
                "attempt": attempts,
            }
            events.append(
                ExecutionEvent(
                    type=AgentEventType.MODEL_CALL_ERROR,
                    name="model_call",
                    timestamp=datetime.now(UTC),
                    payload=error_details,
                )
            )
            final_output = error_details

            if not steps:
                failed_model_step = TraceStep(
                    type=StepType.LLM,
                    name=self.default_model or "model",
                    input=input_payload,
                    output=error_details,
                    metadata={"status": "failed", "error": err_msg},
                )
                steps.append(failed_model_step)

            if not self.suppress_exceptions:
                t1 = time.perf_counter()
                end_wall = datetime.now(UTC)
                duration_ms = (t1 - t0) * 1000.0
                trace = ExecutionTrace(
                    test_id=effective_test_case.id,
                    input=effective_test_case.input,
                    output=final_output,
                    status=status,
                    started_at=start_wall,
                    completed_at=end_wall,
                    latency_ms=max(0.0, duration_ms),
                    steps=steps,
                    token_usage=token_usage_dict,
                    metadata=self.sanitize_metadata(error_details)
                    if self.sanitize_keys
                    else error_details,
                )
                exc.execution_trace = trace  # type: ignore[attr-defined]
                raise exc

        t1 = time.perf_counter()
        end_wall = datetime.now(UTC)
        duration_ms = (t1 - t0) * 1000.0

        trace_meta = {
            "provider": self.provider,
            "attempts": attempts,
            **error_details,
        }
        if self.sanitize_keys:
            trace_meta = self.sanitize_metadata(trace_meta)

        return ExecutionTrace(
            test_id=effective_test_case.id,
            input=effective_test_case.input,
            output=final_output,
            status=status,
            started_at=start_wall,
            completed_at=end_wall,
            latency_ms=max(0.0, duration_ms),
            steps=steps,
            token_usage=token_usage_dict,
            metadata=trace_meta,
        )

    # --------------------------------------------------------------------------
    # Invocation dispatch helpers
    # --------------------------------------------------------------------------

    def _invoke_target(self, target: Any, input_payload: dict[str, Any]) -> Any:
        """Invoke the target object (callable, OpenAI client, or chat.completions)."""
        if hasattr(target, "chat") and hasattr(target.chat, "completions"):
            # Official or duck-typed OpenAI client: client.chat.completions.create(...)
            kwargs = {**self.default_params, **input_payload}
            if self.default_model and "model" not in kwargs:
                kwargs["model"] = self.default_model
            return target.chat.completions.create(**kwargs)

        if hasattr(target, "create") and callable(target.create):
            # completions resource object
            kwargs = {**self.default_params, **input_payload}
            if self.default_model and "model" not in kwargs:
                kwargs["model"] = self.default_model
            return target.create(**kwargs)

        if callable(target):
            # Callable function or mock agent
            return target(input_payload)

        # Direct response dictionary or mock object passed
        return target

    async def _ainvoke_target(self, target: Any, input_payload: dict[str, Any]) -> Any:
        """Asynchronously invoke the target object."""
        if hasattr(target, "chat") and hasattr(target.chat, "completions"):
            create_fn = target.chat.completions.create
            kwargs = {**self.default_params, **input_payload}
            if self.default_model and "model" not in kwargs:
                kwargs["model"] = self.default_model
            if inspect.iscoroutinefunction(create_fn):
                return await create_fn(**kwargs)
            return create_fn(**kwargs)

        if hasattr(target, "create") and callable(target.create):
            create_fn = target.create
            kwargs = {**self.default_params, **input_payload}
            if self.default_model and "model" not in kwargs:
                kwargs["model"] = self.default_model
            if inspect.iscoroutinefunction(create_fn):
                return await create_fn(**kwargs)
            return create_fn(**kwargs)

        if callable(target):
            if inspect.iscoroutinefunction(target):
                return await target(input_payload)
            return target(input_payload)

        return target

    def _format_input(self, tc_input: Any) -> dict[str, Any]:
        """Convert test case inputs into standard OpenAI request parameters."""
        if isinstance(tc_input, dict):
            if "messages" in tc_input:
                return tc_input
            if "prompt" in tc_input:
                return {"messages": [{"role": "user", "content": tc_input["prompt"]}]}
            return {"messages": [{"role": "user", "content": str(tc_input)}]}
        if isinstance(tc_input, list):
            return {"messages": tc_input}
        return {"messages": [{"role": "user", "content": str(tc_input)}]}

    # --------------------------------------------------------------------------
    # Streaming aggregation
    # --------------------------------------------------------------------------

    def _consume_stream(
        self,
        stream: Iterator[Any],
        events: list[ExecutionEvent],
    ) -> dict[str, Any]:
        """Aggregate streaming chunks deterministically into a single response dict."""
        events.append(
            ExecutionEvent(
                type=AgentEventType.STREAM_START,
                name="stream",
                timestamp=datetime.now(UTC),
            )
        )

        content_parts: list[str] = []
        tool_call_deltas: dict[int, dict[str, Any]] = {}
        model_name = self.default_model or "openai-model"
        finish_reason: str | None = None
        usage_data: dict[str, Any] | None = None

        for chunk in stream:
            events.append(
                ExecutionEvent(
                    type=AgentEventType.STREAM_CHUNK,
                    name="chunk",
                    timestamp=datetime.now(UTC),
                )
            )

            # Extract model if available
            c_model = getattr(chunk, "model", None) or (
                chunk.get("model") if isinstance(chunk, dict) else None
            )
            if c_model:
                model_name = c_model

            # Extract choices / deltas
            choices = getattr(chunk, "choices", None) or (
                chunk.get("choices") if isinstance(chunk, dict) else []
            )
            if choices:
                ch0 = choices[0]
                delta = getattr(ch0, "delta", None) or (
                    ch0.get("delta") if isinstance(ch0, dict) else {}
                )
                fr = getattr(ch0, "finish_reason", None) or (
                    ch0.get("finish_reason") if isinstance(ch0, dict) else None
                )
                if fr:
                    finish_reason = fr

                # Text delta
                delta_content = getattr(delta, "content", None) or (
                    delta.get("content") if isinstance(delta, dict) else None
                )
                if delta_content:
                    content_parts.append(delta_content)

                # Tool call deltas
                tc_deltas = getattr(delta, "tool_calls", None) or (
                    delta.get("tool_calls") if isinstance(delta, dict) else None
                )
                if tc_deltas:
                    for tc in tc_deltas:
                        idx = getattr(tc, "index", 0) or (
                            tc.get("index", 0) if isinstance(tc, dict) else 0
                        )
                        if idx not in tool_call_deltas:
                            tool_call_deltas[idx] = {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        cid = getattr(tc, "id", None) or (
                            tc.get("id") if isinstance(tc, dict) else None
                        )
                        if cid:
                            tool_call_deltas[idx]["id"] += cid

                        fn = getattr(tc, "function", None) or (
                            tc.get("function") if isinstance(tc, dict) else None
                        )
                        if fn:
                            fn_name = getattr(fn, "name", None) or (
                                fn.get("name") if isinstance(fn, dict) else None
                            )
                            fn_args = getattr(fn, "arguments", None) or (
                                fn.get("arguments") if isinstance(fn, dict) else None
                            )
                            if fn_name:
                                tool_call_deltas[idx]["function"]["name"] += fn_name
                            if fn_args:
                                tool_call_deltas[idx]["function"]["arguments"] += (
                                    fn_args
                                )

            # Check chunk usage (e.g. stream_options={"include_usage": true})
            chunk_usage = getattr(chunk, "usage", None) or (
                chunk.get("usage") if isinstance(chunk, dict) else None
            )
            if chunk_usage:
                usage_data = (
                    chunk_usage.model_dump()
                    if hasattr(chunk_usage, "model_dump")
                    else dict(chunk_usage)
                )

        events.append(
            ExecutionEvent(
                type=AgentEventType.STREAM_END,
                name="stream",
                timestamp=datetime.now(UTC),
            )
        )

        aggregated_tools = [
            tool_call_deltas[i] for i in sorted(tool_call_deltas.keys())
        ]

        return {
            "model": model_name,
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "".join(content_parts) if content_parts else None,
                        "tool_calls": aggregated_tools if aggregated_tools else None,
                    },
                    "finish_reason": finish_reason or "stop",
                }
            ],
            "usage": usage_data,
        }

    async def _aconsume_stream(
        self,
        stream: AsyncIterator[Any],
        events: list[ExecutionEvent],
    ) -> dict[str, Any]:
        """Asynchronously aggregate streaming chunks."""
        events.append(
            ExecutionEvent(
                type=AgentEventType.STREAM_START,
                name="stream",
                timestamp=datetime.now(UTC),
            )
        )

        content_parts: list[str] = []
        tool_call_deltas: dict[int, dict[str, Any]] = {}
        model_name = self.default_model or "openai-model"
        finish_reason: str | None = None
        usage_data: dict[str, Any] | None = None

        async for chunk in stream:
            events.append(
                ExecutionEvent(
                    type=AgentEventType.STREAM_CHUNK,
                    name="chunk",
                    timestamp=datetime.now(UTC),
                )
            )

            c_model = getattr(chunk, "model", None) or (
                chunk.get("model") if isinstance(chunk, dict) else None
            )
            if c_model:
                model_name = c_model

            choices = getattr(chunk, "choices", None) or (
                chunk.get("choices") if isinstance(chunk, dict) else []
            )
            if choices:
                ch0 = choices[0]
                delta = getattr(ch0, "delta", None) or (
                    ch0.get("delta") if isinstance(ch0, dict) else {}
                )
                fr = getattr(ch0, "finish_reason", None) or (
                    ch0.get("finish_reason") if isinstance(ch0, dict) else None
                )
                if fr:
                    finish_reason = fr

                delta_content = getattr(delta, "content", None) or (
                    delta.get("content") if isinstance(delta, dict) else None
                )
                if delta_content:
                    content_parts.append(delta_content)

                tc_deltas = getattr(delta, "tool_calls", None) or (
                    delta.get("tool_calls") if isinstance(delta, dict) else None
                )
                if tc_deltas:
                    for tc in tc_deltas:
                        idx = getattr(tc, "index", 0) or (
                            tc.get("index", 0) if isinstance(tc, dict) else 0
                        )
                        if idx not in tool_call_deltas:
                            tool_call_deltas[idx] = {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        cid = getattr(tc, "id", None) or (
                            tc.get("id") if isinstance(tc, dict) else None
                        )
                        if cid:
                            tool_call_deltas[idx]["id"] += cid
                        fn = getattr(tc, "function", None) or (
                            tc.get("function") if isinstance(tc, dict) else None
                        )
                        if fn:
                            fn_name = getattr(fn, "name", None) or (
                                fn.get("name") if isinstance(fn, dict) else None
                            )
                            fn_args = getattr(fn, "arguments", None) or (
                                fn.get("arguments") if isinstance(fn, dict) else None
                            )
                            if fn_name:
                                tool_call_deltas[idx]["function"]["name"] += fn_name
                            if fn_args:
                                tool_call_deltas[idx]["function"]["arguments"] += (
                                    fn_args
                                )

            chunk_usage = getattr(chunk, "usage", None) or (
                chunk.get("usage") if isinstance(chunk, dict) else None
            )
            if chunk_usage:
                usage_data = (
                    chunk_usage.model_dump()
                    if hasattr(chunk_usage, "model_dump")
                    else dict(chunk_usage)
                )

        events.append(
            ExecutionEvent(
                type=AgentEventType.STREAM_END,
                name="stream",
                timestamp=datetime.now(UTC),
            )
        )

        aggregated_tools = [
            tool_call_deltas[i] for i in sorted(tool_call_deltas.keys())
        ]

        return {
            "model": model_name,
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "".join(content_parts) if content_parts else None,
                        "tool_calls": aggregated_tools if aggregated_tools else None,
                    },
                    "finish_reason": finish_reason or "stop",
                }
            ],
            "usage": usage_data,
        }

    # --------------------------------------------------------------------------
    # Normalization Helpers
    # --------------------------------------------------------------------------

    def _normalize_response(
        self,
        response: Any,
        *,
        input_payload: Any = None,
        attempt: int = 1,
    ) -> tuple[ModelCallRecord, list[ToolCallRecord], Any]:
        """Normalize an OpenAI completion object or dict into standard structures."""
        # 1. Model name
        model_name = getattr(response, "model", None) or (
            response.get("model") if isinstance(response, dict) else None
        )
        if not model_name:
            model_name = self.default_model or "openai-model"

        # 2. Extract primary choice
        choices = getattr(response, "choices", None) or (
            response.get("choices") if isinstance(response, dict) else []
        )
        choice = choices[0] if choices else None

        message = None
        finish_reason = None
        if choice is not None:
            message = getattr(choice, "message", None) or (
                choice.get("message") if isinstance(choice, dict) else None
            )
            finish_reason = getattr(choice, "finish_reason", None) or (
                choice.get("finish_reason") if isinstance(choice, dict) else None
            )

        # 3. Content output
        content = None
        if message is not None:
            content = getattr(message, "content", None) or (
                message.get("content") if isinstance(message, dict) else None
            )
        elif isinstance(response, (str, int, float)):
            content = str(response)

        # 4. Tool calls
        raw_tool_calls: list[Any] = []
        if message is not None:
            tcs = getattr(message, "tool_calls", None) or (
                message.get("tool_calls") if isinstance(message, dict) else None
            )
            if isinstance(tcs, (list, tuple)):
                raw_tool_calls = list(tcs)

        tool_records: list[ToolCallRecord] = []
        for tc in raw_tool_calls:
            call_id = getattr(tc, "id", None) or (
                tc.get("id") if isinstance(tc, dict) else None
            )
            fn = getattr(tc, "function", None) or (
                tc.get("function") if isinstance(tc, dict) else None
            )

            fn_name = ""
            fn_args_raw: Any = {}
            if fn is not None:
                fn_name = getattr(fn, "name", None) or (
                    fn.get("name") if isinstance(fn, dict) else ""
                )
                fn_args_raw = getattr(fn, "arguments", None) or (
                    fn.get("arguments") if isinstance(fn, dict) else {}
                )
            elif isinstance(tc, dict):
                fn_name = tc.get("name", "")
                fn_args_raw = tc.get("arguments", {})

            # Parse JSON arguments string if supplied as string
            args_dict: dict[str, Any] = {}
            if isinstance(fn_args_raw, str):
                try:
                    args_dict = json.loads(fn_args_raw)
                except Exception:
                    args_dict = {"_raw": fn_args_raw}
            elif isinstance(fn_args_raw, dict):
                args_dict = fn_args_raw

            tr = ToolCallRecord(
                name=fn_name,
                arguments=args_dict,
                call_id=call_id,
                status="completed",
                metadata={"call_id": call_id} if call_id else {},
            )
            tool_records.append(tr)

        # 5. Usage extraction
        usage_record: ModelUsage | None = None
        raw_usage = getattr(response, "usage", None) or (
            response.get("usage") if isinstance(response, dict) else None
        )
        if raw_usage is not None:
            inp_tok = getattr(raw_usage, "prompt_tokens", None) or (
                raw_usage.get("prompt_tokens") if isinstance(raw_usage, dict) else None
            )
            out_tok = getattr(raw_usage, "completion_tokens", None) or (
                raw_usage.get("completion_tokens")
                if isinstance(raw_usage, dict)
                else None
            )
            tot_tok = getattr(raw_usage, "total_tokens", None) or (
                raw_usage.get("total_tokens") if isinstance(raw_usage, dict) else None
            )
            # Support cached token details if available
            cached_tok: int | None = None
            prompt_details = getattr(raw_usage, "prompt_tokens_details", None) or (
                raw_usage.get("prompt_tokens_details")
                if isinstance(raw_usage, dict)
                else None
            )
            if prompt_details is not None:
                cached_tok = getattr(prompt_details, "cached_tokens", None) or (
                    prompt_details.get("cached_tokens")
                    if isinstance(prompt_details, dict)
                    else None
                )

            usage_record = ModelUsage(
                input_tokens=inp_tok,
                output_tokens=out_tok,
                total_tokens=tot_tok,
                cached_tokens=cached_tok,
            )

        model_meta: dict[str, Any] = {"finish_reason": finish_reason}
        if self.sanitize_keys:
            model_meta = self.sanitize_metadata(model_meta)

        model_record = ModelCallRecord(
            model=model_name,
            provider=self.provider,
            input=input_payload,
            output=content,
            status="completed",
            attempt=attempt,
            usage=usage_record,
            tool_calls=tool_records,
            metadata=model_meta,
        )

        # Final output for trace: prefer text content; if empty, format tool names
        final_output = content
        if final_output is None and tool_records:
            final_output = {
                "tool_calls": [
                    {"name": t.name, "arguments": t.arguments} for t in tool_records
                ]
            }

        return model_record, tool_records, final_output
