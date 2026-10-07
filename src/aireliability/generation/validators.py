"""Comprehensive schema, semantic, and safety validation for generated AI tests."""

from __future__ import annotations

import re

from aireliability.generation.fingerprint import compute_fingerprint
from aireliability.generation.models import (
    GeneratedTest,
    TestGenerationStatus,
    TestRiskLevel,
)
from aireliability.telemetry.sanitizer import SanitizationPolicy

_SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),
    re.compile(r"bearer\s+[a-zA-Z0-9_\-\.]{20,}", re.IGNORECASE),
    re.compile(r"ghp_[a-zA-Z0-9]{20,}", re.IGNORECASE),
    re.compile(r"-----BEGIN\s+PRIVATE\s+KEY-----", re.IGNORECASE),
    re.compile(r"password\s*=\s*['\"][^'\"]{6,}['\"]", re.IGNORECASE),
]


class TestValidator:
    """Validates generated test candidates for schema integrity, semantic validity, and safety."""

    def __init__(
        self,
        sanitizer: SanitizationPolicy | None = None,
        enforce_safety: bool = True,
        review_high_risk: bool = False,
    ) -> None:
        self.sanitizer = sanitizer or SanitizationPolicy()
        self.enforce_safety = enforce_safety
        self.review_high_risk = review_high_risk

    def validate(self, test: GeneratedTest) -> GeneratedTest:
        """Validate a generated test candidate and transition its lifecycle state."""
        errors: list[str] = []
        review_reasons: list[str] = []

        # 1. Identifier and naming
        if not test.test_id or not test.test_id.strip():
            errors.append("Test ID cannot be empty.")
        if not test.name or not test.name.strip():
            errors.append("Test name cannot be empty.")

        # 2. Input presence
        # None input is only allowed for edge-case tests specifically testing null inputs
        if (
            test.input is None
            and "null_input" not in test.tags
            and "edge_case" not in test.tags
        ):
            errors.append(
                "Test input is None without explicit edge_case/null_input tag."
            )

        # 3. Provenance presence
        if not test.provenance:
            errors.append("Test provenance is missing.")
        else:
            if not test.provenance.source_id or not test.provenance.source_id.strip():
                errors.append("Provenance source_id cannot be empty.")
            if not test.provenance.source_type:
                errors.append("Provenance source_type cannot be empty.")

        # 4. Expectations and criteria validity
        has_evaluable_target = (
            test.expected_output is not None
            or bool(test.expected_criteria)
            or bool(test.expected_tool_calls)
            or bool(test.expected_trajectory_constraints)
            or test.reference_answer is not None
        )
        if not has_evaluable_target:
            errors.append(
                "Test has no verifiable assertions: expected_output, expected_criteria, "
                "expected_tool_calls, and reference_answer are all empty."
            )

        # Ground truth integrity
        if test.reference_answer is not None and not test.has_ground_truth:
            review_reasons.append(
                "Reference answer present but has_ground_truth flag was False."
            )

        # Conflicting criteria check
        if test.expected_criteria:
            criteria_lower = [c.lower().strip() for c in test.expected_criteria]
            for c in criteria_lower:
                negated = f"not {c}"
                opposite = c.replace("must", "must not") if "must" in c else ""
                if negated in criteria_lower or (
                    opposite and opposite in criteria_lower
                ):
                    errors.append(
                        f"Conflicting criteria detected: '{c}' has opposing constraint."
                    )

        # 5. Tool definition validity
        if test.tool_definitions:
            for idx, tool in enumerate(test.tool_definitions):
                if not isinstance(tool, dict):
                    errors.append(
                        f"Tool definition at index {idx} must be a dictionary."
                    )
                elif "name" not in tool and "type" not in tool:
                    errors.append(
                        f"Tool definition at index {idx} lacks 'name' or 'type'."
                    )

        # 6. Expected tool calls validity
        if test.expected_tool_calls:
            for idx, tc in enumerate(test.expected_tool_calls):
                if not isinstance(tc, dict):
                    errors.append(
                        f"Expected tool call at index {idx} must be a dictionary."
                    )
                elif "name" not in tc:
                    errors.append(f"Expected tool call at index {idx} lacks 'name'.")

        # 7. Safety & Credentials Audit
        if self.enforce_safety:
            input_str = str(test.input)
            context_str = str(test.context or "")
            combined_text = f"{input_str} {context_str}"
            for pattern in _SECRET_PATTERNS:
                if pattern.search(combined_text):
                    errors.append(
                        "Unredacted credential or secret pattern detected in test content."
                    )
                    break

        # 8. High-risk review gate
        if self.review_high_risk and test.risk_level in (
            TestRiskLevel.HIGH,
            TestRiskLevel.CRITICAL,
        ):
            review_reasons.append(
                f"Test is classified as {test.risk_level.value} risk."
            )

        if not test.has_ground_truth and not test.expected_criteria:
            review_reasons.append("Missing ground truth and lacks formal criteria.")

        # 9. Compute / verify fingerprint
        computed_fp = compute_fingerprint(test)
        updated_test = test.model_copy(update={"fingerprint": computed_fp})

        # Lifecycle state resolution
        if errors:
            all_reasons = errors + review_reasons
            return updated_test.model_copy(
                update={
                    "status": TestGenerationStatus.REJECTED,
                    "validation_reasons": all_reasons,
                }
            )
        elif review_reasons:
            return updated_test.model_copy(
                update={
                    "status": TestGenerationStatus.NEEDS_REVIEW,
                    "validation_reasons": review_reasons,
                }
            )
        else:
            return updated_test.model_copy(
                update={
                    "status": TestGenerationStatus.VALIDATED,
                    "validation_reasons": [
                        "Passed all schema, criteria, and safety checks."
                    ],
                }
            )
