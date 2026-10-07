"""Integration tests for Phase 35 AI Reliability Knowledge Graph.

Verifies end-to-end integration across:
- EvaluationEngine & EvaluationReport
- FailureAnalyzer & RootCause
- RegressionGenerator & RegressionTest
- IncidentManager & IncidentRecord
- ReliabilityIntelligenceEngine & IntelligenceAnalysis
- ObservabilityManager & GraphTelemetry
- Security sanitization
- GraphBuilder, Query, Traversal, Impact, and Serialization
"""

from __future__ import annotations

from pathlib import Path

from aireliability import (
    ContinuousReliabilityMonitor,
    EvaluationEngine,
    IncidentManager,
    KnowledgeGraphBuilder,
    ObservabilityManager,
    ProductionRegressionHarvester,
    ProductionSampler,
    ReliabilityIntelligenceEngine,
    ReliabilityRunner,
)
from aireliability.core.models import (
    ExecutionTrace,
    FailureReport,
    StepType,
    TestCase,
    TraceStep,
)
from aireliability.diagnosis.models import RootCause, RootCauseCategory, RootCauseType
from aireliability.evaluation.governance.baselines import EvaluationHistoryManager
from aireliability.evaluation.models import (
    EvaluationReport,
    EvaluationTarget,
    MetricResult,
)
from aireliability.graph.integrations import GraphTelemetry
from aireliability.graph.serialization import GraphSerializer, diff_graphs
from aireliability.regression.models import RegressionTest


def test_phase35_backward_compatibility_v030_apis() -> None:
    """Verify that all public v0.3.0 and Phase 34 platform APIs remain completely intact."""
    # Core & Execution
    tc = TestCase(name="test_1", input="query", expected="answer")
    trace = ExecutionTrace(input="query", output="answer")
    runner = ReliabilityRunner(agent=lambda x: x)
    assert runner is not None
    assert tc.name == "test_1"
    assert trace.input == "query"

    # Evaluation & Target
    target = EvaluationTarget(name="agent_target")
    eval_engine = EvaluationEngine()
    assert eval_engine is not None
    assert target.name == "agent_target"

    # Diagnosis & Governance
    rc = RootCause(
        category=RootCauseCategory.OUTPUT,
        type=RootCauseType.UNEXPECTED_OUTPUT,
    )
    hist_mgr = EvaluationHistoryManager()
    assert rc.category == RootCauseCategory.OUTPUT
    assert hist_mgr is not None

    # Observability & Production
    obs = ObservabilityManager()
    inc_mgr = IncidentManager()
    sampler = ProductionSampler()
    monitor = ContinuousReliabilityMonitor()
    harvester = ProductionRegressionHarvester()
    intel_engine = ReliabilityIntelligenceEngine(
        observability=obs, incident_manager=inc_mgr
    )

    assert obs is not None
    assert inc_mgr is not None
    assert sampler is not None
    assert monitor is not None
    assert harvester is not None
    assert intel_engine is not None


def test_phase35_full_platform_pipeline_integration(tmp_path: Path) -> None:
    """End-to-end integration: Evaluation -> Diagnosis -> Incident -> Intelligence -> Graph."""
    obs = ObservabilityManager()
    inc_mgr = obs.incidents
    intel_engine = ReliabilityIntelligenceEngine(
        observability=obs, incident_manager=inc_mgr
    )

    # 1. Synthesize failing evaluation report with security and retrieval failures
    failures = [
        FailureReport(
            failure_id="f_sec_100",
            trace_id="tr_sec_100",
            category="security",
            type="credential_exposure",
            message="Model leaked private API key in output response",
            metadata={
                "component": "guardrail:data_leak",
                "model": "gpt-4o",
                "severity": "CRITICAL",
            },
        ),
        FailureReport(
            failure_id="f_ret_200",
            trace_id="tr_ret_200",
            category="retrieval",
            type="missing_context",
            message="Knowledge base search failed for user query",
            metadata={
                "component": "retriever:vector_db",
                "model": "gpt-4o",
                "severity": "HIGH",
            },
        ),
    ]

    report = EvaluationReport(
        report_id="rep_full_e2e",
        target_name="medical_advisor_agent",
        dataset_id="golden_clinical_v1",
        total_test_cases=10,
        passed_test_cases=8,
        failed_test_cases=2,
        metrics={
            "accuracy": MetricResult(name="accuracy", value=0.80),
            "safety": MetricResult(name="safety", value=0.60),
        },
        failures=failures,
    )

    # 2. Run Intelligence Engine (Phase 34)
    analysis = intel_engine.analyze_evaluation(report)
    assert len(analysis.clusters) >= 1
    assert len(analysis.recommendations) >= 1

    # 3. Create RootCause and Incident
    rc = RootCause(
        id="rc_sec_100",
        category=RootCauseCategory.OUTPUT,
        type=RootCauseType.UNEXPECTED_OUTPUT,
        description="Jailbreak evasion on prompt template",
        confidence=0.95,
        metadata={"failure_id": "f_sec_100"},
    )

    incident = inc_mgr.create_incident(
        title="Production Credential Leak",
        severity="P0",
        description="Prompt injection vulnerability exposed internal key",
        metadata={"component": "medical_advisor_agent"},
    )

    # 4. Create Regression Test
    reg_test = RegressionTest(
        id="reg_sec_100",
        source_failure_id="f_sec_100",
        name="Regression Test for Credential Leak",
        test_case=TestCase(
            name="tc_sec_100", input="bypass prompt", expected="refusal"
        ),
        metadata={"root_cause_id": "rc_sec_100", "dataset": "golden_clinical_v1"},
    )

    # 5. Build Knowledge Graph (Phase 35)
    builder = KnowledgeGraphBuilder()
    builder.from_evaluation(
        report, model_name="gpt-4o", prompt_name="clinical_prompt_v1"
    )
    builder.from_root_cause(rc)
    builder.from_incident(incident)
    builder.from_regression(reg_test)
    builder.from_intelligence(analysis)

    graph = builder.graph
    assert graph.node_count > 10
    assert graph.edge_count > 10

    # 6. Verify Node presence
    assert graph.has_node("evaluation:rep_full_e2e")
    assert graph.has_node("failure:f_sec_100")
    assert graph.has_node("failure:f_ret_200")
    assert graph.has_node("model:gpt-4o")
    assert graph.has_node("dataset:golden_clinical_v1")
    assert graph.has_node("root_cause:rc_sec_100")
    assert graph.has_node(f"incident:{incident.incident_id}")
    assert graph.has_node("regression:reg_sec_100")

    # 7. Query Capabilities
    model_failures = graph.query.find_failures_for_model("gpt-4o")
    assert len(model_failures) == 2
    fail_ids = {f.node_id for f in model_failures}
    assert fail_ids == {"failure:f_sec_100", "failure:f_ret_200"}

    dataset_regressions = graph.query.find_regressions_for_dataset("golden_clinical_v1")
    assert len(dataset_regressions) >= 1
    assert any(r.node_id == "regression:reg_sec_100" for r in dataset_regressions)

    # 8. Provenance & Lineage
    f_prov = graph.provenance.get_node_provenance("failure:f_sec_100")
    assert f_prov["node_id"] == "failure:f_sec_100"
    assert f_prov["node_type"] == "FAILURE"

    origins = graph.provenance.trace_origin("failure:f_sec_100")
    assert len(origins) >= 1
    origin_types = {o["origin_node_type"] for o in origins}
    assert "DATASET" in origin_types

    # 9. Impact Analysis
    impact = graph.impact_analyzer.analyze("model:gpt-4o")
    assert impact.root_node_id == "model:gpt-4o"
    assert impact.failure_count >= 2
    assert impact.security_critical is True
    assert impact.impact_score > 0.0

    # 10. Serialization & Diff Roundtrip
    export_file = tmp_path / "integrated_graph.json"
    GraphSerializer.export_json(graph, export_file)
    assert export_file.exists()

    imported_graph = GraphSerializer.import_json(export_file)
    assert imported_graph.node_count == graph.node_count
    assert imported_graph.edge_count == graph.edge_count

    diff = diff_graphs(graph, imported_graph)
    assert diff.has_changes is False


def test_phase35_security_sanitization_integration() -> None:
    """Verify that credentials, API keys, bearer tokens, and secrets are sanitized before ingestion."""
    trace = ExecutionTrace(
        trace_id="tr_secret_test",
        input="Please connect to db",
        output="Connected with password=SuperSecret123!",
        metadata={
            "api_key": "sk-proj-super-secret-key-12345",
            "bearer_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            "normal_config": "env_prod",
        },
    )
    step = TraceStep(
        id="step_leak_01",
        name="DB Query",
        step_type=StepType.TOOL,
        metadata={
            "private_key": "-----BEGIN RSA PRIVATE KEY-----SECRET-----END RSA PRIVATE KEY-----"
        },
    )
    trace.steps.append(step)

    builder = KnowledgeGraphBuilder()
    builder.from_trace(trace)

    trace_node = builder.graph.get_node("trace:tr_secret_test")
    assert trace_node is not None
    assert trace_node.metadata.get("api_key") == "[REDACTED]"
    assert trace_node.metadata.get("bearer_token") == "[REDACTED]"
    assert trace_node.metadata.get("normal_config") == "env_prod"

    step_node = builder.graph.get_node("trace_step:step_leak_01")
    assert step_node is not None
    assert step_node.metadata.get("private_key") == "[REDACTED]"


def test_phase35_observability_telemetry_integration() -> None:
    """Verify that graph operations report telemetry events to ObservabilityManager."""
    obs = ObservabilityManager()
    telemetry = GraphTelemetry(observability=obs)

    with telemetry.track_build("evaluation_run_42") as ctx:
        telemetry.record_nodes_created(15)
        telemetry.record_edges_created(22)
        telemetry.record_duplicates_avoided(3)
        assert ctx["source_type"] == "evaluation_run_42"

    with telemetry.track_query("find_failures") as q_ctx:
        assert q_ctx["query_type"] == "find_failures"

    with telemetry.track_traversal("bfs") as t_ctx:
        assert t_ctx["traversal_type"] == "bfs"

    with telemetry.track_serialization("json") as s_ctx:
        assert s_ctx["format"] == "json"

    # Verify metrics were recorded in ObservabilityManager
    assert "aireliability_graph_nodes_created_total" in obs.metrics.counters
    assert "aireliability_graph_edges_created_total" in obs.metrics.counters
    assert "aireliability_graph_duplicates_avoided_total" in obs.metrics.counters
    assert "aireliability_graph_build_completed_total" in obs.metrics.counters
