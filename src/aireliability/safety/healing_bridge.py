"""Self-Healing Remediation Bridge for AI Safety Validation (Phase 41 -> Phase 37)."""

from __future__ import annotations

import logging
from typing import Any

from aireliability.core.models import FailureReport
from aireliability.remediation.engine import RemediationEngine
from aireliability.remediation.models import RemediationProposal
from aireliability.safety.models import SafetyFinding, SafetyVerdict

logger = logging.getLogger(__name__)


class SafetyHealingBridge:
    """Connects safety validation findings to Phase 37 RemediationEngine."""

    def __init__(self, engine: RemediationEngine | None = None) -> None:
        self.engine = engine or RemediationEngine()

    def propose_safety_remediations(
        self,
        findings: list[SafetyFinding],
        context: dict[str, Any] | None = None,
    ) -> list[RemediationProposal]:
        """Formulate remediation proposals for confirmed safety findings."""
        proposals: list[RemediationProposal] = []
        ctx = context or {}

        for f in findings:
            if f.verdict != SafetyVerdict.UNSAFE:
                continue

            fail_report = FailureReport(
                failure_id=f.finding_id,
                trace_id=f.test_id,
                run_id=f.test_id,
                test_case_id=f.test_id,
                category=f.category.value,
                error_message=f.message,
                details={"evidence": [e.description for e in f.evidence]},
            )

            try:
                proposal = self.engine.diagnose_and_plan(
                    evidence={
                        "failure_report": fail_report,
                        "risk": f.risk_dimension.value,
                    },
                    target_component=f"safety_guardrail_{f.category.value.lower()}",
                    context=ctx,
                )
                if proposal:
                    proposals.append(proposal)
            except Exception as exc:
                logger.debug(
                    "Remediation proposal synthesis skipped for %s: %s",
                    f.finding_id,
                    exc,
                )

        return proposals
