"""Round-trip serialization and reporting in JSON, JSONL, CSV, and Markdown formats."""

from __future__ import annotations

import csv
import io
from typing import Any

from aireliability.optimization.models import (
    OptimizationCandidate,
    OptimizationResult,
)


class OptimizationSerializer:
    """Handles serialization and formatted reporting for optimization artifacts."""

    @staticmethod
    def to_json(result: OptimizationResult, indent: int = 2) -> str:
        """Serialize OptimizationResult to indented JSON string."""
        return result.model_dump_json(indent=indent)

    @staticmethod
    def from_json(json_str: str) -> OptimizationResult:
        """Deserialize JSON string into an OptimizationResult instance."""
        return OptimizationResult.model_validate_json(json_str)

    @staticmethod
    def to_jsonl(candidates: list[OptimizationCandidate]) -> str:
        """Serialize list of candidates to JSON Lines format."""
        lines = [c.model_dump_json() for c in candidates]
        return "\n".join(lines)

    @staticmethod
    def from_jsonl(jsonl_str: str) -> list[OptimizationCandidate]:
        """Deserialize JSON Lines string into list of OptimizationCandidates."""
        cands: list[OptimizationCandidate] = []
        for line in jsonl_str.strip().splitlines():
            line_str = line.strip()
            if line_str:
                cands.append(OptimizationCandidate.model_validate_json(line_str))
        return cands

    @staticmethod
    def to_csv(candidates: list[OptimizationCandidate]) -> str:
        """Export candidate evaluation metrics and configuration parameters as CSV."""
        if not candidates:
            return ""

        output = io.StringIO()
        fieldnames = [
            "candidate_id",
            "fingerprint",
            "strategy",
            "status",
            "is_feasible",
            "is_pareto",
            "pareto_rank",
            "crowding_distance",
            "confidence",
        ]

        # Collect unique objective and parameter keys
        obj_keys: set[str] = set()
        param_keys: set[str] = set()
        for c in candidates:
            obj_keys.update(c.objective_values.keys())
            param_keys.update(c.configuration.values.keys())

        sorted_obj_keys = sorted(obj_keys)
        sorted_param_keys = sorted(param_keys)

        for k in sorted_obj_keys:
            fieldnames.append(f"obj_{k}")
        for k in sorted_param_keys:
            fieldnames.append(f"param_{k}")

        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for c in candidates:
            row: dict[str, Any] = {
                "candidate_id": c.candidate_id,
                "fingerprint": c.fingerprint,
                "strategy": c.generation_strategy,
                "status": c.status.value,
                "is_feasible": c.is_feasible,
                "is_pareto": c.is_pareto,
                "pareto_rank": c.pareto_rank,
                "crowding_distance": c.crowding_distance,
                "confidence": c.confidence,
            }
            for k in sorted_obj_keys:
                row[f"obj_{k}"] = c.objective_values.get(k, "")
            for k in sorted_param_keys:
                row[f"param_{k}"] = c.configuration.values.get(k, "")

            writer.writerow(row)

        return output.getvalue()

    @staticmethod
    def to_markdown(result: OptimizationResult) -> str:
        """Generate a GitHub-flavored Markdown optimization summary report."""
        lines = [
            f"# Optimization Report: `{result.optimization_id}`",
            "",
            "## 1. Executive Summary",
            f"- **Problem**: {result.problem.name} (`{result.problem.problem_id}`)",
            f"- **Status**: `{result.stopping_reason.value}`",
            f"- **Duration**: {result.duration_seconds:.2f}s",
            f"- **Confidence**: {result.confidence * 100:.1f}%",
            f"- **Total Candidates Evaluated**: {len(result.candidates)}",
            f"- **Pareto Frontier Size**: {len(result.pareto_frontier.non_dominated_candidate_ids)}",
            "",
            "## 2. Baseline Configuration & Metrics",
            "| Parameter / Metric | Baseline Value |",
            "| :--- | :--- |",
        ]

        for k, v in result.baseline_config.values.items():
            lines.append(f"| `param.{k}` | `{v}` |")
        for k, v in result.baseline_metrics.items():
            lines.append(f"| `metric.{k}` | `{v}` |")

        lines.extend(
            [
                "",
                "## 3. Selected Optimal Candidate",
            ]
        )

        if result.selected_candidate:
            sel = result.selected_candidate
            lines.extend(
                [
                    f"- **Candidate ID**: `{sel.candidate_id}` (Fingerprint: `{sel.fingerprint}`)",
                    f"- **Strategy**: `{sel.generation_strategy}`",
                    f"- **Explanation**: {sel.explanation}",
                    "",
                    "### Configuration Deltas vs Baseline",
                    "| Metric | Baseline | Candidate | Delta | % Change |",
                    "| :--- | :--- | :--- | :--- | :--- |",
                ]
            )
            for m, d in sel.baseline_deltas.items():
                lines.append(
                    f"| `{m}` | {d.get('baseline', '-')} | {d.get('candidate', '-')} | "
                    f"{d.get('absolute', '-')} | {d.get('percentage', '-')}% |"
                )
        else:
            lines.append(
                "> [!WARNING]\n> No feasible candidate satisfied all reliability gates."
            )

        lines.extend(
            [
                "",
                "## 4. Pareto Frontier Candidates",
                "| Candidate ID | Pareto? | Quality | Latency | Cost | Error Rate | Fingerprint |",
                "| :--- | :---: | :---: | :---: | :---: | :---: | :--- |",
            ]
        )

        for c in result.candidates:
            vals = c.objective_values
            q = vals.get("quality", "-")
            lat = vals.get("latency", "-")
            cost = vals.get("cost", "-")
            err = vals.get("error_rate", "-")
            lines.append(
                f"| `{c.candidate_id}` | {'✅' if c.is_pareto else '❌'} | "
                f"{q} | {lat} | {cost} | {err} | `{c.fingerprint[:12]}` |"
            )

        lines.append("")
        return "\n".join(lines)
