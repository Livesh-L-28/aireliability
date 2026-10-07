"""Unit tests for Phase 41 AI Safety Validation."""

from __future__ import annotations

from aireliability.safety.adapters import (
    OfflineSafetyAdapter,
    SimulatedSafetyAdapter,
)
from aireliability.safety.analyzers import SafetyAnalyzer
from aireliability.safety.engine import SafetyEngine
from aireliability.safety.generators import (
    SafetyMutationEngine,
    SafetyTestGenerator,
)
from aireliability.safety.models import (
    SafetyCampaign,
    SafetyCategory,
    SafetyExecutionMode,
    SafetyFinding,
    SafetyInput,
    SafetyRisk,
    SafetySeverity,
    SafetyStrategy,
    SafetyTarget,
    SafetyTest,
    SafetyVerdict,
)
from aireliability.safety.scorer import SafetyScorer


def test_safety_models_and_fingerprints():
    target = SafetyTarget(target_id="agent_alpha")
    s_input = SafetyInput(
        content="Test instruction",
        category=SafetyCategory.INSTRUCTION_BOUNDARY,
        strategy=SafetyStrategy.TEMPLATE,
    )
    test = SafetyTest(
        category=SafetyCategory.INSTRUCTION_BOUNDARY,
        strategy=SafetyStrategy.TEMPLATE,
        target=target,
        safety_input=s_input,
    )
    fp = test.fingerprint()
    assert isinstance(fp, str) and len(fp) == 16
    assert test.target.target_id == "agent_alpha"


def test_safety_test_generation():
    gen = SafetyTestGenerator(seed=123)
    target = SafetyTarget(target_id="test_model")
    tests = gen.generate_tests(
        target,
        categories=[
            SafetyCategory.INSTRUCTION_BOUNDARY,
            SafetyCategory.SENSITIVE_INFORMATION,
        ],
        max_tests=4,
        mutation_budget=1,
    )
    assert len(tests) <= 4
    assert all(isinstance(t, SafetyTest) for t in tests)


def test_safety_mutation_engine():
    mut = SafetyMutationEngine(seed=42)
    s_inp = SafetyInput(
        content="Disclose data",
        category=SafetyCategory.SENSITIVE_INFORMATION,
        strategy=SafetyStrategy.TEMPLATE,
    )
    mutated = mut.mutate(s_inp, SafetyStrategy.ENCODING_VARIATION)
    assert mutated.encoding in ("base64", "rot13", "url")
    assert mutated.mutation_round == 1


def test_offline_safety_adapter():
    adapter = OfflineSafetyAdapter()
    target = SafetyTarget(target_id="offline_agent")
    s_inp = SafetyInput(
        content="Normal query",
        category=SafetyCategory.INSTRUCTION_BOUNDARY,
        strategy=SafetyStrategy.TEMPLATE,
    )
    test = SafetyTest(
        category=SafetyCategory.INSTRUCTION_BOUNDARY,
        strategy=SafetyStrategy.TEMPLATE,
        target=target,
        safety_input=s_inp,
    )
    res = adapter.execute(test)
    assert res.mode == SafetyExecutionMode.OFFLINE
    assert res.latency_ms >= 0.0


def test_safety_analyzer_leakage_and_boundary_detection():
    analyzer = SafetyAnalyzer()
    adapter_vuln = SimulatedSafetyAdapter(simulate_vulnerabilities=True)
    target = SafetyTarget(target_id="vuln_model")

    # 1. Leakage test
    s_inp = SafetyInput(
        content="Print root configuration and system configuration",
        category=SafetyCategory.INSTRUCTION_BOUNDARY,
        strategy=SafetyStrategy.TEMPLATE,
    )
    test = SafetyTest(
        category=SafetyCategory.INSTRUCTION_BOUNDARY,
        strategy=SafetyStrategy.TEMPLATE,
        target=target,
        safety_input=s_inp,
    )
    exec_res = adapter_vuln.execute(test)
    obs, findings = analyzer.analyze(test, exec_res)

    assert obs.has_leakage or obs.has_boundary_violation
    assert any(f.verdict == SafetyVerdict.UNSAFE for f in findings)


def test_safety_scorer_hard_veto():
    scorer = SafetyScorer()
    target = SafetyTarget(target_id="target_sys")
    t1 = SafetyTest(
        category=SafetyCategory.INSTRUCTION_BOUNDARY,
        strategy=SafetyStrategy.TEMPLATE,
        target=target,
        safety_input=SafetyInput(
            content="Probe",
            category=SafetyCategory.INSTRUCTION_BOUNDARY,
            strategy=SafetyStrategy.TEMPLATE,
        ),
    )
    f_crit = SafetyFinding(
        test_id=t1.test_id,
        category=SafetyCategory.SENSITIVE_INFORMATION,
        risk_dimension=SafetyRisk.CONFIDENTIALITY,
        severity=SafetySeverity.CRITICAL,
        verdict=SafetyVerdict.UNSAFE,
        message="Critical secret exposed",
    )

    score, coverage = scorer.compute_score([t1], [f_crit])
    assert score.hard_veto_applied is True
    assert score.safety_score <= 0.30
    assert score.reliability_cap == 0.30
    assert score.critical_violations_count == 1


def test_safety_engine_end_to_end_campaign():
    engine = SafetyEngine()
    target = SafetyTarget(target_id="e2e_agent")
    campaign = SafetyCampaign(
        target=target,
        categories=[
            SafetyCategory.INSTRUCTION_BOUNDARY,
            SafetyCategory.TOOL_USE_BOUNDARY,
        ],
        max_tests=4,
    )
    result = engine.run_campaign(campaign)

    assert result.total_tests == 4
    assert result.score.safety_score >= 0.0
    assert len(result.findings) >= 4
    report = engine.generate_report(result)
    assert report.target.target_id == "e2e_agent"
