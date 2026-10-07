"""Unit tests for Phase 37 sandbox simulation and evaluation gates."""

from aireliability.generation.models import (
    GeneratedTest,
    GenerationStrategy,
    TestProvenance,
)
from aireliability.remediation.gates import RemediationGateChecker
from aireliability.remediation.models import (
    RemediationLifecycleState,
    RemediationPatch,
    RemediationProposal,
    RepairType,
    SimulationResult,
)
from aireliability.remediation.simulator import RemediationSimulator


def test_simulation_passes_with_valid_patches() -> None:
    """Simulator successfully executes valid patches against verification tests."""
    simulator = RemediationSimulator()
    patch = RemediationPatch(
        repair_type=RepairType.PROMPT,
        target_component_id="prompt_1",
        original_value="Base prompt",
        patched_value="Patched prompt with strict instructions",
    )
    proposal = RemediationProposal(
        title="Test Proposal",
        repair_type=RepairType.PROMPT,
        patches=[patch],
    )
    test = GeneratedTest(
        test_type="unit",
        strategy=GenerationStrategy.EDGE_CASE,
        name="Verification Test 1",
        input={"query": "hello"},
        provenance=TestProvenance(source_type="synthetic", source_id="src_1"),
    )

    result = simulator.simulate(
        proposal, tests=[test], baseline_test_cases=["golden_1"]
    )
    assert result.passed is True
    assert result.tests_passed == 2
    assert result.regressions_count == 0
    assert result.failure_recovery_rate == 1.0
    assert proposal.state == RemediationLifecycleState.SIMULATED


def test_simulation_fails_with_empty_patch() -> None:
    """Simulator fails if candidate patches are malformed or missing values."""
    simulator = RemediationSimulator()
    patch = RemediationPatch(
        repair_type=RepairType.PROMPT,
        target_component_id="prompt_1",
        original_value="Base prompt",
        patched_value=None,  # Invalid
    )
    proposal = RemediationProposal(
        title="Broken Proposal",
        repair_type=RepairType.PROMPT,
        patches=[patch],
    )
    test = GeneratedTest(
        test_type="unit",
        strategy=GenerationStrategy.EDGE_CASE,
        name="Verification Test 1",
        input={"query": "hello"},
        provenance=TestProvenance(source_type="synthetic", source_id="src_2"),
    )

    result = simulator.simulate(proposal, tests=[test])
    assert result.passed is False
    assert result.tests_failed == 1


def test_gate_checker_enforces_zero_regression() -> None:
    """RemediationGateChecker fails proposal if regressions are detected."""
    gate_checker = RemediationGateChecker(max_allowed_regressions=0)
    sim = SimulationResult(
        passed=False,
        total_tests_run=10,
        tests_passed=9,
        tests_failed=1,
        regressions_count=1,  # Fails zero regression gate
        failure_recovery_rate=0.9,
    )
    proposal = RemediationProposal(
        title="Gate Test",
        repair_type=RepairType.CONFIG,
        simulation=sim,
    )

    eval_result = gate_checker.evaluate_gates(proposal)
    assert eval_result.gates_passed is False
    assert eval_result.zero_regression_passed is False
    assert any("Regression gate failed" in r for r in eval_result.failed_gate_reasons)


def test_gate_checker_enforces_safety_and_recovery_rate() -> None:
    """RemediationGateChecker requires safety compliance and minimum recovery rate."""
    gate_checker = RemediationGateChecker(min_recovery_rate=0.8)
    sim = SimulationResult(
        passed=False,
        total_tests_run=10,
        tests_passed=6,
        tests_failed=4,
        regressions_count=0,
        failure_recovery_rate=0.6,  # Below 0.8
        safety_violations_count=1,  # Safety violation
    )
    proposal = RemediationProposal(
        title="Safety Gate Test",
        repair_type=RepairType.SAFETY,
        simulation=sim,
    )

    eval_result = gate_checker.evaluate_gates(proposal)
    assert eval_result.gates_passed is False
    assert eval_result.recovery_rate_passed is False
    assert eval_result.safety_passed is False
    assert len(eval_result.failed_gate_reasons) == 2
