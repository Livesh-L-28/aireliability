"""Unit tests for Phase 39 claim extraction, evidence alignment, and citation validation."""

from __future__ import annotations

from aireliability.rag.citation_validator import CitationValidator
from aireliability.rag.claim_extractor import ClaimExtractor
from aireliability.rag.evidence_aligner import EvidenceAligner
from aireliability.rag.models import (
    CitationStatus,
    ClaimImportance,
    ClaimSupportStatus,
    RAGFailureCategory,
    RetrievedChunk,
)


def test_claim_extractor_propositions_and_importance() -> None:
    """Test atomic proposition extraction and importance classification."""
    extractor = ClaimExtractor()

    text = (
        "AI reliability guarantees safety constraints are never violated. "
        "Furthermore, it evaluates precision and recall across all retrieval pipelines. "
        "Finally, it is a helpful library."
    )
    claims = extractor.extract_claims(text)

    assert len(claims) >= 3
    # "safety constraints are never violated" should be CRITICAL
    critical_claims = [c for c in claims if c.importance == ClaimImportance.CRITICAL]
    assert len(critical_claims) >= 1
    assert any("safety" in c.text.lower() for c in critical_claims)


def test_citation_validator_valid_and_missing() -> None:
    """Test citation validation identifying valid citations, non-existent chunks, and missing citations."""
    validator = CitationValidator()

    chunks = [
        RetrievedChunk(
            chunk_id="chk_1",
            document_id="doc_1",
            text="Earth orbits the Sun once every 365 days.",
        ),
    ]

    # 1. Valid citation
    answer_valid = (
        "Earth completes an orbit around the Sun in approximately 365 days [1]."
    )
    citations, failures, _ = validator.validate_citations(answer_valid, chunks)
    assert len(citations) == 1
    assert citations[0].status == CitationStatus.VALID
    assert citations[0].cited_chunk_id == "chk_1"

    # 2. Invalid chunk citation [99]
    answer_invalid = "Earth orbits the Sun [99]."
    citations_inv, failures_inv, _ = validator.validate_citations(
        answer_invalid, chunks
    )
    assert len(citations_inv) == 1
    assert citations_inv[0].status == CitationStatus.INVALID_CHUNK
    assert any(
        f.category
        in (RAGFailureCategory.CITATION_FAILURE, RAGFailureCategory.INVALID_CITATION)
        for f in failures_inv
    )

    # 3. Missing citation
    answer_uncited = "Earth orbits the Sun once every 365 days with zero citations."
    citations_uncited, failures_uncited, _ = validator.validate_citations(
        answer_uncited, chunks
    )
    assert any(
        f.category
        in (RAGFailureCategory.MISSING_CITATION, RAGFailureCategory.CITATION_FAILURE)
        for f in failures_uncited
    )


def test_evidence_aligner_support_and_contradiction() -> None:
    """Test fact-checking claims against chunks with support status classification."""
    aligner = EvidenceAligner()
    extractor = ClaimExtractor()

    chunks = [
        RetrievedChunk(
            chunk_id="chk_1",
            document_id="doc_1",
            text="Python was created by Guido van Rossum and released in 1991.",
        ),
        RetrievedChunk(
            chunk_id="chk_2",
            document_id="doc_2",
            text="The speed of light in vacuum is approximately 299,792,458 meters per second.",
        ),
    ]

    claims = [
        extractor.extract_claims("Python was created by Guido van Rossum in 1991.")[0],
        extractor.extract_claims("Python was created in 2050 by an unknown entity.")[0],
        extractor.extract_claims(
            "The speed of light in vacuum is 300,000 kilometers per second."
        )[0],
    ]

    evaluated_claims, evidence_list, links, metrics = aligner.align_claims(
        claims, chunks
    )

    # First claim is supported
    assert evaluated_claims[0].support_status == ClaimSupportStatus.SUPPORTED
    # Second claim contradicts 1991
    assert evaluated_claims[1].support_status in (
        ClaimSupportStatus.CONTRADICTED,
        ClaimSupportStatus.UNSUPPORTED,
    )
    # Check coverage metrics
    assert metrics["supported_claims_ratio"] > 0.0
    assert "evidence_coverage" in metrics
