"""Unit tests for TestGenerationEngine, KnowledgeGraph, and Observability integrations."""

from __future__ import annotations

from aireliability.core.models import FailureReport
from aireliability.generation.engine import TestGenerationEngine
from aireliability.generation.integrations import (
    GraphIntegrationBridge,
)
from aireliability.generation.models import (
    GenerationStrategy,
    TestGenerationConfig,
    TestGenerationRequest,
)
from aireliability.graph.graph import KnowledgeGraph
from aireliability.graph.models import GraphNode, GraphNodeType
from aireliability.observability.manager import ObservabilityManager


def test_engine_end_to_end_pipeline() -> None:
    """Verify TestGenerationEngine runs end-to-end pipeline deterministically."""
    fail = FailureReport(
        failure_id="f_pipeline_1",
        trace_id="tr_pipeline_1",
        category="output_hallucination",
        message="Model hallucinated medical advice",
        confidence=0.9,
    )
    engine = TestGenerationEngine()
    request = TestGenerationRequest(
        sources=[fail],
        strategies=[GenerationStrategy.FAILURE_DRIVEN],
        config=TestGenerationConfig(deterministic_seed=42),
    )
    result = engine.generate(request)

    assert result.total_generated >= 1
    assert result.total_validated >= 1
    assert result.total_rejected == 0
    assert result.duration_ms > 0
    assert "failure_driven" in result.strategy_distribution
    assert len(result.validated_tests) == 1
    assert result.validated_tests[0].quality_score is not None


def test_engine_resilient_error_handling() -> None:
    """Verify that an invalid source object does not crash the batch."""
    good_fail = FailureReport(
        failure_id="f_good",
        trace_id="tr_good",
        category="rag",
        message="rag error",
    )
    engine = TestGenerationEngine()
    request = TestGenerationRequest(
        sources=[good_fail, "invalid_non_failure_object"],
        strategies=[GenerationStrategy.FAILURE_DRIVEN],
    )
    result = engine.generate(request)

    # Good failure was still generated and validated
    assert result.total_validated >= 1


def test_graph_integration_bridge() -> None:
    """Verify KnowledgeGraph integration records generated tests and provenance edges."""
    graph = KnowledgeGraph()
    fail_node = GraphNode.create(
        node_type=GraphNodeType.FAILURE,
        source_id="fail_core_99",
        name="Critical Core Failure",
    )
    graph.add_node(fail_node)

    fail = FailureReport(
        failure_id="fail_core_99",
        trace_id="tr_core_99",
        category="execution",
        message="Execution failure",
    )

    engine = TestGenerationEngine()
    request = TestGenerationRequest(
        sources=[fail],
        strategies=[GenerationStrategy.FAILURE_DRIVEN],
    )
    result = engine.generate(request, graph=graph)
    assert result.total_validated >= 1

    bridge = GraphIntegrationBridge()
    tests_for_fail = bridge.query_tests_for_failure(graph, "fail_core_99")
    assert len(tests_for_fail) >= 1
    assert tests_for_fail[0].node_type == GraphNodeType.TEST_CASE

    unprotected = bridge.query_failures_without_tests(graph)
    assert len(unprotected) == 0


def test_observability_integration_bridge() -> None:
    """Verify ObservabilityManager metrics are updated during test generation."""
    obs = ObservabilityManager()
    fail = FailureReport(
        failure_id="f_obs",
        trace_id="tr_obs",
        category="perf",
        message="perf error",
    )
    engine = TestGenerationEngine()
    request = TestGenerationRequest(sources=[fail])
    result = engine.generate(request, observability=obs)

    assert result.total_validated >= 1
