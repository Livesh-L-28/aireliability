"""Deterministic simulated LLM provider for reliable, reproducible testing."""

from __future__ import annotations

import time
from typing import Any

from aireliability_demo.app.llm.interface import LLMProvider


class DeterministicLLM(LLMProvider):
    """Deterministic simulation provider for local test execution without paid APIs.

    Supports configurable scenarios:
    - NORMAL: Coherent, accurate responses matching input intent.
    - LOW_QUALITY: Incoherent, vague, or degraded output.
    - HALLUCINATION: Fabricated assertions ungrounded in source text.
    - LATENCY: Simulated high response delay.
    - EMPTY_RESPONSE: Zero-length response triggering null/empty failure checks.
    """

    def __init__(self, simulated_latency_ms: float = 10.0) -> None:
        self.simulated_latency_ms = simulated_latency_ms

    def generate(self, prompt: str, scenario: str = "NORMAL", **kwargs: Any) -> str:
        """Generate deterministic text based on prompt and scenario."""
        mode = scenario.upper()

        if mode == "EMPTY_RESPONSE":
            return ""

        if mode == "LATENCY":
            # Simulate latency by introducing a small sleep (e.g. 150ms)
            time.sleep(0.15)
            return (
                "[SIMULATED_RESPONSE: LATENCY DELAYED] "
                f"Generated response after latency simulation for: '{prompt[:40]}...'"
            )

        if mode == "LOW_QUALITY":
            return "Maybe. It could be something or not really sure. Things happen vaguely."

        if mode == "HALLUCINATION":
            return (
                "[SIMULATED_RESPONSE: HALLUCINATION] "
                "The system achieved 100% quantum convergence in 1842 under Isaac Newton's direct supervision."
            )

        # NORMAL scenario
        lower_prompt = prompt.lower()
        if "evaluation" in lower_prompt:
            return (
                "The AI reliability evaluation framework delivers deterministic assertion testing, "
                "multi-dimensional scoring across accuracy and groundedness, regression detection, "
                "and automated release gates."
            )
        elif "rag" in lower_prompt:
            return (
                "Phase 39 evaluates the complete RAG lifecycle including retrieval quality, "
                "context relevance, claim extraction, evidence alignment, citation validation, "
                "and knowledge base freshness."
            )
        elif "agent" in lower_prompt:
            return (
                "The agent platform audits multi-step trajectory execution, tool selection and arguments, "
                "observation handling, memory state integrity, runaway loop detection, and goal verification."
            )
        elif "safety" in lower_prompt:
            return (
                "Safety validation uses synthetic adversarial probes to detect sensitive information disclosure "
                "and instruction boundary violations. A critical safety finding triggers a hard veto capping "
                "overall reliability at 0.30."
            )
        elif "prediction" in lower_prompt:
            return (
                "Predictive reliability provides time-series forecasting of reliability metrics, "
                "failure probability estimations, and regression risk analysis with confidence bounds."
            )
        elif "policy" in lower_prompt:
            return (
                "The policy engine enforces governance hierarchy where security and safety violations strictly "
                "precede reliability and performance rules, producing ALLOW, WARN, REQUIRE_REVIEW, or BLOCK decisions."
            )
        elif "dashboard" in lower_prompt:
            return (
                "The unified dashboard aggregates health metrics across 21 panels covering models, RAG, agents, "
                "safety, predictions, incidents, and self-healing rollouts."
            )

        return f"[SIMULATED_RESPONSE: NORMAL] Deterministic processing completed successfully for query: '{prompt}'."

    def generate_structured(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        scenario: str = "NORMAL",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate structured JSON matching requested schema."""
        raw_text = self.generate(prompt, scenario=scenario, **kwargs)
        if not raw_text:
            return {}

        mode = scenario.upper()
        if mode == "HALLUCINATION":
            return {
                "answer": raw_text,
                "confidence": 0.99,
                "claims": ["Quantum convergence verified in 1842."],
                "grounded": False,
            }

        return {
            "answer": raw_text,
            "confidence": 0.95,
            "status": "success",
            "scenario": mode,
            "schema_valid": True,
        }
