"""Phase 37 Self-Healing Bridge for Phase 40 Advanced Agent Reliability.

Routes agent trajectory failures to Phase 37 RemediationEngine:
- Tool selection failure -> prompt routing / tool description repair
- Tool argument failure -> schema / parameter constraint repair
- Loop / runaway failure -> loop breaker / retry threshold repair
- Goal drift -> system prompt anchor repair
All proposals pass through Phase 37 validation gates and safety controls.
"""

from __future__ import annotations

import logging
from typing import Any

from aireliability.agent.models import AgentFailure, AgentRun
from aireliability.core.models import FailureReport
from aireliability.remediation.engine import RemediationEngine
from aireliability.remediation.models import RemediationProposal

logger = logging.getLogger(__name__)


class AgentHealingBridge:
    """Connects agent trajectory failures to Phase 37 Self-Healing RemediationEngine."""

    def __init__(self, engine: RemediationEngine | None = None) -> None:
        self.engine = engine or RemediationEngine()

    def propose_agent_remediations(
        self,
        failures: list[AgentFailure],
        run: AgentRun | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[RemediationProposal]:
        """Generate Phase 37 remediation proposals for diagnosed agent failures."""
        proposals: list[RemediationProposal] = []
        ctx = context or {}

        for failure in failures:
            cat_str = failure.stage.value
            rem_cat = "prompt"
            if cat_str in (
                "tool_selection",
                "tool_arguments",
                "tool_execution",
            ) or cat_str in ("loop", "retry", "runaway"):
                rem_cat = "configuration"
            elif cat_str in ("security", "safety"):
                rem_cat = "safety"
            else:
                rem_cat = "prompt"

            target_comp = failure.affected_component or (
                run.agent_id if run else "agent_core"
            )

            fail_report = FailureReport(
                failure_id=failure.failure_id,
                trace_id=run.run_id if run else failure.failure_id,
                category=rem_cat,
                type=failure.category.value,
                message=failure.message,
                metadata={
                    "affected_component": target_comp,
                    "task": run.task.request_text if run else "",
                },
            )

            repair_ctx = dict(ctx)
            repair_ctx.setdefault("target_component", target_comp)

            proposal = self.engine.diagnose_and_plan(
                evidence=fail_report,
                context=repair_ctx,
            )
            if proposal is not None:
                proposals.append(proposal)

        return proposals
