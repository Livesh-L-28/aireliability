"""Regression test validation and duplicate detection engine."""

from collections.abc import Sequence
from typing import Any

from aireliability.core.models import RegressionTest
from aireliability.regression.models import (
    RegressionCandidate,
    RegressionValidation,
)


class RegressionValidator:
    """Validates candidate regression tests against quality criteria.

    Enforces:
    1. Identity: valid ID and source_failure_id
    2. Reproducibility: presence of executable input and expectations/assertions
    3. Provenance: traceability back to failure and trace
    4. Specificity: assertions must specifically target the failure symptom
    5. Duplicate Detection: prevents identical or duplicate regressions
    """

    def validate(
        self,
        candidate: RegressionCandidate,
        existing_tests: Sequence[RegressionTest] | None = None,
    ) -> RegressionValidation:
        """Validate candidate regression test against quality invariants.

        Args:
            candidate: Synthesized regression candidate.
            existing_tests: Optional sequence of existing regression tests
                for duplicate check.

        Returns:
            RegressionValidation report with individual invariant outcomes.
        """
        reasons: list[str] = []
        is_valid = True
        is_reproducible = True
        is_traceable = True
        is_specific = True
        is_duplicate = False

        # 1. Identity & Provenance
        if not candidate.source_failure_id:
            is_valid = False
            is_traceable = False
            reasons.append(
                "Missing source_failure_id: test cannot be traced to a failure."
            )

        tc = candidate.test_case
        if not tc.id or not tc.name:
            is_valid = False
            reasons.append("TestCase lacks unique id or name.")

        # 2. Reproducibility (Executable input & non-empty expectations)
        if tc.input is None and not tc.expectations:
            is_reproducible = False
            is_valid = False
            reasons.append("Candidate lacks both input and expectations to reproduce.")

        # Must have expected_output, expectations, or metadata assertions
        has_assertion = bool(
            tc.expected_output is not None
            or tc.expectations
            or tc.metadata.get("expected_tool")
            or tc.metadata.get("expected_tools")
            or tc.metadata.get("expected_order")
            or tc.metadata.get("expected_arguments")
            or tc.metadata.get("semantic_criteria")
        )
        if not has_assertion:
            is_reproducible = False
            is_valid = False
            reasons.append(
                "Candidate does not specify any testable assertion or expectation."
            )

        # 3. Specificity: Assertions must not be purely trivial
        is_trivial = tc.expectations == ["assert output != ''"] or tc.expectations == [
            "non_empty"
        ]
        if is_trivial:
            is_specific = False
            is_valid = False
            reasons.append("Candidate assertion is overly generic/trivial.")

        # 4. Duplicate Detection against existing suite
        if existing_tests:
            is_duplicate, dup_msg = self.is_duplicate(candidate, existing_tests)
            if is_duplicate:
                reasons.append(dup_msg)

        return RegressionValidation(
            valid=is_valid and not is_duplicate,
            minimal=candidate.minimized,
            reproducible=is_reproducible,
            specific=is_specific,
            traceable=is_traceable,
            duplicate=is_duplicate,
            reasons=reasons,
        )

    def is_duplicate(
        self,
        candidate: RegressionCandidate,
        existing_tests: Sequence[RegressionTest],
    ) -> tuple[bool, str]:
        """Detect whether an equivalent regression test already exists.

        Equivalence is defined by:
        - Same failure type/category
        - Same input payload (or equivalent minimized fields)
        - Same target assertions / expectations
        """
        cand_tc = candidate.test_case
        cand_type = cand_tc.metadata.get("failure_type")
        cand_input = cand_tc.input

        for existing in existing_tests:
            ext_tc = existing.test_case
            ext_type = ext_tc.metadata.get("failure_type")

            # Check if failure type, inputs, and expectations match
            type_match = cand_type and ext_type and cand_type == ext_type
            if (
                type_match
                and self._inputs_equivalent(cand_input, ext_tc.input)
                and self._expectations_equivalent(cand_tc, ext_tc)
            ):
                return True, (
                    f"Equivalent regression test already exists: "
                    f"'{existing.id}' (matches type '{cand_type}' "
                    "and input/expectations)."
                )

        return False, ""

    @staticmethod
    def _inputs_equivalent(input_a: Any, input_b: Any) -> bool:
        """Check if two test inputs are equivalent."""
        if input_a == input_b:
            return True
        if isinstance(input_a, dict) and isinstance(input_b, dict):
            # Check if all keys match
            return input_a == input_b
        return False

    @staticmethod
    def _expectations_equivalent(tc_a: Any, tc_b: Any) -> bool:
        """Check if expectations and expected outputs match."""
        if set(tc_a.expectations) != set(tc_b.expectations):
            return False
        if tc_a.expected_output != tc_b.expected_output:
            return False
        # Check specific metadata assertions if present
        meta_keys = [
            "expected_order",
            "expected_tool",
            "expected_arguments",
            "semantic_criteria",
        ]
        return all(tc_a.metadata.get(mk) == tc_b.metadata.get(mk) for mk in meta_keys)


__all__ = ["RegressionValidator"]
