"""Serialization and multi-format reporting for RAG runs and evaluations."""

from __future__ import annotations

import csv
import io

from aireliability.rag.models import (
    KnowledgeBaseHealthReport,
    RAGEvaluationResult,
    RAGRun,
)


class RAGSerializer:
    """Handles round-trip JSON serialization and multi-format reporting for RAG runs."""

    @staticmethod
    def to_json(obj: RAGRun | RAGEvaluationResult | KnowledgeBaseHealthReport) -> str:
        """Serialize model to JSON string."""
        return obj.model_dump_json(indent=2)

    @staticmethod
    def to_jsonl(runs: list[RAGRun]) -> str:
        """Serialize a list of RAG runs to JSON Lines format."""
        return "\n".join(r.model_dump_json() for r in runs)

    @staticmethod
    def from_json_run(json_str: str) -> RAGRun:
        """Deserialize JSON string into RAGRun."""
        return RAGRun.model_validate_json(json_str)

    @staticmethod
    def from_json_eval(json_str: str) -> RAGEvaluationResult:
        """Deserialize JSON string into RAGEvaluationResult."""
        return RAGEvaluationResult.model_validate_json(json_str)

    @staticmethod
    def to_markdown(run: RAGRun) -> str:
        """Generate structured Markdown report for a RAG run."""
        lines = [
            f"# RAG Reliability Report: {run.run_id}",
            "",
            f"**Query**: {run.query.text}",
            f"**Query Type**: `{run.query.query_type.value}`",
            f"**Model**: `{run.model}` | **Retriever**: `{run.retriever_name}`",
            f"**Overall Reliability Score**: **{run.reliability_score.overall_score:.2f} / 1.00**",
            "",
            "## 1. Stage Reliability Breakdown",
            "",
            "| Stage | Score | Confidence | Failures |",
            "|---|---|---|---|",
        ]

        for st_name, st_res in run.stage_scores.items():
            lines.append(
                f"| `{st_name}` | **{st_res.score:.2f}** | {st_res.confidence:.2f} | {len(st_res.failures)} |"
            )

        lines.extend(
            [
                "",
                "## 2. Generated Answer & Citations",
                "",
                f"> {run.generated_answer.text}",
                "",
                f"Total Claims: **{len(run.claims)}** | Total Citations: **{len(run.citations)}**",
                "",
                "### Claims & Support Status",
                "| Claim ID | Proposition | Importance | Support Status |",
                "|---|---|---|---|",
            ]
        )

        for c in run.claims:
            lines.append(
                f"| `{c.claim_id}` | {c.text} | `{c.importance.value}` | **`{c.support_status.value}`** |"
            )

        if run.failures:
            lines.extend(
                [
                    "",
                    "## 3. Diagnosed RAG Failures",
                    "",
                    "| Severity | Stage | Category | Message |",
                    "|---|---|---|---|",
                ]
            )
            for f in run.failures:
                lines.append(
                    f"| `{f.severity.value.upper()}` | `{f.stage.value}` | `{f.category.value}` | {f.message} |"
                )

        if run.conflicts:
            lines.extend(
                [
                    "",
                    "## 4. Evidence Conflicts",
                    "",
                ]
            )
            for cnf in run.conflicts:
                lines.append(f"- **{cnf.description}** (Status: `{cnf.status.value}`)")

        return "\n".join(lines)

    @staticmethod
    def to_csv(runs: list[RAGRun]) -> str:
        """Export tabular summary of RAG runs to CSV string."""
        output = io.StringIO()
        fieldnames = [
            "run_id",
            "query",
            "overall_score",
            "retrieval_score",
            "grounding_score",
            "faithfulness_score",
            "citation_score",
            "total_claims",
            "total_failures",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for r in runs:
            st = r.stage_scores
            writer.writerow(
                {
                    "run_id": r.run_id,
                    "query": r.query.text,
                    "overall_score": r.reliability_score.overall_score,
                    "retrieval_score": st.get("retrieval").score
                    if "retrieval" in st
                    else None,
                    "grounding_score": st.get("grounding").score
                    if "grounding" in st
                    else None,
                    "faithfulness_score": st.get("faithfulness").score
                    if "faithfulness" in st
                    else None,
                    "citation_score": st.get("citation").score
                    if "citation" in st
                    else None,
                    "total_claims": len(r.claims),
                    "total_failures": len(r.failures),
                }
            )

        return output.getvalue()
