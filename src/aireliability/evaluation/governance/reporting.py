"""Multi-format reporting engine supporting CLI, JSON, JSONL, CSV, Markdown, HTML, and JUnit XML."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from aireliability.evaluation.governance.gates import GateResult
from aireliability.evaluation.governance.scoring import UnifiedReliabilityScore
from aireliability.evaluation.models import EvaluationReport


class EvaluationReporter:
    """Multi-format renderer and exporter for AI evaluation reports."""

    @staticmethod
    def render_cli(
        report: EvaluationReport,
        score: UnifiedReliabilityScore | None = None,
        gate: GateResult | None = None,
    ) -> str:
        """Render beautiful terminal report with ANSI borders and structured sections."""
        lines = [
            "╔══════════════════════════════════════════════════════════════════════════════╗",
            "║                     AI RELIABILITY EVALUATION REPORT                         ║",
            "╚══════════════════════════════════════════════════════════════════════════════╝",
            f" Target:      {report.target_name}",
            f" Dataset:     {report.dataset_id}",
            f" Execution:   {report.report_id}",
            f" Timestamp:   {report.timestamp.isoformat()}",
            "──────────────────────────────────────────────────────────────────────────────",
        ]

        if score:
            veto_tag = " [VETO TRIGGERED]" if score.veto_triggered else ""
            lines.extend(
                [
                    f" Composite Reliability Score: {score.composite_score:.2f} ({score.status}){veto_tag}",
                    f" Unweighted Mean:             {score.unweighted_mean:.2f}",
                    " Dimensional Scores:",
                ]
            )
            for d_name, d_score in score.dimensional_scores.items():
                crit_marker = "*" if d_score.is_critical else " "
                pass_symbol = "✔" if d_score.passed else "✘"
                lines.append(
                    f"   [{pass_symbol}] {crit_marker}{d_name:<14}: {d_score.score:.2f} (weight: {d_score.weight:.2f}, failures: {d_score.failure_count})"
                )

        if gate:
            lines.extend(
                [
                    "──────────────────────────────────────────────────────────────────────────────",
                    f" Release Gate Decision:       {gate.decision.value} (Policy: {gate.policy_name})",
                ]
            )
            if gate.reasons:
                lines.append(" Gate Reasons:")
                for r in gate.reasons:
                    lines.append(f"   • {r}")

        lines.extend(
            [
                "──────────────────────────────────────────────────────────────────────────────",
                f" Test Cases:  {report.total_test_cases} total, {report.passed_test_cases} passed, {report.failed_test_cases} failed",
                f" Failures:    {len(report.failures)} detected",
                f" Root Causes: {len(report.root_causes)} diagnosed",
                f" Regressions: {len(report.regressions)} dimensional regressions",
            ]
        )

        if report.recommendations:
            lines.extend(
                [
                    "──────────────────────────────────────────────────────────────────────────────",
                    " Recommendations:",
                ]
            )
            for rec in report.recommendations:
                lines.append(f"   ➤ {rec}")

        lines.append(
            "══════════════════════════════════════════════════════════════════════════════"
        )
        return "\n".join(lines)

    @staticmethod
    def render_json(
        report: EvaluationReport,
        score: UnifiedReliabilityScore | None = None,
        gate: GateResult | None = None,
        indent: int = 2,
    ) -> str:
        """Render comprehensive structured JSON."""
        data: dict[str, Any] = {
            "report": report.model_dump(mode="json"),
        }
        if score:
            data["reliability_score"] = score.model_dump(mode="json")
        if gate:
            data["gate_result"] = gate.model_dump(mode="json")
        return json.dumps(data, indent=indent, default=str)

    @staticmethod
    def render_jsonl(
        report: EvaluationReport,
        score: UnifiedReliabilityScore | None = None,
        gate: GateResult | None = None,
    ) -> str:
        """Render line-delimited JSON records for streaming and log ingestion."""
        lines: list[str] = []
        # Header / summary record
        summary = {
            "type": "summary",
            "report_id": report.report_id,
            "target": report.target_name,
            "dataset_id": report.dataset_id,
            "total_test_cases": report.total_test_cases,
            "passed_test_cases": report.passed_test_cases,
            "failed_test_cases": report.failed_test_cases,
            "passed": report.passed,
            "composite_score": score.composite_score if score else None,
            "gate_decision": gate.decision.value if gate else None,
        }
        lines.append(json.dumps(summary, default=str))

        # Each evaluation result as a record
        for ev in report.evaluations:
            ev_dict = ev.model_dump(mode="json")
            ev_dict["type"] = "evaluation_result"
            ev_dict["report_id"] = report.report_id
            lines.append(json.dumps(ev_dict, default=str))

        # Each failure as a record
        for fail in report.failures:
            f_dict = fail.model_dump(mode="json")
            f_dict["type"] = "failure_report"
            f_dict["report_id"] = report.report_id
            lines.append(json.dumps(f_dict, default=str))

        return "\n".join(lines)

    @staticmethod
    def render_csv(
        report: EvaluationReport,
        score: UnifiedReliabilityScore | None = None,
        gate: GateResult | None = None,
    ) -> str:
        """Render evaluation assertions and metrics as CSV."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "report_id",
                "target_name",
                "dataset_id",
                "evaluator",
                "passed",
                "score",
                "metric",
                "threshold",
                "confidence",
                "message",
            ]
        )
        for ev in report.evaluations:
            writer.writerow(
                [
                    report.report_id,
                    report.target_name,
                    report.dataset_id,
                    ev.evaluator,
                    ev.passed,
                    ev.score if ev.score is not None else "",
                    ev.metric or "",
                    ev.threshold if ev.threshold is not None else "",
                    ev.confidence if ev.confidence is not None else "",
                    ev.message.replace("\n", " "),
                ]
            )
        return output.getvalue()

    @staticmethod
    def render_markdown(
        report: EvaluationReport,
        score: UnifiedReliabilityScore | None = None,
        gate: GateResult | None = None,
    ) -> str:
        """Render GitHub-Flavored Markdown report with tables, badges, and alerts."""
        md: list[str] = [
            f"# AI Reliability Evaluation Report — `{report.target_name}`",
            "",
            f"- **Execution ID:** `{report.report_id}`",
            f"- **Dataset:** `{report.dataset_id}`",
            f"- **Timestamp:** `{report.timestamp.isoformat()}`",
            "",
        ]

        if score:
            status_emoji = (
                "🟢"
                if score.status in ("EXCELLENT", "HEALTHY")
                else ("🟡" if score.status == "DEGRADED" else "🔴")
            )
            md.extend(
                [
                    f"## {status_emoji} Reliability Score: `{score.composite_score:.2f}` ({score.status})",
                    "",
                    f"> **Explanation:** {score.explanation}",
                    "",
                ]
            )
            if score.veto_triggered:
                md.extend(
                    [
                        "> [!CAUTION]",
                        "> **CRITICAL VETO TRIGGERED!** Safety, security, or critical faithfulness breaches override composite performance.",
                        "",
                    ]
                )

            md.extend(
                [
                    "### Dimensional Breakdown",
                    "",
                    "| Dimension | Score | Weight | Passed | Critical | Failures |",
                    "| :--- | :---: | :---: | :---: | :---: | :---: |",
                ]
            )
            for dim, d_score in score.dimensional_scores.items():
                p_str = "✅ Yes" if d_score.passed else "❌ No"
                c_str = "⚠️ Critical" if d_score.is_critical else "Standard"
                md.append(
                    f"| **{dim.capitalize()}** | {d_score.score:.2f} | {d_score.weight:.2f} | {p_str} | {c_str} | {d_score.failure_count} |"
                )
            md.append("")

        if gate:
            decision_badge = (
                "🟢 **PASS**"
                if gate.decision.value == "PASS"
                else (
                    "🟡 **FAIL**" if gate.decision.value == "FAIL" else "🛑 **BLOCK**"
                )
            )
            md.extend(
                [
                    f"## Release Gate: {decision_badge}",
                    f"**Policy:** `{gate.policy_name}`",
                    "",
                ]
            )
            if gate.reasons:
                md.append("#### Reasons:")
                for r in gate.reasons:
                    md.append(f"- {r}")
                md.append("")

        # Summary Metrics
        md.extend(
            [
                "## Test Suite Summary",
                "",
                f"- **Total Test Cases:** `{report.total_test_cases}`",
                f"- **Passed:** `{report.passed_test_cases}`",
                f"- **Failed:** `{report.failed_test_cases}`",
                f"- **Failures Logged:** `{len(report.failures)}`",
                f"- **Root Causes:** `{len(report.root_causes)}`",
                f"- **Regressions:** `{len(report.regressions)}`",
                "",
            ]
        )

        if report.recommendations:
            md.extend(["## 💡 Recommendations", ""])
            for rec in report.recommendations:
                md.append(f"- {rec}")
            md.append("")

        return "\n".join(md)

    @staticmethod
    def render_pr_comment(
        report: EvaluationReport,
        score: UnifiedReliabilityScore | None = None,
        gate: GateResult | None = None,
        baseline_score: float | None = None,
    ) -> str:
        """Render high-impact PR comment Markdown with summary badge, score delta, and breakdown."""
        status_badge = "✅ **PASSED**" if report.passed else "❌ **FAILED**"
        gate_badge = f"`{gate.decision.value}`" if gate else "`N/A`"
        score_val = (
            f"`{score.composite_score:.2f}` ({score.status})" if score else "`N/A`"
        )

        delta_str = ""
        if score and baseline_score is not None:
            delta = score.composite_score - baseline_score
            sign = "+" if delta >= 0 else ""
            delta_str = f" ({sign}{delta:.2f} vs baseline)"

        lines = [
            "### 🤖 AI Reliability Evaluation Summary",
            "",
            "| Metric | Result |",
            "| :--- | :--- |",
            f"| **Target** | `{report.target_name}` |",
            f"| **Dataset** | `{report.dataset_id}` |",
            f"| **Verdict** | {status_badge} |",
            f"| **Composite Score** | {score_val}{delta_str} |",
            f"| **Release Gate** | {gate_badge} |",
            f"| **Test Cases** | {report.passed_test_cases}/{report.total_test_cases} passed |",
            f"| **Regressions** | `{len(report.regressions)}` detected |",
            "",
        ]

        if gate and gate.decision.value in ("FAIL", "BLOCK"):
            alert_type = "CAUTION" if gate.decision.value == "BLOCK" else "WARNING"
            lines.extend(
                [
                    f"> [!{alert_type}]",
                    f"> **Release Gate: {gate.decision.value}** - Policy: `{gate.policy_name}`",
                ]
            )
            for r in gate.reasons:
                lines.append(f"> - {r}")
            lines.append("")

        if score:
            lines.extend(
                [
                    "#### Dimensional Reliability",
                    "",
                    "| Dimension | Score | Status | Failures |",
                    "| :--- | :---: | :---: | :---: |",
                ]
            )
            for d_name, d_score in score.dimensional_scores.items():
                p_icon = "✅" if d_score.passed else "❌"
                lines.append(
                    f"| {d_name.capitalize()} | `{d_score.score:.2f}` | {p_icon} | {d_score.failure_count} |"
                )
            lines.append("")

        if report.root_causes:
            lines.extend(
                [
                    "<details>",
                    f"<summary><b>🔍 Diagnosed Root Causes ({len(report.root_causes)})</b></summary>",
                    "",
                ]
            )
            for rc in report.root_causes:
                cat = (
                    rc.get("category", "Unknown")
                    if isinstance(rc, dict)
                    else getattr(rc, "category", "Unknown")
                )
                desc = (
                    rc.get("summary", "")
                    if isinstance(rc, dict)
                    else getattr(rc, "summary", "")
                )
                lines.append(f"- **{cat}**: {desc}")
            lines.extend(["", "</details>", ""])

        if report.recommendations:
            lines.extend(
                [
                    "#### 💡 Recommended Actions",
                    "",
                ]
            )
            for rec in report.recommendations:
                lines.append(f"- {rec}")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def render_html(
        report: EvaluationReport,
        score: UnifiedReliabilityScore | None = None,
        gate: GateResult | None = None,
    ) -> str:
        """Render self-contained interactive modern HTML dashboard with zero external dependencies."""
        import math

        score_val = score.composite_score if score else 0.85
        score_pct = int(score_val * 100)
        gate_decision = gate.decision.value if gate else "PASS"

        gate_color = (
            "#10b981"
            if gate_decision == "PASS"
            else ("#f59e0b" if gate_decision == "FAIL" else "#ef4444")
        )

        dim_rows = ""
        radar_points = []
        radar_labels = []
        radar_grids = ""
        cx, cy, r_max = 160, 160, 110

        if score and score.dimensional_scores:
            dims = list(score.dimensional_scores.keys())
            n = len(dims)
            for i, dim in enumerate(dims):
                ds = score.dimensional_scores[dim]
                pct = int(ds.score * 100)
                status_icon = "✔" if ds.passed else "✘"
                bar_color = "#10b981" if ds.passed else "#ef4444"
                crit_badge = (
                    '<span style="color:#ef4444;font-size:11px;font-weight:700;">[CRITICAL]</span> '
                    if ds.is_critical
                    else ""
                )
                dim_rows += f"""
                <tr>
                    <td style="font-weight: 600; text-transform: capitalize;">{crit_badge}{dim}</td>
                    <td><div style="background: #334155; border-radius: 4px; overflow: hidden; width: 140px; height: 10px;">
                        <div style="background: {bar_color}; width: {pct}%; height: 100%;"></div>
                    </div></td>
                    <td><b>{ds.score:.2f}</b></td>
                    <td>{ds.weight:.2f}</td>
                    <td><span style="color: {bar_color}; font-weight: bold;">{status_icon}</span></td>
                </tr>
                """
                angle = (2 * math.pi * i / n) - (math.pi / 2)
                r_val = r_max * max(0.05, min(1.0, ds.score))
                px = cx + r_val * math.cos(angle)
                py = cy + r_val * math.sin(angle)
                radar_points.append(f"{px:.1f},{py:.1f}")

                lx = cx + (r_max + 22) * math.cos(angle)
                ly = cy + (r_max + 14) * math.sin(angle)
                anchor = "middle"
                if math.cos(angle) > 0.3:
                    anchor = "start"
                elif math.cos(angle) < -0.3:
                    anchor = "end"
                radar_labels.append(
                    f'<text x="{lx:.1f}" y="{ly:.1f}" fill="#94a3b8" font-size="10" text-anchor="{anchor}" font-weight="600">{dim.capitalize()}</text>'
                )

            # Circular concentric grid rings
            for ring_pct in [0.25, 0.5, 0.75, 1.0]:
                ring_r = r_max * ring_pct
                radar_grids += f'<circle cx="{cx}" cy="{cy}" r="{ring_r}" fill="none" stroke="#334155" stroke-dasharray="2,2" stroke-width="1"/>\n'

        radar_polygon = " ".join(radar_points) if radar_points else ""
        radar_labels_svg = "\n".join(radar_labels)

        eval_rows = ""
        for idx, ev in enumerate(report.evaluations):
            p_color = "#10b981" if ev.passed else "#ef4444"
            status_text = "PASS" if ev.passed else "FAIL"
            msg = xml_escape(ev.message[:120] if ev.message else "")
            eval_rows += f"""
            <tr class="eval-row" data-passed="{"true" if ev.passed else "false"}">
                <td>#{idx + 1}</td>
                <td><code>{xml_escape(ev.evaluator)}</code></td>
                <td><span class="badge" style="background:{p_color}22; color:{p_color}; border:1px solid {p_color}; padding:2px 8px; font-size:12px;">{status_text}</span></td>
                <td><b>{ev.score if ev.score is not None else "-"}</b></td>
                <td>{ev.latency or 0.0:.3f}s</td>
                <td style="color: #94a3b8; font-size: 13px;">{msg}</td>
            </tr>
            """

        root_cause_cards = ""
        if report.root_causes:
            for rc in report.root_causes:
                cat = (
                    rc.get("category", "Diagnosis")
                    if isinstance(rc, dict)
                    else getattr(rc, "category", "Diagnosis")
                )
                summary = (
                    rc.get("summary", "Root cause identified")
                    if isinstance(rc, dict)
                    else getattr(rc, "summary", "Root cause identified")
                )
                evid = (
                    rc.get("evidence", {})
                    if isinstance(rc, dict)
                    else getattr(rc, "evidence", {})
                )
                evid_str = (
                    xml_escape(json.dumps(evid, indent=2))
                    if evid
                    else "No extra evidence recorded."
                )
                root_cause_cards += f"""
                <div style="background: #1e293b; border-left: 4px solid #f59e0b; border-radius: 6px; padding: 14px; margin-bottom: 12px;">
                    <div style="font-weight: 700; color: #fbbf24; margin-bottom: 4px;">{xml_escape(str(cat))}</div>
                    <div style="color: #e2e8f0; font-size: 14px; margin-bottom: 8px;">{xml_escape(str(summary))}</div>
                    <pre style="background: #0f172a; padding: 8px; border-radius: 4px; font-size: 11px; color: #94a3b8; margin: 0; overflow-x: auto;"><code>{evid_str}</code></pre>
                </div>
                """
        else:
            root_cause_cards = '<div style="color: #94a3b8; font-size: 14px;">No failures or root causes recorded in this evaluation run.</div>'

        reg_rows = ""
        if report.regressions:
            for reg in report.regressions:
                dim_str = (
                    reg.get("dimension", "unknown")
                    if isinstance(reg, dict)
                    else getattr(reg, "dimension", "unknown")
                )
                base_s = (
                    reg.get("baseline_score", 0.0)
                    if isinstance(reg, dict)
                    else getattr(reg, "baseline_score", 0.0)
                )
                cand_s = (
                    reg.get("candidate_score", 0.0)
                    if isinstance(reg, dict)
                    else getattr(reg, "candidate_score", 0.0)
                )
                delta = cand_s - base_s
                reg_rows += f"""
                <tr>
                    <td style="font-weight: 600; text-transform: capitalize;">{xml_escape(str(dim_str))}</td>
                    <td>{base_s:.2f}</td>
                    <td>{cand_s:.2f}</td>
                    <td style="color: #ef4444; font-weight: 700;">{delta:.2f}</td>
                </tr>
                """
        else:
            reg_rows = '<tr><td colspan="4" style="color: #10b981; text-align: center; padding: 16px;">✔ Zero dimensional regressions detected against baseline.</td></tr>'

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Reliability Report - {xml_escape(report.target_name)}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0b1120; color: #f8fafc; margin: 0; padding: 24px; line-height: 1.5; }}
  .container {{ max-width: 1200px; margin: 0 auto; }}
  .card {{ background: #1e293b; border-radius: 12px; padding: 24px; margin-bottom: 24px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3); border: 1px solid #334155; }}
  .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; padding-bottom: 16px; margin-bottom: 20px; }}
  .badge {{ display: inline-block; padding: 6px 14px; border-radius: 9999px; font-weight: 700; font-size: 13px; text-transform: uppercase; letter-spacing: 0.04em; }}
  .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 20px; }}
  .metric-card {{ background: #0f172a; padding: 16px; border-radius: 8px; border: 1px solid #334155; }}
  .metric-val {{ font-size: 28px; font-weight: 800; color: #38bdf8; }}
  .metric-lbl {{ color: #94a3b8; font-size: 13px; text-transform: uppercase; letter-spacing: 0.05em; }}
  .chart-layout {{ display: flex; gap: 32px; align-items: center; flex-wrap: wrap; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
  th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid #334155; font-size: 14px; }}
  th {{ color: #94a3b8; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; }}
  code {{ background: #0f172a; padding: 2px 6px; border-radius: 4px; font-family: monospace; color: #38bdf8; font-size: 13px; }}
  .filter-btn {{ background: #334155; color: #f8fafc; border: none; padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; }}
  .filter-btn.active {{ background: #38bdf8; color: #0f172a; font-weight: 700; }}
  .search-input {{ background: #0f172a; border: 1px solid #334155; color: #f8fafc; padding: 8px 12px; border-radius: 6px; font-size: 13px; width: 260px; }}
</style>
</head>
<body>
<div class="container">
  <!-- Header Card -->
  <div class="card">
    <div class="header">
      <div>
        <h1 style="margin: 0 0 6px 0; font-size: 24px; color: #f8fafc;">AI Reliability Platform Report &bull; AI Reliability Evaluation Dashboard</h1>
        <div style="color: #94a3b8; font-size: 14px;">Target: <code>{xml_escape(report.target_name)}</code> &bull; Dataset: <code>{xml_escape(report.dataset_id)}</code> &bull; ID: <code>{xml_escape(report.report_id)}</code></div>
      </div>
      <div>
        <span class="badge" style="background: {gate_color}22; color: {gate_color}; border: 1px solid {gate_color};">
          RELEASE GATE: {gate_decision}
        </span>
      </div>
    </div>

    <!-- Summary Metrics -->
    <div class="metrics-grid">
      <div class="metric-card">
        <div class="metric-val">{score_pct}%</div>
        <div class="metric-lbl">Composite Score ({score.status if score else "PASS"})</div>
      </div>
      <div class="metric-card">
        <div class="metric-val" style="color: {"#10b981" if report.failed_test_cases == 0 else "#ef4444"};">{report.passed_test_cases}/{report.total_test_cases}</div>
        <div class="metric-lbl">Tests Passed</div>
      </div>
      <div class="metric-card">
        <div class="metric-val" style="color: {"#10b981" if len(report.failures) == 0 else "#ef4444"};">{len(report.failures)}</div>
        <div class="metric-lbl">Failures Detected</div>
      </div>
      <div class="metric-card">
        <div class="metric-val" style="color: {"#10b981" if len(report.regressions) == 0 else "#f59e0b"};">{len(report.regressions)}</div>
        <div class="metric-lbl">Regressions</div>
      </div>
    </div>
  </div>

  <!-- Multidimensional Reliability Breakdown with SVG Radar Chart -->
  <div class="card">
    <h2 style="font-size: 18px; margin-top: 0; margin-bottom: 16px;">Multidimensional Reliability Breakdown</h2>
    <div class="chart-layout">
      <!-- Pure SVG Radar Chart -->
      <div style="flex: 0 0 340px; text-align: center;">
        <svg width="340" height="340" viewBox="0 0 320 320">
          <!-- Background Grids -->
          {radar_grids}
          <!-- Filled Polygon -->
          {f'<polygon points="{radar_polygon}" fill="rgba(56, 189, 248, 0.25)" stroke="#38bdf8" stroke-width="2"/>' if radar_polygon else ""}
          <!-- Labels -->
          {radar_labels_svg}
        </svg>
      </div>

      <!-- Dimensions Table -->
      <div style="flex: 1; min-width: 300px;">
        <table>
          <thead>
            <tr><th>Dimension</th><th>Progress</th><th>Score</th><th>Weight</th><th>Status</th></tr>
          </thead>
          <tbody>
            {dim_rows}
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Root Causes & Failures Visualization -->
  <div class="card">
    <h2 style="font-size: 18px; margin-top: 0; margin-bottom: 16px;">Root Cause Diagnosis & Failure Insights</h2>
    {root_cause_cards}
  </div>

  <!-- Regression Comparison View -->
  <div class="card">
    <h2 style="font-size: 18px; margin-top: 0; margin-bottom: 16px;">Baseline vs Candidate Regression Analysis</h2>
    <table>
      <thead>
        <tr><th>Dimension</th><th>Baseline Score</th><th>Candidate Score</th><th>Delta</th></tr>
      </thead>
      <tbody>
        {reg_rows}
      </tbody>
    </table>
  </div>

  <!-- Test Assertions Drill-down -->
  <div class="card">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
      <h2 style="font-size: 18px; margin: 0;">Evaluation Test Assertions ({len(report.evaluations)})</h2>
      <div style="display: flex; gap: 8px; align-items: center;">
        <input type="text" id="searchInput" class="search-input" placeholder="Search assertions..." onkeyup="filterTable()">
        <button class="filter-btn active" onclick="setFilter('all', this)">All</button>
        <button class="filter-btn" onclick="setFilter('pass', this)">Passed</button>
        <button class="filter-btn" onclick="setFilter('fail', this)">Failed</button>
      </div>
    </div>
    <table>
      <thead>
        <tr><th>#</th><th>Evaluator</th><th>Verdict</th><th>Score</th><th>Latency</th><th>Message</th></tr>
      </thead>
      <tbody id="evalTableBody">
        {eval_rows}
      </tbody>
    </table>
  </div>
</div>

<script>
let currentFilter = 'all';
function setFilter(type, btn) {{
  currentFilter = type;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  filterTable();
}}

function filterTable() {{
  const query = document.getElementById('searchInput').value.toLowerCase();
  const rows = document.querySelectorAll('.eval-row');
  rows.forEach(row => {{
    const passed = row.getAttribute('data-passed') === 'true';
    const text = row.innerText.toLowerCase();
    const matchesFilter = (currentFilter === 'all') || (currentFilter === 'pass' && passed) || (currentFilter === 'fail' && !passed);
    const matchesSearch = text.includes(query);
    row.style.display = (matchesFilter && matchesSearch) ? '' : 'none';
  }});
}}
</script>
</body>
</html>
"""
        return html

    @staticmethod
    def render_junit_xml(
        report: EvaluationReport,
        score: UnifiedReliabilityScore | None = None,
        gate: GateResult | None = None,
    ) -> str:
        """Render standard JUnit XML format directly ingestible by CI/CD test runners."""
        total = max(1, len(report.evaluations))
        failures = sum(1 for e in report.evaluations if not e.passed)

        xml = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<testsuites name="AIReliability" tests="{total}" failures="{failures}" errors="0" time="0.0">',
            f'  <testsuite name="{xml_escape(report.target_name)}" tests="{total}" failures="{failures}" errors="0" time="0.0">',
        ]

        for idx, ev in enumerate(report.evaluations):
            classname = f"aireliability.evaluators.{xml_escape(ev.evaluator)}"
            name = f"test_eval_{idx}_{xml_escape(ev.metric or ev.evaluator)}"
            xml.append(
                f'    <testcase classname="{classname}" name="{name}" time="{ev.latency or 0.0}">'
            )
            if not ev.passed:
                msg = xml_escape(ev.message or "Evaluation assertion failed.")
                xml.append(
                    f'      <failure message="{msg}" type="AssertionError">{msg}</failure>'
                )
            xml.append("    </testcase>")

        xml.extend(["  </testsuite>", "</testsuites>"])
        return "\n".join(xml)

    @classmethod
    def export_report(
        cls,
        report: EvaluationReport,
        file_path: Path | str,
        fmt: str = "json",
        score: UnifiedReliabilityScore | None = None,
        gate: GateResult | None = None,
    ) -> None:
        """Export report to designated file in specified format (json, jsonl, csv, md, html, junit, pr-comment)."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fmt_lower = fmt.lower()

        if fmt_lower in ("json",):
            content = cls.render_json(report, score, gate)
        elif fmt_lower in ("jsonl",):
            content = cls.render_jsonl(report, score, gate)
        elif fmt_lower in ("csv",):
            content = cls.render_csv(report, score, gate)
        elif fmt_lower in ("md", "markdown"):
            content = cls.render_markdown(report, score, gate)
        elif fmt_lower in ("pr-comment", "pr_comment", "pr"):
            content = cls.render_pr_comment(report, score, gate)
        elif fmt_lower in ("html", "htm"):
            content = cls.render_html(report, score, gate)
        elif fmt_lower in ("junit", "xml", "junit_xml"):
            content = cls.render_junit_xml(report, score, gate)
        elif fmt_lower in ("cli", "txt", "text"):
            content = cls.render_cli(report, score, gate)
        else:
            raise ValueError(f"Unsupported report format: {fmt!r}")

        path.write_text(content, encoding="utf-8")

    @classmethod
    def serve_report(
        cls,
        report: EvaluationReport,
        score: UnifiedReliabilityScore | None = None,
        gate: GateResult | None = None,
        port: int = 8080,
    ) -> None:
        """Serve the interactive HTML dashboard locally using lightweight built-in HTTP server."""
        import http.server
        import socketserver

        html_content = cls.render_html(report, score, gate).encode("utf-8")

        class DashboardHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_content)))
                self.end_headers()
                self.wfile.write(html_content)

            def log_message(self, format: str, *args: Any) -> None:
                # Suppress verbose request logs to keep terminal clean
                pass

        with socketserver.TCPServer(("", port), DashboardHandler) as httpd:
            print(
                f"Serving AI Reliability Dashboard at http://localhost:{port}/ (Press Ctrl+C to stop)"
            )
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\nDashboard server stopped.")
