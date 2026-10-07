"""Config repair generator adjusting runtime and inference hyperparameters."""

from __future__ import annotations

from typing import Any

from aireliability.remediation.models import (
    RemediationPatch,
    RemediationRiskTier,
    RepairType,
)
from aireliability.remediation.repairs.base import BaseRepairGenerator


class ConfigRepairer(BaseRepairGenerator):
    """Diagnoses model configuration defects and tunes inference parameters."""

    def __init__(self) -> None:
        super().__init__(RepairType.CONFIG)

    def can_handle(self, evidence: Any) -> bool:
        """Check if failure is related to configuration, temperature, or token limits."""
        text = self._extract_text_content(evidence)
        return any(
            kw in text
            for kw in [
                "config",
                "temperature",
                "max_tokens",
                "truncat",
                "hyperparameter",
                "top_p",
                "variance",
                "determinism",
            ]
        )

    def generate_patches(
        self,
        evidence: Any,
        context: dict[str, Any] | None = None,
    ) -> list[RemediationPatch]:
        """Synthesize inference hyperparameter patches."""
        context = context or {}
        target_component = context.get("target_component", "model_inference_config")
        original_config = context.get(
            "original_config",
            {"temperature": 0.7, "max_tokens": 512, "top_p": 1.0, "timeout": 30},
        )

        error_msg = self._extract_text_content(evidence)

        patches: list[RemediationPatch] = []

        # Strategy 1: Truncation -> Increase max_tokens
        if "truncat" in error_msg or "token" in error_msg or "length" in error_msg:
            current_tokens = original_config.get("max_tokens", 512)
            new_tokens = min(4096, current_tokens * 2)
            patched_config = dict(original_config)
            patched_config["max_tokens"] = new_tokens
            patches.append(
                RemediationPatch(
                    repair_type=self.repair_type,
                    target_component_id=target_component,
                    target_component_type="config",
                    description=f"Increase max_tokens from {current_tokens} to {new_tokens} to prevent response truncation",
                    original_value=original_config,
                    patched_value=patched_config,
                    diff_summary=f"max_tokens: {current_tokens} -> {new_tokens}",
                    parameters={
                        "action": "increase_max_tokens",
                        "max_tokens": new_tokens,
                    },
                )
            )

        # Strategy 2: Variance / Non-determinism -> Lower temperature
        elif (
            "variance" in error_msg
            or "format" in error_msg
            or "determinism" in error_msg
        ):
            current_temp = original_config.get("temperature", 0.7)
            new_temp = 0.1
            patched_config = dict(original_config)
            patched_config["temperature"] = new_temp
            patches.append(
                RemediationPatch(
                    repair_type=self.repair_type,
                    target_component_id=target_component,
                    target_component_type="config",
                    description=f"Lower temperature from {current_temp} to {new_temp} to ensure deterministic outputs",
                    original_value=original_config,
                    patched_value=patched_config,
                    diff_summary=f"temperature: {current_temp} -> {new_temp}",
                    parameters={"action": "lower_temperature", "temperature": new_temp},
                )
            )

        # Strategy 3: General latency/timeout increase
        else:
            current_timeout = original_config.get("timeout", 30)
            new_timeout = current_timeout + 15
            patched_config = dict(original_config)
            patched_config["timeout"] = new_timeout
            patches.append(
                RemediationPatch(
                    repair_type=self.repair_type,
                    target_component_id=target_component,
                    target_component_type="config",
                    description=f"Increase request timeout from {current_timeout}s to {new_timeout}s",
                    original_value=original_config,
                    patched_value=patched_config,
                    diff_summary=f"timeout: {current_timeout}s -> {new_timeout}s",
                    parameters={"action": "increase_timeout", "timeout": new_timeout},
                )
            )

        return patches

    def estimate_risk(self, patches: list[RemediationPatch]) -> RemediationRiskTier:
        return RemediationRiskTier.LOW
