"""Unit tests for Phase 16 Semantic Evaluation Engine.

Covers:
1. MockSemanticJudge:
   - pass/fail conditions
   - score, confidence, and reasoning
   - criteria validation
   - custom hook execution
2. SemanticExpectation / SemanticRelevance / SemanticSimilarity:
   - threshold triggering (pass >= threshold, fail < threshold)
   - threshold validation (0.0 to 1.0)
   - criteria-based evaluation
   - reference answer resolution
   - grounding context
   - evidence and audit metadata preservation
3. Composition (Deterministic + Semantic):
   - deterministic PASS + semantic PASS -> overall PASS
   - deterministic PASS + semantic FAIL -> overall FAIL
   - deterministic FAIL + semantic PASS -> overall FAIL
   - preserving individual evaluation results without masking
4. Failure & Regression Integration:
   - semantic failures producing structured FailureReport
   - FailureCategory.OUTPUT and FailureType.SEMANTIC_VIOLATION / SEMANTIC_RELEVANCE
   - regression test generation from semantic failures
   - baseline comparison with semantic regressions
"""

import pytest

from aireliability import (
    BaselineManager,
    ComparisonStatus,
    ExecutionStatus,
    ExecutionTrace,
    FailureCategory,
    FailureType,
    JudgeResult,
    MockSemanticJudge,
    OutputEquals,
    RegressionGenerator,
    ReliabilityRunner,
    SemanticExpectation,
    SemanticRelevance,
    SemanticSimilarity,
    TestCase,
)
from aireliability.failures.analyzer import FailureAnalyzer

# ---------------------------------------------------------------------------
# 1. MockSemanticJudge Tests
# ---------------------------------------------------------------------------


def test_mock_semantic_judge_defaults():
    """Verify MockSemanticJudge returns expected default structured result."""
    judge = MockSemanticJudge(
        default_score=0.88,
        threshold=0.75,
        confidence=0.90,
    )
    res = judge.judge(prompt="Hello", output="Hello there")

    assert isinstance(res, JudgeResult)
    assert res.score == 0.88
    assert res.passed is True
    assert res.confidence == 0.90
    assert "Mock evaluation completed" in res.reasoning
    assert res.evidence["evaluated_prompt"] == "Hello"
    assert res.evidence["evaluated_output"] == "Hello there"
    assert res.provider == "mock"
    assert res.model == "mock-judge-v1"


def test_mock_semantic_judge_failing_condition():
    """Verify MockSemanticJudge correctly flags failing scores below threshold."""
    judge = MockSemanticJudge(
        default_score=0.45,
        threshold=0.70,
    )
    res = judge.judge(prompt="Query", output="Incomplete output")

    assert res.score == 0.45
    assert res.passed is False


def test_mock_semantic_judge_criteria_assessment():
    """Verify criteria evaluation flags missing requirements in output."""
    judge = MockSemanticJudge(
        default_score=1.0,
        threshold=0.80,
    )
    criteria = ["state refund timeframe", "reference order 123"]
    # Output missing timeframe
    output = "Your order 123 is cancelled."

    res = judge.judge(
        prompt="Refund order",
        output=output,
        criteria=criteria,
    )

    assert "state refund timeframe" in res.criteria_results
    assert res.criteria_results["state refund timeframe"] is False
    assert res.criteria_results["reference order 123"] is True
    # Penalized score due to failed criteria
    assert res.score < 0.80
    assert res.passed is False


def test_mock_semantic_judge_custom_rule():
    """Verify custom rule hook allows deterministic control for specific tests."""

    def rule(p: str, o: str, r: str | None, c: list[str] | None) -> tuple[float, str]:
        if "hallucination" in o:
            return 0.1, "Detected factual contradiction with reference."
        return 0.95, "Semantically accurate."

    judge = MockSemanticJudge(custom_rule=rule, threshold=0.7)

    res_good = judge.judge("prompt", "All facts correct")
    assert res_good.score == 0.95
    assert res_good.passed is True

    res_bad = judge.judge("prompt", "Contains hallucination here")
    assert res_bad.score == 0.10
    assert res_bad.passed is False
    assert "contradiction" in res_bad.reasoning


# ---------------------------------------------------------------------------
# 2. SemanticExpectation / Relevance / Similarity Tests
# ---------------------------------------------------------------------------


def test_semantic_expectation_invalid_threshold():
    """Verify ValueError when threshold is out of range [0.0, 1.0]."""
    with pytest.raises(ValueError, match="threshold must be between 0.0 and 1.0"):
        SemanticExpectation(threshold=1.5)

    with pytest.raises(ValueError, match="threshold must be between 0.0 and 1.0"):
        SemanticExpectation(threshold=-0.1)


def test_semantic_expectation_pass_and_fail():
    """Verify SemanticExpectation evaluate() returns passing or failing result."""
    judge_pass = MockSemanticJudge(default_score=0.85, threshold=0.70, confidence=0.85)
    exp_pass = SemanticExpectation(threshold=0.70, judge=judge_pass)

    trace = ExecutionTrace(input="Hello", output="Hi there")
    eval_res_pass = exp_pass.evaluate(trace)

    assert eval_res_pass.passed is True
    assert eval_res_pass.score == 0.85
    assert eval_res_pass.metadata["confidence"] == 0.85
    assert eval_res_pass.evidence["score"] == 0.85

    # Failing threshold
    judge_fail = MockSemanticJudge(default_score=0.60, threshold=0.75, confidence=0.60)
    exp_fail = SemanticExpectation(threshold=0.75, judge=judge_fail)

    eval_res_fail = exp_fail.evaluate(trace)
    assert eval_res_fail.passed is False
    assert eval_res_fail.score == 0.60
    assert "Semantic evaluation failed" in eval_res_fail.message


def test_semantic_relevance_and_similarity():
    """Verify SemanticRelevance and SemanticSimilarity specializations."""
    judge = MockSemanticJudge(default_score=0.92, threshold=0.80)

    rel_exp = SemanticRelevance(threshold=0.80, judge=judge)
    sim_exp = SemanticSimilarity(reference="Expected text", threshold=0.80, judge=judge)

    trace = ExecutionTrace(input="Query", output="Expected text is here")
    res_rel = rel_exp.evaluate(trace)
    res_sim = sim_exp.evaluate(trace)

    assert res_rel.passed is True
    assert res_sim.passed is True
    assert res_rel.metadata["failure_type"] == "semantic_relevance"
    assert res_sim.metadata["failure_type"] == "semantic_similarity"


def test_grounding_context_and_reference_resolution():
    """Verify test_case expected_output is resolved when reference is omitted."""

    def hook(p: str, o: str, r: str | None, c: list[str] | None) -> tuple[float, str]:
        assert r == "Expected answer from TestCase"
        return 0.9, "Matched test case reference"

    judge = MockSemanticJudge(custom_rule=hook, threshold=0.7)
    exp = SemanticExpectation(
        context={"retrieved_docs": ["doc1", "doc2"]},
        judge=judge,
    )

    tc = TestCase(
        name="grounding_test",
        input="What is X?",
        expected_output="Expected answer from TestCase",
    )
    trace = ExecutionTrace(input="What is X?", output="X is a variable")

    eval_res = exp.evaluate(trace, test_case=tc)
    assert eval_res.passed is True
    assert eval_res.evidence["reference"] == "Expected answer from TestCase"
    assert eval_res.evidence["context"]["retrieved_docs"] == ["doc1", "doc2"]


# ---------------------------------------------------------------------------
# 3. Composition (Deterministic + Semantic) Tests
# ---------------------------------------------------------------------------


def test_composition_deterministic_pass_semantic_pass():
    """Deterministic PASS + Semantic PASS = Overall PASS."""
    tc = TestCase(
        name="pass_pass", input="Test input", expected_output="Expected output"
    )

    def agent(x):
        return "Expected output"

    evaluators = [
        OutputEquals("Expected output"),
        SemanticRelevance(threshold=0.70, judge=MockSemanticJudge(default_score=0.90)),
    ]

    runner = ReliabilityRunner(agent=agent, evaluators=evaluators)
    result = runner.run(tc)

    assert result.passed is True
    assert len(result.evaluations) == 2
    assert all(e.passed for e in result.evaluations)
    assert len(result.failures) == 0


def test_composition_deterministic_pass_semantic_fail():
    """Deterministic PASS + Semantic FAIL = Overall FAIL (preserves both results)."""
    tc = TestCase(
        name="pass_fail", input="Refund request", expected_output="Refund approved"
    )

    def agent(x):
        # Passes exact text match, but fails semantic criteria judge
        return "Refund approved"

    evaluators = [
        OutputEquals("Refund approved"),
        SemanticExpectation(
            threshold=0.85,
            judge=MockSemanticJudge(
                default_score=0.40,
                threshold=0.85,
                default_reasoning="Omitted policy explanation",
            ),
        ),
    ]

    runner = ReliabilityRunner(agent=agent, evaluators=evaluators)
    result = runner.run(tc)

    assert result.passed is False
    assert len(result.evaluations) == 2
    # First passed, second failed
    assert result.evaluations[0].passed is True
    assert result.evaluations[1].passed is False

    assert len(result.failures) == 1
    failure = result.failures[0]
    assert failure.category == FailureCategory.OUTPUT.value
    assert failure.type == FailureType.SEMANTIC_VIOLATION.value
    assert failure.evidence["score"] == 0.40


def test_composition_deterministic_fail_semantic_pass():
    """Deterministic FAIL + Semantic PASS = Overall FAIL."""
    tc = TestCase(name="fail_pass", input="Input", expected_output="Exact A")

    def agent(x):
        return "Different B"

    evaluators = [
        OutputEquals("Exact A"),
        SemanticRelevance(threshold=0.70, judge=MockSemanticJudge(default_score=0.95)),
    ]

    runner = ReliabilityRunner(agent=agent, evaluators=evaluators)
    result = runner.run(tc)

    assert result.passed is False
    assert len(result.evaluations) == 2
    assert result.evaluations[0].passed is False
    assert result.evaluations[1].passed is True
    assert len(result.failures) == 1
    assert result.failures[0].category == FailureCategory.TASK.value


# ---------------------------------------------------------------------------
# 4. Failure and Regression Integration Tests
# ---------------------------------------------------------------------------


def test_semantic_failure_analyzer_and_regression_generation():
    """Verify semantic failure converts to FailureReport and RegressionTest."""
    tc = TestCase(
        id="sem_tc_01",
        name="semantic_test",
        input="How do I return item?",
        expected_output="Drop it off at UPS store.",
    )

    failing_judge = MockSemanticJudge(
        default_score=0.35,
        threshold=0.75,
        confidence=0.88,
        default_reasoning="Incorrect return instructions provided.",
    )
    sem_eval = SemanticRelevance(threshold=0.75, judge=failing_judge)

    trace = ExecutionTrace(
        test_id=tc.id,
        input=tc.input,
        output="Throw it away.",
        status=ExecutionStatus.COMPLETED,
    )

    eval_result = sem_eval.evaluate(trace, test_case=tc)
    assert not eval_result.passed

    # Failure analyzer builds structured FailureReport
    analyzer = FailureAnalyzer()
    failures = analyzer.analyze_trace_failures(trace, [eval_result], test_id=tc.id)

    assert len(failures) == 1
    failure = failures[0]
    assert failure.category == FailureCategory.OUTPUT.value
    assert failure.type == FailureType.SEMANTIC_RELEVANCE.value
    assert failure.confidence == 0.88
    assert "Incorrect return instructions" in failure.message

    # RegressionGenerator builds traceable RegressionTest
    generator = RegressionGenerator()
    reg_test = generator.generate(failure=failure, test_case=tc)

    assert reg_test.source_failure_id == failure.failure_id
    assert "type:semantic_relevance" in reg_test.test_case.tags
    assert reg_test.test_case.metadata["source_failure_id"] == failure.failure_id

    # BaselineManager tracks semantic regression
    baseline_mgr = BaselineManager()
    # Baseline was passing
    baseline_mgr.create_baseline(
        [
            type(
                "MockRunResult",
                (),
                {
                    "test": tc,
                    "passed": True,
                    "failures": [],
                },
            )()
        ],
        name="default",
    )

    current_run = type(
        "MockRunResult",
        (),
        {
            "test": tc,
            "passed": False,
            "failures": failures,
        },
    )()

    comp = baseline_mgr.compare_single(current_run, baseline_name="default")
    assert comp.status == ComparisonStatus.REGRESSION
