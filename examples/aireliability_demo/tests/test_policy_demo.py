"""Tests for Enterprise Policy Engine and Governance (Phase 44)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from aireliability_demo.app.reliability.integration import DemoReliabilityIntegrator

from aireliability.policy.models import PolicyDecision, PolicyPriority


def test_policy_allow_on_healthy_context() -> None:
    integrator = DemoReliabilityIntegrator()
    ctx = {
        "reliability_score": 0.95,
        "safety_score": 1.0,
        "credential_leakage": False,
        "latency_p95": 0.5,
    }
    eval_res = integrator.evaluate_policy(ctx)
    assert eval_res.decision == PolicyDecision.ALLOW
    assert len(eval_res.violations) == 0


def test_policy_block_on_critical_security_breach() -> None:
    integrator = DemoReliabilityIntegrator()
    ctx = {
        "reliability_score": 0.99,
        "safety_score": 1.0,
        "credential_leakage": True,
        "latency_p95": 0.5,
    }
    eval_res = integrator.evaluate_policy(ctx)
    assert eval_res.decision == PolicyDecision.BLOCK
    assert eval_res.effective_priority == PolicyPriority.SECURITY
    assert any(v.priority == PolicyPriority.SECURITY for v in eval_res.violations)


def test_policy_precedence_hierarchy() -> None:
    integrator = DemoReliabilityIntegrator()
    # Both a security violation (leakage) and performance violation (latency 10s)
    ctx = {
        "credential_leakage": True,
        "latency_p95": 10.0,
    }
    eval_res = integrator.evaluate_policy(ctx)
    # Security must strictly dominate performance
    assert eval_res.decision == PolicyDecision.BLOCK
    assert eval_res.effective_priority == PolicyPriority.SECURITY
