"""Unit tests for Phase 35 KnowledgeGraphBuilder ingestion and idempotency."""

from aireliability.core.models import (
    ExecutionTrace,
    FailureReport,
    FailureSeverity,
    RegressionTest,
    StepType,
    TestCase,
    TraceStep,
)
from aireliability.diagnosis.models import RootCause, RootCauseCategory, RootCauseType
from aireliability.evaluation.datasets.models import EvaluationDataset
from aireliability.evaluation.experiments.models import (
    ABComparisonResult,
    VariantConfig,
)
from aireliability.evaluation.governance.baselines import (
    EvaluationBaseline,
    EvaluationComparisonResult,
)
from aireliability.evaluation.models import (
    EvaluationReport,
    EvaluationRequest,
    EvaluationTarget,
    MetricResult,
)
from aireliability.failures.taxonomy import FailureCategory, FailureType
from aireliability.graph.builder import KnowledgeGraphBuilder
from aireliability.graph.models import GraphRelationship
from aireliability.intelligence.models import (
    CrossRunCorrelation,
    FailureCluster,
    FailurePattern,
    IntelligenceAnalysis,
    IntelligenceSummary,
    PatternType,
    RecommendationPriority,
    ReliabilityRecommendation,
    ReliabilityTrend,
    TrendDirection,
)
from aireliability.observability.incidents import IncidentRecord


def test_builder_from_evaluation() -> None:
    """Test graph construction from an EvaluationReport."""
    report = EvaluationReport(
        report_id="rep_test_01",
        target_name="gpt-4o-pipeline",
        dataset_id="ds_qa_v1",
        total_test_cases=2,
        passed_test_cases=1,
        failed_test_cases=1,
        request=EvaluationRequest(
            target=EvaluationTarget(name="gpt-4o-pipeline", type="model"),
            dataset="ds_qa_v1",
        ),
        metrics={
            "accuracy": MetricResult(name="accuracy", value=0.95),
            "hallucination_rate": MetricResult(name="hallucination_rate", value=0.04),
        },
        failures=[
            FailureReport(
                failure_id="f_001",
                trace_id="tr_001",
                category=FailureCategory.RETRIEVAL,
                type=FailureType.HALLUCINATION,
                message="Ungrounded claim in answer",
                severity=FailureSeverity.HIGH,
            )
        ],
        metadata={
            "model": "gpt-4o",
            "model_version": "2024-05-13",
            "prompt": "qa_system",
            "prompt_version": "v1.2",
            "retriever": "hybrid_rag",
            "tool": "calculator",
        },
    )

    builder = KnowledgeGraphBuilder()
    builder.from_evaluation(report)
    kg = builder.graph

    assert kg.has_node("dataset:ds_qa_v1") is True
    assert kg.has_node("evaluation:rep_test_01") is True
    assert kg.has_node("model:gpt-4o:2024-05-13") is True
    assert kg.has_node("prompt:qa_system:v1.2") is True
    assert kg.has_node("retriever:hybrid_rag") is True
    assert kg.has_node("tool:calculator") is True
    assert kg.has_node("metric:accuracy") is True
    assert kg.has_node("failure:f_001") is True

    # Check edges
    assert len(kg.list_edges(relationship_type=GraphRelationship.USED_MODEL)) >= 1
    assert len(kg.list_edges(relationship_type=GraphRelationship.FAILED)) >= 1
    assert len(kg.list_edges(relationship_type=GraphRelationship.MEASURED_BY)) == 2


def test_builder_from_trace() -> None:
    """Test graph construction from ExecutionTrace and steps."""
    step = TraceStep(
        id="step_calc",
        name="step_calc",
        type=StepType.TOOL,
        metadata={"tool_name": "calculator"},
        input={"expr": "2+2"},
        output={"res": 4},
    )
    trace = ExecutionTrace(
        trace_id="tr_999",
        target="math_agent",
        test_id="tc_math_1",
        steps=[step],
        metadata={"execution_id": "exec_888"},
    )

    builder = KnowledgeGraphBuilder()
    builder.from_trace(trace)
    kg = builder.graph

    assert kg.has_node("trace:tr_999") is True
    assert kg.has_node("execution:exec_888") is True
    assert kg.has_node("test_case:tc_math_1") is True
    assert kg.has_node("trace_step:step_calc") is True
    assert kg.has_node("tool:calculator") is True


def test_builder_from_failure_and_root_cause() -> None:
    """Test graph construction from FailureReport and RootCause."""
    failure = FailureReport(
        failure_id="fail_timeout_01",
        trace_id="tr_002",
        category=FailureCategory.PERFORMANCE,
        type=FailureType.LATENCY,
        message="Request timed out after 3000ms",
        severity=FailureSeverity.CRITICAL,
        metadata={"component": "tool:web_search"},
    )
    rc = RootCause(
        id="rc_slow_network",
        category=RootCauseCategory.PERFORMANCE,
        type=RootCauseType.LATENCY_REGRESSION,
        description="Downstream search provider experiencing 504 gateway timeouts",
        confidence=0.91,
    )

    builder = KnowledgeGraphBuilder()
    builder.from_failure(failure, root_cause=rc)
    kg = builder.graph

    assert kg.has_node("failure:fail_timeout_01") is True
    assert kg.has_node("tool:web_search") is True
    assert kg.has_node("root_cause:rc_slow_network") is True
    edges = kg.list_edges(relationship_type=GraphRelationship.HAS_ROOT_CAUSE)
    assert len(edges) == 1
    assert edges[0].confidence == 0.91


def test_builder_from_incident() -> None:
    """Test graph construction from IncidentRecord."""
    incident = IncidentRecord(
        incident_id="inc_sec_01",
        title="Prompt Injection Attack Bypassed Safety Filter",
        description="Filter bypassed during adversarial probe",
        severity="CRITICAL",
        trace_ids=["tr_injected_100"],
        execution_ids=["exec_100"],
        metadata={
            "failure_id": "fail_injection_01",
            "root_cause_id": "rc_safety_bypass",
        },
    )

    builder = KnowledgeGraphBuilder()
    builder.from_incident(incident)
    kg = builder.graph

    assert kg.has_node("incident:inc_sec_01") is True
    assert kg.has_node("trace:tr_injected_100") is True
    assert kg.has_node("failure:fail_injection_01") is True
    assert kg.has_node("root_cause:rc_safety_bypass") is True


def test_builder_from_regression_and_baseline() -> None:
    """Test graph construction from RegressionTest, EvaluationBaseline, and EvaluationComparisonResult."""
    reg = RegressionTest(
        id="reg_case_01",
        name="Regression test_accuracy_drop",
        source_failure_id="f_001",
        test_case=TestCase(name="tc_001_name", input="hello"),
        metadata={"model": "gpt-4o-mini"},
    )
    baseline = EvaluationBaseline(
        name="release_v1_baseline",
        version="1.0.0",
        dataset_version="v2.1",
        model_version="gpt-4o-2024-05-13",
    )
    comp = EvaluationComparisonResult(
        baseline_name="release_v1_baseline",
        baseline_version="1.0.0",
        current_report_id="rep_candidate_01",
        regressions=["test_accuracy_drop"],
        has_regressions=True,
    )

    builder = KnowledgeGraphBuilder()
    builder.from_regression(reg)
    builder.from_baseline(baseline)
    builder.from_comparison(comp)
    kg = builder.graph

    assert kg.has_node("regression:reg_case_01") is True
    assert kg.has_node("baseline:release_v1_baseline:1.0.0") is True
    assert kg.has_node("regression:rep_candidate_01_test_accuracy_drop") is True


def test_builder_from_dataset_and_experiment() -> None:
    """Test building from EvaluationDataset and ABComparisonResult."""
    dataset = EvaluationDataset(
        id="ds_med_test",
        name="MedQA",
        version="1.0.0",
        test_cases=[TestCase(id="tc_med_1", name="tc_med_1", input="What is dosage?")],
    )
    exp = ABComparisonResult(
        experiment_id="ab_exp_01",
        variant_a=VariantConfig(name="variant_a", model_version="gpt-4o"),
        variant_b=VariantConfig(name="variant_b", model_version="claude-3-5"),
        metric_deltas={"f1": 0.05},
        overall_winner="variant_b",
    )

    builder = KnowledgeGraphBuilder()
    builder.from_dataset(dataset)
    builder.from_experiment(exp)
    kg = builder.graph

    assert kg.has_node("dataset:ds_med_test") is True
    assert kg.has_node("test_case:tc_med_1") is True
    assert kg.has_node("experiment:ab_exp_01") is True
    assert kg.has_node("model:variant_a:gpt-4o") is True
    assert kg.has_node("model:variant_b:claude-3-5") is True


def test_builder_from_intelligence() -> None:
    """Test graph construction from Phase 34 IntelligenceAnalysis."""
    analysis = IntelligenceAnalysis(
        target_name="prod_agent",
        summary=IntelligenceSummary(
            total_failures_analyzed=2,
            total_clusters=1,
            total_patterns=1,
            total_correlations=1,
        ),
        clusters=[
            FailureCluster(
                cluster_id="fc_hallucination",
                name="Hallucination Cluster",
                fingerprint="fp_hallucination_1",
                representative_failure_id="f_01",
                failure_ids=["f_01", "f_02"],
                affected_components=["retriever:dense_passage_retriever"],
            )
        ],
        patterns=[
            FailurePattern(
                pattern_id="pat_drift",
                pattern_type=PatternType.PERSISTENT,
                title="Systemic context length exhaustion",
                description="Context length exhausted repeatedly across traces",
                fingerprint="fp_drift_01",
            )
        ],
        correlations=[
            CrossRunCorrelation(
                correlation_id="corr_01",
                source_change_type="model_change",
                source_change_value="gpt-4o",
                affected_metric_or_failure="latency",
                observed_effect="Latency increased by 200ms",
                strength=0.82,
                is_causal=False,  # Explicitly non-causal
            )
        ],
        trends=[
            ReliabilityTrend(
                trend_id="trend_cost",
                metric_or_dimension="cost",
                direction=TrendDirection.STABLE,
            )
        ],
        recommendations=[
            ReliabilityRecommendation(
                recommendation_id="rec_chunk_size",
                title="Reduce chunk size to 256 tokens",
                description="Chunk size is causing context overflow",
                suggested_action="Set chunk_size to 256 tokens in retriever config",
                rationale="Prevents context length exhaustion",
                priority=RecommendationPriority.HIGH,
                related_clusters=["fc_hallucination"],
            )
        ],
    )

    builder = KnowledgeGraphBuilder()
    builder.from_intelligence(analysis)
    kg = builder.graph

    assert kg.has_node("failure_cluster:fc_hallucination") is True
    assert kg.has_node("pattern:pat_drift") is True
    assert kg.has_node("model:gpt-4o") is True
    assert kg.has_node("trend:trend_cost") is True
    assert kg.has_node("recommendation:rec_chunk_size") is True

    # Verify SUPPORTED_BY edge from recommendation to cluster
    sup_edges = kg.list_edges(relationship_type=GraphRelationship.SUPPORTED_BY)
    assert len(sup_edges) == 1
    assert sup_edges[0].source_node_id == "recommendation:rec_chunk_size"
    assert sup_edges[0].target_node_id == "failure_cluster:fc_hallucination"


def test_builder_idempotency() -> None:
    """MANDATORY: Adding the same source artifact twice must not duplicate nodes or edges."""
    report = EvaluationReport(
        report_id="rep_idemp_01",
        target_name="agent_v1",
        dataset_id="ds_idemp",
        total_test_cases=1,
        passed_test_cases=1,
        failed_test_cases=0,
        request=EvaluationRequest(
            target=EvaluationTarget(name="agent_v1", type="model"),
            dataset="ds_idemp",
        ),
        metrics={"accuracy": MetricResult(name="accuracy", value=0.90)},
    )

    builder = KnowledgeGraphBuilder()
    builder.from_evaluation(report)
    n_nodes_first = builder.graph.node_count
    n_edges_first = builder.graph.edge_count

    # Second ingestion of the same report
    builder.from_evaluation(report)
    assert builder.graph.node_count == n_nodes_first
    assert builder.graph.edge_count == n_edges_first
