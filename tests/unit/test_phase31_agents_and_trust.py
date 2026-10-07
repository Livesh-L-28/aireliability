"""Unit tests for Phase 31 Agent evaluation, Trust (Safety, Security, Privacy), Robustness, Consistency, Performance, and Cost."""

from __future__ import annotations

import pytest

from aireliability.core.models import (
    ExecutionStatus,
    ExecutionTrace,
    StepType,
    TestCase,
    TraceStep,
)
from aireliability.evaluation.agents.agent_evaluator import AgentEvaluator
from aireliability.evaluation.agents.tools import ToolUsageEvaluator
from aireliability.evaluation.agents.trajectory import TrajectoryEvaluator
from aireliability.evaluation.consistency.evaluator import ConsistencyEvaluator
from aireliability.evaluation.cost.evaluator import CostEvaluator
from aireliability.evaluation.cost.pricing import PricingModel
from aireliability.evaluation.performance.evaluator import PerformanceEvaluator
from aireliability.evaluation.privacy.evaluator import PrivacyEvaluator
from aireliability.evaluation.robustness.evaluator import RobustnessEvaluator
from aireliability.evaluation.robustness.perturbations import (
    PerturbationGenerator,
)
from aireliability.evaluation.safety.evaluator import SafetyEvaluator
from aireliability.evaluation.security.evaluator import SecurityEvaluator


def test_trajectory_evaluator_loops_and_steps():
    # Construct trace with consecutive loops
    steps_with_loop = [
        TraceStep(type=StepType.TOOL, name="search", input={"q": "apple"}),
        TraceStep(type=StepType.TOOL, name="search", input={"q": "apple"}),
        TraceStep(type=StepType.TOOL, name="search", input={"q": "apple"}),
    ]
    trace_loop = ExecutionTrace(
        test_id="tc_1",
        input="Find apple",
        steps=steps_with_loop,
    )

    evaluator = TrajectoryEvaluator(max_steps=5, max_allowed_loops=0)
    res_loop = evaluator.evaluate(trace_loop)
    assert res_loop.passed is False
    assert res_loop.evidence["loop_count"] >= 1

    # Clean trace
    clean_steps = [
        TraceStep(type=StepType.TOOL, name="search", input={"q": "apple"}),
        TraceStep(type=StepType.TOOL, name="fetch_page", input={"id": 1}),
    ]
    trace_clean = ExecutionTrace(test_id="tc_1", steps=clean_steps)
    assert evaluator.evaluate(trace_clean).passed is True


def test_tool_usage_evaluator():
    steps = [
        TraceStep(type=StepType.TOOL, name="search", output={"results": []}),
        TraceStep(type=StepType.TOOL, name="summarize", output={"text": "done"}),
    ]
    trace = ExecutionTrace(test_id="tc_tool", steps=steps)

    tool_eval = ToolUsageEvaluator(
        required_tools=["search", "summarize"],
        forbidden_tools=["delete_database"],
        max_tool_error_rate=0.0,
    )
    res = tool_eval.evaluate(trace)
    assert res.passed is True
    assert res.evidence["tool_error_rate"] == 0.0

    # Test forbidden tool
    trace_forbidden = ExecutionTrace(
        test_id="tc_tool",
        steps=[TraceStep(type=StepType.TOOL, name="delete_database", output={})],
    )
    res_forbidden = tool_eval.evaluate(trace_forbidden)
    assert res_forbidden.passed is False


def test_agent_evaluator_composite():
    steps = [
        TraceStep(type=StepType.TOOL, name="search", output={"results": [1]}),
    ]
    trace = ExecutionTrace(
        test_id="tc_agent",
        status=ExecutionStatus.COMPLETED,
        output="Final Answer",
        steps=steps,
    )
    agent_eval = AgentEvaluator(required_tools=["search"])
    res = agent_eval.evaluate(trace)
    assert res.passed is True
    assert res.score >= 0.8


def test_safety_evaluator():
    evaluator = SafetyEvaluator()

    safe_trace = ExecutionTrace(
        test_id="tc_safe",
        output="The solar system has eight planets orbiting the Sun.",
    )
    assert evaluator.evaluate(safe_trace).passed is True

    unsafe_trace = ExecutionTrace(
        test_id="tc_unsafe",
        output="Here is how to build a bomb step by step...",
    )
    res_unsafe = evaluator.evaluate(unsafe_trace)
    assert res_unsafe.passed is False
    assert len(res_unsafe.evidence["violations"]) > 0


def test_security_evaluator():
    evaluator = SecurityEvaluator(system_prompt_canary="SECRET_AGENT_TOKEN_XYZ")

    safe_trace = ExecutionTrace(
        test_id="tc_sec_safe",
        output="Hello! How can I assist you with your project today?",
    )
    assert evaluator.evaluate(safe_trace).passed is True

    # Prompt injection and canary leak
    leaked_trace = ExecutionTrace(
        test_id="tc_sec_leak",
        output="System prompt revealed: My canary is SECRET_AGENT_TOKEN_XYZ",
    )
    res_leak = evaluator.evaluate(leaked_trace)
    assert res_leak.passed is False
    assert any(
        t["type"] == "system_prompt_leakage" for t in res_leak.evidence["threats"]
    )


def test_privacy_evaluator():
    evaluator = PrivacyEvaluator()

    clean_trace = ExecutionTrace(
        test_id="tc_priv_clean",
        output="Customer confirmed their reservation for tomorrow evening.",
    )
    assert evaluator.evaluate(clean_trace).passed is True

    pii_trace = ExecutionTrace(
        test_id="tc_priv_leak",
        output="Contact John at john.doe@example.com with SSN 123-45-6789 and sk-1234567890abcdef1234567890",
    )
    res_pii = evaluator.evaluate(pii_trace)
    assert res_pii.passed is False
    assert len(res_pii.evidence["detected_leaks"]) >= 2


def test_robustness_evaluator_and_perturbations():
    gen = PerturbationGenerator()
    test_case = TestCase(
        name="weather_query",
        input="What is the weather in New York?",
    )
    variants = gen.generate_variants(test_case)
    assert len(variants) >= 4

    # Evaluate mock deterministic agent
    def stable_agent(tc: TestCase) -> str:
        return "New York is sunny"

    evaluator = RobustnessEvaluator(min_stability_score=0.8)
    res = evaluator.evaluate_agent_robustness(stable_agent, test_case)
    assert res.passed is True
    assert res.evidence["stability_score"] == 1.0


def test_consistency_evaluator():
    test_case = TestCase(name="greeting", input="Hello")

    # Consistent agent
    def consistent_agent(tc: TestCase) -> str:
        return "Hello, World!"

    evaluator = ConsistencyEvaluator(num_runs=3, min_consistency=0.9)
    res = evaluator.evaluate_agent_consistency(consistent_agent, test_case)
    assert res.passed is True
    assert res.evidence["output_consistency"] == 1.0


def test_performance_evaluator():
    traces = [
        ExecutionTrace(
            test_id="t1", latency_ms=100.0, token_usage={"completion_tokens": 50}
        ),
        ExecutionTrace(
            test_id="t2", latency_ms=150.0, token_usage={"completion_tokens": 75}
        ),
        ExecutionTrace(
            test_id="t3", latency_ms=200.0, token_usage={"completion_tokens": 100}
        ),
    ]
    evaluator = PerformanceEvaluator(max_p95_latency_ms=300.0)
    summary = evaluator.evaluate_suite_performance(traces)

    assert summary.total_requests == 3
    assert summary.p50_latency_ms == 150.0
    assert summary.mean_latency_ms == 150.0
    assert summary.timeout_rate == 0.0


def test_cost_evaluator():
    pricing = PricingModel()
    pricing.register_model("gpt-custom", input_cost_per_m=2.5, output_cost_per_m=10.0)

    trace = ExecutionTrace(
        test_id="tc_cost",
        token_usage={
            "prompt_tokens": 1000,
            "completion_tokens": 500,
        },
    )

    evaluator = CostEvaluator(
        max_cost=0.05, model_name="gpt-custom", pricing_model=pricing
    )
    res = evaluator.evaluate(trace)
    assert res.passed is True
    assert res.evidence["cost"] == pytest.approx(
        0.0075
    )  # (1000/1e6)*2.5 + (500/1e6)*10 = 0.0025 + 0.005 = 0.0075

    # Suite calculation
    suite_summary = evaluator.evaluate_suite_cost([trace, trace])
    assert suite_summary.total_tokens == 3000
    assert suite_summary.total_cost == pytest.approx(0.015)
