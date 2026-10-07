"""Unit tests for all 14 Phase 36 test generation strategies."""

from __future__ import annotations

from aireliability.core.models import (
    ExecutionTrace,
    FailureReport,
    RegressionTest,
    StepType,
    TestCase,
    TraceStep,
)
from aireliability.evaluation.governance.baselines import EvaluationComparisonResult
from aireliability.evaluation.models import EvaluationReport
from aireliability.generation.models import (
    GenerationStrategy,
    TestGenerationConfig,
    TestPriority,
    TestRiskLevel,
    TestType,
)
from aireliability.generation.strategies import (
    AdversarialTestGenerator,
    AgentTestGenerator,
    ConsistencyTestGenerator,
    EdgeCaseGenerator,
    FailureTestGenerator,
    GraphTestGenerator,
    IncidentTestGenerator,
    MutationGenerator,
    PatternTestGenerator,
    RAGTestGenerator,
    RegressionTestGenerator,
    RobustnessTestGenerator,
    SafetyTestGenerator,
    TraceTestGenerator,
)
from aireliability.graph.graph import KnowledgeGraph
from aireliability.graph.models import (
    GraphEdge,
    GraphNode,
    GraphNodeType,
    GraphRelationship,
)
from aireliability.intelligence.models import (
    ConfidenceLevel,
    FailureCluster,
    FailurePattern,
    IntelligenceConfidence,
    PatternType,
    ReliabilityRecommendation,
)
from aireliability.observability.incidents import IncidentRecord


def test_failure_test_generator() -> None:
    """Verify FailureTestGenerator handles FailureReport and EvaluationReport."""
    f1 = FailureReport(
        failure_id="f_output_1",
        trace_id="tr_1",
        category="output_hallucination",
        type="factual_error",
        message="Model stated wrong revenue number",
        confidence=0.9,
    )
    f2 = FailureReport(
        failure_id="f_tool_2",
        trace_id="tr_2",
        category="tool_failure",
        type="invalid_arguments",
        message="Tool called with missing city param",
        evidence={"tool_name": "weather_api"},
    )
    eval_rep = EvaluationReport(
        report_id="rep_1",
        target_name="test_target",
        dataset_id="ds_1",
        total_test_cases=2,
        passed_test_cases=0,
        failed_test_cases=2,
        failures=[f1, f2],
    )

    gen = FailureTestGenerator()
    config = TestGenerationConfig()
    tests = gen.generate(eval_rep, config)

    assert len(tests) == 2
    assert tests[0].strategy == GenerationStrategy.FAILURE_DRIVEN
    assert tests[0].provenance.source_failure_id == "f_output_1"
    assert tests[1].test_type == TestType.AGENT
    assert tests[1].tool_definitions[0]["name"] == "weather_api"


def test_regression_test_generator() -> None:
    """Verify RegressionTestGenerator handles RegressionTest and EvaluationComparisonResult."""
    tc = TestCase(id="tc_1", name="math_case", input="2+2", expected_output="4")
    reg = RegressionTest(
        id="reg_1", name="reg_math", source_failure_id="fail_9", test_case=tc
    )

    gen = RegressionTestGenerator()
    config = TestGenerationConfig()
    tests = gen.generate(reg, config)

    assert len(tests) == 1
    assert tests[0].strategy == GenerationStrategy.REGRESSION_DRIVEN
    assert tests[0].has_ground_truth
    assert tests[0].expected_output == "4"

    cmp = EvaluationComparisonResult(
        baseline_name="v1_baseline",
        baseline_version="1.0.0",
        current_report_id="rep_cur",
        regressions=["accuracy degraded by 12%"],
        has_regressions=True,
    )
    tests_cmp = gen.generate(cmp, config)
    assert len(tests_cmp) == 1
    assert "accuracy degraded" in tests_cmp[0].expected_criteria[0]


def test_graph_test_generator() -> None:
    """Verify GraphTestGenerator generates tests traversing failing graph paths."""
    g = KnowledgeGraph()
    fail_node = GraphNode.create(
        node_type=GraphNodeType.FAILURE,
        source_id="fail_xyz",
        name="Retriever Timeout Failure",
        tags=["critical"],
    )
    retriever_node = GraphNode.create(
        node_type=GraphNodeType.RETRIEVER,
        source_id="elastic_retriever",
        name="Elasticsearch Retriever",
    )
    g.add_node(fail_node)
    g.add_node(retriever_node)
    g.add_edge(
        GraphEdge.create(
            relationship_type=GraphRelationship.AFFECTS,
            source_node_id=retriever_node.node_id,
            target_node_id=fail_node.node_id,
        )
    )

    gen = GraphTestGenerator()
    config = TestGenerationConfig()
    tests = gen.generate(g, config)

    assert len(tests) >= 1
    assert tests[0].strategy == GenerationStrategy.GRAPH_DRIVEN
    assert tests[0].test_type == TestType.RAG
    assert tests[0].risk_level == TestRiskLevel.HIGH
    assert tests[0].provenance.source_graph_node == fail_node.node_id


def test_pattern_test_generator() -> None:
    """Verify PatternTestGenerator handles patterns, clusters, and recommendations."""
    pat = FailurePattern(
        pattern_id="pat_1",
        pattern_type=PatternType.PERSISTENT,
        title="Persistent schema mismatch",
        description="Persistent mismatch across API versions",
        fingerprint="fp_pat",
        affected_components=["api_gateway"],
        confidence=IntelligenceConfidence(score=0.95, level=ConfidenceLevel.HIGH),
    )
    cluster = FailureCluster(
        cluster_id="cl_1",
        name="Authentication Drops",
        fingerprint="fp_cl",
        representative_failure_id="f_rep",
        dominant_category="security",
        dominant_root_cause="token_expiration",
    )
    rec = ReliabilityRecommendation(
        recommendation_id="rec_1",
        title="Add token refresh retry",
        description="Auto-refresh tokens",
        suggested_action="configure refresh hook",
        rationale="Prevents 95% of token expirations",
    )

    gen = PatternTestGenerator()
    config = TestGenerationConfig()
    tests = gen.generate([pat, cluster, rec], config)

    assert len(tests) == 3
    assert tests[0].priority == TestPriority.CRITICAL
    assert tests[1].provenance.source_cluster_id == "cl_1"
    assert tests[2].provenance.source_recommendation_id == "rec_1"


def test_incident_test_generator() -> None:
    """Verify IncidentTestGenerator converts IncidentRecords to regression protection."""
    inc = IncidentRecord(
        incident_id="inc_999",
        title="High Latency Outage",
        description="P99 exceeded 5000ms in EU cluster",
        severity="CRITICAL",
        trace_ids=["tr_outage"],
    )

    gen = IncidentTestGenerator()
    config = TestGenerationConfig()
    tests = gen.generate(inc, config)

    assert len(tests) == 1
    assert tests[0].strategy == GenerationStrategy.INCIDENT_DRIVEN
    assert tests[0].risk_level == TestRiskLevel.CRITICAL
    assert tests[0].priority == TestPriority.CRITICAL
    assert tests[0].provenance.source_incident_id == "inc_999"


def test_trace_test_generator_with_sanitization() -> None:
    """Verify TraceTestGenerator sanitizes input/output and extracts tool calls."""
    trace = ExecutionTrace(
        trace_id="tr_prod_100",
        input={"prompt": "Fetch order details for user", "api_key": "secret_key_123"},
        output="Order details loaded",
        steps=[
            TraceStep(name="order_db_call", type=StepType.TOOL, input={"id": 10}),
            TraceStep(name="format_response", type=StepType.LLM),
        ],
        latency_ms=120.0,
    )

    gen = TraceTestGenerator()
    config = TestGenerationConfig()
    tests = gen.generate(trace, config)

    assert len(tests) == 1
    assert tests[0].strategy == GenerationStrategy.PRODUCTION_TRACE_DRIVEN
    # Sensitive key 'api_key' must be sanitized
    assert tests[0].input["api_key"] == "[REDACTED]"
    assert len(tests[0].expected_tool_calls) == 1
    assert tests[0].expected_tool_calls[0]["name"] == "order_db_call"


def test_edge_case_generator() -> None:
    """Verify EdgeCaseGenerator outputs boundary and null inputs bounded by limit."""
    gen = EdgeCaseGenerator()
    config = TestGenerationConfig(max_candidates=6)
    tests = gen.generate("Test query", config)

    assert len(tests) == 6
    names = [t.name for t in tests]
    assert any("empty_input" in n for n in names)
    assert any("null_input" in n for n in names)
    assert any("unicode_emoji" in n for n in names)


def test_mutation_generator() -> None:
    """Verify MutationGenerator applies bounded mutations on parent test."""
    tc = TestCase(id="tc_parent", name="parent_calc", input="Calculate total tax rate.")
    gen = MutationGenerator()
    config = TestGenerationConfig(max_mutation_count=4)
    mutations = gen.generate(tc, config)

    assert len(mutations) <= 4
    for m in mutations:
        assert m.strategy == GenerationStrategy.MUTATION_BASED
        assert m.provenance.parent_test_id == "tc_parent"
        assert m.provenance.mutation_type is not None


def test_adversarial_and_safety_generators() -> None:
    """Verify AdversarialTestGenerator and SafetyTestGenerator scenarios."""
    adv_gen = AdversarialTestGenerator()
    adv_tests = adv_gen.generate("Process request", TestGenerationConfig())
    assert len(adv_tests) >= 3
    assert any(t.risk_level == TestRiskLevel.CRITICAL for t in adv_tests)

    safety_gen = SafetyTestGenerator()
    safety_tests = safety_gen.generate(None, TestGenerationConfig())
    assert len(safety_tests) >= 3
    assert any(t.name == "safety_secret_credential_leakage" for t in safety_tests)


def test_rag_and_agent_generators() -> None:
    """Verify RAGTestGenerator and AgentTestGenerator behavior."""
    rag_gen = RAGTestGenerator()
    rag_tests = rag_gen.generate(None, TestGenerationConfig())
    assert len(rag_tests) >= 3
    assert any(t.name == "rag_relevant_grounded_query" for t in rag_tests)

    agent_gen = AgentTestGenerator()
    agent_tests = agent_gen.generate(None, TestGenerationConfig())
    assert len(agent_tests) >= 3
    assert any(t.name == "agent_tool_selection_and_call" for t in agent_tests)


def test_robustness_and_consistency_generators() -> None:
    """Verify RobustnessTestGenerator and ConsistencyTestGenerator."""
    rob_gen = RobustnessTestGenerator()
    rob_tests = rob_gen.generate("What is 1+1?", TestGenerationConfig())
    assert len(rob_tests) >= 3
    assert any("case_mutation" in t.name for t in rob_tests)

    const_gen = ConsistencyTestGenerator()
    const_tests = const_gen.generate(
        "What is the capital of Italy?", TestGenerationConfig()
    )
    assert len(const_tests) == 4
    # All members share same consistency group ID
    grp_id = const_tests[0].metadata["consistency_group_id"]
    assert all(t.metadata["consistency_group_id"] == grp_id for t in const_tests)
