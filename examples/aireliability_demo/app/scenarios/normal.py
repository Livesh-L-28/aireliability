"""Normal operational scenarios demonstrating healthy execution."""

from __future__ import annotations

from typing import Any

from aireliability_demo.app.agent.agent import ControlledAgent
from aireliability_demo.app.llm.deterministic import DeterministicLLM
from aireliability_demo.app.rag.pipeline import RAGPipeline


def run_normal_scenario() -> dict[str, Any]:
    """Execute healthy end-to-end scenario across LLM, RAG, and Agent."""
    llm = DeterministicLLM()
    rag_pipe = RAGPipeline(llm=llm)
    agent = ControlledAgent("HealthyDemoAgent")

    # 1. LLM Normal
    llm_output = llm.generate(
        "Explain the capabilities of the evaluation framework.",
        scenario="NORMAL",
    )

    # 2. RAG Normal
    rag_result = rag_pipe.run(
        "What are the core capabilities of the AI reliability evaluation framework?",
        scenario="NORMAL_RETRIEVAL",
        expected_document_ids=["evaluation.md"],
    )

    # 3. Agent Normal
    agent_run = agent.execute_task(
        "Calculate the projected reliability score after a 15% improvement from 0.80.",
        scenario="NORMAL_AGENT",
    )

    return {
        "status": "HEALTHY",
        "llm_output": llm_output,
        "rag_result": rag_result,
        "agent_run": agent_run,
    }
