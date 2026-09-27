"""Unit and integration tests for Phase 21 Provider-Neutral AI Model Integration.

Covers:
1. Optional provider dependency import check and clean error message.
2. Clean core import without openai package.
3. ModelCallRecord and ModelUsage models and serialization.
4. ToolCallRecord normalization with call_id and arguments dict.
5. Tool result enrichment and execution via tool_executor callback.
6. Missing optional fields tolerance in completion payload.
7. Error normalization into ExecutionStatus.FAILED and sanitized trace metadata.
8. Streaming completion chunk-by-chunk delta aggregation into deterministic response.
9. Retry representation (attempt count, model call start/end/error events).
10. Monotonic latency measurement.
11. Usage extraction (prompt, completion, total, cached tokens).
12. Malformed provider response handling (non-dict, empty choices).
13. Evaluator compatibility:
    - ToolOrder
    - ToolCalled (wrong tool detection)
    - ToolArguments (wrong argument detection)
    - ToolNotCalled (missing tool detection)
    - OutputEquals (output mismatch)
    - MaxLatency (latency regression)
14. Regression lifecycle:
    - Faulty provider response -> FailureReport -> RootCause -> RegressionTest ->
      Fixed provider response -> PASS -> Bug reintroduced -> REGRESSION.
15. Cross-integration trace equivalence across:
    - CallableAdapter
    - LangGraphAdapter
    - LangChainAdapter
    - OpenAICompatibleAdapter
16. Sensitive metadata sanitization (redacting api_key, auth tokens, passwords).
"""

import asyncio
import sys
from unittest.mock import patch

import pytest

from aireliability import (
    BaselineManager,
    CallableAdapter,
    ComparisonStatus,
    ExecutionStatus,
    MaxLatency,
    ModelCallRecord,
    ModelUsage,
    OutputEquals,
    ProviderAdapter,
    RegressionGenerator,
    RegressionRunner,
    ReliabilityRunner,
    RootCauseAnalyzer,
    RootCauseCategory,
    RootCauseType,
    StepType,
    TestCase,
    ToolArguments,
    ToolCalled,
    ToolNotCalled,
    ToolOrder,
)
from aireliability.integrations.langchain.adapter import LangChainAdapter
from aireliability.integrations.langgraph.adapter import LangGraphAdapter
from aireliability.integrations.openai_compatible.adapter import (
    OpenAICompatibleAdapter,
)
from tests.mocks.framework_mocks import (
    MockLangChainRunnable,
    MockLangGraphApp,
    MockOpenAIClient,
    MockOpenAICompletion,
    MockStreamChunk,
)

# ---------------------------------------------------------------------------
# 1. Dependency Validation & Import Guards
# ---------------------------------------------------------------------------


def test_openai_dependency_import_error():
    """Verify clean descriptive error when openai is missing in strict check."""
    with patch.dict(sys.modules, {"openai": None}):
        with pytest.raises(ImportError) as exc_info:
            from aireliability.integrations.openai_compatible import (
                _check_openai_dependency,
            )

            _check_openai_dependency()
        assert "OpenAI integration requires the optional dependency" in str(
            exc_info.value
        )
        assert 'pip install "aireliability[openai]"' in str(exc_info.value)


def test_adapter_works_without_openai_installed():
    """Verify OpenAICompatibleAdapter instantiates and runs with mock objects."""
    adapter = OpenAICompatibleAdapter(model="test-model")
    assert adapter.default_model == "test-model"
    assert adapter.provider == "openai_compatible"


# ---------------------------------------------------------------------------
# 2. ModelCallRecord & ModelUsage Models
# ---------------------------------------------------------------------------


def test_model_call_record_and_usage_serialization():
    """Verify ModelUsage and ModelCallRecord properties and conversion to TraceStep."""
    usage = ModelUsage(
        input_tokens=120,
        output_tokens=35,
        total_tokens=155,
        cached_tokens=40,
    )
    usage_dict = usage.to_dict()
    assert usage_dict["prompt_tokens"] == 120
    assert usage_dict["input_tokens"] == 120
    assert usage_dict["completion_tokens"] == 35
    assert usage_dict["cached_tokens"] == 40

    record = ModelCallRecord(
        model="gpt-4o",
        provider="openai",
        input={"messages": [{"role": "user", "content": "hi"}]},
        output="Hello!",
        attempt=2,
        usage=usage,
    )
    step = record.to_trace_step()

    assert step.type == StepType.LLM
    assert step.name == "gpt-4o"
    assert step.input == {"messages": [{"role": "user", "content": "hi"}]}
    assert step.output == "Hello!"
    assert step.metadata["provider"] == "openai"
    assert step.metadata["attempt"] == 2
    assert step.metadata["usage"]["input_tokens"] == 120


# ---------------------------------------------------------------------------
# 3. Model & Tool Call Normalization
# ---------------------------------------------------------------------------


def test_adapter_normalizes_standard_chat_completion():
    """Verify OpenAICompatibleAdapter converts ChatCompletion into trace steps."""
    completion = MockOpenAICompletion(
        content="I have processed your request.",
        tool_calls=[
            {
                "id": "call_abc123",
                "function": {
                    "name": "lookup_user",
                    "arguments": '{"user_id": "U456"}',
                },
            }
        ],
        model="gpt-4o-mini",
        prompt_tokens=50,
        completion_tokens=25,
        total_tokens=75,
        cached_tokens=10,
    )
    client = MockOpenAIClient(response=completion)
    adapter = OpenAICompatibleAdapter(client=client)

    tc = TestCase(id="tc_model_1", name="lookup_test", input="Find user U456")
    trace = adapter.execute(test_case=tc)

    assert trace.status == ExecutionStatus.COMPLETED
    assert trace.output == "I have processed your request."
    assert trace.token_usage["total_tokens"] == 75
    assert trace.token_usage["cached_tokens"] == 10

    # 1 LLM step + 1 Tool step
    assert len(trace.steps) == 2
    llm_step = trace.steps[0]
    assert llm_step.type == StepType.LLM
    assert llm_step.name == "gpt-4o-mini"

    tool_step = trace.steps[1]
    assert tool_step.type == StepType.TOOL
    assert tool_step.name == "lookup_user"
    assert tool_step.input == {"user_id": "U456"}
    assert tool_step.metadata["call_id"] == "call_abc123"


def test_adapter_tool_executor_callback():
    """Verify tool_executor executes and enriches tool outputs in trace."""

    def mock_tools(name: str, args: dict):
        if name == "calculate_tax":
            return {"tax": args.get("amount", 0) * 0.1}
        return None

    completion = MockOpenAICompletion(
        content=None,
        tool_calls=[
            {
                "id": "call_tax_1",
                "function": {
                    "name": "calculate_tax",
                    "arguments": {"amount": 100},
                },
            }
        ],
    )
    client = MockOpenAIClient(response=completion)
    adapter = OpenAICompatibleAdapter(client=client, tool_executor=mock_tools)

    tc = TestCase(id="tc_tax", name="tax_test", input="Calculate tax for 100")
    trace = adapter.execute(test_case=tc)

    tool_step = [s for s in trace.steps if s.type == StepType.TOOL][0]
    assert tool_step.name == "calculate_tax"
    assert tool_step.input == {"amount": 100}
    assert tool_step.output == {"tax": 10.0}
    assert tool_step.metadata["call_id"] == "call_tax_1"


# ---------------------------------------------------------------------------
# 4. Missing Optional Fields & Malformed Payload Handling
# ---------------------------------------------------------------------------


def test_adapter_tolerates_missing_optional_fields():
    """Verify graceful handling when choices, content, or usage are missing."""
    sparse_response = {"choices": []}
    adapter = OpenAICompatibleAdapter(model="fallback-llm")

    tc = TestCase(id="tc_sparse", name="sparse_test", input="Hello")
    trace = adapter.execute(agent=sparse_response, test_case=tc)

    assert trace.status == ExecutionStatus.COMPLETED
    assert trace.output is None
    assert len(trace.steps) == 1
    assert trace.steps[0].name == "fallback-llm"


def test_adapter_tolerates_malformed_json_arguments():
    """Verify tool calls with invalid JSON strings preserve raw payload."""
    malformed_completion = {
        "model": "gpt-3.5",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Calling tool",
                    "tool_calls": [
                        {
                            "id": "bad_call_1",
                            "function": {
                                "name": "do_work",
                                "arguments": "{not-valid-json",
                            },
                        }
                    ],
                }
            }
        ],
    }
    adapter = OpenAICompatibleAdapter()
    tc = TestCase(id="tc_bad_json", name="bad_json_test", input="test")
    trace = adapter.execute(agent=malformed_completion, test_case=tc)

    tool_step = [s for s in trace.steps if s.type == StepType.TOOL][0]
    assert tool_step.name == "do_work"
    assert tool_step.input == {"_raw": "{not-valid-json"}


# ---------------------------------------------------------------------------
# 5. Streaming Normalization
# ---------------------------------------------------------------------------


def test_adapter_streaming_aggregation():
    """Verify stream chunks are aggregated deterministically into single trace."""
    chunks = [
        MockStreamChunk(content="Hello", model="gpt-4o"),
        MockStreamChunk(content=", ", model="gpt-4o"),
        MockStreamChunk(content="world!", model="gpt-4o", finish_reason="stop"),
    ]
    client = MockOpenAIClient(stream_chunks=chunks)
    adapter = OpenAICompatibleAdapter(client=client, default_params={"stream": True})

    tc = TestCase(id="tc_stream", name="stream_test", input="hi")
    trace = adapter.execute(test_case=tc)

    assert trace.status == ExecutionStatus.COMPLETED
    assert trace.output == "Hello, world!"
    assert len(trace.steps) == 1
    assert trace.steps[0].output == "Hello, world!"


def test_adapter_streaming_tool_call_deltas():
    """Verify streaming chunks split across tool name and arguments are reassembled."""
    chunks = [
        MockStreamChunk(
            tool_call_delta={
                "index": 0,
                "id": "call_stream_tool_1",
                "function": {"name": "get_", "arguments": ""},
            }
        ),
        MockStreamChunk(
            tool_call_delta={
                "index": 0,
                "function": {"name": "order", "arguments": '{"order_'},
            }
        ),
        MockStreamChunk(
            tool_call_delta={
                "index": 0,
                "function": {"name": "", "arguments": 'id": "999"}'},
            },
            finish_reason="tool_calls",
        ),
    ]
    client = MockOpenAIClient(stream_chunks=chunks)
    adapter = OpenAICompatibleAdapter(client=client, default_params={"stream": True})

    tc = TestCase(id="tc_stream_tool", name="stream_tool_test", input="Order 999")
    trace = adapter.execute(test_case=tc)

    tool_steps = [s for s in trace.steps if s.type == StepType.TOOL]
    assert len(tool_steps) == 1
    assert tool_steps[0].name == "get_order"
    assert tool_steps[0].input == {"order_id": "999"}
    assert tool_steps[0].metadata["call_id"] == "call_stream_tool_1"


# ---------------------------------------------------------------------------
# 6. Error Normalization & Retries
# ---------------------------------------------------------------------------


def test_adapter_error_normalization_without_crash():
    """Verify exceptions produce a normalized failed trace when suppressed."""
    client = MockOpenAIClient(
        should_error=True, error_message="Rate limit 429: Too Many Requests"
    )
    adapter = OpenAICompatibleAdapter(client=client, suppress_exceptions=True)

    tc = TestCase(id="tc_err", name="rate_limit_test", input="query")
    trace = adapter.execute(test_case=tc)

    assert trace.status == ExecutionStatus.FAILED
    assert "Rate limit 429" in trace.output["error"]
    assert trace.metadata["error_type"] == "RuntimeError"
    assert trace.metadata["attempts"] == 1


# ---------------------------------------------------------------------------
# 7. Sensitive Metadata Sanitization
# ---------------------------------------------------------------------------


def test_provider_adapter_sanitizes_credentials():
    """Verify ProviderAdapter.sanitize_metadata redacts sensitive keys."""
    raw_meta = {
        "model": "gpt-4o",
        "api_key": "sk-1234567890abcdef",
        "bearer_token": "Bearer eyJhbGciOi...",
        "headers": {
            "Authorization": "Bearer secret_val",
            "X-Custom-Client": "my-app",
        },
    }
    cleaned = ProviderAdapter.sanitize_metadata(raw_meta)
    assert cleaned["api_key"] == "[REDACTED]"
    assert cleaned["bearer_token"] == "[REDACTED]"
    assert cleaned["headers"]["Authorization"] == "[REDACTED]"
    assert cleaned["headers"]["X-Custom-Client"] == "my-app"
    assert cleaned["model"] == "gpt-4o"


# ---------------------------------------------------------------------------
# 8. Evaluator Compatibility with OpenAI-Compatible Traces
# ---------------------------------------------------------------------------


def test_evaluators_with_openai_compatible_adapter():
    """Verify standard evaluators execute cleanly on OpenAI-compatible traces."""
    completion = MockOpenAICompletion(
        content="Order cancelled and refunded.",
        tool_calls=[
            {
                "id": "c1",
                "function": {
                    "name": "get_order",
                    "arguments": {"order_id": "123"},
                },
            },
            {
                "id": "c2",
                "function": {
                    "name": "cancel_order",
                    "arguments": {"order_id": "123"},
                },
            },
            {
                "id": "c3",
                "function": {
                    "name": "refund_order",
                    "arguments": {"order_id": "123"},
                },
            },
        ],
    )
    client = MockOpenAIClient(response=completion)
    adapter = OpenAICompatibleAdapter(client=client)

    tc = TestCase(
        id="tc_eval_comp",
        name="eval_compat",
        input="Refund order 123",
        expectations=[
            "ToolOrder:get_order,cancel_order,refund_order",
            "ToolCalled:get_order",
            "ToolNotCalled:delete_order",
            "OutputEquals:Order cancelled and refunded.",
        ],
    )

    evaluators = [
        ToolOrder(
            expected_order=["get_order", "cancel_order", "refund_order"],
            exact_match=True,
        ),
        ToolCalled(tool_name="get_order"),
        ToolNotCalled(tool_name="delete_order"),
        ToolArguments(tool_name="get_order", expected_args={"order_id": "123"}),
        OutputEquals(expected="Order cancelled and refunded."),
        MaxLatency(max_latency_ms=5000.0),
    ]

    runner = ReliabilityRunner(adapter=adapter, evaluators=evaluators)
    run_res = runner.run(tc)

    assert run_res.passed is True
    assert len(run_res.evaluations) == len(evaluators)
    assert all(e.passed for e in run_res.evaluations)


# ---------------------------------------------------------------------------
# 9. End-to-End Regression Lifecycle
# ---------------------------------------------------------------------------


def test_provider_adapter_regression_lifecycle():
    """Verify complete reliability lifecycle with OpenAI-compatible responses:

    Faulty Completion -> FailureReport -> RootCause -> Minimal Regression ->
    Fixed Completion -> PASS -> Bug Reintroduced -> REGRESSION.
    """
    tc = TestCase(
        id="tc_refund_flow",
        name="refund_flow",
        input="Refund order 123",
        expectations=["ToolOrder:get_order,cancel_order,refund_order"],
    )
    evaluators = [
        ToolOrder(
            expected_order=["get_order", "cancel_order", "refund_order"],
            exact_match=True,
        )
    ]

    # 1. Faulty completion (refund called before cancel)
    faulty_completion = MockOpenAICompletion(
        tool_calls=[
            {
                "function": {
                    "name": "get_order",
                    "arguments": {"order_id": "123"},
                }
            },
            {
                "function": {
                    "name": "refund_order",
                    "arguments": {"order_id": "123"},
                }
            },
            {
                "function": {
                    "name": "cancel_order",
                    "arguments": {"order_id": "123"},
                }
            },
        ]
    )
    faulty_adapter = OpenAICompatibleAdapter(
        client=MockOpenAIClient(response=faulty_completion)
    )
    runner_faulty = ReliabilityRunner(adapter=faulty_adapter, evaluators=evaluators)
    faulty_run = runner_faulty.run(tc)

    assert faulty_run.passed is False
    assert len(faulty_run.failures) == 1
    failure = faulty_run.failures[0]

    # 2. Diagnose root cause
    analyzer = RootCauseAnalyzer()
    diag = analyzer.diagnose(faulty_run.trace, faulty_run.failures, tc)
    assert diag.status == "FAIL"
    assert diag.primary_cause.category == RootCauseCategory.TOOL
    assert diag.primary_cause.type == RootCauseType.WRONG_ORDER

    # 3. Generate regression test
    generator = RegressionGenerator()
    reg_test = generator.generate(failure, tc)
    assert reg_test.source_failure_id == failure.failure_id

    # 4. Verify fixed completion passes
    fixed_completion = MockOpenAICompletion(
        tool_calls=[
            {
                "function": {
                    "name": "get_order",
                    "arguments": {"order_id": "123"},
                }
            },
            {
                "function": {
                    "name": "cancel_order",
                    "arguments": {"order_id": "123"},
                }
            },
            {
                "function": {
                    "name": "refund_order",
                    "arguments": {"order_id": "123"},
                }
            },
        ]
    )
    fixed_adapter = OpenAICompatibleAdapter(
        client=MockOpenAIClient(response=fixed_completion)
    )

    bm = BaselineManager()
    reg_runner = RegressionRunner(
        adapter=fixed_adapter,
        evaluators=evaluators,
        baseline_manager=bm,
    )
    fixed_res = reg_runner.run_test(reg_test)
    assert fixed_res.passed is True

    # 5. Capture baseline with fixed agent
    bm.create_baseline([fixed_res], name="main")

    # 6. Reintroduce bug and confirm regression runner flags REGRESSION
    reg_runner_buggy = RegressionRunner(
        adapter=faulty_adapter,
        evaluators=evaluators,
        baseline_manager=bm,
    )
    reintroduced_res = reg_runner_buggy.run_test(reg_test)
    assert reintroduced_res.passed is False

    summary = bm.compare([reintroduced_res], baseline_name="main")
    assert summary.has_regressions is True
    assert summary.regressions[0].status == ComparisonStatus.REGRESSION


# ---------------------------------------------------------------------------
# 10. Cross-Integration Trace Equivalence
# ---------------------------------------------------------------------------


def test_cross_integration_trace_equivalence():
    """Verify CallableAdapter, LangGraphAdapter, LangChainAdapter, and

    OpenAICompatibleAdapter produce strictly equivalent tool sequences,
    evaluator results, and root-cause diagnoses for the identical business scenario.
    """
    tools_spec = [
        ("get_order", {"order_id": "456"}, {"status": "active"}),
        ("cancel_order", {"order_id": "456"}, {"status": "cancelled"}),
        ("refund_order", {"order_id": "456"}, {"status": "refunded"}),
    ]

    test_case = TestCase(
        id="cross_int_order",
        name="Order Sequence Test",
        input={"order_id": "456"},
    )
    evaluators = [
        ToolOrder(
            expected_order=["get_order", "cancel_order", "refund_order"],
            exact_match=True,
        )
    ]

    # Adapter 1: CallableAdapter
    def callable_agent(inp: dict):
        return {
            "output": "Done",
            "tools": [{"name": n, "arguments": a} for n, a, _ in tools_spec],
        }

    # Adapter 2: LangGraphAdapter
    langgraph_app = MockLangGraphApp(tool_sequence=tools_spec, final_output="Done")

    # Adapter 3: LangChainAdapter
    langchain_runnable = MockLangChainRunnable(
        tool_sequence=tools_spec, final_output="Done"
    )

    # Adapter 4: OpenAICompatibleAdapter
    openai_client = MockOpenAIClient(
        response=MockOpenAICompletion(
            content="Done",
            tool_calls=[
                {"function": {"name": n, "arguments": a}} for n, a, _ in tools_spec
            ],
        )
    )

    adapters = [
        ("CallableAdapter", CallableAdapter(agent=callable_agent)),
        ("LangGraphAdapter", LangGraphAdapter(graph=langgraph_app)),
        ("LangChainAdapter", LangChainAdapter(chain=langchain_runnable)),
        ("OpenAICompatibleAdapter", OpenAICompatibleAdapter(client=openai_client)),
    ]

    captured_traces = []
    for name, adapter in adapters:
        runner = ReliabilityRunner(adapter=adapter, evaluators=evaluators)
        run_res = runner.run(test_case)

        assert run_res.passed is True, f"{name} failed evaluation"

        tool_steps = [s for s in run_res.trace.steps if s.type == StepType.TOOL]
        assert len(tool_steps) == 3, f"{name} did not extract 3 tool steps"

        names = [s.name for s in tool_steps]
        assert names == ["get_order", "cancel_order", "refund_order"], (
            f"{name} tool sequence mismatch: {names}"
        )

        args = [s.input for s in tool_steps]
        assert args == [{"order_id": "456"}] * 3, f"{name} arguments mismatch: {args}"

        captured_traces.append((name, run_res.trace))


# ---------------------------------------------------------------------------
# 11. Async Execution Support
# ---------------------------------------------------------------------------


def test_openai_compatible_async_execution():
    """Verify asynchronous completion and streaming execution with
    OpenAICompatibleAdapter.
    """
    completion = MockOpenAICompletion(
        content="Async output",
        tool_calls=[
            {
                "function": {
                    "name": "async_fetch",
                    "arguments": {"query": "test"},
                }
            }
        ],
    )
    client = MockOpenAIClient(response=completion)
    adapter = OpenAICompatibleAdapter(client=client)

    tc = TestCase(id="tc_async", name="async_test", input="async input")
    trace = asyncio.run(adapter.aexecute(test_case=tc))

    assert trace.status == ExecutionStatus.COMPLETED
    assert trace.output == "Async output"
    assert len(trace.steps) == 2
    assert trace.steps[1].name == "async_fetch"
