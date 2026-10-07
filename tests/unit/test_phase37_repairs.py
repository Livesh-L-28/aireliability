"""Unit tests for Phase 37 repair generators across all 6 repair domains."""

from aireliability.core.models import FailureReport
from aireliability.remediation.models import RemediationRiskTier
from aireliability.remediation.repairs.agent import AgentRepairer
from aireliability.remediation.repairs.config import ConfigRepairer
from aireliability.remediation.repairs.prompt import PromptRepairer
from aireliability.remediation.repairs.retrieval import RetrievalRepairer
from aireliability.remediation.repairs.safety import SafetyRepairer
from aireliability.remediation.repairs.tool import ToolRepairer


def test_prompt_repairer_json_format() -> None:
    """PromptRepairer synthesizes formatting constraints for schema failures."""
    repairer = PromptRepairer()
    evidence = FailureReport(
        failure_id="fail_1",
        trace_id="tr_1",
        category="syntax",
        message="Output parsing failed: invalid JSON syntax",
    )
    assert repairer.can_handle(evidence) is True
    patches = repairer.generate_patches(
        evidence, context={"original_prompt": "You are a bot."}
    )
    assert len(patches) == 1
    assert "CRITICAL OUTPUT FORMAT INSTRUCTION" in patches[0].patched_value
    assert "JSON" in patches[0].diff_summary
    assert repairer.estimate_risk(patches) == RemediationRiskTier.LOW


def test_prompt_repairer_hallucination_refusal() -> None:
    """PromptRepairer synthesizes refusal constraints for hallucination failures."""
    repairer = PromptRepairer()
    evidence = {
        "error_message": "hallucination detected: model claimed unsupported fact"
    }
    assert repairer.can_handle(evidence) is True
    patches = repairer.generate_patches(evidence)
    assert len(patches) == 1
    assert "GROUNDING AND FACTUALITY CONSTRAINT" in patches[0].patched_value
    assert "sufficient information" in patches[0].patched_value


def test_retrieval_repairer_top_k_and_reranker() -> None:
    """RetrievalRepairer tunes top_k and enables neural reranking."""
    repairer = RetrievalRepairer()
    evidence = FailureReport(
        failure_id="fail_2",
        trace_id="tr_2",
        category="retrieval",
        message="retrieval failure: missing documents for query",
        metadata={"root_cause": "retriever_low_recall"},
    )
    assert repairer.can_handle(evidence) is True
    patches = repairer.generate_patches(
        evidence,
        context={
            "original_retrieval_config": {"top_k": 3, "similarity_threshold": 0.70}
        },
    )
    assert len(patches) == 1
    assert patches[0].patched_value["top_k"] == 7
    assert repairer.estimate_risk(patches) == RemediationRiskTier.MEDIUM

    # Noise scenario
    noise_evidence = {
        "error_message": "noisy irrelevant retrieval results causing hallucinations"
    }
    noise_patches = repairer.generate_patches(
        noise_evidence,
        context={
            "original_retrieval_config": {"top_k": 5, "similarity_threshold": 0.65}
        },
    )
    assert noise_patches[0].patched_value["reranking_enabled"] is True
    assert noise_patches[0].patched_value["similarity_threshold"] == 0.82


def test_tool_repairer_timeout_and_fallback() -> None:
    """ToolRepairer adds retries, expands timeout, and configures fallback tools."""
    repairer = ToolRepairer()
    evidence = FailureReport(
        failure_id="fail_3",
        trace_id="tr_3",
        category="tool",
        message="tool invocation timeout: weather_api connection timed out",
    )
    assert repairer.can_handle(evidence) is True
    patches = repairer.generate_patches(
        evidence,
        context={
            "target_component": "weather_api",
            "original_tool_spec": {"timeout_seconds": 5, "retry_count": 0},
        },
    )
    assert len(patches) == 1
    assert patches[0].patched_value["timeout_seconds"] == 15
    assert patches[0].patched_value["retry_count"] == 3


def test_agent_repairer_loop_breaker() -> None:
    """AgentRepairer activates loop detector and sets max execution step bounds."""
    repairer = AgentRepairer()
    evidence = {"error_message": "agent infinite loop detected in trajectory cycle"}
    assert repairer.can_handle(evidence) is True
    patches = repairer.generate_patches(
        evidence,
        context={"original_agent_config": {"max_steps": 30, "detect_loops": False}},
    )
    assert len(patches) == 1
    assert patches[0].patched_value["detect_loops"] is True
    assert patches[0].patched_value["max_steps"] == 10


def test_config_repairer_temperature_reduction() -> None:
    """ConfigRepairer lowers temperature for determinism and increases max_tokens."""
    repairer = ConfigRepairer()
    # High variance / non-deterministic
    evidence = {
        "error_message": "high variance in formatting across repeated evaluations"
    }
    assert repairer.can_handle(evidence) is True
    patches = repairer.generate_patches(
        evidence,
        context={"original_config": {"temperature": 0.8, "max_tokens": 512}},
    )
    assert len(patches) == 1
    assert patches[0].patched_value["temperature"] == 0.1

    # Token truncation
    trunc_evidence = {
        "error_message": "max_tokens reached: response was truncated mid-sentence"
    }
    trunc_patches = repairer.generate_patches(
        trunc_evidence,
        context={"original_config": {"temperature": 0.2, "max_tokens": 512}},
    )
    assert trunc_patches[0].patched_value["max_tokens"] == 1024


def test_safety_repairer_pii_and_injection() -> None:
    """SafetyRepairer adds PII regex patterns and activates prompt injection barriers."""
    repairer = SafetyRepairer()
    leak_evidence = {
        "error_message": "PII secret leak: bearer token exposed in model completion"
    }
    assert repairer.can_handle(leak_evidence) is True
    patches = repairer.generate_patches(leak_evidence)
    assert len(patches) == 1
    assert patches[0].patched_value["redact_pii"] is True
    assert patches[0].patched_value["redact_secrets"] is True
    assert repairer.estimate_risk(patches) == RemediationRiskTier.HIGH

    inj_evidence = {"error_message": "prompt injection bypass detected"}
    inj_patches = repairer.generate_patches(inj_evidence)
    assert inj_patches[0].patched_value["block_injection_signatures"] is True
