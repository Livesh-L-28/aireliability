"""Approval manager governing human and automated sign-off for remediation proposals."""

from __future__ import annotations

import hashlib
import hmac
import logging
from uuid import uuid4

from aireliability.remediation.models import (
    ApprovalRecord,
    RemediationLifecycleState,
    RemediationProposal,
)

logger = logging.getLogger(__name__)


class ApprovalManager:
    """Manages explicit approval tokens, reviewer signatures, and rejections."""

    def __init__(self, secret_key: str = "aireliability-remediation-secret") -> None:
        self.secret_key = secret_key.encode("utf-8")

    def generate_token(self, proposal_id: str, approver: str) -> str:
        """Create a verifiable cryptographic HMAC token for an approval action."""
        data = f"{proposal_id}:{approver}:{uuid4().hex[:8]}".encode()
        return hmac.new(self.secret_key, data, hashlib.sha256).hexdigest()[:24]

    def approve(
        self,
        proposal: RemediationProposal,
        approver: str,
        rationale: str = "Approved by operator",
    ) -> ApprovalRecord:
        """Approve a proposal currently pending approval."""
        if proposal.state not in (
            RemediationLifecycleState.NEEDS_APPROVAL,
            RemediationLifecycleState.SIMULATED,
            RemediationLifecycleState.PROPOSED,
        ):
            raise ValueError(
                f"Cannot approve proposal {proposal.proposal_id} in state {proposal.state.value}."
            )

        token = self.generate_token(proposal.proposal_id, approver)
        record = ApprovalRecord(
            approver=approver,
            approved=True,
            approval_token=token,
            rationale=rationale,
        )
        proposal.approval = record
        proposal.record_transition(
            to_state=RemediationLifecycleState.APPROVED,
            actor=approver,
            action="approve",
            reason=rationale,
            metadata={"token": token},
        )
        return record

    def reject(
        self,
        proposal: RemediationProposal,
        approver: str,
        reason: str = "Rejected by operator",
    ) -> ApprovalRecord:
        """Reject a proposed remediation."""
        token = self.generate_token(proposal.proposal_id, approver)
        record = ApprovalRecord(
            approver=approver,
            approved=False,
            approval_token=token,
            rationale=reason,
        )
        proposal.approval = record
        proposal.record_transition(
            to_state=RemediationLifecycleState.REJECTED,
            actor=approver,
            action="reject",
            reason=reason,
            metadata={"token": token},
        )
        return record
