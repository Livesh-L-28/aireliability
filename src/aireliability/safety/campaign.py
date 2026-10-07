"""Automated safety campaign planner, runner, and result aggregator (Phase 41)."""

from __future__ import annotations

from typing import Any

from aireliability.safety.adapters import (
    OfflineSafetyAdapter,
    SafetyExecutionAdapter,
    SimulatedSafetyAdapter,
)
from aireliability.safety.analyzers import SafetyAnalyzer
from aireliability.safety.generators import SafetyTestGenerator
from aireliability.safety.models import (
    SafetyCampaign,
    SafetyCampaignResult,
    SafetyExecutionMode,
    SafetyFinding,
    SafetyRecommendation,
    SafetyRegression,
    SafetySeverity,
    SafetyTest,
    SafetyVerdict,
)
from aireliability.safety.scorer import SafetyScorer


class SafetyCampaignPlanner:
    """Plans safety validation campaigns based on target profile and requirements."""

    def plan_campaign(self, campaign: SafetyCampaign) -> list[SafetyTest]:
        """Generate test suite for the given campaign specification."""
        generator = SafetyTestGenerator(seed=campaign.deterministic_seed)
        return generator.generate_tests(
            target=campaign.target,
            categories=campaign.categories or None,
            strategies=campaign.strategies or None,
            max_tests=campaign.max_tests,
            mutation_budget=campaign.mutation_budget,
        )


class SafetyCampaignRunner:
    """Executes campaign test suites in safe sandboxed environments."""

    def __init__(
        self,
        adapter: SafetyExecutionAdapter | None = None,
        analyzer: SafetyAnalyzer | None = None,
        scorer: SafetyScorer | None = None,
    ) -> None:
        self.adapter = adapter
        self.analyzer = analyzer or SafetyAnalyzer()
        self.scorer = scorer or SafetyScorer()

    def run_campaign(
        self,
        campaign: SafetyCampaign,
        tests: list[SafetyTest] | None = None,
    ) -> SafetyCampaignResult:
        """Execute a full safety validation campaign and aggregate outcomes."""
        if tests is None:
            planner = SafetyCampaignPlanner()
            tests = planner.plan_campaign(campaign)

        # Resolve execution adapter according to campaign mode
        adapter = self.adapter
        if adapter is None:
            if campaign.mode == SafetyExecutionMode.OFFLINE:
                adapter = OfflineSafetyAdapter()
            else:
                adapter = SimulatedSafetyAdapter()

        all_findings: list[SafetyFinding] = []
        verdicts_summary: dict[str, int] = {}

        for test in tests:
            execution = adapter.execute(test)
            _obs, findings = self.analyzer.analyze(test, execution)
            all_findings.extend(findings)
            for f in findings:
                v_key = f.verdict.value
                verdicts_summary[v_key] = verdicts_summary.get(v_key, 0) + 1

        score, coverage = self.scorer.compute_score(tests, all_findings)

        # Generate recommendations and promote regressions for UNSAFE findings
        recommendations: list[SafetyRecommendation] = []
        regressions: list[SafetyRegression] = []

        for f in all_findings:
            if f.verdict == SafetyVerdict.UNSAFE:
                # Promote to regression test
                matching_test = next(
                    (t for t in tests if t.test_id == f.test_id), tests[0]
                )
                regressions.append(
                    SafetyRegression(
                        safety_test=matching_test,
                        initial_finding=f,
                    )
                )

                # Formulate remediation recommendation
                rec = SafetyRecommendation(
                    finding_id=f.finding_id,
                    action_type="input_guardrail"
                    if f.category.value == "INSTRUCTION_BOUNDARY"
                    else "boundary_hardening",
                    title=f"Harden {f.category.value} boundary",
                    description=f"Remediate finding: {f.message}",
                    priority=f.severity
                    if f.severity in (SafetySeverity.CRITICAL, SafetySeverity.HIGH)
                    else SafetySeverity.HIGH,
                    suggested_fix=f"Add pre-call validation guardrail or boundary filter for {f.category.value}.",
                )
                recommendations.append(rec)

        return SafetyCampaignResult(
            campaign_id=campaign.campaign_id,
            target=campaign.target,
            total_tests=len(tests),
            total_findings=len(all_findings),
            score=score,
            coverage=coverage,
            verdicts_summary=verdicts_summary,
            findings=all_findings,
            regressions_promoted=regressions,
            recommendations=recommendations,
        )


class SafetyCampaignAggregator:
    """Aggregates multiple campaign results across targets or historical runs."""

    def aggregate_campaigns(
        self,
        results: list[SafetyCampaignResult],
    ) -> dict[str, Any]:
        """Produce macro-level safety summary across multiple campaigns."""
        total_tests = sum(r.total_tests for r in results)
        total_findings = sum(r.total_findings for r in results)
        avg_score = (
            sum(r.score.safety_score for r in results) / len(results)
            if results
            else 1.0
        )
        hard_vetoes = sum(1 for r in results if r.score.hard_veto_applied)

        return {
            "campaigns_count": len(results),
            "total_tests": total_tests,
            "total_findings": total_findings,
            "average_safety_score": round(avg_score, 4),
            "hard_veto_count": hard_vetoes,
        }
