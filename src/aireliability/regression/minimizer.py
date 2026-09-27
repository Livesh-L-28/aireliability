"""Conservative input and trace minimizer for regression test synthesis.

Minimizes test inputs and execution steps strictly when empirical evidence
or test case metadata justifies reduction. Always prefers correctness
over aggressive reduction.
"""

from typing import Any

from aireliability.core.models import ExecutionTrace, TestCase, TraceStep
from aireliability.diagnosis.models import RootCause


class RegressionMinimizer:
    """Conservative minimizer for test inputs and execution traces."""

    def minimize_input(
        self,
        original_input: Any,
        root_cause: RootCause | None = None,
        test_case: TestCase | None = None,
    ) -> tuple[Any, bool]:
        """Safely minimize an input dictionary to relevant fields supported by evidence.

        Args:
            original_input: The original input payload.
            root_cause: Optional diagnosed RootCause with evidence.
            test_case: Optional source TestCase.

        Returns:
            A tuple of (minimized_input, was_minimized_boolean).
        """
        if not isinstance(original_input, dict):
            # Non-dict inputs (primitives, strings, lists) cannot be safely field-pruned
            return original_input, False

        if not root_cause or not root_cause.evidence:
            return original_input, False

        # Collect keys referenced in evidence or argument expectations
        required_keys: set[str] = set()
        for ev in root_cause.evidence:
            # Check if evidence points to specific field
            if ev.field and ev.field in original_input:
                required_keys.add(ev.field)

            # Check expected/actual argument dictionaries
            for val in (ev.expected, ev.actual):
                if isinstance(val, dict):
                    for k in val:
                        if k in original_input:
                            required_keys.add(k)

            # Check metadata
            if isinstance(ev.metadata, dict):
                for k in ev.metadata:
                    if k in original_input:
                        required_keys.add(k)

        # Check test_case expectations or metadata for declared key dependencies
        if test_case and test_case.metadata:
            declared = test_case.metadata.get("required_input_fields")
            if isinstance(declared, list):
                for k in declared:
                    if k in original_input:
                        required_keys.add(str(k))

        # Only minimize if at least one required key was safely identified
        # and strictly fewer keys than the original input are retained
        if required_keys and len(required_keys) < len(original_input):
            minimized = {
                k: original_input[k] for k in required_keys if k in original_input
            }
            return minimized, True

        return original_input, False

    def minimize_trace_steps(
        self,
        trace: ExecutionTrace,
        root_cause: RootCause | None = None,
    ) -> tuple[list[TraceStep], bool]:
        """Conservatively prune execution steps unrelated to the diagnosed root cause.

        Args:
            trace: The ExecutionTrace containing recorded steps.
            root_cause: The diagnosed RootCause with affected_step and evidence.

        Returns:
            A tuple of (minimized_steps, was_minimized_boolean).
        """
        if not trace.steps or not root_cause:
            return list(trace.steps), False

        # Identify key tools and affected steps from root cause evidence
        relevant_tool_names: set[str] = set()
        affected_step_ids: set[str] = set()

        if root_cause.affected_step:
            affected_step_ids.add(root_cause.affected_step)

        for ev in root_cause.evidence:
            if ev.step_id:
                affected_step_ids.add(ev.step_id)
            if ev.field in ("tool_name", "tool_called", "tool_not_called"):
                if isinstance(ev.expected, str):
                    relevant_tool_names.add(ev.expected)
                if isinstance(ev.actual, str):
                    relevant_tool_names.add(ev.actual)
            if ev.field == "tool_order":
                # Both sequences are relevant
                for seq in (ev.expected, ev.actual):
                    if isinstance(seq, str) and " → " in seq:
                        for item in seq.split(" → "):
                            relevant_tool_names.add(item.strip())
                    elif isinstance(seq, list):
                        for item in seq:
                            relevant_tool_names.add(str(item))

        # If no specific tools or steps were identified, preserve full trace
        if not relevant_tool_names and not affected_step_ids:
            return list(trace.steps), False

        # Filter steps: keep steps that match relevant tools, affected IDs,
        # or causal links
        kept_steps: list[TraceStep] = []
        for step in trace.steps:
            in_affected = step.id in affected_step_ids
            in_tools = step.name in relevant_tool_names
            in_causal = any(
                link.source == step.id or link.target == step.id
                for link in root_cause.causal_links
            )
            if in_affected or in_tools or in_causal:
                kept_steps.append(step)

        # Conservative safety check: if pruning removed all steps, revert to full trace
        if not kept_steps or len(kept_steps) == len(trace.steps):
            return list(trace.steps), False

        return kept_steps, True


__all__ = ["RegressionMinimizer"]
