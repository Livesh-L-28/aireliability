"""Deterministic example demonstrating reliability testing on a LangGraph agent.

Workflow:
1. Define a LangGraph StateGraph (or mock graph) performing customer support tasks.
2. Observe execution through LangGraphAdapter without external APIs or credentials.
3. Evaluate tool ordering and assertions deterministically.
4. Diagnose empirical root cause upon failure.
5. Synthesize minimal regression test.
"""

import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from aireliability import (
    RegressionGenerator,
    ReliabilityRunner,
    RootCauseAnalyzer,
    TestCase,
    ToolOrder,
)
from aireliability.integrations.langgraph.adapter import LangGraphAdapter
from tests.mocks.framework_mocks import MockLangGraphApp


def main() -> None:
    print("AI Reliability Engine — LangGraph Integration Example")
    print("=" * 60)

    # 1. Define customer support test case
    test_case = TestCase(
        id="tc_lg_refund_01",
        name="customer_refund_flow",
        input={"query": "refund order 501", "order_id": "501"},
        expected_output="Refund completed successfully",
    )

    # 2. Simulate a LangGraph agent with a tool sequence bug:
    # Expected: get_order -> cancel_order -> refund_order
    # Actual:   get_order -> refund_order -> cancel_order (WRONG_ORDER)
    buggy_graph = MockLangGraphApp(
        tool_sequence=[
            ("get_order", {"order_id": "501"}, {"status": "active"}),
            ("refund_order", {"order_id": "501"}, {"status": "failed_order_active"}),
            ("cancel_order", {"order_id": "501"}, {"status": "cancelled"}),
        ],
        final_output="Refund failed: order was active at refund time",
    )

    # 3. Instantiate LangGraphAdapter
    adapter = LangGraphAdapter(graph=buggy_graph)

    # 4. Configure Evaluators
    evaluators = [
        ToolOrder(
            expected_order=["get_order", "cancel_order", "refund_order"],
            exact_match=True,
        )
    ]

    # 5. Run test
    runner = ReliabilityRunner(adapter=adapter, evaluators=evaluators)
    run_result = runner.run(test_case)

    print(f"Test Status:  {'PASS' if run_result.passed else 'FAIL'}")
    print(f"Observed Steps: {[s.name for s in run_result.trace.steps]}")
    print(f"Failures:     {len(run_result.failures)}")

    # 6. Diagnose Root Cause
    analyzer = RootCauseAnalyzer()
    diag = analyzer.diagnose_run_result(run_result)
    print("\nRoot Cause Report:")
    print(diag.format_terminal())

    # 7. Synthesize Regression Test
    generator = RegressionGenerator()
    candidate = generator.synthesize(
        failure=run_result.failures[0],
        test_case=test_case,
        trace=run_result.trace,
        root_cause=diag.primary_cause,
        root_cause_report=diag,
    )
    reg_test = candidate.to_regression_test()

    print("\nSynthesized Regression Test:")
    print(f"ID:             {reg_test.id}")
    print(f"Source Failure: {reg_test.source_failure_id}")
    print(f"Root Cause ID:  {reg_test.metadata.get('root_cause_id')}")
    print(f"Minimization:   minimized={candidate.minimized}")


if __name__ == "__main__":
    main()
