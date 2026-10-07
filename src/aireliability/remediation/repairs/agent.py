"""Agent repair generator fixing trajectory loops, step limits, and planning recovery."""

from __future__ import annotations

from typing import Any

from aireliability.remediation.models import (
    RemediationPatch,
    RemediationRiskTier,
    RepairType,
)
from aireliability.remediation.repairs.base import BaseRepairGenerator


class AgentRepairer(BaseRepairGenerator):
    """Diagnoses agent trajectory failures and synthesizes agent runtime guardrails."""

    def __init__(self) -> None:
        super().__init__(RepairType.AGENT)

    def can_handle(self, evidence: Any) -> bool:
        """Check if failure is related to agent loops, trajectory, or execution limits."""
        text = self._extract_text_content(evidence)
        return any(
            kw in text
            for kw in [
                "agent",
                "trajectory",
                "loop",
                "recursion",
                "max_steps",
                "cycle",
                "stuck",
            ]
        )

    def generate_patches(
        self,
        evidence: Any,
        context: dict[str, Any] | None = None,
    ) -> list[RemediationPatch]:
        """Synthesize agent execution bounds and loop breaker patches."""
        context = context or {}
        target_component = context.get("target_component", "default_agent")
        original_agent_config = context.get(
            "original_agent_config",
            {"max_steps": 25, "detect_loops": False, "recovery_strategy": "fail_fast"},
        )

        error_msg = self._extract_text_content(evidence)

        patches: list[RemediationPatch] = []

        # Strategy 1: Loop or cycle detected -> Enable loop breaker and bound max steps
        if "loop" in error_msg or "cycle" in error_msg or "stuck" in error_msg:
            patched_config = dict(original_agent_config)
            patched_config["detect_loops"] = True
            patched_config["max_repeated_calls"] = 2
            patched_config["max_steps"] = min(
                original_agent_config.get("max_steps", 25), 10
            )
            patches.append(
                RemediationPatch(
                    repair_type=self.repair_type,
                    target_component_id=target_component,
                    target_component_type="agent",
                    description="Enable deterministic loop detector and cap maximum execution steps to 10",
                    original_value=original_agent_config,
                    patched_value=patched_config,
                    diff_summary="detect_loops: True, max_repeated_calls: 2, max_steps: 10",
                    parameters={"action": "enable_loop_breaker", "max_steps": 10},
                )
            )

        # Strategy 2: Recovery / Plan deviation
        else:
            patched_config = dict(original_agent_config)
            patched_config["recovery_strategy"] = "replan_and_retry"
            patched_config["max_replan_attempts"] = 2
            patches.append(
                RemediationPatch(
                    repair_type=self.repair_type,
                    target_component_id=target_component,
                    target_component_type="agent",
                    description="Configure agent replan and recovery strategy upon tool or action failure",
                    original_value=original_agent_config,
                    patched_value=patched_config,
                    diff_summary="recovery_strategy: replan_and_retry, max_replan_attempts: 2",
                    parameters={"action": "enable_agent_recovery"},
                )
            )

        return patches

    def estimate_risk(self, patches: list[RemediationPatch]) -> RemediationRiskTier:
        return RemediationRiskTier.MEDIUM
