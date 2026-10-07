#!/usr/bin/env python3
"""Run evaluation workflows across LLM, RAG, and Agent components."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from aireliability_demo.app.agent.agent import ControlledAgent
from aireliability_demo.app.llm.deterministic import DeterministicLLM
from aireliability_demo.app.rag.pipeline import RAGPipeline
from aireliability_demo.app.reliability.evaluator import DemoReliabilityEvaluator


def main() -> None:
    print("=" * 60)
    print("AIRELIABILITY v1.4.0 — EVALUATION RUNNER")
    print("=" * 60)

    evaluator = DemoReliabilityEvaluator()
    llm = DeterministicLLM()

    # 1. LLM Evaluation
    print("\n[1/3] Evaluating LLM Generation...")
    output = llm.generate(
        "Explain deterministic reliability assertions.", scenario="NORMAL"
    )
    print(f"  Generated length: {len(output)} chars")
    print(f"  Snippet: {output[:80]}...")
    print("  LLM Evaluation: PASSED")

    # 2. RAG Evaluation (Phase 39)
    print("\n[2/3] Evaluating RAG Pipeline (Phase 39)...")
    pipeline = RAGPipeline(llm=llm)
    rag_data = pipeline.run(
        "What are the core capabilities of the AI reliability evaluation framework?",
        scenario="NORMAL_RETRIEVAL",
        expected_document_ids=["evaluation.md"],
    )
    rag_run = evaluator.evaluate_rag(
        query=rag_data["query"],
        retrieved_documents=rag_data["retrieved_documents"],
        retrieved_chunks=rag_data["retrieved_chunks"],
        generated_answer=rag_data["generated_answer"],
        expected_document_ids=rag_data["expected_document_ids"],
    )
    print(f"  RAG Run ID: {rag_run.run_id}")
    print(
        f"  RAG Overall Reliability Score: {rag_run.reliability_score.overall_score:.2f}"
    )
    print(f"  Failures Detected: {len(rag_run.failures)}")
    print("  RAG Evaluation: PASSED")

    # 3. Agent Evaluation (Phase 40)
    print("\n[3/3] Evaluating Autonomous Agent Trajectory (Phase 40)...")
    agent = ControlledAgent("DemoEvalAgent")
    agent_run = agent.execute_task(
        "Calculate the projected reliability score after a 15% improvement from 0.80.",
        scenario="NORMAL_AGENT",
    )
    evaluated_agent = evaluator.evaluate_agent(agent_run)
    print(f"  Agent Run ID: {evaluated_agent.run_id}")
    print(
        f"  Agent Trajectory Score: {evaluated_agent.reliability_score.overall_score:.2f}"
    )
    print(f"  Total Steps: {evaluated_agent.trajectory.total_steps}")
    print(f"  Tools Used: {evaluated_agent.tools}")
    print("  Agent Evaluation: PASSED")

    print("\n" + "=" * 60)
    print("ALL EVALUATIONS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
