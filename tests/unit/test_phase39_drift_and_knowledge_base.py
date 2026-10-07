"""Unit tests for Phase 39 statistical drift and knowledge base auditing."""

from __future__ import annotations

from aireliability.rag.drift import RAGDriftDetector
from aireliability.rag.knowledge_base import KnowledgeBaseAuditor
from aireliability.rag.models import (
    KBHealthStatus,
    RAGFailureCategory,
    RetrievedChunk,
    RetrievedDocument,
)


def test_rag_drift_detector() -> None:
    """Test statistical drift detection across query, retrieval, and grounding metrics."""
    detector = RAGDriftDetector(threshold_delta=0.10)

    baseline_metrics = {
        "grounding_score": 0.90,
        "retrieval_score": 0.88,
        "query_length": 15.0,
    }

    # Observed metrics with significant degradation in grounding and retrieval
    observed_metrics = {
        "grounding_score": 0.65,  # -0.25 degradation
        "retrieval_score": 0.70,  # -0.18 degradation
        "query_length": 16.0,  # negligible delta
    }

    drifts, failures = detector.detect_drift(baseline_metrics, observed_metrics)

    assert any(d.metric_name == "grounding_score" and d.drift_detected for d in drifts)
    assert any(d.metric_name == "retrieval_score" and d.drift_detected for d in drifts)
    assert any(
        f.category == RAGFailureCategory.GROUNDING_FAILURE
        or f.category == RAGFailureCategory.RETRIEVAL_DRIFT
        for f in failures
    )

    # Test embedding model change drift
    emb_drift, emb_fails = detector.detect_embedding_drift(
        baseline_embedding_model="text-embedding-3-small",
        observed_embedding_model="text-embedding-3-large",
    )
    assert emb_drift.drift_detected is True
    assert any(f.category == RAGFailureCategory.EMBEDDING_DRIFT for f in emb_fails)


def test_knowledge_base_auditor() -> None:
    """Test comprehensive knowledge base audit detecting duplicates and stale docs."""
    auditor = KnowledgeBaseAuditor()

    docs = [
        RetrievedDocument(
            document_id="doc_valid",
            title="Valid Doc",
            text="Valid distinct content 1",
            source="kb_a",
        ),
        RetrievedDocument(
            document_id="doc_empty", title="Empty Doc", text="", source="kb_a"
        ),
        RetrievedDocument(
            document_id="doc_dup",
            title="Dup Doc",
            text="Valid distinct content 1",
            source="kb_b",
        ),
    ]
    chunks = [
        RetrievedChunk(
            chunk_id="c1", document_id="doc_valid", text="Valid distinct content 1"
        ),
        RetrievedChunk(
            chunk_id="c2", document_id="doc_valid", text="Valid distinct content 1"
        ),  # Duplicate chunk
        RetrievedChunk(
            chunk_id="c3", document_id="doc_valid", text="Short"
        ),  # Fragmented tiny chunk
    ]

    report = auditor.audit_knowledge_base(docs, chunks)

    assert report.status in (KBHealthStatus.DEGRADED, KBHealthStatus.CRITICAL)
    assert report.empty_document_count >= 1
    assert report.duplicate_chunk_rate > 0.0
    assert len(report.recommendations) >= 1
