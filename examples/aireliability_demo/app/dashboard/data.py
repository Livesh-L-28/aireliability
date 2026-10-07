"""Unified Enterprise Reliability Intelligence Dashboard data provider."""

from __future__ import annotations

from typing import Any

from aireliability.dashboard.models import Dashboard
from aireliability.dashboard.service import DashboardBuilder, DashboardService


class DemoDashboardManager:
    """Unified dashboard manager providing multi-panel views and exports."""

    def __init__(self) -> None:
        self.service = DashboardService(builder=DashboardBuilder())

    def generate_dashboard(
        self,
        metrics: dict[str, Any] | None = None,
    ) -> tuple[Dashboard, str, str, str]:
        """Generate Dashboard object and JSON, Markdown, and HTML representations."""
        default_metrics = {
            "reliability": 0.96,
            "safety": 1.0,
            "security": 1.0,
            "rag": 0.94,
            "agent": 0.93,
            "quality": 0.95,
            "incidents": 0,
            "hard_veto": False,
            "total_failures": 0,
            "latency_p95": 0.38,
            "predicted_reliability": 0.95,
            "active_healing_rollouts": 1,
            "optimization_gain_pct": 8.5,
            "policy_decision": "ALLOW",
        }
        merged = {**default_metrics, **(metrics or {})}

        dashboard = self.service.get_dashboard(metrics=merged)
        json_out = self.service.export_json(dashboard)
        md_out = self.service.export_markdown(dashboard)

        # Lightweight HTML representation for local viewing
        health = dashboard.health_summary
        status_color = (
            "#10b981"
            if health.health_status == "HEALTHY"
            else ("#f59e0b" if health.health_status == "WARNING" else "#ef4444")
        )
        html_out = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>AI Reliability Platform Dashboard</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 2rem; background: #0f172a; color: #f8fafc; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; padding-bottom: 1rem; }}
        .badge {{ background: {status_color}; color: white; padding: 0.3rem 0.8rem; border-radius: 9999px; font-weight: bold; font-size: 0.9rem; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 1rem; margin-top: 1.5rem; }}
        .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 1rem; }}
        .card h3 {{ margin-top: 0; font-size: 0.9rem; color: #94a3b8; text-transform: uppercase; }}
        .value {{ font-size: 1.8rem; font-weight: bold; color: #38bdf8; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Enterprise Reliability Intelligence Dashboard</h1>
        <span class="badge">{health.health_status}</span>
    </div>
    <div class="grid">
        <div class="card"><h3>Overall Health</h3><div class="value">{health.overall_health:.2f}</div></div>
        <div class="card"><h3>Reliability Score</h3><div class="value">{health.reliability_score:.2f}</div></div>
        <div class="card"><h3>Safety Score</h3><div class="value">{health.safety_score:.2f}</div></div>
        <div class="card"><h3>Security Score</h3><div class="value">{health.security_score:.2f}</div></div>
        <div class="card"><h3>RAG Score</h3><div class="value">{health.rag_score:.2f}</div></div>
        <div class="card"><h3>Agent Score</h3><div class="value">{health.agent_score:.2f}</div></div>
        <div class="card"><h3>Active Incidents</h3><div class="value">{health.active_incidents_count}</div></div>
        <div class="card"><h3>Hard Veto Applied</h3><div class="value">{str(health.hard_veto_applied)}</div></div>
    </div>
</body>
</html>"""

        return dashboard, json_out, md_out, html_out
