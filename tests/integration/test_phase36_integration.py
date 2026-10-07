"""End-to-end integration test for Phase 36 Automated AI Test Generation.

Validates complete reliability loop:
Evaluation Failure -> Intelligence Analysis -> Knowledge Graph ->
Automated Test Generation -> Validation -> Deduplication -> Quality Scoring ->
Golden Dataset Promotion -> Graph Provenance Sync.
"""

from __future__ import annotations

from aireliability.core.models import (
    EvaluationResult,
    ExecutionTrace,
    FailureReport,
    StepType,
    TestCase,
    TraceStep,
)
from aireliability.evaluation.datasets.models import EvaluationDataset
from aireliability.evaluation.models import EvaluationReport
from aireliability.generation.engine import TestGenerationEngine
from aireliability.generation.integrations import GraphIntegrationBridge
from aireliability.generation.models import (
    TestGenerationConfig,
    TestGenerationRequest,
    TestGenerationStatus,
)
from aireliability.generation.promotion import TestPromotionManager
from aireliability.graph.builder import KnowledgeGraphBuilder
from aireliability.graph.models import GraphNodeType
from aireliability.intelligence.engine import ReliabilityIntelligenceEngine


def test_phase36_complete_reliability_closed_loop() -> None:
    """Validate full end-to-end test generation and dataset promotion pipeline."""
    # 1. Setup Evidence: ExecutionTrace and FailureReport
    trace = ExecutionTrace(
        trace_id="tr_int_001",
        input="Find the latest earnings report for ACME Corp.",
        output="ACME Corp earned $50 billion in Q1 (hallucinated).",
        steps=[
            TraceStep(
                name="search_docs", type=StepType.TOOL, input={"q": "ACME earnings"}
            ),
            TraceStep(name="llm_generate", type=StepType.LLM),
        ],
    )
    fail = FailureReport(
        failure_id="fail_int_001",
        trace_id="tr_int_001",
        category="output_hallucination",
        type="financial_figure_inaccuracy",
        message="Model hallucinated 50 billion instead of 5 million",
        confidence=0.98,
        evidence={"input": "Find the latest earnings report for ACME Corp."},
    )
    eval_result = EvaluationResult(
        evaluator="hallucination_evaluator",
        passed=False,
        score=0.20,
        message="Unsubstantiated earnings claim",
    )
    report = EvaluationReport(
        report_id="rep_int_001",
        target_name="AcmeAgent_v1",
        dataset_id="financial_qa",
        total_test_cases=1,
        passed_test_cases=0,
        failed_test_cases=1,
        evaluations=[eval_result],
        failures=[fail],
    )

    # 2. Phase 34 Intelligence Analysis
    intel_engine = ReliabilityIntelligenceEngine()
    analysis = intel_engine.analyze(report)
    assert analysis.summary.total_failures_analyzed >= 1

    # 3. Phase 35 Knowledge Graph Construction
    graph_builder = KnowledgeGraphBuilder()
    graph_builder.from_evaluation(report)
    graph = graph_builder.graph
    assert graph.has_node("failure:fail_int_001")

    # 4. Phase 36 Automated AI Test Generation
    gen_engine = TestGenerationEngine()
    config = TestGenerationConfig(
        max_candidates=20,
        min_quality_threshold=0.50,
        promotion_threshold=0.75,
        deterministic_seed=42,
    )
    request = TestGenerationRequest(
        sources=[report, trace, analysis, graph],
        config=config,
    )
    result = gen_engine.generate(request, graph=graph)

    assert result.total_generated >= 4
    assert result.total_validated >= 3
    assert result.total_rejected == 0

    # 5. Verify Generated Tests & Quality Scores
    for vt in result.validated_tests:
        assert vt.status == TestGenerationStatus.VALIDATED
        assert vt.quality_score is not None
        assert vt.quality_score.total_score >= 0.50
        assert vt.fingerprint != ""

    # 6. Safe Promotion to Golden EvaluationDataset
    golden_ds = EvaluationDataset(
        id="golden_financial_protection",
        name="Golden Financial Protection Suite",
        description="Regression and golden cases generated automatically from failures",
    )
    promoter = TestPromotionManager(min_promotion_quality=0.75)
    promoted_tests, updated_ds = promoter.batch_promote_to_dataset(
        result.validated_tests, golden_ds
    )

    assert len(promoted_tests) >= 1
    assert len(updated_ds.test_cases) == len(promoted_tests)
    assert all(t.status == TestGenerationStatus.PROMOTED for t in promoted_tests)

    # 7. Knowledge Graph Provenance Synchronization
    bridge = GraphIntegrationBridge()
    for pt in promoted_tests:
        bridge.record_generated_test(graph, pt, dataset_id=updated_ds.id)

    # 8. Knowledge Graph Queries
    tests_for_failure = bridge.query_tests_for_failure(graph, "fail_int_001")
    assert len(tests_for_failure) >= 1
    assert any(t.node_type == GraphNodeType.TEST_CASE for t in tests_for_failure)

    # Verify no unhedged failures remain
    unprotected = bridge.query_failures_without_tests(graph)
    assert len(unprotected) == 0

    # 9. Verify generated TestCase is executable by platform
    first_promoted_tc = updated_ds.test_cases[0]
    assert isinstance(first_promoted_tc, TestCase)
    assert first_promoted_tc.id.startswith("gen_")
    assert "generated" in first_promoted_tc.tags
    assert first_promoted_tc.metadata["generated_test_id"] is not None
