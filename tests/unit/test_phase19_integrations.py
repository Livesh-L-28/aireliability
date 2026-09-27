"""Unit and integration tests for Phase 19 Framework Integration Layer.

Covers:
1. Graceful import failure when optional framework packages are absent.
2. LangGraphAdapter:
   - Tool sequence extraction and normalization from stream and invoke.
   - Node-level execution capture.
   - Error capture and trace status normalization.
   - Async execution via aexecute().
3. LangChainAdapter:
   - Standard ReliabilityCallbackHandler tool start/end/error event capture.
   - Tool argument and result normalization.
   - Output normalization.
   - Async execution via aexecute().
4. Normalized Trace Equivalence:
   - Verifying that CallableAdapter, LangGraphAdapter, and LangChainAdapter produce
     strictly equivalent ToolCall sequences for the same business logic.
5. Cross-Framework Failure Detection:
   - Verifying that the same ToolOrder evaluator identifies TOOL.WRONG_ORDER across
     all three adapters.
6. Full Provenance & Regression Lifecycle:
   - Trace -> FailureReport -> RootCauseReport -> RegressionGenerator -> RegressionTest.
"""

import asyncio
from typing import Any

import pytest

from aireliability import (
    CallableAdapter,
    ExecutionStatus,
    RegressionGenerator,
    ReliabilityRunner,
    RootCauseAnalyzer,
    RootCauseCategory,
    RootCauseType,
    StepType,
    TestCase,
    ToolOrder,
)
from aireliability.integrations.langchain.adapter import (
    LangChainAdapter,
)
from aireliability.integrations.langgraph.adapter import LangGraphAdapter
from tests.mocks.framework_mocks import (
    MockLangChainRunnable,
    MockLangGraphApp,
)

# ---------------------------------------------------------------------------
# 1. Graceful Import and Dependency Validation
# ---------------------------------------------------------------------------


def test_langgraph_import_error_message():
    """Verify clean error message if langgraph is imported without dependency."""
    import sys
    from unittest.mock import patch

    with patch.dict(sys.modules, {"langgraph": None}):
        with pytest.raises(ImportError) as exc_info:
            from aireliability.integrations.langgraph import (
                LangGraphAdapter,  # noqa: F401
            )
        assert "LangGraph integration requires the optional dependency" in str(
            exc_info.value
        )
        assert 'pip install "aireliability[langgraph]"' in str(exc_info.value)


def test_langchain_import_error_message():
    """Verify clean error message if langchain is imported without dependency."""
    import sys
    from unittest.mock import patch

    with patch.dict(sys.modules, {"langchain_core": None}):
        with pytest.raises(ImportError) as exc_info:
            from aireliability.integrations.langchain import (
                LangChainAdapter,  # noqa: F401
            )
        assert "LangChain integration requires the optional dependency" in str(
            exc_info.value
        )
        assert 'pip install "aireliability[langchain]"' in str(exc_info.value)


# ---------------------------------------------------------------------------
# 2. LangGraphAdapter Tests
# ---------------------------------------------------------------------------


def test_langgraph_adapter_stream_tool_calls():
    """Verify LangGraphAdapter extracts tool sequence, arguments, and outputs."""
    app = MockLangGraphApp(
        tool_sequence=[
            ("get_order", {"order_id": "123"}, {"id": "123", "status": "active"}),
            ("cancel_order", {"order_id": "123"}, {"status": "cancelled"}),
            ("refund_order", {"order_id": "123", "amount": 50}, {"refund_id": "ref_9"}),
        ],
        final_output="Order cancelled and refunded",
    )
    adapter = LangGraphAdapter(graph=app)
    tc = TestCase(name="langgraph_test", input={"order_id": "123"})

    trace = adapter.execute(test_case=tc)

    assert trace.status == ExecutionStatus.COMPLETED
    assert trace.output == "Order cancelled and refunded"
    assert trace.latency_ms is not None and trace.latency_ms >= 0.0

    # Verify extracted tool steps
    tool_steps = [s for s in trace.steps if s.type == StepType.TOOL]
    assert len(tool_steps) == 3
    assert [s.name for s in tool_steps] == [
        "get_order",
        "cancel_order",
        "refund_order",
    ]
    assert tool_steps[0].input == {"order_id": "123"}
    assert tool_steps[0].output == {"id": "123", "status": "active"}
    assert tool_steps[2].input == {"order_id": "123", "amount": 50}


def test_langgraph_adapter_error_normalization():
    """Verify LangGraph error produces normalized ExecutionTrace without crash."""
    app = MockLangGraphApp(should_error=True, error_message="Graph node timeout")
    adapter = LangGraphAdapter(graph=app, suppress_exceptions=True)
    tc = TestCase(name="err_test", input="ping")

    trace = adapter.execute(test_case=tc)

    assert trace.status == ExecutionStatus.FAILED
    assert isinstance(trace.output, dict)
    assert trace.output.get("error") == "Graph node timeout"
    assert trace.output.get("framework") == "langgraph"


def test_langgraph_adapter_async_execution():
    """Verify LangGraphAdapter async execution via aexecute()."""
    app = MockLangGraphApp(
        tool_sequence=[("ping", {}, "pong")],
        final_output="Done",
    )
    adapter = LangGraphAdapter(graph=app)
    tc = TestCase(name="async_lg", input="ping")

    trace = asyncio.run(adapter.aexecute(test_case=tc))

    assert trace.status == ExecutionStatus.COMPLETED
    assert trace.output == "Done"
    tool_steps = [s for s in trace.steps if s.type == StepType.TOOL]
    assert len(tool_steps) == 1
    assert tool_steps[0].name == "ping"


# ---------------------------------------------------------------------------
# 3. LangChainAdapter Tests
# ---------------------------------------------------------------------------


def test_langchain_adapter_callback_capture():
    """Verify LangChainAdapter ReliabilityCallbackHandler captures tools and outputs."""
    runnable = MockLangChainRunnable(
        tool_sequence=[
            ("get_order", {"order_id": "999"}, {"status": "shipped"}),
            ("notify_user", {"message": "Delayed"}, "sent"),
        ],
        final_output="Notification dispatched",
    )
    adapter = LangChainAdapter(chain=runnable)
    tc = TestCase(name="langchain_test", input="Order 999")

    trace = adapter.execute(test_case=tc)

    assert trace.status == ExecutionStatus.COMPLETED
    assert trace.output == "Notification dispatched"

    tool_steps = [s for s in trace.steps if s.type == StepType.TOOL]
    assert len(tool_steps) == 2
    assert [s.name for s in tool_steps] == ["get_order", "notify_user"]
    assert tool_steps[0].input == {"order_id": "999"}
    assert tool_steps[0].output == {"status": "shipped"}


def test_langchain_adapter_error_normalization():
    """Verify LangChain error produces normalized failed trace when suppressed."""
    runnable = MockLangChainRunnable(
        should_error=True, error_message="Chain connection lost"
    )
    adapter = LangChainAdapter(chain=runnable, suppress_exceptions=True)
    tc = TestCase(name="chain_err", input="query")

    trace = adapter.execute(test_case=tc)

    assert trace.status == ExecutionStatus.FAILED
    assert isinstance(trace.output, dict)
    assert trace.output.get("error") == "Chain connection lost"
    assert trace.output.get("framework") == "langchain"


def test_langchain_adapter_async_execution():
    """Verify LangChainAdapter async execution via aexecute()."""
    runnable = MockLangChainRunnable(
        tool_sequence=[("db_query", {"q": "SELECT 1"}, [{"1": 1}])],
        final_output="Record found",
    )
    adapter = LangChainAdapter(chain=runnable)
    tc = TestCase(name="async_lc", input="query")

    trace = asyncio.run(adapter.aexecute(test_case=tc))

    assert trace.status == ExecutionStatus.COMPLETED
    assert trace.output == "Record found"
    tool_steps = [s for s in trace.steps if s.type == StepType.TOOL]
    assert len(tool_steps) == 1
    assert tool_steps[0].name == "db_query"


# ---------------------------------------------------------------------------
# 4. Normalized Trace Equivalence Test
# ---------------------------------------------------------------------------


def test_normalized_trace_equivalence_across_frameworks():
    """Verify that equivalent executions across Callable, LangGraph, and LangChain

    produce equivalent normalized tool-call sequences and step structures.
    """
    target_tools = [
        ("get_order", {"order_id": "100"}, {"id": "100"}),
        ("cancel_order", {"order_id": "100"}, {"cancelled": True}),
        ("refund_order", {"order_id": "100"}, {"refunded": True}),
    ]
    test_case = TestCase(name="equiv_test", input={"order_id": "100"})

    # 1. Callable Adapter
    def callable_agent(inp: dict[str, Any]) -> dict[str, Any]:
        return {
            "output": "Completed flow",
            "tools": [
                {"name": name, "arguments": args, "result": res}
                for name, args, res in target_tools
            ],
        }

    call_adapter = CallableAdapter(agent=callable_agent)
    call_trace = call_adapter.execute(test_case=test_case)

    # 2. LangGraph Adapter
    lg_app = MockLangGraphApp(
        tool_sequence=target_tools,
        final_output="Completed flow",
    )
    lg_adapter = LangGraphAdapter(graph=lg_app)
    lg_trace = lg_adapter.execute(test_case=test_case)

    # 3. LangChain Adapter
    lc_runnable = MockLangChainRunnable(
        tool_sequence=target_tools,
        final_output="Completed flow",
    )
    lc_adapter = LangChainAdapter(chain=lc_runnable)
    lc_trace = lc_adapter.execute(test_case=test_case)

    # Architectural Equivalence Assertion
    for trace, label in [
        (call_trace, "Callable"),
        (lg_trace, "LangGraph"),
        (lc_trace, "LangChain"),
    ]:
        tools = [s for s in trace.steps if s.type == StepType.TOOL]
        assert len(tools) == 3, f"{label} did not extract 3 tools"
        assert [s.name for s in tools] == [
            "get_order",
            "cancel_order",
            "refund_order",
        ], f"{label} tool sequence mismatch"
        assert tools[0].input == {"order_id": "100"}
        assert tools[0].output == {"id": "100"}
        assert trace.output == "Completed flow"


# ---------------------------------------------------------------------------
# 5. Cross-Framework Failure Detection & Diagnosis
# ---------------------------------------------------------------------------


def test_cross_framework_wrong_order_detection():
    """Verify that existing evaluators detect TOOL.WRONG_ORDER identically

    regardless of whether the trace originated from Callable, LangGraph, or LangChain.
    """
    evaluators = [
        ToolOrder(
            expected_order=["get_order", "cancel_order", "refund_order"],
            exact_match=True,
        )
    ]
    test_case = TestCase(name="order_check", input={"order_id": "42"})

    # Buggy tool order: get_order -> refund_order -> cancel_order
    buggy_tools = [
        ("get_order", {"order_id": "42"}, {}),
        ("refund_order", {"order_id": "42"}, {}),
        ("cancel_order", {"order_id": "42"}, {}),
    ]

    # Test under all 3 adapters
    adapters = [
        (
            "CallableAdapter",
            CallableAdapter(
                agent=lambda inp: {
                    "tools": [{"name": n, "arguments": a} for n, a, _ in buggy_tools],
                    "output": "failed",
                }
            ),
        ),
        (
            "LangGraphAdapter",
            LangGraphAdapter(
                graph=MockLangGraphApp(tool_sequence=buggy_tools, final_output="failed")
            ),
        ),
        (
            "LangChainAdapter",
            LangChainAdapter(
                chain=MockLangChainRunnable(
                    tool_sequence=buggy_tools, final_output="failed"
                )
            ),
        ),
    ]

    analyzer = RootCauseAnalyzer()

    for name, adapter in adapters:
        runner = ReliabilityRunner(adapter=adapter, evaluators=evaluators)
        run_res = runner.run(test_case)

        assert not run_res.passed, f"{name} should have failed"
        assert len(run_res.failures) == 1

        diag = analyzer.diagnose_run_result(run_res)
        assert diag.primary_cause is not None
        assert diag.primary_cause.category == RootCauseCategory.TOOL, (
            f"{name} primary cause category mismatch"
        )
        assert diag.primary_cause.type == RootCauseType.WRONG_ORDER, (
            f"{name} primary cause type mismatch"
        )


# ---------------------------------------------------------------------------
# 6. Full Provenance & Regression Lifecycle from Framework Traces
# ---------------------------------------------------------------------------


def test_langgraph_trace_to_regression_lifecycle():
    """Verify that a failure from LangGraph cleanly flows through:

    Trace -> Failure -> RootCause -> RegressionGenerator -> RegressionTest.
    """
    buggy_tools = [
        ("get_order", {"order_id": "77"}, {}),
        ("refund_order", {"order_id": "77"}, {}),
    ]
    app = MockLangGraphApp(tool_sequence=buggy_tools, final_output="Refunded early")
    adapter = LangGraphAdapter(graph=app)

    tc = TestCase(
        id="lg_reg_tc",
        name="lg_refund_flow",
        input={"order_id": "77", "unrelated_session": "sess_x"},
        expectations=["ToolOrder:get_order,cancel_order,refund_order"],
    )
    evaluators = [
        ToolOrder(expected_order=["get_order", "cancel_order", "refund_order"])
    ]

    runner = ReliabilityRunner(adapter=adapter, evaluators=evaluators)
    run_res = runner.run(tc)

    assert not run_res.passed

    # Diagnose
    analyzer = RootCauseAnalyzer()
    diag = analyzer.diagnose_run_result(run_res)
    assert diag.primary_cause is not None

    # Synthesize Regression
    generator = RegressionGenerator()
    candidate = generator.synthesize(
        failure=run_res.failures[0],
        test_case=tc,
        trace=run_res.trace,
        root_cause=diag.primary_cause,
        root_cause_report=diag,
    )

    assert candidate.status == "success"
    assert candidate.root_cause_id == diag.primary_cause.id
    reg_test = candidate.to_regression_test()

    assert reg_test.source_failure_id == run_res.failures[0].failure_id
    assert reg_test.metadata["root_cause_id"] == diag.primary_cause.id
    assert reg_test.metadata["source_trace_id"] == run_res.trace.trace_id
