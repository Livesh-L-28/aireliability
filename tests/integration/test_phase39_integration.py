"""End-to-end integration tests for Phase 39 Advanced RAG Reliability Engine."""

from __future__ import annotations

from aireliability.rag.engine import AdvancedRAGReliabilityEngine
from aireliability.rag.models import (
    QueryType,
    RAGFailureCategory,
    RAGStage,
    RetrievedChunk,
    RetrievedDocument,
)


def test_rag_end_to_end_lifecycle() -> None:
    """Verify complete 11-stage pipeline execution on a golden query."""
    engine = AdvancedRAGReliabilityEngine()

    query = "What is the primary function of the AI reliability engine?"
    documents = [
        RetrievedDocument(
            document_id="doc_core",
            title="AI Reliability Architecture",
            text="The primary function of the AI reliability engine is to evaluate, diagnose, and heal AI systems.",
            source="kb_docs",
        )
    ]
    chunks = [
        RetrievedChunk(
            chunk_id="chk_1",
            document_id="doc_core",
            text="The primary function of the AI reliability engine is to evaluate, diagnose, and heal AI systems.",
            rank=1,
            retrieval_score=0.96,
        )
    ]
    generated_answer = "The primary function of the AI reliability engine is to evaluate, diagnose, and heal AI systems [1]."

    run = engine.evaluate_run(
        query=query,
        retrieved_documents=documents,
        retrieved_chunks=chunks,
        generated_answer=generated_answer,
        expected_document_ids=["doc_core"],
        expected_chunk_ids=["chk_1"],
    )

    # 1. Query Analysis
    assert run.query.query_type == QueryType.SIMPLE_FACTUAL
    assert run.query.completeness_score > 0.8

    # 2. Retrieval Evaluation
    assert run.retrieval_result.ground_truth_available is True
    assert run.retrieval_result.exact_metrics["document_recall"] == 1.0

    # 3. Context Analysis
    assert run.context_window.is_truncated is False

    # 4. Claims & Citations
    assert len(run.claims) >= 1
    assert len(run.citations) == 1
    assert run.citations[0].cited_chunk_id == "chk_1"

    # 5. Grounding & Faithfulness
    g_score = run.stage_scores["grounding"].score
    assert g_score == 1.0

    # 6. Overall Reliability Score
    assert run.reliability_score.overall_score > 0.90
    assert run.reliability_score.security_passed is True
    assert len(run.failures) == 0


def test_retrieval_failure_never_hidden_by_correct_answer() -> None:
    """Architectural tenet: High final answer score must NOT hide a retrieval failure."""
    engine = AdvancedRAGReliabilityEngine()

    # Retriever returned irrelevant documents
    irrelevant_doc = RetrievedDocument(
        document_id="doc_noise",
        title="Noise Document",
        text="Bananas are rich in potassium and grown in tropical regions.",
        source="kb_noise",
    )
    irrelevant_chunk = RetrievedChunk(
        chunk_id="chk_noise",
        document_id="doc_noise",
        text="Bananas are rich in potassium.",
        rank=1,
        retrieval_score=0.30,
    )

    # But LLM hallucinated/guessed the correct factual answer without evidence
    query = "What is the speed of light in vacuum?"
    answer = (
        "The speed of light in vacuum is approximately 299,792,458 meters per second."
    )

    run = engine.evaluate_run(
        query=query,
        retrieved_documents=[irrelevant_doc],
        retrieved_chunks=[irrelevant_chunk],
        generated_answer=answer,
        expected_document_ids=["doc_physics_gold"],
    )

    # The system MUST detect retrieval failure
    assert any(f.stage == RAGStage.RETRIEVAL for f in run.failures)
    assert any(f.category == RAGFailureCategory.LOW_RECALL for f in run.failures)

    # And grounding failure because the answer has zero supporting evidence in retrieved context
    assert any(f.stage == RAGStage.GROUNDING for f in run.failures)


def test_generation_failure_never_blamed_on_retriever() -> None:
    """Architectural tenet: Good retriever must NOT be blamed for generation hallucination."""
    engine = AdvancedRAGReliabilityEngine()

    # Retriever returns perfect evidence
    gold_doc = RetrievedDocument(
        document_id="doc_gold",
        title="Physics Constants",
        text="The speed of light in vacuum is 299,792,458 meters per second.",
    )
    gold_chunk = RetrievedChunk(
        chunk_id="chk_gold",
        document_id="doc_gold",
        text="The speed of light in vacuum is 299,792,458 meters per second.",
        retrieval_score=0.98,
    )

    # But LLM completely ignored evidence and hallucinated
    query = "What is the speed of light in vacuum?"
    hallucinated_answer = "The speed of light is 500 miles per hour [1]."

    run = engine.evaluate_run(
        query=query,
        retrieved_documents=[gold_doc],
        retrieved_chunks=[gold_chunk],
        generated_answer=hallucinated_answer,
        expected_document_ids=["doc_gold"],
        expected_chunk_ids=["chk_gold"],
    )

    # Retrieval stage should have high score
    assert run.stage_scores["retrieval"].score > 0.90
    assert not any(f.stage == RAGStage.RETRIEVAL for f in run.failures)

    # Generation/Grounding stage must fail
    assert any(f.stage == RAGStage.GROUNDING for f in run.failures)
    assert any(
        f.category == RAGFailureCategory.HALLUCINATION
        or f.category == RAGFailureCategory.GROUNDING_FAILURE
        for f in run.failures
    )


def test_batch_evaluation_and_release_gates() -> None:
    """Test batch evaluation and release gate enforcement."""
    engine = AdvancedRAGReliabilityEngine()

    cases = [
        {
            "query": "Valid query 1",
            "retrieved_documents": [
                {"document_id": "d1", "title": "T1", "text": "Valid context 1"}
            ],
            "retrieved_chunks": [
                {
                    "chunk_id": "c1",
                    "document_id": "d1",
                    "text": "Valid context 1",
                    "retrieval_score": 0.9,
                }
            ],
            "generated_answer": "Valid context 1 [1].",
        },
        {
            "query": "Valid query 2",
            "retrieved_documents": [
                {"document_id": "d2", "title": "T2", "text": "Valid context 2"}
            ],
            "retrieved_chunks": [
                {
                    "chunk_id": "c2",
                    "document_id": "d2",
                    "text": "Valid context 2",
                    "retrieval_score": 0.9,
                }
            ],
            "generated_answer": "Valid context 2 [1].",
        },
    ]

    batch_res = engine.evaluate_batch(cases, min_grounding_score=0.70)
    assert batch_res.passed_release_gates is True
    assert batch_res.total_runs == 2
    assert batch_res.overall_score > 0.85
