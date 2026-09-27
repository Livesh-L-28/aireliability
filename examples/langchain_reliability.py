"""Deterministic example demonstrating reliability testing on a LangChain chain.

Workflow:
1. Define a LangChain Runnable with tools and callbacks.
2. Observe execution through LangChainAdapter without external APIs or credentials.
3. Evaluate tool arguments and sequence.
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
    ToolArguments,
)
from aireliability.integrations.langchain.adapter import LangChainAdapter
from tests.mocks.framework_mocks import MockLangChainRunnable


def main() -> None:
    print("AI Reliability Engine — LangChain Integration Example")
    print("=" * 60)

    # 1. Define support test case
    test_case = TestCase(
        id="tc_lc_lookup_01",
        name="account_lookup_flow",
        input={"user_id": "usr_999", "action": "verify_status"},
        expected_output="Account verified",
    )

    # 2. Simulate a LangChain runnable with an argument error:
    # Expected: query_user(user_id='usr_999')
    # Actual:   query_user(user_id='usr_000') (WRONG_ARGUMENT)
    buggy_chain = MockLangChainRunnable(
        tool_sequence=[
            (
                "query_user",
                {"user_id": "usr_000"},
                {"error": "user not found"},
            ),
        ],
        final_output="Verification failed: user not found",
    )

    # 3. Instantiate LangChainAdapter
    adapter = LangChainAdapter(chain=buggy_chain)

    # 4. Configure Evaluators
    evaluators = [
        ToolArguments("query_user", {"user_id": "usr_999"}),
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
