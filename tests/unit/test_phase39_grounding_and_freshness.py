"""Unit tests for Phase 39 grounding, faithfulness, and knowledge freshness."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from aireliability.rag.freshness import FreshnessTracker
from aireliability.rag.grounding_evaluator import GroundingEvaluator
from aireliability.rag.models import (
    Citation,
    CitationStatus,
    Claim,
    ClaimImportance,
    ClaimSupportStatus,
    ConfidenceLevel,
    RAGFailureCategory,
    RetrievedChunk,
    RetrievedDocument,
)


def test_grounding_evaluator_scoring_and_hallucination() -> None:
    """Test groundedness, faithfulness, and hallucination rate scoring."""
    evaluator = GroundingEvaluator()

    # 2 supported claims, 1 unsupported claim
    claims = [
        Claim(
            claim_id="c1",
            text="Supported fact 1",
            importance=ClaimImportance.CRITICAL,
            support_status=ClaimSupportStatus.SUPPORTED,
        ),
        Claim(
            claim_id="c2",
            text="Supported fact 2",
            importance=ClaimImportance.STANDARD,
            support_status=ClaimSupportStatus.SUPPORTED,
        ),
        Claim(
            claim_id="c3",
            text="Fabricated hallucination",
            importance=ClaimImportance.CRITICAL,
            support_status=ClaimSupportStatus.UNSUPPORTED,
        ),
    ]
    citations = [
        Citation(
            citation_id="cit1",
            marker="[1]",
            cited_chunk_id="chk_1",
            status=CitationStatus.VALID,
        ),
    ]

    res, failures = evaluator.evaluate_grounding(claims, citations)

    assert pytest.approx(res.grounding_score, 0.05) == 0.67
    assert res.hallucination_rate > 0.0
    assert res.confidence == ConfidenceLevel.HIGH
    assert any(f.category == RAGFailureCategory.GROUNDING_FAILURE for f in failures)
    assert any(f.category == RAGFailureCategory.HALLUCINATION for f in failures)


def test_freshness_tracker_stale_documents_and_index() -> None:
    """Test knowledge freshness tracking against max_age_days policy and index staleness."""
    tracker = FreshnessTracker(default_max_age_days=30)

    now = datetime.now(UTC)
    fresh_time = now - timedelta(days=5)
    stale_time = now - timedelta(days=90)

    docs = [
        RetrievedDocument(
            document_id="doc_fresh",
            title="Fresh Doc",
            text="Content",
            updated_at=fresh_time,
        ),
        RetrievedDocument(
            document_id="doc_stale",
            title="Stale Doc",
            text="Content",
            updated_at=stale_time,
        ),
    ]
    chunks = [
        RetrievedChunk(
            chunk_id="chk_fresh",
            document_id="doc_fresh",
            text="Content",
            timestamp=fresh_time,
        ),
        RetrievedChunk(
            chunk_id="chk_stale",
            document_id="doc_stale",
            text="Content",
            timestamp=stale_time,
        ),
    ]

    score, stale_rate, failures, expl = tracker.evaluate_freshness(docs, chunks)

    assert stale_rate == 0.50
    assert score == 0.50
    assert any(f.category == RAGFailureCategory.FRESHNESS_FAILURE for f in failures)

    # Test index staleness (doc updated more recently than index build)
    index_time = now - timedelta(days=10)
    idx_fails = tracker.detect_index_staleness(
        docs=[
            RetrievedDocument(
                document_id="doc_new", title="New Doc", text="Content", updated_at=now
            )
        ],
        index_timestamp=index_time,
    )
    assert any(f.category == RAGFailureCategory.INDEX_STALENESS for f in idx_fails)
