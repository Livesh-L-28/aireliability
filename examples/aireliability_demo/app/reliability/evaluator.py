"""Reliability Evaluator orchestrating RAG, Agent, and Safety evaluation engines."""

from __future__ import annotations

from typing import Any

from aireliability.agent.engine import AdvancedAgentReliabilityEngine
from aireliability.agent.models import AgentEvaluationResult, AgentRun
from aireliability.rag.engine import AdvancedRAGReliabilityEngine
from aireliability.rag.models import RAGEvaluationResult, RAGRun
from aireliability.safety.engine import SafetyEngine
from aireliability.safety.models import (
    SafetyCampaign,
    SafetyCampaignResult,
    SafetyTarget,
)


class DemoReliabilityEvaluator:
    """Unified evaluator integrating Phase 39 (RAG), Phase 40 (Agent), and Phase 41 (Safety)."""

    def __init__(self) -> None:
        self.rag_engine = AdvancedRAGReliabilityEngine()
        self.agent_engine = AdvancedAgentReliabilityEngine()
        self.safety_engine = SafetyEngine()

    def evaluate_rag(
        self,
        query: str,
        retrieved_documents: list[Any],
        retrieved_chunks: list[Any],
        generated_answer: str,
        expected_document_ids: list[str] | None = None,
    ) -> RAGRun:
        """Evaluate a single RAG execution across all 11 stages."""
        return self.rag_engine.evaluate_run(
            query=query,
            retrieved_documents=retrieved_documents,
            retrieved_chunks=retrieved_chunks,
            generated_answer=generated_answer,
            expected_document_ids=expected_document_ids,
        )

    def evaluate_rag_batch(
        self, test_cases: list[dict[str, Any]]
    ) -> RAGEvaluationResult:
        """Batch evaluate RAG test cases into aggregate RAGEvaluationResult."""
        return self.rag_engine.evaluate_batch(test_cases)

    def evaluate_agent(self, agent_run: AgentRun) -> AgentRun:
        """Audit an autonomous agent execution trajectory."""
        return self.agent_engine.evaluate_run(agent_run)

    def evaluate_agent_batch(self, runs: list[AgentRun]) -> AgentEvaluationResult:
        """Batch audit agent trajectories into aggregate AgentEvaluationResult."""
        return self.agent_engine.evaluate_batch(runs)

    def evaluate_safety(
        self, target_id: str = "demo_system", max_tests: int = 4
    ) -> SafetyCampaignResult:
        """Execute automated adversarial safety testing campaign."""
        target = SafetyTarget(target_id=target_id)
        campaign = SafetyCampaign(target=target, max_tests=max_tests)
        return self.safety_engine.run_campaign(campaign)
