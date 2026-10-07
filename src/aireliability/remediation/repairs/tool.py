"""Tool repair generator fixing tool schemas, retry parameters, and fallback tools."""

from __future__ import annotations

from typing import Any

from aireliability.remediation.models import (
    RemediationPatch,
    RemediationRiskTier,
    RepairType,
)
from aireliability.remediation.repairs.base import BaseRepairGenerator


class ToolRepairer(BaseRepairGenerator):
    """Diagnoses tool invocation failures and synthesizes tool definition patches."""

    def __init__(self) -> None:
        super().__init__(RepairType.TOOL)

    def can_handle(self, evidence: Any) -> bool:
        """Check if failure is related to tool definitions or tool call execution."""
        text = self._extract_text_content(evidence)
        return any(
            kw in text
            for kw in [
                "tool",
                "argument",
                "parameter",
                "invocation",
                "function_call",
                "schema_validation",
            ]
        )

    def generate_patches(
        self,
        evidence: Any,
        context: dict[str, Any] | None = None,
    ) -> list[RemediationPatch]:
        """Synthesize tool parameter, retry, or fallback patches."""
        context = context or {}
        target_component = context.get("target_component", "default_tool")
        original_tool_spec = context.get(
            "original_tool_spec",
            {
                "name": target_component,
                "timeout_seconds": 5,
                "retry_count": 0,
                "fallback_tool": None,
                "schema": {"type": "object", "properties": {}},
            },
        )

        error_msg = self._extract_text_content(evidence)

        patches: list[RemediationPatch] = []

        # Strategy 1: Timeout / network error -> Add retry backoff and increase timeout
        if (
            "timeout" in error_msg
            or "network" in error_msg
            or "connection" in error_msg
        ):
            patched_spec = dict(original_tool_spec)
            patched_spec["timeout_seconds"] = max(
                15, original_tool_spec.get("timeout_seconds", 5) * 3
            )
            patched_spec["retry_count"] = 3
            patched_spec["retry_backoff_factor"] = 1.5
            patches.append(
                RemediationPatch(
                    repair_type=self.repair_type,
                    target_component_id=target_component,
                    target_component_type="tool",
                    description="Increase tool timeout and add exponential retry policy",
                    original_value=original_tool_spec,
                    patched_value=patched_spec,
                    diff_summary="timeout: 5s -> 15s, retry_count: 0 -> 3",
                    parameters={
                        "action": "add_retry_policy",
                        "timeout_seconds": 15,
                        "retry_count": 3,
                    },
                )
            )

        # Strategy 2: Missing argument / parameter validation error
        elif (
            "missing" in error_msg or "argument" in error_msg or "required" in error_msg
        ):
            patched_spec = dict(original_tool_spec)
            patched_spec["allow_default_arguments"] = True
            patched_spec["sanitize_arguments"] = True
            patches.append(
                RemediationPatch(
                    repair_type=self.repair_type,
                    target_component_id=target_component,
                    target_component_type="tool",
                    description="Enable parameter defaults and input sanitization to prevent missing argument errors",
                    original_value=original_tool_spec,
                    patched_value=patched_spec,
                    diff_summary="allow_default_arguments: True, sanitize_arguments: True",
                    parameters={"action": "add_argument_fallbacks"},
                )
            )

        # Strategy 3: Fallback tool assignment
        else:
            patched_spec = dict(original_tool_spec)
            patched_spec["fallback_tool"] = f"{target_component}_fallback"
            patches.append(
                RemediationPatch(
                    repair_type=self.repair_type,
                    target_component_id=target_component,
                    target_component_type="tool",
                    description=f"Configure safe fallback tool {target_component}_fallback upon failure",
                    original_value=original_tool_spec,
                    patched_value=patched_spec,
                    diff_summary=f"fallback_tool: {target_component}_fallback",
                    parameters={"action": "configure_fallback_tool"},
                )
            )

        return patches

    def estimate_risk(self, patches: list[RemediationPatch]) -> RemediationRiskTier:
        return RemediationRiskTier.MEDIUM
