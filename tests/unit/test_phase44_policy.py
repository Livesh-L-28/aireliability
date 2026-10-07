"""Unit tests for Phase 44 Reliability Policy Engine."""

from __future__ import annotations

from aireliability.policy.engine import PolicyEngine
from aireliability.policy.models import (
    PolicyDecision,
    PolicyPriority,
)


def test_policy_engine_allow_on_healthy_context():
    engine = PolicyEngine()
    ctx = {
        "reliability_score": 0.95,
        "safety_score": 1.0,
        "credential_leakage": False,
        "latency_p95": 1.2,
    }
    evaluation = engine.evaluate(ctx)
    assert evaluation.decision == PolicyDecision.ALLOW
    assert len(evaluation.violations) == 0


def test_policy_engine_block_on_critical_security_breach():
    engine = PolicyEngine()
    # Even if reliability is perfect (1.0), credential leakage triggers hard security BLOCK
    ctx = {
        "reliability_score": 1.0,
        "safety_score": 1.0,
        "credential_leakage": True,
    }
    evaluation = engine.evaluate(ctx)
    assert evaluation.decision == PolicyDecision.BLOCK
    assert evaluation.effective_priority == PolicyPriority.SECURITY
    assert any(v.priority == PolicyPriority.SECURITY for v in evaluation.violations)


def test_policy_engine_priority_precedence():
    engine = PolicyEngine()
    # Security violation (credential_leakage) and performance violation (latency_p95=10s)
    # Security must strictly dominate performance
    ctx = {
        "credential_leakage": True,
        "latency_p95": 10.0,
    }
    evaluation = engine.evaluate(ctx)
    assert evaluation.decision == PolicyDecision.BLOCK
    assert evaluation.effective_priority == PolicyPriority.SECURITY
