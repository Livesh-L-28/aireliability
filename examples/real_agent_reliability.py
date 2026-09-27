"""End-to-end real agent integration and regression demonstration.

Demonstrates:
1. Connecting a real Python agent via CallableAdapter.
2. Executing with ReliabilityRunner and evaluating with ToolOrder.
3. Catching the faulty agent execution (TOOL.WRONG_ORDER).
4. Generating a RegressionTest.
5. Verifying the fixed agent passes.
6. Re-introducing the bug and verifying the regression is re-detected.
"""

import sys
from pathlib import Path

# Add project root to sys.path so examples runs directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aireliability import (
    BaselineManager,
    CallableAdapter,
    ComparisonStatus,
    RegressionGenerator,
    ReliabilityRunner,
    TestCase,
    ToolOrder,
)
from examples.local_agent import LocalSupportAgent


def main() -> None:
    print("=" * 60)
    print("AI Reliability Engine — Real Agent Integration Workflow")
    print("=" * 60)

    # 1. Define the test case and expectations
    test = TestCase(
        id="refund_flow_test",
        name="refund_flow",
        input="I want a refund for order 123.",
        expected_output=(
            "Your refund and cancellation for order 123 has been processed."
        ),
        metadata={"domain": "customer_support", "priority": "high"},
    )

    # Expected tool order: get_order -> cancel_order -> refund_order
    evaluators = [
        ToolOrder(
            expected_order=["get_order", "cancel_order", "refund_order"],
            exact_match=True,
        )
    ]

    # 2. Step 1: Run Faulty Agent
    faulty_agent = LocalSupportAgent(mode="faulty")
    adapter = CallableAdapter(agent=faulty_agent)
    runner = ReliabilityRunner(
        agent=faulty_agent,
        adapter=adapter,
        evaluators=evaluators,
    )

    result_faulty = runner.run(test)

    print("\nAI Reliability Engine")
    print("──────────────────────")
    print(f"Test: {result_faulty.test.name}")
    print(f"Status: {'PASS' if result_faulty.passed else 'FAIL'}")

    if result_faulty.failures:
        failure = result_faulty.failures[0]
        print("\nFailure:")
        print(f"  Category: {failure.category}")
        print(f"  Type: {failure.type}")
        print(f"  Confidence: {failure.confidence}")

        actual_tools = [s.name for s in result_faulty.trace.steps if s.type == "tool"]
        print("\nExpected:")
        print("  get_order → cancel_order → refund_order")
        print("\nActual:")
        print(f"  {' → '.join(actual_tools)}")

    # 3. Step 2: Generate Regression Test
    print("\n" + "-" * 60)
    print("Generating Regression Test from Failure...")
    generator = RegressionGenerator()
    reg_test = generator.generate(
        failure=result_faulty.failures[0],
        test_case=test,
    )
    print(f"Generated RegressionTest ID: {reg_test.id}")
    print(f"Source Failure ID: {reg_test.source_failure_id}")

    # Baseline tracking setup: record the initial failure
    baseline_mgr = BaselineManager()
    baseline_mgr.create_baseline([result_faulty], name="default")

    # 4. Step 3: Run Fixed Agent
    print("\n" + "-" * 60)
    print("Executing Fixed Agent against Regression Test...")
    fixed_agent = LocalSupportAgent(mode="nominal")
    fixed_adapter = CallableAdapter(agent=fixed_agent)
    fixed_runner = ReliabilityRunner(
        agent=fixed_agent,
        adapter=fixed_adapter,
        evaluators=evaluators,
    )

    result_fixed = fixed_runner.run(test)
    print(f"Fixed Agent Status: {'PASS' if result_fixed.passed else 'FAIL'}")
    assert result_fixed.passed, "Fixed agent was expected to pass!"

    comparison_fixed = baseline_mgr.compare_single(
        result_fixed, baseline_name="default"
    )
    print(f"Baseline Comparison: {comparison_fixed.status.value}")
    assert comparison_fixed.status == ComparisonStatus.FIXED

    # Update baseline with the passing run
    baseline_mgr.create_baseline([result_fixed], name="default")

    # 5. Step 4: Reintroduce Bug and Verify Regression Detected
    print("\n" + "-" * 60)
    print("Re-introducing Faulty Agent...")
    result_reintroduced = runner.run(test)
    print(
        f"Reintroduced Bug Status: {'PASS' if result_reintroduced.passed else 'FAIL'}"
    )
    assert not result_reintroduced.passed, "Reintroduced bug was expected to fail!"

    comparison_reintroduced = baseline_mgr.compare_single(
        result_reintroduced, baseline_name="default"
    )
    print(f"Baseline Comparison: {comparison_reintroduced.status.value}")
    assert comparison_reintroduced.status == ComparisonStatus.REGRESSION

    print("\n" + "=" * 60)
    print("✓ Full Lifecycle Verified: FAIL → REGRESSION TEST → FIXED → REGRESSION")
    print("=" * 60)


if __name__ == "__main__":
    main()
