"""Enforceable policy evaluation engine with strict priority precedence (Phase 44)."""

from __future__ import annotations

import logging
from typing import Any

from aireliability.policy.models import (
    PolicyAction,
    PolicyCondition,
    PolicyDecision,
    PolicyEvaluation,
    PolicyOperator,
    PolicyPriority,
    PolicyRule,
    PolicyScope,
    PolicyViolation,
    ReliabilityPolicy,
)

logger = logging.getLogger(__name__)


# Priority precedence rank: lower number = higher precedence
PRIORITY_PRECEDENCE = {
    PolicyPriority.SECURITY: 0,
    PolicyPriority.SAFETY: 1,
    PolicyPriority.TENANT_ISOLATION: 2,
    PolicyPriority.AUTHORIZATION: 3,
    PolicyPriority.COMPLIANCE: 4,
    PolicyPriority.RELIABILITY: 5,
    PolicyPriority.PERFORMANCE: 6,
    PolicyPriority.COST: 7,
}


class PolicyEngine:
    """Enterprise policy engine evaluating reliability rules and hard constraints."""

    def __init__(self, default_policy: ReliabilityPolicy | None = None) -> None:
        self.default_policy = default_policy or self._build_default_policy()

    def _build_default_policy(self) -> ReliabilityPolicy:
        """Construct standard default policy with built-in hard constraints."""
        rules = [
            # 1. SECURITY: Block on credential leakage
            PolicyRule(
                name="Security - No Credential Leakage",
                description="Block execution if credentials or secrets are detected in output",
                priority=PolicyPriority.SECURITY,
                is_hard_constraint=True,
                conditions=[
                    PolicyCondition(
                        field="credential_leakage",
                        operator=PolicyOperator.EQ,
                        target_value=True,
                    )
                ],
                action=PolicyAction(
                    decision=PolicyDecision.BLOCK,
                    message="Credential leakage detected in trace",
                ),
            ),
            # 2. SAFETY: Block on critical safety violation
            PolicyRule(
                name="Safety - Hard Veto Constraint",
                description="Block execution if critical safety boundary is breached",
                priority=PolicyPriority.SAFETY,
                is_hard_constraint=True,
                conditions=[
                    PolicyCondition(
                        field="safety_score",
                        operator=PolicyOperator.LTE,
                        target_value=0.30,
                    )
                ],
                action=PolicyAction(
                    decision=PolicyDecision.BLOCK,
                    message="Safety score fell below hard threshold 0.30",
                ),
            ),
            # 3. TENANT ISOLATION: Block on cross-tenant access
            PolicyRule(
                name="Tenancy - Cross Tenant Access Prevention",
                description="Block any cross-tenant data traversal attempt",
                priority=PolicyPriority.TENANT_ISOLATION,
                is_hard_constraint=True,
                conditions=[
                    PolicyCondition(
                        field="cross_tenant_access",
                        operator=PolicyOperator.EQ,
                        target_value=True,
                    )
                ],
                action=PolicyAction(
                    decision=PolicyDecision.BLOCK,
                    message="Cross-tenant access attempt prohibited",
                ),
            ),
            # 4. AUTHORIZATION: Block unauthorized tool execution
            PolicyRule(
                name="Authorization - Unauthorized Tool",
                description="Block invocation of forbidden tool",
                priority=PolicyPriority.AUTHORIZATION,
                is_hard_constraint=True,
                conditions=[
                    PolicyCondition(
                        field="unauthorized_tool",
                        operator=PolicyOperator.EQ,
                        target_value=True,
                    )
                ],
                action=PolicyAction(
                    decision=PolicyDecision.BLOCK,
                    message="Unauthorized tool execution attempted",
                ),
            ),
            # 5. RELIABILITY: Require review if reliability score drops below 0.70
            PolicyRule(
                name="Reliability - Minimum Standard",
                description="Require review if reliability degrades below 0.70",
                priority=PolicyPriority.RELIABILITY,
                conditions=[
                    PolicyCondition(
                        field="reliability_score",
                        operator=PolicyOperator.LT,
                        target_value=0.70,
                    )
                ],
                action=PolicyAction(
                    decision=PolicyDecision.REQUIRE_REVIEW,
                    message="Reliability dropped below 0.70",
                ),
            ),
            # 6. PERFORMANCE: Warn if P95 latency exceeds 5.0 seconds
            PolicyRule(
                name="Performance - High Latency Warning",
                description="Warn if latency exceeds 5.0s",
                priority=PolicyPriority.PERFORMANCE,
                conditions=[
                    PolicyCondition(
                        field="latency_p95",
                        operator=PolicyOperator.GT,
                        target_value=5.0,
                    )
                ],
                action=PolicyAction(
                    decision=PolicyDecision.WARN,
                    message="P95 latency exceeded 5.0 seconds",
                ),
            ),
        ]
        return ReliabilityPolicy(
            name="Default Enterprise Reliability Policy",
            version="1.0.0",
            scope=PolicyScope.GLOBAL,
            rules=rules,
        )

    def _eval_condition(
        self, condition: PolicyCondition, context: dict[str, Any]
    ) -> bool:
        """Evaluate a single condition against input context."""
        val = context.get(condition.field)
        if val is None:
            return False

        op = condition.operator
        target = condition.target_value

        try:
            if op == PolicyOperator.EQ:
                return bool(val == target)
            elif op == PolicyOperator.NEQ:
                return bool(val != target)
            elif op == PolicyOperator.LT:
                return bool(val < target)
            elif op == PolicyOperator.LTE:
                return bool(val <= target)
            elif op == PolicyOperator.GT:
                return bool(val > target)
            elif op == PolicyOperator.GTE:
                return bool(val >= target)
            elif op == PolicyOperator.IN:
                return bool(val in target)
            elif op == PolicyOperator.CONTAINS:
                return bool(target in val)
        except Exception:
            return False
        return False

    def evaluate(
        self,
        context: dict[str, Any],
        policy: ReliabilityPolicy | None = None,
        actor: str = "system",
        tenant_id: str | None = None,
    ) -> PolicyEvaluation:
        """Evaluate all policy rules enforcing strict priority precedence."""
        active_policy = policy or self.default_policy
        triggered_rules: list[str] = []
        violations: list[PolicyViolation] = []

        # Sort rules strictly by precedence (lower rank number = higher precedence)
        sorted_rules = sorted(
            active_policy.rules,
            key=lambda r: PRIORITY_PRECEDENCE.get(r.priority, 99),
        )

        final_decision = PolicyDecision.ALLOW
        effective_priority = PolicyPriority.COST

        for rule in sorted_rules:
            # Check if all conditions match
            matches = all(self._eval_condition(c, context) for c in rule.conditions)
            if matches and rule.conditions:
                triggered_rules.append(rule.name)
                # Formulate violation
                for c in rule.conditions:
                    v = PolicyViolation(
                        rule_id=rule.rule_id,
                        rule_name=rule.name,
                        priority=rule.priority,
                        field=c.field,
                        threshold=c.target_value,
                        observed_value=context.get(c.field),
                        message=rule.action.message,
                    )
                    violations.append(v)

                # Decisions: BLOCK > REQUIRE_APPROVAL > REQUIRE_REVIEW > QUARANTINE > WARN > ALLOW
                rule_dec = rule.action.decision
                if rule_dec == PolicyDecision.BLOCK:
                    final_decision = PolicyDecision.BLOCK
                    effective_priority = rule.priority
                    # Hard constraint stops further overriding
                    break
                elif (
                    rule_dec
                    in (PolicyDecision.REQUIRE_APPROVAL, PolicyDecision.REQUIRE_REVIEW)
                    and final_decision != PolicyDecision.BLOCK
                ):
                    final_decision = rule_dec
                    effective_priority = rule.priority
                elif (
                    rule_dec == PolicyDecision.WARN
                    and final_decision == PolicyDecision.ALLOW
                ):
                    final_decision = PolicyDecision.WARN
                    effective_priority = rule.priority

        explanation = (
            f"Policy '{active_policy.name}' evaluated {len(sorted_rules)} rules. "
            f"Decision: {final_decision.value} governed by priority {effective_priority.value}. "
            f"Violations observed: {len(violations)}."
        )

        return PolicyEvaluation(
            policy_id=active_policy.policy_id,
            policy_version=active_policy.version,
            decision=final_decision,
            effective_priority=effective_priority,
            triggered_rules=triggered_rules,
            violations=violations,
            explanation=explanation,
            actor=actor,
            tenant_id=tenant_id,
        )
