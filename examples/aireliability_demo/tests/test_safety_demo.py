"""Tests for Safety validation, synthetic adversarial probes, and hard veto."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from aireliability_demo.app.scenarios.safety_failure import run_safety_failure_scenario


def test_safe_adversarial_probe() -> None:
    safe_res = run_safety_failure_scenario(simulate_critical_breach=False)
    assert safe_res["safety_score"] == 1.0
    assert safe_res["hard_veto_applied"] is False
    assert safe_res["reliability_cap"] == 1.0
    assert safe_res["critical_violations"] == 0


def test_critical_synthetic_breach_hard_veto() -> None:
    vuln_res = run_safety_failure_scenario(simulate_critical_breach=True)
    assert vuln_res["safety_score"] <= 0.30
    assert vuln_res["hard_veto_applied"] is True
    assert vuln_res["reliability_cap"] <= 0.30
    assert vuln_res["critical_violations"] == 1
    assert any("TEST_SECRET_123" in f["message"] for f in vuln_res["findings"])
