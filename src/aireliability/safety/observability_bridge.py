"""Observability bridge for AI Safety Validation (Phase 41)."""

from __future__ import annotations

import logging

from aireliability.observability.manager import ObservabilityManager
from aireliability.safety.models import SafetyCampaignResult

logger = logging.getLogger(__name__)


class SafetyObservabilityBridge:
    """Emits safety metrics and telemetry events."""

    def __init__(self, manager: ObservabilityManager | None = None) -> None:
        self.manager = manager or ObservabilityManager()
        self._init_metrics()

    def _init_metrics(self) -> None:
        """Register Phase 41 safety telemetry counters and gauges."""
        metrics = self.manager.metrics
        self.c_tests = metrics.register_counter(
            "safety_tests_total", "Total safety validation tests executed"
        )
        self.c_findings = metrics.register_counter(
            "safety_findings_total", "Total safety findings identified"
        )
        self.c_critical = metrics.register_counter(
            "safety_critical_total", "Critical safety violations count"
        )
        self.c_campaigns = metrics.register_counter(
            "safety_campaigns_total", "Total automated safety campaigns executed"
        )
        self.c_regressions = metrics.register_counter(
            "safety_regressions_total", "Total safety regression cases promoted"
        )
        self.c_remediations = metrics.register_counter(
            "safety_remediations_total", "Total safety remediation proposals"
        )
        self.g_detection_rate = metrics.register_gauge(
            "safety_detection_rate", "Safety validation detection rate"
        )
        self.g_coverage = metrics.register_gauge(
            "safety_coverage", "Taxonomy coverage ratio"
        )

    def record_campaign(self, result: SafetyCampaignResult) -> None:
        """Record telemetry for a completed safety campaign."""
        self.c_campaigns.increment(1.0)
        self.c_tests.increment(float(result.total_tests))
        self.c_findings.increment(float(result.total_findings))
        self.c_critical.increment(float(result.score.critical_violations_count))
        self.c_regressions.increment(float(len(result.regressions_promoted)))
        self.c_remediations.increment(float(len(result.recommendations)))

        self.g_detection_rate.set(result.score.detection_rate)
        self.g_coverage.set(result.coverage.coverage_ratio)
