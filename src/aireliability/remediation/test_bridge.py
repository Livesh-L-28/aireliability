"""Integration bridge connecting Remediation Engine with Phase 36 Test Generation."""

from __future__ import annotations

import logging
from typing import Any

from aireliability.core.models import FailureReport
from aireliability.generation.engine import TestGenerationEngine
from aireliability.generation.models import (
    GeneratedTest,
    GenerationStrategy,
    TestGenerationConfig,
    TestGenerationRequest,
    TestProvenance,
)
from aireliability.remediation.models import RemediationProposal, RepairType

logger = logging.getLogger(__name__)


class RemediationTestBridge:
    """Invokes Phase 36 Automated AI Test Generation to synthesize validation suites for repairs."""

    def __init__(self, test_gen_engine: TestGenerationEngine | None = None) -> None:
        self.test_gen_engine = test_gen_engine or TestGenerationEngine()

    def generate_verification_tests(
        self,
        proposal: RemediationProposal,
        evidence: Any = None,
        max_tests: int = 5,
    ) -> list[GeneratedTest]:
        """Generate targeted test cases verifying the proposed repair patch."""
        # Determine appropriate strategies based on repair type
        strategies = [GenerationStrategy.EDGE_CASE, GenerationStrategy.ROBUSTNESS]

        if proposal.repair_type == RepairType.SAFETY:
            strategies.append(GenerationStrategy.SAFETY_SECURITY_PRIVACY)
        elif proposal.repair_type == RepairType.RETRIEVAL:
            strategies.append(GenerationStrategy.RAG_FOCUSED)
        elif proposal.repair_type == RepairType.AGENT:
            strategies.append(GenerationStrategy.AGENT_TRAJECTORY)
        else:
            strategies.append(GenerationStrategy.FAILURE_DRIVEN)

        # Build source list
        sources: list[Any] = []
        if evidence is not None:
            sources.append(evidence)
        elif proposal.provenance.source_failure_id:
            sources.append(
                FailureReport(
                    failure_id=proposal.provenance.source_failure_id,
                    trace_id="trace_auto",
                    category="general_failure",
                    message=proposal.description,
                )
            )
        else:
            # Fallback source dict
            sources.append(
                {
                    "proposal_id": proposal.proposal_id,
                    "target_component": proposal.patches[0].target_component_id
                    if proposal.patches
                    else "component",
                    "description": proposal.description,
                }
            )

        config = TestGenerationConfig(
            max_candidates=max_tests,
            strategies=strategies,
            deterministic_seed=42,
            auto_promote=False,  # Keep verification tests bound to the remediation lifecycle
        )

        request = TestGenerationRequest(
            sources=sources,
            strategies=strategies,
            config=config,
            tags=["phase37", "remediation_verification", proposal.proposal_id],
        )

        try:
            result = self.test_gen_engine.generate(request)
            generated_tests = result.candidates
            proposal.generated_test_ids = [t.test_id for t in generated_tests]
            return generated_tests
        except Exception as exc:
            logger.warning(
                "Phase 36 test generation encountered an issue (%s); falling back to synthetic verification tests.",
                exc,
            )
            # Create a deterministic fallback verification test
            fallback_test = GeneratedTest(
                test_type="remediation_verification",
                strategy=GenerationStrategy.EDGE_CASE,
                name=f"Verify {proposal.title}",
                input={"query": f"Verification test for {proposal.proposal_id}"},
                expected_criteria=["Must resolve diagnosed issue without regression"],
                tags=["phase37", "fallback_verification"],
                provenance=TestProvenance(
                    source_type="remediation",
                    source_id=proposal.proposal_id,
                ),
            )
            proposal.generated_test_ids = [fallback_test.test_id]
            return [fallback_test]
