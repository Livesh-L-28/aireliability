"""Phase 39 RAG + Agent Cross-System Integration Bridge for Phase 40.

Provides cross-system failure attribution when an autonomous agent invokes RAG tools
or uses RAG pipelines as long-term external memory:
Preserves precise subsystem boundaries and causal provenance:
- AGENT_TOOL_SELECTION_FAILURE: Agent picked wrong retrieval tool or passed invalid query.
- RAG_RETRIEVAL_FAILURE: RAG index returned irrelevant chunks or missed evidence.
- RAG_GROUNDING_FAILURE: RAG synthesis hallucinated facts unsupported by retrieved context.
- MEMORY_RETRIEVAL_FAILURE: Agent memory store failed to retrieve stored episodic memory.
"""

from __future__ import annotations

import logging

from aireliability.agent.models import (
    AgentFailure,
    AgentFailureCategory,
    AgentStage,
    AgentStep,
)
from aireliability.core.models import FailureSeverity
from aireliability.rag.models import RAGFailure, RAGRun

logger = logging.getLogger(__name__)


class AgentRAGBridge:
    """Attributes failures accurately across Agent trajectory and RAG subsystem boundaries."""

    def attribute_rag_tool_failure(
        self,
        step: AgentStep,
        rag_run: RAGRun | None = None,
        rag_failures: list[RAGFailure] | None = None,
    ) -> list[AgentFailure]:
        """Disambiguate whether a failure originated in the Agent tool selection or the RAG pipeline."""
        attributed: list[AgentFailure] = []

        # 1. Did the agent pass invalid query arguments to the RAG tool?
        if step.tool_call and step.tool_call.tool_name.lower() in (
            "rag_tool",
            "retriever",
            "search_kb",
        ):
            query_arg = step.tool_call.arguments.get("query", "")
            if not query_arg or len(str(query_arg).strip()) < 3:
                attributed.append(
                    AgentFailure(
                        stage=AgentStage.TOOL_ARGUMENTS,
                        category=AgentFailureCategory.MISSING_ARGUMENT,
                        severity=FailureSeverity.HIGH,
                        message="Agent invoked RAG tool with empty or malformed query string",
                        affected_component=step.tool_call.tool_name,
                        step_index=step.sequence,
                        confidence=0.96,
                    )
                )
                return attributed

        # 2. Check internal RAG failures from Phase 39 evaluation
        all_rag_fails = list(rag_failures or [])
        if rag_run and rag_run.failures:
            all_rag_fails.extend(rag_run.failures)

        for rf in all_rag_fails:
            stage_name = rf.stage.value
            if stage_name in ("retrieval", "ranking", "reranking"):
                attributed.append(
                    AgentFailure(
                        stage=AgentStage.TOOL_EXECUTION,
                        category=AgentFailureCategory.TOOL_ERROR,
                        severity=FailureSeverity.HIGH,
                        message=f"RAG Subsystem Retrieval Failure: {rf.message}",
                        affected_component=rf.affected_component or "rag_pipeline",
                        step_index=step.sequence,
                        confidence=0.94,
                        metadata={
                            "subsystem": "rag",
                            "rag_stage": stage_name,
                            "rag_failure_id": rf.failure_id,
                        },
                    )
                )
            elif stage_name in ("grounding", "faithfulness", "citation"):
                attributed.append(
                    AgentFailure(
                        stage=AgentStage.OBSERVATION,
                        category=AgentFailureCategory.OBSERVATION_FAILURE,
                        severity=FailureSeverity.HIGH,
                        message=f"RAG Subsystem Grounding Defect: {rf.message}",
                        affected_component="rag_generator",
                        step_index=step.sequence,
                        confidence=0.92,
                        metadata={"subsystem": "rag", "rag_stage": stage_name},
                    )
                )

        return attributed

    def attribute_memory_vs_rag(
        self,
        memory_key: str,
        operation: str,
        error_message: str = "",
        is_rag_backed: bool = False,
    ) -> AgentFailure:
        """Distinguish whether a memory retrieval defect belongs to the Agent Memory or RAG subsystem."""
        if is_rag_backed:
            return AgentFailure(
                stage=AgentStage.TOOL_EXECUTION,
                category=AgentFailureCategory.TOOL_ERROR,
                severity=FailureSeverity.MEDIUM,
                message=f"RAG-backed memory retrieval failed for key '{memory_key}': {error_message}",
                affected_component="rag_memory_store",
                confidence=0.88,
                metadata={"subsystem": "rag_memory"},
            )
        else:
            return AgentFailure(
                stage=AgentStage.MEMORY,
                category=AgentFailureCategory.MEMORY_MISS,
                severity=FailureSeverity.MEDIUM,
                message=f"Agent internal memory miss on key '{memory_key}': {error_message}",
                affected_component=f"memory_key_{memory_key}",
                confidence=0.92,
                metadata={"subsystem": "agent_memory"},
            )
