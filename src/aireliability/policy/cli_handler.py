"""CLI handler for Phase 44 Reliability Policy Engine commands."""

from __future__ import annotations

import argparse
import json

from aireliability.policy.engine import PolicyEngine


def handle_policy_cli(args: argparse.Namespace) -> int:
    """Entry point for `airel policy` subcommands."""
    action = getattr(args, "policy_action", "list") or "list"
    engine = PolicyEngine()

    if action == "list":
        pol = engine.default_policy
        if (
            getattr(args, "json", False)
            or getattr(args, "format", "terminal") == "json"
        ):
            print(json.dumps(pol.model_dump(), default=str, indent=2))
            return 0
        print("\n=======================================================")
        print("          RELIABILITY POLICIES (PHASE 44)")
        print("=======================================================")
        print(f"Policy: {pol.name} (v{pol.version}) [{pol.scope.value}]")
        print(f"Total Rules: {len(pol.rules)}")
        for r in pol.rules:
            hard_tag = " [HARD]" if r.is_hard_constraint else ""
            print(
                f"  - [{r.priority.value}] {r.name}: {r.action.decision.value}{hard_tag}"
            )
        print("=======================================================\n")
        return 0

    # Evaluate / simulate
    # Mock context or read from arguments
    ctx = {
        "reliability_score": float(getattr(args, "reliability", 0.95)),
        "safety_score": float(getattr(args, "safety", 1.0)),
        "credential_leakage": getattr(args, "leakage", False),
        "cross_tenant_access": getattr(args, "cross_tenant", False),
    }
    evaluation = engine.evaluate(ctx)

    if getattr(args, "json", False) or getattr(args, "format", "terminal") == "json":
        print(json.dumps(evaluation.model_dump(), default=str, indent=2))
    else:
        print("\n=======================================================")
        print("         POLICY EVALUATION REPORT (PHASE 44)")
        print("=======================================================")
        print(f"Decision:            {evaluation.decision.value}")
        print(f"Effective Priority:  {evaluation.effective_priority.value}")
        print(f"Violations:          {len(evaluation.violations)}")
        for v in evaluation.violations:
            print(f"  ! [{v.priority.value}] {v.rule_name}: {v.message}")
        print(f"Explanation:         {evaluation.explanation}")
        print("=======================================================\n")

    return 0 if evaluation.decision.value != "BLOCK" else 1
