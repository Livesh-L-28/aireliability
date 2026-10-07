"""CLI handler for Phase 43 Reliability Intelligence Dashboard commands."""

from __future__ import annotations

import argparse

from aireliability.dashboard.service import DashboardService


def handle_dashboard_cli(args: argparse.Namespace) -> int:
    """Entry point for `airel dashboard` subcommands."""
    action = getattr(args, "dashboard_action", "overview") or "overview"
    service = DashboardService()
    dashboard = service.get_dashboard()

    if action == "export":
        fmt = getattr(args, "format", "json") or "json"
        if fmt == "csv":
            print(service.export_csv(dashboard))
        elif fmt == "markdown":
            print(service.export_markdown(dashboard))
        else:
            print(service.export_json(dashboard))
        return 0

    if action == "snapshot":
        snap = service.create_snapshot(dashboard)
        print(
            f"Snapshot created successfully: {snap.snapshot_id} (Fingerprint: {snap.fingerprint()})"
        )
        return 0

    if getattr(args, "json", False) or getattr(args, "format", "terminal") == "json":
        print(service.export_json(dashboard))
        return 0

    print("\n=======================================================")
    print("      RELIABILITY INTELLIGENCE DASHBOARD (PHASE 43)")
    print("=======================================================")
    print(
        f"System Health:      {dashboard.health_summary.overall_health:.2f} ({dashboard.health_summary.health_status})"
    )
    print(
        f"Hard Veto Applied:  {'YES' if dashboard.health_summary.hard_veto_applied else 'NO'}"
    )
    print(f"Active Incidents:   {dashboard.health_summary.active_incidents_count}")
    print(f"Active Alerts:      {dashboard.health_summary.active_alerts_count}")
    print("-------------------------------------------------------")
    print("Subsystem Scores:")
    print(f"  - Reliability:    {dashboard.health_summary.reliability_score:.2f}")
    print(f"  - Safety:         {dashboard.health_summary.safety_score:.2f}")
    print(f"  - Security:       {dashboard.health_summary.security_score:.2f}")
    print(f"  - Agent Success:  {dashboard.health_summary.agent_score:.2f}")
    print(f"  - RAG Quality:    {dashboard.health_summary.rag_score:.2f}")
    print(f"  - Output Quality: {dashboard.health_summary.quality_score:.2f}")
    print(f"Panels Available:   {len(dashboard.panels)}")
    print("=======================================================\n")

    return 0
