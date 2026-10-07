#!/usr/bin/env python3
"""Scenario CLI runner for AI Reliability Demonstration.

Usage:
    python scripts/run_demo.py --scenario normal
    python scripts/run_demo.py --scenario llm_failure
    python scripts/run_demo.py --scenario rag_failure
    python scripts/run_demo.py --scenario agent_failure
    python scripts/run_demo.py --scenario safety_failure
    python scripts/run_demo.py --scenario regression
    python scripts/run_demo.py --scenario rag_failure --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from aireliability_demo.app.dashboard.data import DemoDashboardManager
from aireliability_demo.app.reliability.integration import DemoReliabilityIntegrator
from aireliability_demo.app.scenarios.agent_failure import run_agent_failure_scenario
from aireliability_demo.app.scenarios.normal import run_normal_scenario
from aireliability_demo.app.scenarios.rag_failure import run_rag_failure_scenario
from aireliability_demo.app.scenarios.regression import run_regression_scenario
from aireliability_demo.app.scenarios.reliability_failure import (
    run_llm_failure_scenario,
)
from aireliability_demo.app.scenarios.safety_failure import run_safety_failure_scenario


def execute_scenario(scenario_name: str) -> dict:
    """Execute scenario and run through Intelligence -> Root Cause -> Test Gen -> Prediction -> Policy -> Dashboard."""
    integrator = DemoReliabilityIntegrator()
    dash_mgr = DemoDashboardManager()
    sc = scenario_name.lower()

    if sc == "normal":
        raw_res = run_normal_scenario()
        failures = []
        status = "PASSED"
    elif sc == "llm_failure":
        raw_res = run_llm_failure_scenario("HALLUCINATION")
        failures = raw_res["failures"]
        status = "FAILED"
    elif sc == "rag_failure":
        raw_res = run_rag_failure_scenario("GROUNDING_FAILURE")
        failures = raw_res["failures"]
        status = "FAILED"
    elif sc == "agent_failure":
        raw_res = run_agent_failure_scenario("RUNAWAY_LOOP")
        failures = raw_res["failures"]
        status = "FAILED"
    elif sc == "safety_failure":
        raw_res = run_safety_failure_scenario(simulate_critical_breach=True)
        failures = raw_res.get("failure_reports", [])
        status = "BLOCKED"
    elif sc == "regression":
        raw_res = run_regression_scenario()
        failures = raw_res["failure_reports"]
        status = "REGRESSION"
    else:
        raise ValueError(f"Unknown scenario: {scenario_name}")

    # Intelligence & Root Cause (Phase 34)
    if failures:
        analysis, expl = integrator.analyze_failures(failures, target_name=f"demo_{sc}")
        clusters_count = analysis.summary.total_clusters
        recommendations = analysis.recommendations
        root_cause_summary = str(
            expl.get("questions", {}).get("2_why_did_it_fail", "Unknown")
        )
        # Regression Test Generation (Phase 36)
        test_gen = integrator.generate_regression_tests(failures)
        generated_tests_count = test_gen.total_validated
        # Self-Healing Remediation (Phase 37)
        proposal, sim = integrator.remediate_failure(failures[0])
        healing_summary = {
            "proposal_id": proposal.proposal_id,
            "repair_type": proposal.repair_type.value,
            "simulated_success": sim.passed,
        }
    else:
        clusters_count = 0
        recommendations = ["Continue standard operational monitoring."]
        root_cause_summary = "None (clean execution)"
        generated_tests_count = 0
        healing_summary = {"status": "NO_REMEDIATION_NEEDED"}

    # Reliability Prediction (Phase 42)
    history = [0.95, 0.94, 0.92, 0.90] if failures else [0.98, 0.98, 0.99, 0.99]
    pred = integrator.predict_reliability(history, target_id=f"demo_{sc}")

    # Policy Evaluation (Phase 44)
    policy_ctx = {
        "reliability_score": pred.reliability_forecast.forecasted_value,
        "safety_score": 0.20 if sc == "safety_failure" else 1.0,
        "credential_leakage": sc == "safety_failure",
        "latency_p95": 0.50 if sc != "regression" else 2.5,
    }
    policy_eval = integrator.evaluate_policy(policy_ctx)

    # Dashboard (Phase 43)
    dash, _j, _m, _h = dash_mgr.generate_dashboard(
        {
            "reliability": 0.50 if failures else 0.98,
            "safety": 0.20 if sc == "safety_failure" else 1.0,
            "hard_veto": sc == "safety_failure",
            "total_failures": len(failures),
        }
    )

    return {
        "scenario": sc,
        "status": status,
        "failures_detected": len(failures),
        "intelligence": {
            "clusters": clusters_count,
            "root_cause": root_cause_summary,
            "recommendations_count": len(recommendations),
        },
        "regression_tests_generated": generated_tests_count,
        "self_healing": healing_summary,
        "prediction": {
            "forecasted_reliability": round(
                pred.reliability_forecast.forecasted_value, 4
            ),
            "trend": pred.risk_forecast.trend.value,
            "confidence": round(pred.confidence.confidence, 4),
        },
        "policy": {
            "decision": policy_eval.decision.value,
            "effective_priority": policy_eval.effective_priority.name,
            "violations": [v.rule_id for v in policy_eval.violations],
        },
        "dashboard_health": dash.health_summary.health_status,
        "overall_health_score": round(dash.health_summary.overall_health, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Reliability Scenario Runner")
    parser.add_argument(
        "--scenario",
        type=str,
        default="normal",
        choices=[
            "normal",
            "llm_failure",
            "rag_failure",
            "agent_failure",
            "safety_failure",
            "regression",
        ],
        help="Controlled scenario to execute",
    )
    parser.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    args = parser.parse_args()

    result = execute_scenario(args.scenario)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("=" * 60)
        print(f"AIRELIABILITY v1.4.0 — SCENARIO EXECUTION: {args.scenario.upper()}")
        print("=" * 60)
        print(f"Status:                      {result['status']}")
        print(f"Failures Detected:           {result['failures_detected']}")
        print(f"Failure Clusters (Ph 34):    {result['intelligence']['clusters']}")
        print(
            f"Root Cause:                  {result['intelligence']['root_cause'][:50]}..."
        )
        print(f"Tests Generated (Ph 36):     {result['regression_tests_generated']}")
        print(
            f"Self-Healing (Ph 37):        {result['self_healing'].get('repair_type', 'NONE')}"
        )
        print(
            f"Reliability Forecast (Ph 42): {result['prediction']['forecasted_reliability']} ({result['prediction']['trend']})"
        )
        print(
            f"Policy Decision (Ph 44):     {result['policy']['decision']} (Priority: {result['policy']['effective_priority']})"
        )
        print(
            f"Dashboard Health (Ph 43):    {result['dashboard_health']} ({result['overall_health_score']:.2f})"
        )
        print("=" * 60)
        print("SCENARIO EXECUTION COMPLETE")
        print("=" * 60)


if __name__ == "__main__":
    main()
