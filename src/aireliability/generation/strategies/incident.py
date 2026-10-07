"""Incident-driven test generation converting IncidentRecords into regression protection tests."""

from __future__ import annotations

from typing import Any

from aireliability.generation.models import (
    GeneratedTest,
    GenerationSourceType,
    GenerationStrategy,
    TestGenerationConfig,
    TestPriority,
    TestProvenance,
    TestRiskLevel,
    TestType,
)
from aireliability.observability.incidents import IncidentRecord


class IncidentTestGenerator:
    """Converts operational IncidentRecords into permanent regression guard tests."""

    strategy = GenerationStrategy.INCIDENT_DRIVEN

    def generate(
        self,
        source: Any,
        config: TestGenerationConfig,
    ) -> list[GeneratedTest]:
        records: list[IncidentRecord] = []

        if isinstance(source, IncidentRecord):
            records = [source]
        elif isinstance(source, list):
            for item in source:
                if isinstance(item, IncidentRecord):
                    records.append(item)

        tests: list[GeneratedTest] = []
        for inc in records[: config.max_candidates]:
            tests.append(self._from_incident(inc, config))

        return tests

    def _from_incident(
        self,
        incident: IncidentRecord,
        config: TestGenerationConfig,
    ) -> GeneratedTest:
        sev = incident.severity.upper()
        if sev == "CRITICAL":
            risk = TestRiskLevel.CRITICAL
            prio = TestPriority.CRITICAL
        elif sev == "HIGH":
            risk = TestRiskLevel.HIGH
            prio = TestPriority.HIGH
        elif sev == "MEDIUM":
            risk = TestRiskLevel.MEDIUM
            prio = TestPriority.MEDIUM
        else:
            risk = TestRiskLevel.LOW
            prio = TestPriority.LOW

        trace_link = incident.trace_ids[0] if incident.trace_ids else None
        prov = TestProvenance(
            source_type=GenerationSourceType.INCIDENT,
            source_id=incident.incident_id,
            source_incident_id=incident.incident_id,
            source_trace_id=trace_link,
            generator_name="IncidentTestGenerator",
            deterministic_seed=config.deterministic_seed,
            rationale=f"Incident {incident.incident_id} [{incident.severity}]: {incident.title}",
            metadata={"status": str(incident.status), "severity": incident.severity},
        )

        test_input = (
            incident.metadata.get("input")
            or f"Regression query preventing recurrence of incident: {incident.title}"
        )

        criteria = [
            f"must prevent operational failure: {incident.title}",
            f"incident root symptoms must not trigger: {incident.description[:100]}",
        ]

        return GeneratedTest(
            name=f"incident_guard_{incident.incident_id[:8]}",
            test_type=TestType.REGRESSION,
            strategy=self.strategy,
            input=test_input,
            expected_output=None,
            expected_criteria=criteria,
            reference_answer=None,
            has_ground_truth=False,
            provenance=prov,
            confidence=0.95,
            risk_level=risk,
            priority=prio,
            tags=["incident_driven", f"severity:{incident.severity.lower()}"],
            metadata=dict(incident.metadata),
            deterministic_seed=config.deterministic_seed,
        )
