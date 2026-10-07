"""Unit tests for Phase 39 retrieval and ranking evaluations."""

from __future__ import annotations

import pytest

from aireliability.rag.models import (
    RAGFailureCategory,
    RetrievedChunk,
    RetrievedDocument,
)
from aireliability.rag.ranking_evaluator import RankingEvaluator
from aireliability.rag.retrieval_evaluator import RetrievalEvaluator


def test_retrieval_evaluator_with_ground_truth() -> None:
    """Test exact recall, precision, MRR, and NDCG when ground truth is known."""
    evaluator = RetrievalEvaluator()

    docs = [
        RetrievedDocument(document_id="doc_1", title="D1", text="Target text"),
        RetrievedDocument(document_id="doc_2", title="D2", text="Irrelevant text"),
        RetrievedDocument(document_id="doc_3", title="D3", text="Target secondary"),
    ]
    chunks = [
        RetrievedChunk(
            chunk_id="chk_1", document_id="doc_1", text="Chunk 1", retrieval_score=0.9
        ),
        RetrievedChunk(
            chunk_id="chk_2", document_id="doc_2", text="Chunk 2", retrieval_score=0.7
        ),
        RetrievedChunk(
            chunk_id="chk_3", document_id="doc_3", text="Chunk 3", retrieval_score=0.6
        ),
    ]

    expected_doc_ids = ["doc_1", "doc_3", "doc_4"]
    expected_chunk_ids = ["chk_1", "chk_3"]

    result, failures = evaluator.evaluate_retrieval(
        retrieved_documents=docs,
        retrieved_chunks=chunks,
        expected_document_ids=expected_doc_ids,
        expected_chunk_ids=expected_chunk_ids,
    )

    assert result.ground_truth_available is True
    # 2 retrieved out of 3 expected -> recall = 2/3
    assert pytest.approx(result.exact_metrics["document_recall"], 0.01) == 0.6667
    # 2 relevant out of 3 retrieved -> precision = 2/3
    assert pytest.approx(result.exact_metrics["document_precision"], 0.01) == 0.6667
    assert result.exact_metrics["hit_rate"] == 1.0
    assert result.exact_metrics["mrr"] == 1.0  # First doc is relevant
    assert result.exact_metrics["ndcg_at_k"] > 0.7


def test_retrieval_evaluator_without_ground_truth() -> None:
    """Verify that retrieval metrics are NEVER fabricated when ground truth is absent."""
    evaluator = RetrievalEvaluator()

    docs = [RetrievedDocument(document_id="doc_1", title="D1", text="Text 1")]
    chunks = [
        RetrievedChunk(
            chunk_id="chk_1", document_id="doc_1", text="Chunk 1", retrieval_score=0.85
        )
    ]

    result, failures = evaluator.evaluate_retrieval(
        retrieved_documents=docs,
        retrieved_chunks=chunks,
        expected_document_ids=None,
        expected_chunk_ids=None,
    )

    assert result.ground_truth_available is False
    assert "document_recall" not in result.exact_metrics
    assert result.semantic_contribution > 0.0


def test_retrieval_failures_detection() -> None:
    """Test detection of empty results and duplicate chunks."""
    evaluator = RetrievalEvaluator()

    # 1. No results failure
    res_empty, fails_empty = evaluator.evaluate_retrieval([], [])
    assert any(f.category == RAGFailureCategory.NO_RESULTS for f in fails_empty)

    # 2. Duplicate chunks failure
    dup_chunks = [
        RetrievedChunk(chunk_id="chk_1", document_id="doc_1", text="Identical content"),
        RetrievedChunk(chunk_id="chk_2", document_id="doc_1", text="Identical content"),
    ]
    res_dup, fails_dup = evaluator.evaluate_retrieval(
        [RetrievedDocument(document_id="doc_1", title="D1", text="Doc")],
        dup_chunks,
    )
    assert any(f.category == RAGFailureCategory.DUPLICATE_RESULTS for f in fails_dup)


def test_ranking_evaluator_buried_evidence() -> None:
    """Test ranking metrics and detection of buried relevant evidence."""
    evaluator = RankingEvaluator()

    chunks = [
        RetrievedChunk(
            chunk_id="chk_irr_1",
            document_id="doc_irr",
            text="Noise",
            rank=1,
            retrieval_score=0.9,
        ),
        RetrievedChunk(
            chunk_id="chk_irr_2",
            document_id="doc_irr",
            text="Noise",
            rank=2,
            retrieval_score=0.8,
        ),
        RetrievedChunk(
            chunk_id="chk_rel",
            document_id="doc_rel",
            text="Gold fact",
            rank=3,
            retrieval_score=0.7,
        ),
    ]

    ranking_res, failures = evaluator.evaluate_ranking(
        ranked_chunks=chunks,
        expected_chunk_ids=["chk_rel"],
    )

    assert ranking_res.mrr == pytest.approx(1.0 / 3.0, 0.01)
    # The gold fact is buried at rank 3 below 2 irrelevant results
    assert any(f.category == RAGFailureCategory.RANKING_FAILURE for f in failures)


def test_reranker_degradation_detection() -> None:
    """Test detection when reranker makes ranking worse."""
    evaluator = RankingEvaluator()

    # Before: gold was rank 1
    before = [
        RetrievedChunk(chunk_id="chk_gold", document_id="doc_1", text="Gold", rank=1),
        RetrievedChunk(chunk_id="chk_noise", document_id="doc_2", text="Noise", rank=2),
    ]
    # After reranking: gold was demoted to rank 2
    after = [
        RetrievedChunk(
            chunk_id="chk_noise",
            document_id="doc_2",
            text="Noise",
            rank=1,
            reranker_score=0.9,
        ),
        RetrievedChunk(
            chunk_id="chk_gold",
            document_id="doc_1",
            text="Gold",
            rank=2,
            reranker_score=0.4,
        ),
    ]

    ranking_res, failures = evaluator.evaluate_reranking(
        before_chunks=before,
        after_chunks=after,
        expected_chunk_ids=["chk_gold"],
    )

    assert ranking_res.reranker_degradation is True
    assert ranking_res.ndcg_change < 0
    assert any(f.category == RAGFailureCategory.RERANKING_FAILURE for f in failures)
