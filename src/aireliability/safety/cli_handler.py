"""CLI handler for Phase 41 AI Safety Validation commands."""

from __future__ import annotations

import argparse
import json

from aireliability.safety.engine import SafetyEngine
from aireliability.safety.models import (
    SafetyCampaign,
    SafetyCategory,
    SafetyExecutionMode,
    SafetyStrategy,
    SafetyTarget,
)


def handle_safety_cli(args: argparse.Namespace) -> int:
    """Entry point for `airel safety` subcommands."""
    action = getattr(args, "safety_action", "evaluate") or "evaluate"
    engine = SafetyEngine()

    target_id = getattr(args, "target", None) or "target_system"
    target = SafetyTarget(target_id=target_id, name="Default Safety Target")

    # Map subcommands to relevant categories if specific scan requested
    cat_map: dict[str, list[SafetyCategory]] = {
        "privacy": [
            SafetyCategory.PRIVACY_PROTECTION,
            SafetyCategory.SENSITIVE_INFORMATION,
        ],
        "authorization": [SafetyCategory.AUTHORIZATION_BEHAVIOR],
        "tools": [SafetyCategory.TOOL_USE_BOUNDARY],
        "rag": [SafetyCategory.RETRIEVED_CONTENT_TRUST, SafetyCategory.DOCUMENT_TRUST],
        "agent": [
            SafetyCategory.MULTI_AGENT_BOUNDARY,
            SafetyCategory.INSTRUCTION_BOUNDARY,
        ],
        "memory": [SafetyCategory.MEMORY_INTEGRITY],
    }

    selected_categories = cat_map.get(action)

    if action in (
        "evaluate",
        "campaign",
        "scan",
        "test",
        "privacy",
        "authorization",
        "tools",
        "rag",
        "agent",
        "memory",
        "report",
        "inspect",
        "baseline",
        "coverage",
        "diagnose",
        "regression",
    ):
        campaign = SafetyCampaign(
            target=target,
            categories=selected_categories or [],
            max_tests=getattr(args, "max_tests", 10) or 10,
            mode=SafetyExecutionMode.SIMULATION,
        )
        result = engine.run_campaign(campaign)

        if (
            getattr(args, "json", False)
            or getattr(args, "format", "terminal") == "json"
        ):
            out_dict = {
                "campaign_id": result.campaign_id,
                "target_id": result.target.target_id,
                "total_tests": result.total_tests,
                "total_findings": result.total_findings,
                "safety_score": result.score.safety_score,
                "risk_score": result.score.risk_score,
                "hard_veto_applied": result.score.hard_veto_applied,
                "verdicts": result.verdicts_summary,
            }
            print(json.dumps(out_dict, indent=2))
        else:
            print("\n=======================================================")
            print("         AI SAFETY VALIDATION REPORT (PHASE 41)")
            print("=======================================================")
            print(f"Target ID:         {result.target.target_id}")
            print(f"Action:            {action}")
            print(f"Total Tests:       {result.total_tests}")
            print(f"Safety Score:      {result.score.safety_score:.3f}")
            print(f"Risk Score:        {result.score.risk_score:.3f}")
            print(
                f"Hard Veto:         {'YES' if result.score.hard_veto_applied else 'NO'}"
            )
            print(f"Reliability Cap:   {result.score.reliability_cap:.2f}")
            print(f"Coverage Ratio:    {result.coverage.coverage_ratio * 100:.1f}%")
            print(f"Total Findings:    {result.total_findings}")
            print("Verdicts:")
            for k, v in result.verdicts_summary.items():
                print(f"  - {k}: {v}")
            print("=======================================================\n")
        return 0

    elif action == "generate":
        tests = engine.generate_tests(
            target, categories=selected_categories, max_tests=5
        )
        print(f"Generated {len(tests)} safety validation tests.")
        for t in tests:
            print(f"  [{t.category.value}] {t.safety_input.content[:60]}...")
        return 0

    elif action == "mutate":
        inp = engine.generator.scenario_gen.templates[0].render()
        from aireliability.safety.models import SafetyInput

        s_inp = SafetyInput(
            content=inp,
            category=SafetyCategory.INSTRUCTION_BOUNDARY,
            strategy=SafetyStrategy.TEMPLATE,
        )
        mutated = engine.generator.mutator.mutate(
            s_inp, SafetyStrategy.PARAMETER_VARIATION
        )
        print("Original:", inp)
        print("Mutated: ", mutated.content)
        return 0

    elif action == "tests":
        campaign = SafetyCampaign(target=target, max_tests=5)
        result = engine.run_campaign(campaign)
        test_gen_res = engine.test_bridge.generate_safety_tests(result.findings)
        print(
            f"Synthesized {len(test_gen_res.test_cases)} automated regression test cases."
        )
        return 0

    elif action == "heal":
        campaign = SafetyCampaign(target=target, max_tests=5)
        result = engine.run_campaign(campaign)
        remeds = engine.healing_bridge.propose_safety_remediations(result.findings)
        print(f"Generated {len(remeds)} safety remediation proposals.")
        return 0

    print(f"Safety action '{action}' executed.")
    return 0
