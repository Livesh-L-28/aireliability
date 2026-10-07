"""Unit tests for fingerprinting, token similarity, and deduplication (Phase 36)."""

from __future__ import annotations

from datetime import UTC, datetime

from aireliability.generation.deduplication import TestDeduplicator
from aireliability.generation.fingerprint import (
    compute_fingerprint,
    compute_token_similarity,
)
from aireliability.generation.models import (
    GeneratedTest,
    GenerationSourceType,
    GenerationStrategy,
    TestProvenance,
    TestQualityScore,
)


def _make_test(
    test_id: str,
    input_text: str,
    criteria: list[str],
    quality: float = 0.8,
) -> GeneratedTest:
    prov = TestProvenance(
        source_type=GenerationSourceType.SYNTHETIC,
        source_id="test_src",
        timestamp=datetime.now(UTC),
    )
    score = TestQualityScore(total_score=quality)
    return GeneratedTest(
        test_id=test_id,
        name=f"test_{test_id}",
        strategy=GenerationStrategy.EDGE_CASE,
        input=input_text,
        expected_criteria=criteria,
        provenance=prov,
        quality_score=score,
    )


def test_fingerprint_determinism_and_invariance() -> None:
    """Verify fingerprints are invariant to volatile IDs but sensitive to semantics."""
    t1 = _make_test("id_1", "What is the capital of Japan?", ["must answer Tokyo"])
    t2 = _make_test("id_2", "what is the capital of japan?  ", ["must answer tokyo"])
    # Volatile difference only (test_id, whitespace, case)
    fp1 = compute_fingerprint(t1)
    fp2 = compute_fingerprint(t2)
    assert fp1 == fp2

    # Semantic difference
    t3 = _make_test("id_3", "What is the capital of France?", ["must answer Paris"])
    fp3 = compute_fingerprint(t3)
    assert fp1 != fp3


def test_token_similarity() -> None:
    """Verify token Jaccard similarity behaves properly."""
    t1 = _make_test("1", "Calculate the discount on order", ["valid answer"])
    t2 = _make_test("2", "Calculate the discount on order", ["valid answer"])
    t3 = _make_test("3", "Unrelated query about astronomy galaxies", ["stars"])

    assert compute_token_similarity(t1, t2) == 1.0
    sim_unrelated = compute_token_similarity(t1, t3)
    assert sim_unrelated < 0.20


def test_exact_deduplication() -> None:
    """Verify exact duplicates are pruned and higher quality candidate kept."""
    t1 = _make_test("t1", "Query A", ["must match"], quality=0.7)
    t2 = _make_test("t2", "Query A", ["must match"], quality=0.9)
    t3 = _make_test("t3", "Query B", ["different criteria"], quality=0.8)

    dedup = TestDeduplicator(mode="exact")
    unique, dropped = dedup.deduplicate([t1, t2, t3])

    assert len(unique) == 2
    assert dropped == 1
    # Check that higher quality test (t2 with 0.9) was retained over t1 (0.7)
    retained_q_a = next(t for t in unique if "Query A" in str(t.input))
    assert retained_q_a.test_id == "t2"


def test_near_duplicate_deduplication() -> None:
    """Verify near-duplicate detection prunes semantically close candidates."""
    t1 = _make_test(
        "1",
        "Please summarize the main article in three sentences",
        ["summary criteria"],
        quality=0.9,
    )
    t2 = _make_test(
        "2",
        "Please summarize the main article in three sentences.",
        ["summary criteria"],
        quality=0.8,
    )
    t3 = _make_test(
        "3",
        "Completely different query about quantum computing",
        ["quantum criteria"],
        quality=0.85,
    )

    dedup = TestDeduplicator(mode="exact_and_near", near_duplicate_threshold=0.80)
    unique, dropped = dedup.deduplicate([t1, t2, t3])

    assert len(unique) == 2
    assert dropped == 1
    assert any(t.test_id == "1" for t in unique)
    assert any(t.test_id == "3" for t in unique)


def test_deduplicator_mode_off() -> None:
    """Verify deduplication can be disabled."""
    t1 = _make_test("1", "Same query", ["criteria"])
    t2 = _make_test("2", "Same query", ["criteria"])

    dedup = TestDeduplicator(mode="off")
    unique, dropped = dedup.deduplicate([t1, t2])
    assert len(unique) == 2
    assert dropped == 0
