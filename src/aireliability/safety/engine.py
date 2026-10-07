"""Main orchestrator engine for AI Safety Validation (Phase 41)."""

from __future__ import annotations

import logging

from aireliability.safety.adapters import (
    OfflineSafetyAdapter,
    SafetyExecutionAdapter,
    SimulatedSafetyAdapter,
)
from aireliability.safety.analyzers import SafetyAnalyzer
from aireliability.safety.campaign import SafetyCampaignPlanner, SafetyCampaignRunner
from aireliability.safety.generators import SafetyTestGenerator
from aireliability.safety.graph_bridge import SafetyGraphBridge
from aireliability.safety.healing_bridge import SafetyHealingBridge
from aireliability.safety.models import (
    SafetyCampaign,
    SafetyCampaignResult,
    SafetyCategory,
    SafetyExecution,
    SafetyExecutionMode,
    SafetyFinding,
    SafetyObservation,
    SafetyReport,
    SafetyStrategy,
    SafetyTarget,
    SafetyTest,
)
from aireliability.safety.observability_bridge import SafetyObservabilityBridge
from aireliability.safety.scorer import SafetyScorer
from aireliability.safety.test_bridge import SafetyTestBridge

logger = logging.getLogger(__name__)


class SafetyEngine:
    """Enterprise-grade AI Safety Validation Engine."""

    def __init__(
        self,
        default_mode: SafetyExecutionMode = SafetyExecutionMode.SIMULATION,
        seed: int = 42,
    ) -> None:
        self.default_mode = default_mode
        self.seed = seed
        self.generator = SafetyTestGenerator(seed=seed)
        self.planner = SafetyCampaignPlanner()
        self.analyzer = SafetyAnalyzer()
        self.scorer = SafetyScorer()
        self.runner = SafetyCampaignRunner(analyzer=self.analyzer, scorer=self.scorer)
        self.graph_bridge = SafetyGraphBridge()
        self.healing_bridge = SafetyHealingBridge()
        self.test_bridge = SafetyTestBridge()
        self.observability = SafetyObservabilityBridge()

    def generate_tests(
        self,
        target: SafetyTarget,
        categories: list[SafetyCategory] | None = None,
        strategies: list[SafetyStrategy] | None = None,
        max_tests: int = 50,
        mutation_budget: int = 1,
    ) -> list[SafetyTest]:
        """Generate a suite of safety validation tests for the given target."""
        return self.generator.generate_tests(
            target=target,
            categories=categories,
            strategies=strategies,
            max_tests=max_tests,
            mutation_budget=mutation_budget,
        )

    def execute_test(
        self,
        test: SafetyTest,
        adapter: SafetyExecutionAdapter | None = None,
    ) -> tuple[SafetyExecution, SafetyObservation, list[SafetyFinding]]:
        """Safely execute a single test in a controlled sandbox and analyze outcomes."""
        exec_adapter = adapter or (
            OfflineSafetyAdapter()
            if self.default_mode == SafetyExecutionMode.OFFLINE
            else SimulatedSafetyAdapter()
        )
        execution = exec_adapter.execute(test)
        observation, findings = self.analyzer.analyze(test, execution)
        return execution, observation, findings

    def run_campaign(
        self,
        campaign: SafetyCampaign,
        tests: list[SafetyTest] | None = None,
        adapter: SafetyExecutionAdapter | None = None,
        sync_graph: bool = True,
    ) -> SafetyCampaignResult:
        """Execute a complete automated safety validation campaign."""
        exec_runner = SafetyCampaignRunner(
            adapter=adapter,
            analyzer=self.analyzer,
            scorer=self.scorer,
        )
        result = exec_runner.run_campaign(campaign, tests=tests)

        # Telemetry
        self.observability.record_campaign(result)

        # Sync to Knowledge Graph
        if sync_graph:
            try:
                self.graph_bridge.sync_campaign_result(result, tests=tests)
            except Exception as exc:
                logger.debug("Graph sync failed: %s", exc)

        return result

    def generate_report(self, result: SafetyCampaignResult) -> SafetyReport:
        """Compile a human- and machine-readable safety validation report."""
        summary = (
            f"Safety validation completed for target '{result.target.target_id}'. "
            f"Score: {result.score.safety_score:.3f}, Risk: {result.score.risk_score:.3f}. "
            f"Hard veto applied: {'YES' if result.score.hard_veto_applied else 'NO'}. "
            f"Total findings: {result.total_findings} across {result.total_tests} tests."
        )
        return SafetyReport(
            target=result.target,
            campaign_result=result,
            system_reliability_capped=result.score.hard_veto_applied,
            effective_reliability_ceiling=result.score.reliability_cap,
            summary=summary,
        )
