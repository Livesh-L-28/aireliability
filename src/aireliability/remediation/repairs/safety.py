"""Safety repair generator injecting guardrails, sanitization rules, and injection barriers."""

from __future__ import annotations

from typing import Any

from aireliability.remediation.models import (
    RemediationPatch,
    RemediationRiskTier,
    RepairType,
)
from aireliability.remediation.repairs.base import BaseRepairGenerator


class SafetyRepairer(BaseRepairGenerator):
    """Diagnoses safety and security vulnerabilities and injects strict guardrails."""

    def __init__(self) -> None:
        super().__init__(RepairType.SAFETY)

    def can_handle(self, evidence: Any) -> bool:
        """Check if failure is related to safety, security, PII, or prompt injection."""
        text = self._extract_text_content(evidence)
        return any(
            kw in text
            for kw in [
                "safety",
                "security",
                "pii",
                "secret",
                "injection",
                "jailbreak",
                "leak",
                "toxic",
            ]
        )

    def generate_patches(
        self,
        evidence: Any,
        context: dict[str, Any] | None = None,
    ) -> list[RemediationPatch]:
        """Synthesize safety guardrail and redaction patches."""
        context = context or {}
        target_component = context.get("target_component", "safety_guardrail")
        original_policy = context.get(
            "original_safety_policy",
            {
                "redact_pii": False,
                "block_injection_signatures": False,
                "sanitization_patterns": [],
            },
        )

        error_msg = self._extract_text_content(evidence)

        patches: list[RemediationPatch] = []

        # Strategy 1: Secret / PII Leakage -> Enforce redaction rules
        if "leak" in error_msg or "secret" in error_msg or "pii" in error_msg:
            patched_policy = dict(original_policy)
            patched_policy["redact_pii"] = True
            patched_policy["redact_secrets"] = True
            patched_policy["sanitization_patterns"] = list(
                original_policy.get("sanitization_patterns", [])
            ) + [
                r"(?i)(api[_-]?key|secret|token|bearer)\s*[:=]\s*['\"]?[\w\-]{8,}['\"]?",
                r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            ]
            patches.append(
                RemediationPatch(
                    repair_type=self.repair_type,
                    target_component_id=target_component,
                    target_component_type="safety",
                    description="Activate PII and credential sanitization regex filters",
                    original_value=original_policy,
                    patched_value=patched_policy,
                    diff_summary="+ Add PII and secret redaction filters",
                    parameters={"action": "enable_sanitization", "redact_pii": True},
                )
            )

        # Strategy 2: Prompt injection / Jailbreak -> Enable injection defense barrier
        else:
            patched_policy = dict(original_policy)
            patched_policy["block_injection_signatures"] = True
            patched_policy["strict_safety_evaluator"] = True
            patches.append(
                RemediationPatch(
                    repair_type=self.repair_type,
                    target_component_id=target_component,
                    target_component_type="safety",
                    description="Enable strict prompt injection signature detection and input guardrail",
                    original_value=original_policy,
                    patched_value=patched_policy,
                    diff_summary="block_injection_signatures: True, strict_safety_evaluator: True",
                    parameters={"action": "enable_injection_guardrail"},
                )
            )

        return patches

    def estimate_risk(self, patches: list[RemediationPatch]) -> RemediationRiskTier:
        return RemediationRiskTier.HIGH
