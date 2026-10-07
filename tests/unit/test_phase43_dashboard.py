"""Unit tests for Phase 43 Reliability Intelligence Dashboard."""

from __future__ import annotations

from aireliability.dashboard.health import ReliabilityHealthCalculator
from aireliability.dashboard.service import DashboardBuilder, DashboardService


def test_dashboard_builder_and_panels():
    builder = DashboardBuilder()
    dashboard = builder.build_dashboard(
        metrics={"reliability": 0.96, "safety": 1.0, "total_failures": 5}
    )
    assert dashboard.health_summary.overall_health > 0.8
    assert len(dashboard.panels) == 21
    assert dashboard.health_summary.health_status == "HEALTHY"


def test_dashboard_health_hard_veto():
    calc = ReliabilityHealthCalculator()
    # High reliability but safety compromised (0.2)
    summary = calc.calculate_health(
        reliability_score=0.99,
        safety_score=0.20,
        security_score=1.0,
    )
    assert summary.hard_veto_applied is True
    assert summary.overall_health <= 0.30
    assert summary.health_status == "COMPROMISED"


def test_dashboard_service_exports():
    service = DashboardService()
    dashboard = service.get_dashboard()

    json_out = service.export_json(dashboard)
    assert '"overall_health"' in json_out

    csv_out = service.export_csv(dashboard)
    assert "Panel,Metric Key,Metric Label,Value,Unit" in csv_out

    md_out = service.export_markdown(dashboard)
    assert "# Enterprise Reliability Intelligence" in md_out

    snap = service.create_snapshot(dashboard)
    assert snap.fingerprint() is not None
