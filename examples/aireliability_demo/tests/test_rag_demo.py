"""Tests for RAG component, deterministic retriever, and Phase 39 evaluation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from aireliability_demo.app.rag.chunker import chunk_document
from aireliability_demo.app.rag.documents import load_documents
from aireliability_demo.app.rag.pipeline import RAGPipeline
from aireliability_demo.app.rag.retriever import DeterministicRetriever
from aireliability_demo.app.reliability.evaluator import DemoReliabilityEvaluator


def test_document_loading_and_chunking() -> None:
    docs = load_documents()
    assert len(docs) >= 5
    assert any(d.document_id == "evaluation.md" for d in docs)

    eval_doc = [d for d in docs if d.document_id == "evaluation.md"][0]
    chunks = chunk_document(eval_doc)
    assert len(chunks) >= 1
    assert chunks[0].document_id == "evaluation.md"


def test_deterministic_retriever() -> None:
    docs = load_documents()
    retriever = DeterministicRetriever(docs)

    matched_docs, matched_chunks = retriever.retrieve(
        "evaluation framework deterministic testing assertions",
        top_k=2,
    )
    assert len(matched_chunks) > 0
    assert matched_chunks[0].document_id == "evaluation.md"
    assert matched_chunks[0].retrieval_score > 0.1


def test_rag_normal_pipeline_and_phase39_evaluation() -> None:
    pipeline = RAGPipeline()
    evaluator = DemoReliabilityEvaluator()

    query = "What are the core capabilities of the AI reliability evaluation framework?"
    rag_result = pipeline.run(
        query_text=query,
        scenario="NORMAL_RETRIEVAL",
        expected_document_ids=["evaluation.md"],
    )

    assert len(rag_result["retrieved_chunks"]) > 0
    assert len(rag_result["generated_answer"]) > 20

    # Phase 39 evaluation
    rag_run = evaluator.evaluate_rag(
        query=rag_result["query"],
        retrieved_documents=rag_result["retrieved_documents"],
        retrieved_chunks=rag_result["retrieved_chunks"],
        generated_answer=rag_result["generated_answer"],
        expected_document_ids=rag_result["expected_document_ids"],
    )
    assert rag_run.run_id is not None
    assert rag_run.reliability_score.overall_score >= 0.50


def test_rag_failure_scenarios() -> None:
    pipeline = RAGPipeline()

    # Missing document
    res_miss = pipeline.run("Test query", scenario="MISSING_DOCUMENT")
    assert len(res_miss["retrieved_chunks"]) == 0

    # Conflicting document
    res_conf = pipeline.run("Test query", scenario="CONFLICTING_DOCUMENT")
    assert any("conflicting" in c.document_id for c in res_conf["retrieved_chunks"])

    # Stale document
    res_stale = pipeline.run("Test query", scenario="STALE_DOCUMENT")
    assert any(
        c.metadata.get("last_updated") == "2021-01-01T00:00:00Z"
        for c in res_stale["retrieved_chunks"]
    )

    # Grounding failure
    res_ground = pipeline.run("Test query", scenario="GROUNDING_FAILURE")
    assert "1842" in res_ground["generated_answer"]
