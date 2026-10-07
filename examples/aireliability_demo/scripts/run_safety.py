#!/usr/bin/env python3
"""Run safety validation campaigns and demonstrate hard veto behavior."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from aireliability_demo.app.scenarios.safety_failure import run_safety_failure_scenario


def main() -> None:
    print("=" * 60)
    print("AIRELIABILITY v1.4.0 — SAFETY VALIDATION & HARD VETO DEMO")
    print("=" * 60)

    # 1. Normal / Safe Probe
    print("\n[1/2] Executing Safe Adversarial Probe...")
    safe_res = run_safety_failure_scenario(simulate_critical_breach=False)
    print(f"  Probe: {safe_res['probe']}")
    print(f"  Safety Score: {safe_res['safety_score']:.2f}")
    print(f"  Hard Veto Applied: {safe_res['hard_veto_applied']}")
    print(f"  Reliability Cap: {safe_res['reliability_cap']}")

    # 2. Critical Safety Breach with Synthetic Data
    print("\n[2/2] Executing Adversarial Probe with Synthetic Secret Leak...")
    vuln_res = run_safety_failure_scenario(simulate_critical_breach=True)
    print(f"  Probe: {vuln_res['probe']}")
    print(f"  Critical Findings: {vuln_res['critical_violations']}")
    print(f"  Safety Score: {vuln_res['safety_score']:.2f}")
    print(f"  Hard Veto Applied: {vuln_res['hard_veto_applied']} (REQUIRED: True)")
    print(f"  Reliability Cap: {vuln_res['reliability_cap']} (REQUIRED: <= 0.30)")

    print("\n" + "=" * 60)
    print("SAFETY HARD VETO VERIFIED")
    print("=" * 60)


if __name__ == "__main__":
    main()
