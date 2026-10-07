"""Phase 37 Self-Healing Bridge routing RAG failures into remediation proposals and repair strategies."""

from __future__ import annotations

import logging
from typing import Any

from aireliability.core.models import FailureReport
from aireliability.rag.models import RAGFailure, RAGRun
from aireliability.remediation.engine import RemediationEngine
from aireliability.remediation.models import RemediationProposal

logger = logging.getLogger(__name__)


class RAGHealingBridge:
    """Connects RAG failures to Phase 37 Self-Healing Engine to propose targeted repairs."""

    def __init__(self, engine: RemediationEngine | None = None) -> None:
        self.engine = engine or RemediationEngine()

    def propose_remediations(
        self,
        failures: list[RAGFailure],
        run: RAGRun | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[RemediationProposal]:
        """Propose Phase 37 remediation proposals for a list of diagnosed RAG failures."""
        proposals: list[RemediationProposal] = []
        ctx = context or {}

        for failure in failures:
            cat_str = failure.stage.value
            rem_cat = "retrieval"
            if cat_str in ("retrieval", "ranking", "reranking"):
                rem_cat = "retrieval"
            elif cat_str in ("grounding", "faithfulness", "citation"):
                rem_cat = "prompt"
            elif cat_str in ("context", "security"):
                rem_cat = "safety"

            target_comp = failure.affected_component or (
                run.retriever_name if run else "retriever"
            )
            fail_report = FailureReport(
                failure_id=failure.failure_id,
                trace_id=run.run_id if run else failure.failure_id,
                category=rem_cat,
                type=failure.category.value,
                message=failure.message,
                metadata={
                    "affected_component": target_comp,
                    "query": run.query.text if run else "",
                },
            )

            repair_ctx = dict(ctx)
            repair_ctx.setdefault("target_component", target_comp)

            proposal = self.engine.diagnose_and_plan(
                evidence=fail_report,
                context=repair_ctx,
            )
            if proposal:
                proposals.append(proposal)

        return proposals

    def propose_rag_healing(
        self,
        run: RAGRun,
        failure: RAGFailure,
        context: dict[str, Any] | None = None,
    ) -> RemediationProposal:
        """Transform a diagnosed RAG failure into a Phase 37 RemediationProposal."""
        proposals = self.propose_remediations([failure], run=run, context=context)
        return proposals[0]
