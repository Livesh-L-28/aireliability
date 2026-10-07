"""Policy precedence, non-bypassable hard constraints, and priority testing."""

from __future__ import annotations

from aireliability.policy.engine import PRIORITY_PRECEDENCE, PolicyEngine
from aireliability.policy.models import (
    PolicyAction,
    PolicyCondition,
    PolicyDecision,
    PolicyOperator,
    PolicyPriority,
    PolicyRule,
    ReliabilityPolicy,
)


def test_strict_priority_precedence_ordering():
    """Verify numeric priority precedence ordering is strictly maintained."""
    assert (
        PRIORITY_PRECEDENCE[PolicyPriority.SECURITY]
        < PRIORITY_PRECEDENCE[PolicyPriority.SAFETY]
    )
    assert (
        PRIORITY_PRECEDENCE[PolicyPriority.SAFETY]
        < PRIORITY_PRECEDENCE[PolicyPriority.TENANT_ISOLATION]
    )
    assert (
        PRIORITY_PRECEDENCE[PolicyPriority.TENANT_ISOLATION]
        < PRIORITY_PRECEDENCE[PolicyPriority.AUTHORIZATION]
    )
    assert (
        PRIORITY_PRECEDENCE[PolicyPriority.AUTHORIZATION]
        < PRIORITY_PRECEDENCE[PolicyPriority.COMPLIANCE]
    )
    assert (
        PRIORITY_PRECEDENCE[PolicyPriority.COMPLIANCE]
        < PRIORITY_PRECEDENCE[PolicyPriority.RELIABILITY]
    )
    assert (
        PRIORITY_PRECEDENCE[PolicyPriority.RELIABILITY]
        < PRIORITY_PRECEDENCE[PolicyPriority.PERFORMANCE]
    )
    assert (
        PRIORITY_PRECEDENCE[PolicyPriority.PERFORMANCE]
        < PRIORITY_PRECEDENCE[PolicyPriority.COST]
    )


def test_lower_priority_rule_cannot_override_security_block():
    """Verify that a lower-priority ALLOW or WARN rule cannot override a SECURITY BLOCK."""
    engine = PolicyEngine()

    rule_sec = PolicyRule(
        name="Security Hard Constraint",
        priority=PolicyPriority.SECURITY,
        is_hard_constraint=True,
        conditions=[
            PolicyCondition(
                field="secret_leaked",
                operator=PolicyOperator.EQ,
                target_value=True,
            )
        ],
        action=PolicyAction(decision=PolicyDecision.BLOCK, message="Secret leaked!"),
    )

    rule_cost = PolicyRule(
        name="Cost Optimization Allow",
        priority=PolicyPriority.COST,
        is_hard_constraint=False,
        conditions=[
            PolicyCondition(
                field="cost_savings",
                operator=PolicyOperator.GT,
                target_value=100.0,
            )
        ],
        action=PolicyAction(decision=PolicyDecision.ALLOW, message="Massive savings!"),
    )

    policy = ReliabilityPolicy(
        name="Precedence Test Policy",
        rules=[rule_cost, rule_sec],  # Defined in reverse order intentionally
    )

    context = {
        "secret_leaked": True,
        "cost_savings": 500.0,
    }

    eval_result = engine.evaluate(context, policy=policy)
    assert eval_result.decision == PolicyDecision.BLOCK
    assert eval_result.effective_priority == PolicyPriority.SECURITY
    assert "Secret leaked" in eval_result.violations[0].message


def test_safety_and_tenant_isolation_hard_blocks():
    """Verify SAFETY and TENANT_ISOLATION hard rules cannot be bypassed by high performance."""
    engine = PolicyEngine()

    context_safety_breach = {
        "safety_score": 0.15,  # triggers hard veto <= 0.30
        "latency_p95": 0.05,  # excellent performance
        "reliability_score": 0.99,  # excellent reliability
    }

    eval_result = engine.evaluate(context_safety_breach)
    assert eval_result.decision == PolicyDecision.BLOCK
    assert eval_result.effective_priority == PolicyPriority.SAFETY

    context_tenant_breach = {
        "cross_tenant_access": True,
        "reliability_score": 0.99,
    }

    eval_result_tenant = engine.evaluate(context_tenant_breach)
    assert eval_result_tenant.decision == PolicyDecision.BLOCK
    assert eval_result_tenant.effective_priority == PolicyPriority.TENANT_ISOLATION


def test_authorization_block_precedes_performance_and_cost():
    """Verify unauthorized actions are blocked even if cost and latency metrics are optimal."""
    engine = PolicyEngine()

    context = {
        "unauthorized_tool": True,
        "latency_p95": 0.1,
        "cost": 0.0,
    }

    eval_result = engine.evaluate(context)
    assert eval_result.decision == PolicyDecision.BLOCK
    assert eval_result.effective_priority == PolicyPriority.AUTHORIZATION
