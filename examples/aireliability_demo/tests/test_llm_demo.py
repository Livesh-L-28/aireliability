"""Unit and integration tests for Demo LLM Provider component."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from aireliability_demo.app.llm.deterministic import DeterministicLLM
from aireliability_demo.app.llm.local import OptionalLocalLLM


def test_deterministic_llm_normal() -> None:
    llm = DeterministicLLM()
    res = llm.generate("Explain evaluation in AI reliability.", scenario="NORMAL")
    assert isinstance(res, str)
    assert len(res) > 20
    assert "evaluation" in res.lower() or "reliability" in res.lower()


def test_deterministic_llm_empty_response() -> None:
    llm = DeterministicLLM()
    res = llm.generate("Prompt here", scenario="EMPTY_RESPONSE")
    assert res == ""


def test_deterministic_llm_hallucination() -> None:
    llm = DeterministicLLM()
    res = llm.generate("Prompt here", scenario="HALLUCINATION")
    assert "1842" in res
    assert "Isaac Newton" in res


def test_deterministic_llm_low_quality() -> None:
    llm = DeterministicLLM()
    res = llm.generate("Prompt here", scenario="LOW_QUALITY")
    assert "vaguely" in res.lower() or "maybe" in res.lower()


def test_deterministic_llm_structured_output() -> None:
    llm = DeterministicLLM()
    struct_res = llm.generate_structured("Explain RAG", scenario="NORMAL")
    assert isinstance(struct_res, dict)
    assert struct_res.get("status") == "success"
    assert "answer" in struct_res


def test_optional_local_llm_fallback() -> None:
    # Pointing to non-existent port ensures deterministic fallback works offline
    local_llm = OptionalLocalLLM(base_url="http://localhost:59999")
    res = local_llm.generate("Explain agent reliability.", scenario="NORMAL")
    assert isinstance(res, str)
    assert len(res) > 20
