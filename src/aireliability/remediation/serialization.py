"""Serialization and report formatting for remediation proposals and audit trails."""

from __future__ import annotations

import csv
import io
import json

from aireliability.remediation.models import RemediationProposal


class RemediationSerializer:
    """Serializes remediation proposals and simulation results into multiple output formats."""

    @staticmethod
    def to_json(
        proposals: RemediationProposal | list[RemediationProposal], indent: int = 2
    ) -> str:
        """Serialize proposal(s) to formatted JSON string."""
        if isinstance(proposals, list):
            data = [p.model_dump(mode="json") for p in proposals]
        else:
            data = proposals.model_dump(mode="json")
        return json.dumps(data, indent=indent, default=str)

    @staticmethod
    def to_jsonl(proposals: list[RemediationProposal]) -> str:
        """Serialize a list of proposals to JSON Lines."""
        lines = [json.dumps(p.model_dump(mode="json"), default=str) for p in proposals]
        return "\n".join(lines)

    @staticmethod
    def to_csv(proposals: list[RemediationProposal]) -> str:
        """Export high-level proposal summary as CSV string."""
        output = io.StringIO()
        fieldnames = [
            "proposal_id",
            "title",
            "repair_type",
            "state",
            "risk_tier",
            "confidence",
            "patches_count",
            "simulation_passed",
            "gates_passed",
            "rollout_strategy",
            "active_percentage",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for p in proposals:
            writer.writerow(
                {
                    "proposal_id": p.proposal_id,
                    "title": p.title,
                    "repair_type": p.repair_type.value,
                    "state": p.state.value,
                    "risk_tier": p.risk_tier.value,
                    "confidence": f"{p.confidence:.2f}",
                    "patches_count": len(p.patches),
                    "simulation_passed": str(
                        p.simulation.passed if p.simulation else False
                    ),
                    "gates_passed": str(
                        p.gate_evaluation.gates_passed if p.gate_evaluation else False
                    ),
                    "rollout_strategy": p.rollout_state.strategy.value,
                    "active_percentage": f"{p.rollout_state.active_percentage:.1f}%",
                }
            )
        return output.getvalue()

    @staticmethod
    def to_markdown(proposals: list[RemediationProposal]) -> str:
        """Generate a GitHub-flavored Markdown report detailing remediation proposals."""
        lines = [
            "# AI Reliability Self-Healing Remediation Report",
            "",
            f"**Total Proposals:** {len(proposals)}",
            "",
            "| Proposal ID | Repair Type | State | Risk | Sim Passed | Gates Passed | Active % |",
            "|---|---|---|---|---|---|---|",
        ]
        for p in proposals:
            sim_passed = "✓" if (p.simulation and p.simulation.passed) else "✗"
            gates_passed = (
                "✓" if (p.gate_evaluation and p.gate_evaluation.gates_passed) else "✗"
            )
            lines.append(
                f"| `{p.proposal_id}` | {p.repair_type.value} | `{p.state.value}` | "
                f"{p.risk_tier.value} | {sim_passed} | {gates_passed} | {p.rollout_state.active_percentage:.1f}% |"
            )

        lines.append("")
        lines.append("## Detailed Proposals")
        lines.append("")
        for p in proposals:
            lines.append(f"### `{p.proposal_id}`: {p.title}")
            lines.append(
                f"- **State:** `{p.state.value}` | **Risk:** `{p.risk_tier.value}`"
            )
            lines.append(f"- **Description:** {p.description}")
            if p.patches:
                lines.append("- **Patches:**")
                for patch in p.patches:
                    lines.append(
                        f"  - `{patch.target_component_type}:{patch.target_component_id}`: {patch.diff_summary}"
                    )
            if p.simulation:
                lines.append(f"- **Simulation Summary:** {p.simulation.summary}")
            if p.gate_evaluation and not p.gate_evaluation.gates_passed:
                lines.append(
                    f"- **Failed Gates:** {'; '.join(p.gate_evaluation.failed_gate_reasons)}"
                )
            if p.audit_trail:
                lines.append("- **Audit Trail:**")
                for audit in p.audit_trail[-3:]:
                    lines.append(
                        f"  - `{audit.from_state.value} -> {audit.to_state.value}` by {audit.actor} ({audit.action}): {audit.reason}"
                    )
            lines.append("")

        return "\n".join(lines)
