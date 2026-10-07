"""Dashboard query, service, builder, and export implementation (Phase 43)."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from aireliability.dashboard.health import ReliabilityHealthCalculator
from aireliability.dashboard.models import (
    Dashboard,
    DashboardAlert,
    DashboardFilter,
    DashboardSnapshot,
    DashboardTimeRange,
)
from aireliability.dashboard.panels import DashboardPanelBuilder


class DashboardBuilder:
    """Builds unified Dashboard instances from multi-subsystem intelligence."""

    def __init__(self) -> None:
        self.health_calculator = ReliabilityHealthCalculator()
        self.panel_builder = DashboardPanelBuilder()

    def build_dashboard(
        self,
        metrics: dict[str, Any] | None = None,
        alerts: list[DashboardAlert] | None = None,
        time_range: DashboardTimeRange | None = None,
        filters: DashboardFilter | None = None,
    ) -> Dashboard:
        """Construct a complete, populated Dashboard."""
        m = metrics or {}
        health = self.health_calculator.calculate_health(
            reliability_score=m.get("reliability", 0.95),
            safety_score=m.get("safety", 1.0),
            security_score=m.get("security", 1.0),
            rag_score=m.get("rag", 0.92),
            agent_score=m.get("agent", 0.94),
            quality_score=m.get("quality", 0.93),
            active_incidents=m.get("incidents", 0),
            active_alerts=len(alerts or []),
            hard_veto_flag=m.get("hard_veto", False),
        )
        panels = self.panel_builder.build_all_panels(m)

        return Dashboard(
            health_summary=health,
            panels=panels,
            alerts=alerts or [],
            time_range=time_range or DashboardTimeRange(),
            filters=filters or DashboardFilter(),
        )


class DashboardService:
    """Service layer for querying dashboards, snapshots, and generating exports."""

    def __init__(self, builder: DashboardBuilder | None = None) -> None:
        self.builder = builder or DashboardBuilder()
        self._snapshots: list[DashboardSnapshot] = []

    def get_dashboard(self, metrics: dict[str, Any] | None = None) -> Dashboard:
        """Retrieve current live dashboard."""
        return self.builder.build_dashboard(metrics=metrics)

    def create_snapshot(self, dashboard: Dashboard) -> DashboardSnapshot:
        """Create a deterministic snapshot from the dashboard."""
        snap = DashboardSnapshot(
            health=dashboard.health_summary,
            safety_status="SAFE"
            if dashboard.health_summary.safety_score > 0.8
            else "RISK_DETECTED",
            prediction_status="STABLE",
            active_incidents=[
                f"Incident-{i}"
                for i in range(dashboard.health_summary.active_incidents_count)
            ],
            top_failures=[],
            recommendations=["Maintain proactive regression testing."],
        )
        self._snapshots.append(snap)
        return snap

    def export_json(self, dashboard: Dashboard) -> str:
        """Export dashboard data as structured JSON."""
        return json.dumps(dashboard.model_dump(), default=str, indent=2)

    def export_csv(self, dashboard: Dashboard) -> str:
        """Export key metrics table as CSV."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Panel", "Metric Key", "Metric Label", "Value", "Unit"])

        for p in dashboard.panels:
            for w in p.widgets:
                for m in w.metrics:
                    writer.writerow([p.title, m.key, m.label, m.value, m.unit])

        return output.getvalue()

    def export_markdown(self, dashboard: Dashboard) -> str:
        """Export dashboard as structured Markdown report."""
        lines = [
            f"# {dashboard.name}",
            f"**Generated:** {dashboard.generated_at.isoformat()}",
            f"**Overall Health:** {dashboard.health_summary.overall_health:.2f} ({dashboard.health_summary.health_status})",
            "",
            "## Subsystem Scores",
            f"- Reliability: {dashboard.health_summary.reliability_score:.2f}",
            f"- Quality:     {dashboard.health_summary.quality_score:.2f}",
            f"- Safety:      {dashboard.health_summary.safety_score:.2f}",
            f"- Security:    {dashboard.health_summary.security_score:.2f}",
            f"- Agent:       {dashboard.health_summary.agent_score:.2f}",
            f"- RAG:         {dashboard.health_summary.rag_score:.2f}",
            "",
            "## Panels Summary",
        ]
        for p in dashboard.panels:
            lines.append(f"### {p.title}")
            for w in p.widgets:
                for m in w.metrics:
                    lines.append(f"- **{m.label}**: {m.value} {m.unit}")
        return "\n".join(lines)


class DashboardRegistry:
    """In-memory registry of named dashboards."""

    def __init__(self) -> None:
        self._dashboards: dict[str, Dashboard] = {}

    def register(self, name: str, dashboard: Dashboard) -> None:
        self._dashboards[name] = dashboard

    def get(self, name: str) -> Dashboard | None:
        return self._dashboards.get(name)

    def list_names(self) -> list[str]:
        return list(self._dashboards.keys())


class DashboardQuery:
    """Filters and queries dashboard metrics."""

    @staticmethod
    def filter_panels(dashboard: Dashboard, category: str) -> list[Any]:
        return [p for p in dashboard.panels if p.category == category]
