"""Prompt repair generator producing targeted prompt modifications."""

from __future__ import annotations

from typing import Any

from aireliability.remediation.models import (
    RemediationPatch,
    RemediationRiskTier,
    RepairType,
)
from aireliability.remediation.repairs.base import BaseRepairGenerator


class PromptRepairer(BaseRepairGenerator):
    """Diagnoses prompt weaknesses and synthesizes prompt template repairs."""

    def __init__(self) -> None:
        super().__init__(RepairType.PROMPT)

    def can_handle(self, evidence: Any) -> bool:
        """Check if failure is related to prompt or output formatting."""
        text = self._extract_text_content(evidence)
        return any(
            kw in text
            for kw in [
                "prompt",
                "format",
                "instruction",
                "schema",
                "hallucination",
                "parsing",
            ]
        )

    def generate_patches(
        self,
        evidence: Any,
        context: dict[str, Any] | None = None,
    ) -> list[RemediationPatch]:
        """Synthesize concrete prompt patch instructions."""
        context = context or {}
        target_component = context.get("target_component", "system_prompt")
        original_prompt = context.get(
            "original_prompt",
            "You are a helpful AI assistant. Answer user queries accurately.",
        )

        error_msg = self._extract_text_content(evidence)

        patches: list[RemediationPatch] = []

        # Strategy 1: JSON / Formatting failure repair
        if "json" in error_msg or "format" in error_msg or "schema" in error_msg:
            constraint = (
                "\n\nCRITICAL OUTPUT FORMAT INSTRUCTION:\n"
                "You must strictly output valid JSON. Do not include introductory text, "
                "markdown formatting like ```json, or explanations outside the JSON object."
            )
            patched_prompt = original_prompt + constraint
            patches.append(
                RemediationPatch(
                    repair_type=self.repair_type,
                    target_component_id=target_component,
                    target_component_type="prompt",
                    description="Enforce strict valid JSON output formatting constraints",
                    original_value=original_prompt,
                    patched_value=patched_prompt,
                    diff_summary="+ Add strict JSON format instruction to system prompt",
                    parameters={
                        "action": "append_instruction",
                        "added_constraint": constraint,
                    },
                )
            )

        # Strategy 2: Hallucination / Grounding failure repair
        elif (
            "hallucin" in error_msg
            or "ground" in error_msg
            or "unsupported" in error_msg
        ):
            constraint = (
                "\n\nGROUNDING AND FACTUALITY CONSTRAINT:\n"
                "Rely strictly on provided context documents. If the requested information is not "
                'explicitly stated in the context, respond: "I do not have sufficient information to answer."'
            )
            patched_prompt = original_prompt + constraint
            patches.append(
                RemediationPatch(
                    repair_type=self.repair_type,
                    target_component_id=target_component,
                    target_component_type="prompt",
                    description="Enforce factuality and refusal constraint when context is missing",
                    original_value=original_prompt,
                    patched_value=patched_prompt,
                    diff_summary="+ Add factuality and refusal constraint",
                    parameters={
                        "action": "append_instruction",
                        "added_constraint": constraint,
                    },
                )
            )

        # Strategy 3: General instruction adherence repair
        else:
            clarification = (
                "\n\nINSTRUCTION CLARIFICATION:\n"
                "Follow all steps systematically. Verify assumptions before producing final answer."
            )
            patched_prompt = original_prompt + clarification
            patches.append(
                RemediationPatch(
                    repair_type=self.repair_type,
                    target_component_id=target_component,
                    target_component_type="prompt",
                    description="Add step-by-step reasoning guidance to improve instruction compliance",
                    original_value=original_prompt,
                    patched_value=patched_prompt,
                    diff_summary="+ Add systematic step-by-step instruction",
                    parameters={
                        "action": "append_instruction",
                        "added_constraint": clarification,
                    },
                )
            )

        return patches

    def estimate_risk(self, patches: list[RemediationPatch]) -> RemediationRiskTier:
        return RemediationRiskTier.LOW
