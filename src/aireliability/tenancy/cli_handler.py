"""CLI handler for Phase 45 Enterprise Multi-Tenancy commands."""

from __future__ import annotations

import argparse
import json

from aireliability.tenancy.models import Tenant
from aireliability.tenancy.usage import UsageTracker


def handle_tenant_cli(args: argparse.Namespace) -> int:
    """Entry point for `airel tenant` subcommands."""
    action = getattr(args, "tenant_action", "list") or "list"
    tracker = UsageTracker()

    # Predefined mock tenant registry for CLI inspection
    sample_tenant = Tenant(
        tenant_id=getattr(args, "tenant", "tenant_alpha"),
        organization_id="org_enterprise",
        name="Enterprise Tenant Alpha",
    )

    if action in ("list", "get"):
        if (
            getattr(args, "json", False)
            or getattr(args, "format", "terminal") == "json"
        ):
            print(json.dumps([sample_tenant.model_dump()], default=str, indent=2))
        else:
            print("\n=======================================================")
            print("         ENTERPRISE MULTI-TENANCY (PHASE 45)")
            print("=======================================================")
            print(f"Tenant ID:       {sample_tenant.tenant_id}")
            print(f"Organization:    {sample_tenant.organization_id}")
            print(f"Tenant Name:     {sample_tenant.name}")
            print(
                f"Status:          {'Enabled' if sample_tenant.enabled else 'Disabled'}"
            )
            print("=======================================================\n")
        return 0

    elif action == "quotas":
        quota = tracker.get_quota(sample_tenant.tenant_id)
        print(f"Quotas for {sample_tenant.tenant_id}:")
        print(f"  - Max Evaluations: {quota.max_evaluations}")
        print(f"  - Max API Requests: {quota.max_api_requests}")
        print(f"  - Max Safety Tests: {quota.max_safety_tests}")
        return 0

    elif action == "usage":
        usage = tracker.get_usage(sample_tenant.tenant_id)
        print(f"Usage for {sample_tenant.tenant_id}:")
        print(f"  - Evaluations: {usage.evaluations_count}")
        print(f"  - Requests:    {usage.requests_count}")
        print(f"  - Tests Run:   {usage.safety_tests_run}")
        return 0

    print(f"Tenant action '{action}' completed.")
    return 0
