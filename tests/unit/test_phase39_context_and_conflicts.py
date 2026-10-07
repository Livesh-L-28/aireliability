"""Unit tests for Phase 39 context window analysis and conflict detection."""

from __future__ import annotations

from aireliability.rag.context_analyzer import ContextAnalyzer
from aireliability.rag.models import (
    ConflictStatus,
    RAGFailureCategory,
    RetrievedChunk,
)


def test_context_analyzer_truncation_and_redundancy() -> None:
    """Test context truncation, token bounds, and redundancy calculation."""
    analyzer = ContextAnalyzer(max_context_tokens=100)

    # 4 chunks of 30 words each -> ~120 words -> ~150 tokens, exceeds 100 limit
    chunk1 = RetrievedChunk(
        chunk_id="c1", document_id="d1", text="Data item " * 15, rank=1
    )
    chunk2 = RetrievedChunk(
        chunk_id="c2", document_id="d1", text="Data item " * 15, rank=2
    )
    chunk3 = RetrievedChunk(
        chunk_id="c3", document_id="d2", text="Data item " * 15, rank=3
    )

    ctx_win, conflicts, failures = analyzer.analyze_context(
        chunks=[chunk1, chunk2, chunk3],
        query_text="What are the data items?",
    )

    assert ctx_win.redundancy_score > 0.5  # Chunk 1 and Chunk 2 are nearly identical
    assert ctx_win.is_truncated is True
    assert any(f.category == RAGFailureCategory.CONTEXT_OVERFLOW for f in failures)


def test_lost_in_the_middle_position_sensitivity() -> None:
    """Test lost-in-the-middle potential sensitivity detection."""
    analyzer = ContextAnalyzer()

    # 10 chunks, relevant critical chunk is in the middle (rank 5)
    chunks = [
        RetrievedChunk(
            chunk_id=f"c_{i}",
            document_id="d1",
            text=f"Irrelevant preamble text {i}",
            rank=i,
        )
        for i in range(1, 10)
    ]
    chunks[4] = RetrievedChunk(
        chunk_id="c_5",
        document_id="d1",
        text="The exact secret access code is ALPHA-42.",
        rank=5,
    )

    ctx_win, conflicts, failures = analyzer.analyze_context(
        chunks=chunks,
        query_text="What is the access code?",
        answer_text="The code was not found in the documents.",
        critical_chunk_ids=["c_5"],
    )

    assert ctx_win.lost_in_the_middle_detected is True
    assert ctx_win.potential_position_sensitivity > 0.0


def test_conflict_detection_unresolved_and_temporal() -> None:
    """Test bounded factual contradiction detection between retrieved documents."""
    analyzer = ContextAnalyzer()

    chunk_a = RetrievedChunk(
        chunk_id="c_a",
        document_id="d_a",
        text="The release date of Product X was in 2024.",
        rank=1,
    )
    chunk_b = RetrievedChunk(
        chunk_id="c_b",
        document_id="d_b",
        text="The release date of Product X was in 2025.",
        rank=2,
    )

    ctx_win, conflicts, failures = analyzer.analyze_context(
        chunks=[chunk_a, chunk_b],
        query_text="When was Product X released?",
    )

    assert len(conflicts) >= 1
    c = conflicts[0]
    assert c.status in (ConflictStatus.UNRESOLVED, ConflictStatus.TEMPORAL_CONFLICT)
    assert any(f.category == RAGFailureCategory.KNOWLEDGE_CONFLICT for f in failures)
