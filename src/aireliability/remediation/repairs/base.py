"""Base class and protocol for remediation repair generators."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from aireliability.core.models import FailureReport
from aireliability.diagnosis.models import RootCauseReport
from aireliability.intelligence.models import (
    FailureCluster,
    FailurePattern,
    ReliabilityRecommendation,
)
from aireliability.observability.incidents import IncidentRecord
from aireliability.remediation.models import (
    RemediationPatch,
    RemediationProposal,
    RemediationProvenance,
    RemediationRiskTier,
    RepairType,
)


class BaseRepairGenerator(ABC):
    """Abstract base generator producing domain-specific remediation patches."""

    def __init__(self, repair_type: RepairType) -> None:
        self.repair_type = repair_type

    def _extract_text_content(self, evidence: Any) -> str:
        """Extract searchable textual content across any evidence model."""
        texts: list[str] = []
        if isinstance(evidence, FailureReport):
            if evidence.message:
                texts.append(evidence.message)
            if evidence.category:
                texts.append(evidence.category)
            if evidence.type:
                texts.append(evidence.type)
            if "root_cause" in evidence.metadata:
                texts.append(str(evidence.metadata["root_cause"]))
        elif isinstance(evidence, dict):
            texts.extend(str(v) for v in evidence.values())
        else:
            for attr in (
                "title",
                "description",
                "suggested_action",
                "name",
                "error_message",
                "message",
                "rationale",
                "summary",
            ):
                val = getattr(evidence, attr, None)
                if val:
                    texts.append(str(val))
        if not texts:
            texts.append(str(evidence))
        return " ".join(texts).lower()

    @abstractmethod
    def can_handle(self, evidence: Any) -> bool:
        """Determine if this repair generator can formulate fixes for the given evidence."""
        ...

    @abstractmethod
    def generate_patches(
        self,
        evidence: Any,
        context: dict[str, Any] | None = None,
    ) -> list[RemediationPatch]:
        """Generate concrete configuration/code patches addressing the diagnosed failure."""
        ...

    def estimate_risk(self, patches: list[RemediationPatch]) -> RemediationRiskTier:
        """Estimate the operational risk tier of applying these patches."""
        if not patches:
            return RemediationRiskTier.LOW
        # By default, prompt and config changes are LOW, tools/agents MEDIUM, safety HIGH
        if self.repair_type in (RepairType.PROMPT, RepairType.CONFIG):
            return RemediationRiskTier.LOW
        if self.repair_type in (
            RepairType.RETRIEVAL,
            RepairType.TOOL,
            RepairType.AGENT,
        ):
            return RemediationRiskTier.MEDIUM
        if self.repair_type == RepairType.SAFETY:
            return RemediationRiskTier.HIGH
        return RemediationRiskTier.MEDIUM

    def extract_provenance(self, evidence: Any) -> RemediationProvenance:
        """Extract provenance tracking links from the input evidence object."""
        provenance = RemediationProvenance()
        if isinstance(evidence, FailureReport):
            return RemediationProvenance(
                source_failure_id=evidence.failure_id,
                source_trace_id=evidence.trace_id,
            )
        if isinstance(evidence, RootCauseReport):
            return RemediationProvenance(
                source_root_cause_id=evidence.report_id,
                source_failure_id=evidence.failure_id,
            )
        if isinstance(evidence, IncidentRecord):
            return RemediationProvenance(
                source_incident_id=evidence.incident_id,
            )
        if isinstance(evidence, FailureCluster):
            return RemediationProvenance(
                source_cluster_id=evidence.cluster_id,
            )
        if isinstance(evidence, FailurePattern):
            return RemediationProvenance(
                source_pattern_id=evidence.pattern_id,
            )
        if isinstance(evidence, ReliabilityRecommendation):
            return RemediationProvenance(
                source_recommendation_id=evidence.recommendation_id,
            )
        if isinstance(evidence, dict):
            return RemediationProvenance(
                source_failure_id=evidence.get("failure_id"),
                source_root_cause_id=evidence.get("root_cause_id"),
                source_incident_id=evidence.get("incident_id"),
                source_cluster_id=evidence.get("cluster_id"),
                source_graph_node_id=evidence.get("graph_node_id"),
            )
        return provenance

    def generate_proposal(
        self,
        evidence: Any,
        context: dict[str, Any] | None = None,
    ) -> RemediationProposal:
        """Generate a complete RemediationProposal from evidence."""
        context = context or {}
        patches = self.generate_patches(evidence, context)
        risk_tier = self.estimate_risk(patches)
        provenance = self.extract_provenance(evidence)

        title = context.get(
            "title",
            f"Remediation: {self.repair_type.value.replace('_', ' ').title()} for issue",
        )
        description = context.get(
            "description",
            f"Automated self-healing patch generated by {self.__class__.__name__}",
        )

        return RemediationProposal(
            title=title,
            description=description,
            repair_type=self.repair_type,
            risk_tier=risk_tier,
            patches=patches,
            provenance=provenance,
            confidence=context.get("confidence", 0.95),
            tags=[self.repair_type.value, f"risk:{risk_tier.value}"],
            metadata=dict(context),
        )
