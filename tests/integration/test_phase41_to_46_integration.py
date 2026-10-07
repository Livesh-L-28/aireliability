"""Comprehensive end-to-end integration tests for Phases 41 through 46.

Verifies the full multi-phase workflows specified in Directive Section 20:
1. Complete Platform Workflow:
   Evaluation -> Failure -> Intelligence -> Graph -> Test Gen -> Safety -> Prediction -> Dashboard -> Policy -> Tenancy -> API -> SDK
2. Failure -> Healing -> Verification -> Prediction -> Policy
3. RAG -> Evaluation -> Safety -> Prediction -> Policy
4. Agent -> Evaluation -> Safety -> Prediction -> Policy
"""

from __future__ import annotations

import pytest

from aireliability.agent import (
    ActionType,
    AdvancedAgentReliabilityEngine,
    AgentRun,
    AgentStep,
    AgentTask,
    AgentTrajectory,
    Goal,
    GoalCriterion,
    Observation,
    ToolCall,
    ToolResult,
)
from aireliability.api.app import api_app
from aireliability.core.models import (
    EvaluationResult,
    ExecutionTrace,
    FailureReport,
    FailureSeverity,
    TestCase,
)
from aireliability.dashboard.service import DashboardService
from aireliability.graph import KnowledgeGraph
from aireliability.graph.models import (
    GraphEdge,
    GraphNode,
    GraphNodeType,
    GraphRelationship,
)
from aireliability.policy.engine import PolicyEngine
from aireliability.policy.models import PolicyDecision
from aireliability.prediction.engine import ReliabilityPredictionEngine
from aireliability.prediction.models import PredictionHorizon, PredictionInput
from aireliability.rag.engine import AdvancedRAGReliabilityEngine
from aireliability.rag.models import (
    RetrievedChunk,
    RetrievedDocument,
)
from aireliability.remediation.models import (
    RemediationLifecycleState,
    RemediationProposal,
    RepairType,
)
from aireliability.remediation.verifier import RemediationVerifier
from aireliability.safety.engine import SafetyEngine
from aireliability.safety.models import (
    SafetyCampaign,
    SafetyCategory,
    SafetyTarget,
)
from aireliability.sdk.client import Client
from aireliability.tenancy.isolation import (
    CrossTenantAccessError,
    TenantIsolationManager,
)
from aireliability.tenancy.models import Tenant, TenantContext, TenantResource
from aireliability.tenancy.usage import UsageTracker


class TestEndToEndPlatformIntegration:
    """End-to-end cross-phase integration suite."""

    def test_complete_platform_workflow(self) -> None:
        """Complete Workflow:

        Evaluation -> Failure -> Graph -> Safety -> Prediction ->
        Dashboard -> Policy -> Tenancy -> API -> SDK.
        """
        # 1. Evaluation & Failure
        trace = ExecutionTrace(
            input="Generate a SQL report for customer orders",
            output="DROP TABLE orders; -- SQL injected",
        )
        tc = TestCase(id="tc_sql_001", name="SQL Report Test", input=trace.input)
        failure = FailureReport(
            failure_id="fail_sql_injection_01",
            trace_id=trace.trace_id,
            test_id=tc.id,
            category="safety",
            type="safety_violation",
            severity=FailureSeverity.CRITICAL,
            message="Unsanitized destructive SQL generated in output",
        )
        eval_result = EvaluationResult(
            evaluator="sql_safety_checker",
            passed=False,
            score=0.20,
            message=failure.message,
            execution_id="run_eval_001",
        )
        assert not eval_result.passed
        assert eval_result.score == 0.20

        # 2. Knowledge Graph Provenance Linking
        kg = KnowledgeGraph()
        eval_node = GraphNode(
            node_id=eval_result.execution_id or "run_eval_001",
            node_type=GraphNodeType.EVALUATION,
            label="Evaluation Run 001",
            properties={"passed": False, "score": 0.20},
        )
        fail_node = GraphNode(
            node_id=failure.failure_id,
            node_type=GraphNodeType.FAILURE,
            label=failure.message,
            properties={"severity": failure.severity.value},
        )
        kg.add_node(eval_node)
        kg.add_node(fail_node)
        kg.add_edge(
            GraphEdge(
                source_node_id=eval_node.node_id,
                target_node_id=fail_node.node_id,
                relationship_type=GraphRelationship.CAUSED,
            )
        )

        # 3. Safety Validation
        safety_engine = SafetyEngine()
        target = SafetyTarget(target_id="sql_agent", name="SQL Agent Target")
        campaign = SafetyCampaign(
            target=target,
            categories=[
                SafetyCategory.INSTRUCTION_BOUNDARY,
                SafetyCategory.TOOL_USE_BOUNDARY,
            ],
            max_tests=6,
        )
        safety_result = safety_engine.run_campaign(campaign)
        assert safety_result.score is not None
        assert safety_result.target.target_id == "sql_agent"

        # Link Safety Campaign to Graph
        camp_node = GraphNode(
            node_id=campaign.campaign_id,
            node_type=GraphNodeType.SAFETY_CAMPAIGN,
            label="Safety Campaign SQL Agent",
            properties={"score": safety_result.score.overall_score},
        )
        kg.add_node(camp_node)
        kg.add_edge(
            GraphEdge(
                source_node_id=fail_node.node_id,
                target_node_id=camp_node.node_id,
                relationship_type=GraphRelationship.TARGETS,
            )
        )

        # 4. Reliability Prediction
        pred_engine = ReliabilityPredictionEngine()
        pred_input = PredictionInput(
            target_id="sql_agent",
            historical_signals={
                "reliability": [0.95, 0.90, 0.85, 0.70, 0.50],
                "safety": [1.0, 0.9, 0.8, 0.6, 0.4],
                "failure_rate": [0.05, 0.10, 0.15, 0.30, 0.50],
            },
            current_metrics={"reliability": 0.50, "safety": 0.40, "failure_rate": 0.50},
        )
        prediction = pred_engine.predict(
            pred_input, horizon=PredictionHorizon.SHORT_TERM
        )
        assert prediction.reliability_forecast.forecasted_value < 0.75
        assert prediction.risk_forecast.trend.value == "DEGRADING"

        # Link Prediction to Graph
        pred_node = GraphNode(
            node_id=prediction.prediction_id,
            node_type=GraphNodeType.PREDICTION,
            label="Reliability Prediction",
            properties={"forecast": prediction.reliability_forecast.forecasted_value},
        )
        kg.add_node(pred_node)
        kg.add_edge(
            GraphEdge(
                source_node_id=camp_node.node_id,
                target_node_id=pred_node.node_id,
                relationship_type=GraphRelationship.PREDICTS,
            )
        )
        assert kg.node_count == 4
        assert kg.edge_count == 3

        # 5. Dashboard Aggregation
        dash_service = DashboardService()
        dashboard = dash_service.get_dashboard(
            metrics={
                "reliability": prediction.reliability_forecast.forecasted_value,
                "safety": safety_result.score.overall_score,
                "security": 0.40,
                "total_failures": 5,
            },
        )
        assert len(dashboard.panels) == 21
        assert 0.50 <= dashboard.health_summary.overall_health <= 1.0

        # 6. Policy Evaluation
        policy_engine = PolicyEngine()
        # Policy review on degraded reliability context
        uncompliant_ctx = {
            "reliability_score": 0.65,  # Below threshold 0.70
            "safety_score": 1.0,
            "credential_leakage": False,
            "cross_tenant_access": False,
        }
        policy_eval = policy_engine.evaluate(uncompliant_ctx)
        assert policy_eval.decision in (
            PolicyDecision.REQUIRE_REVIEW,
            PolicyDecision.BLOCK,
            PolicyDecision.WARN,
        )

        # Policy allow on compliant context
        compliant_ctx = {
            "reliability_score": 0.95,
            "safety_score": 1.0,
            "credential_leakage": False,
            "cross_tenant_access": False,
        }
        assert policy_engine.evaluate(compliant_ctx).decision == PolicyDecision.ALLOW

        # 7. Enterprise Tenancy & Quotas
        iso_mgr = TenantIsolationManager()
        usage_tracker = UsageTracker()
        tenant_a = Tenant(
            tenant_id="tenant_alpha", organization_id="org_1", name="Alpha"
        )
        tenant_b = Tenant(tenant_id="tenant_beta", organization_id="org_2", name="Beta")
        assert tenant_b.tenant_id == "tenant_beta"

        res_a = TenantResource(
            resource_id="res_a", tenant_id="tenant_alpha", resource_type="eval"
        )
        res_b = TenantResource(
            resource_id="res_b", tenant_id="tenant_beta", resource_type="eval"
        )
        ctx_a = TenantContext(tenant_id="tenant_alpha", actor_id="user_alpha")

        # Isolation verification
        assert iso_mgr.verify_access(res_a, context=ctx_a) is True
        with pytest.raises(CrossTenantAccessError):
            iso_mgr.verify_access(res_b, context=ctx_a)

        # Usage tracking
        usage_tracker.record_usage(tenant_a.tenant_id, evaluations=1)
        usage = usage_tracker.get_usage(tenant_a.tenant_id)
        assert usage.evaluations_count == 1

        # 8. API & SDK In-Memory Client Validation
        client = Client(base_url="http://testserver", app=api_app)
        health = client.get_health()
        assert health["status"] == "healthy"
        assert health["version"] == "1.4.0"

        # Submit evaluation through SDK
        sdk_eval = client.evaluations.create(
            input_text="SDK query test",
            output_text="Benign SDK response",
            expected_output="Benign SDK response",
        )
        assert sdk_eval["passed"] is True
        assert sdk_eval["score"] == 1.0

        # Retrieve dashboard via SDK
        sdk_dash = client.dashboard.get()
        assert "health_summary" in sdk_dash
        assert "panels" in sdk_dash

    def test_failure_healing_verification_prediction_policy(self) -> None:
        """Workflow:

        Failure -> Healing -> Verification -> Prediction -> Policy.
        """
        # 1. Failure
        failure = FailureReport(
            failure_id="fail_lat_01",
            trace_id="trace_query_lat",
            category="latency",
            type="latency_breach",
            severity=FailureSeverity.MEDIUM,
            message="Query latency exceeded SLA threshold (4.5s > 2.0s)",
        )
        assert failure.failure_id == "fail_lat_01"

        # 2. Remediation (Self-Healing) Proposal
        proposal = RemediationProposal(
            proposal_id="heal_lat_cache",
            title="Add Semantic Response Caching",
            repair_type=RepairType.CONFIG,
            confidence=0.95,
            state=RemediationLifecycleState.ACTIVE,
        )

        # 3. Verification
        verifier = RemediationVerifier()
        verified = verifier.verify(
            proposal,
            sample_count=20,
            remediation_error_rate=0.01,
            baseline_error_rate=0.05,
        )
        assert verified is True
        assert proposal.state == RemediationLifecycleState.VERIFIED

        # 4. Reliability Prediction with Post-Healing Gains
        pred_engine = ReliabilityPredictionEngine()
        pred_input = PredictionInput(
            target_id="query_engine",
            historical_signals={
                "reliability": [0.85, 0.88, 0.92, 0.95, 0.96],
                "failure_rate": [0.15, 0.12, 0.08, 0.05, 0.04],
            },
            current_metrics={"reliability": 0.96, "failure_rate": 0.04},
        )
        prediction = pred_engine.predict(
            pred_input, horizon=PredictionHorizon.SHORT_TERM
        )
        assert prediction.reliability_forecast.forecasted_value >= 0.90
        assert prediction.risk_forecast.risk_level.value == "LOW"

        # 5. Policy Evaluation passes with post-healing metrics
        policy_engine = PolicyEngine()
        policy_eval = policy_engine.evaluate(
            {
                "reliability_score": prediction.reliability_forecast.forecasted_value,
                "safety_score": 1.0,
                "credential_leakage": False,
                "cross_tenant_access": False,
            }
        )
        assert policy_eval.decision == PolicyDecision.ALLOW

    def test_rag_evaluation_safety_prediction_policy(self) -> None:
        """Workflow:

        RAG -> Evaluation -> Safety -> Prediction -> Policy.
        """
        # 1. RAG Run & Execution
        rag_engine = AdvancedRAGReliabilityEngine()
        doc = RetrievedDocument(
            document_id="doc_auth",
            title="Authorization Guidelines",
            text="Admins have full read/write access to internal tenant databases.",
        )
        chunk = RetrievedChunk(
            chunk_id="chk_01",
            document_id="doc_auth",
            text="Admins have full read/write access to internal tenant databases.",
            retrieval_score=0.92,
        )
        answer = (
            "Admins possess full read and write access to internal tenant databases."
        )

        # 2. RAG Reliability Evaluation
        rag_run = rag_engine.evaluate_run(
            query="What are the access privileges for admin?",
            retrieved_documents=[doc],
            retrieved_chunks=[chunk],
            generated_answer=answer,
        )
        assert rag_run.reliability_score.overall_score >= 0.50

        # 3. Safety Boundary Check on Retrieved Context
        safety_engine = SafetyEngine()
        target = SafetyTarget(target_id="rag_retriever", name="RAG Pipeline")
        campaign = SafetyCampaign(
            target=target,
            categories=[
                SafetyCategory.RETRIEVED_CONTENT_TRUST,
                SafetyCategory.DOCUMENT_TRUST,
            ],
            max_tests=4,
        )
        safety_res = safety_engine.run_campaign(campaign)
        assert safety_res.score.overall_score > 0.70

        # 4. Reliability Prediction
        pred_engine = ReliabilityPredictionEngine()
        pred_input = PredictionInput(
            target_id="rag_pipeline",
            historical_signals={
                "reliability": [0.90, 0.91, 0.92, 0.94],
                "grounding": [0.88, 0.89, 0.91, 0.93],
            },
            current_metrics={"reliability": rag_run.reliability_score.overall_score},
        )
        prediction = pred_engine.predict(pred_input)
        assert prediction.reliability_forecast.forecasted_value >= 0.80

        # 5. Policy Check
        policy_engine = PolicyEngine()
        policy_eval = policy_engine.evaluate(
            {
                "reliability_score": prediction.reliability_forecast.forecasted_value,
                "safety_score": safety_res.score.overall_score,
                "credential_leakage": False,
                "cross_tenant_access": False,
            }
        )
        assert policy_eval.decision == PolicyDecision.ALLOW

    def test_agent_evaluation_safety_prediction_policy(self) -> None:
        """Workflow:

        Agent -> Evaluation -> Safety -> Prediction -> Policy.
        """
        # 1. Agent Run & Trajectory
        agent_engine = AdvancedAgentReliabilityEngine()
        goal = Goal(
            goal_id="goal_calc",
            description="Calculate sum of invoice items",
            criteria=[GoalCriterion(description="calculate sum", is_mandatory=False)],
        )
        task = AgentTask(
            task_id="task_calc",
            request_text="Calculate sum of invoice items",
            goals=[goal],
        )
        steps = [
            AgentStep(
                sequence=1,
                action="call sum_calculator tool",
                action_type=ActionType.TOOL_CALL,
                tool_call=ToolCall(
                    tool_name="sum_calculator", arguments={"items": [10, 20, 30]}
                ),
                tool_result=ToolResult(
                    call_id="c1", tool_name="sum_calculator", output=60
                ),
                observation=Observation(interpreted_content="Calculate sum: 60"),
            ),
            AgentStep(
                sequence=2,
                action="return final response",
                action_type=ActionType.FINAL_RESPONSE,
                observation=Observation(interpreted_content="Completed calculate sum"),
            ),
        ]
        agent_run = AgentRun(
            run_id="run_agent_01",
            task=task,
            trajectory=AgentTrajectory(steps=steps, total_steps=2),
            final_output="Total invoice sum is 60",
            success=True,
        )

        # 2. Agent Evaluation
        evaluated_run = agent_engine.evaluate_run(agent_run)
        assert evaluated_run.reliability_score.overall_score >= 0.70

        # 3. Safety Boundary Check on Agent Tools & Multi-Agent Handoffs
        safety_engine = SafetyEngine()
        target = SafetyTarget(target_id="math_agent", name="Invoice Agent")
        campaign = SafetyCampaign(
            target=target,
            categories=[
                SafetyCategory.TOOL_USE_BOUNDARY,
                SafetyCategory.MULTI_AGENT_BOUNDARY,
            ],
            max_tests=4,
        )
        safety_res = safety_engine.run_campaign(campaign)
        assert safety_res.score.overall_score > 0.70

        # 4. Reliability Prediction
        pred_engine = ReliabilityPredictionEngine()
        pred_input = PredictionInput(
            target_id="math_agent",
            historical_signals={
                "reliability": [0.92, 0.93, 0.95, 0.97],
                "success_rate": [1.0, 1.0, 1.0, 1.0],
            },
            current_metrics={
                "reliability": evaluated_run.reliability_score.overall_score
            },
        )
        prediction = pred_engine.predict(pred_input)
        assert prediction.reliability_forecast.forecasted_value >= 0.85

        # 5. Policy Check
        policy_engine = PolicyEngine()
        policy_eval = policy_engine.evaluate(
            {
                "reliability_score": prediction.reliability_forecast.forecasted_value,
                "safety_score": safety_res.score.overall_score,
                "credential_leakage": False,
                "cross_tenant_access": False,
            }
        )
        assert policy_eval.decision == PolicyDecision.ALLOW
