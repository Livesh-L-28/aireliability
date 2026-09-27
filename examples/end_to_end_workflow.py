"""Practical end-to-end examples for AI Reliability Engine (`aireliability`).

Demonstrates:
1. Defining TestCases with deterministic expectations.
2. Executing an agent with ReliabilityRunner to capture ExecutionTrace.
3. Automatically categorizing failures into structured FailureReports.
4. Synthesizing reproducible RegressionTest cases preserving provenance.
5. Managing baselines and detecting behavioral regressions.
"""

from aireliability.core.models import (
    StepType,
    TestCase,
    TraceStep,
)
from aireliability.evaluation import (
    MaxLatency,
    OutputContains,
    ToolCalled,
    ToolOrder,
)
from aireliability.execution import ReliabilityRunner
from aireliability.regression import BaselineManager, RegressionGenerator


# ==============================================================================
# 1. Define Agents (Simulated Function Callables)
# ==============================================================================
def nominal_order_agent(user_prompt: str) -> dict[str, str]:
    """Agent version 1 (Working as expected)."""
    return {
        "reply": f"Order refund processed: {user_prompt}",
        "order_id": "ORD-123",
        "status": "refunded",
    }


def regressed_order_agent(user_prompt: str) -> dict[str, str]:
    """Agent version 2 (Regressed: missing required refund phrasing)."""
    return {
        "reply": f"Order query acknowledged: {user_prompt}",
        "order_id": "ORD-123",
        "status": "pending",
    }


def main() -> None:
    print("=" * 70)
    print("AI Reliability Engine: End-to-End Reliability & Regression Workflow")
    print("=" * 70)

    # --------------------------------------------------------------------------
    # Step 1: Create Test Cases with Expectations
    # --------------------------------------------------------------------------
    test_refund = TestCase(
        id="tc_refund_flow",
        name="test_refund_flow",
        input="Please refund order ORD-123",
        expected_output="Order refund processed",
        expectations=[
            "OutputContains: refund processed",
            "ToolCalled: verify_order",
            "ToolOrder: [verify_order, execute_refund]",
            "MaxLatency: 2000",
        ],
        tags=["billing", "refunds"],
    )

    # Configure evaluators matching the expectations
    evaluators = [
        OutputContains("refund processed"),
        ToolCalled("verify_order"),
        ToolOrder(["verify_order", "execute_refund"]),
        MaxLatency(2000.0),
    ]

    # Explicit tool trace steps emitted by the agent or framework adapter
    nominal_tool_steps = [
        TraceStep(
            step_type=StepType.TOOL,
            name="verify_order",
            input={"order_id": "ORD-123"},
            output={"valid": True},
        ),
        TraceStep(
            step_type=StepType.TOOL,
            name="execute_refund",
            input={"order_id": "ORD-123", "amount": 49.99},
            output={"success": True},
        ),
    ]

    # --------------------------------------------------------------------------
    # Step 2: Execute Nominal Agent & Establish Baseline
    # --------------------------------------------------------------------------
    print("\n--- 1. Executing Nominal Agent (V1) ---")
    runner_v1 = ReliabilityRunner(
        agent=nominal_order_agent,
        evaluators=evaluators,
    )
    result_v1 = runner_v1.run(test_refund, steps=nominal_tool_steps)

    passed_evals = sum(1 for e in result_v1.evaluations if e.passed)
    total_evals = len(result_v1.evaluations)
    print(f"Evaluations passed: {passed_evals}/{total_evals}")

    # Store baseline
    baseline_mgr = BaselineManager()
    baseline_mgr.create_baseline([result_v1], name="production_baseline")
    print("✓ Saved V1 run result as 'production_baseline'")

    # --------------------------------------------------------------------------
    # Step 3: Execute Regressed Agent (V2) & Detect Failures
    # --------------------------------------------------------------------------
    print("\n--- 2. Executing Regressed Agent (V2) ---")
    # In V2, the developer forgot to invoke execute_refund and changed the output
    regressed_tool_steps = [
        TraceStep(
            step_type=StepType.TOOL,
            name="verify_order",
            input={"order_id": "ORD-123"},
            output={"valid": True},
        ),
    ]

    runner_v2 = ReliabilityRunner(
        agent=regressed_order_agent,
        evaluators=evaluators,
    )
    result_v2 = runner_v2.run(test_refund, steps=regressed_tool_steps)

    print(f"Test Status: {'PASSED ✓' if result_v2.passed else 'FAILED ✗'}")
    print(f"Failures detected: {len(result_v2.failures)}")

    for failure in result_v2.failures:
        print(f"  • Category: {failure.category} | Type: {failure.type}")
        print(f"    Severity: {failure.severity} | Confidence: {failure.confidence}")
        print(f"    Message:  {failure.message}")

    # --------------------------------------------------------------------------
    # Step 4: Compare Against Baseline to Detect Regression
    # --------------------------------------------------------------------------
    print("\n--- 3. Baseline Comparison ---")
    summary = baseline_mgr.compare([result_v2], baseline_name="production_baseline")
    print(f"Regressions detected: {len(summary.regressions)}")
    for reg in summary.regressions:
        print(f"  ! REGRESSION in '{reg.test_name}': was PASSING, now FAILING.")

    # --------------------------------------------------------------------------
    # Step 5: Synthesize Reproducible Regression Test Case
    # --------------------------------------------------------------------------
    print("\n--- 4. Synthesizing Regression Test ---")
    generator = RegressionGenerator()
    primary_failure = result_v2.failures[0]
    regression_test = generator.generate(
        failure=primary_failure,
        test_case=test_refund,
    )

    print(f"Synthesized Regression Test ID: {regression_test.id}")
    print(f"Name:                           {regression_test.name}")
    print(f"Source Failure ID:              {regression_test.source_failure_id}")
    print(f"Tags:                           {regression_test.test_case.tags}")
    prov_meta = regression_test.test_case.metadata["source_failure_id"]
    print(f"Provenance Meta:                {prov_meta}")
    print("=" * 70)


if __name__ == "__main__":
    main()
