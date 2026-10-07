"""Unit tests for Phase 34 failure normalization, fingerprinting, and clustering."""

from __future__ import annotations

from aireliability.core.models import FailureReport
from aireliability.diagnosis.models import RootCause, RootCauseCategory, RootCauseType
from aireliability.intelligence.clustering import FailureClusterer
from aireliability.intelligence.similarity import (
    FailureNormalizer,
    compute_fingerprint,
    failure_similarity,
    token_similarity,
)


def test_failure_normalizer_sanitization() -> None:
    normalizer = FailureNormalizer()

    raw_msg = (
        "Failed with apiKey=sk-abcdef1234567890 at 2026-10-06T12:00:00Z "
        "pointer 0x7ffee1234abc for session 12345678-1234-1234-1234-123456789abc"
    )
    sanitized = normalizer.sanitize_message(raw_msg)
    assert "sk-abcdef1234567890" not in sanitized
    assert "0x7ffee1234abc" not in sanitized
    assert "12345678-1234-1234-1234-123456789abc" not in sanitized
    assert "<UUID>" in sanitized
    assert "<HEX>" in sanitized


def test_failure_normalizer_stable_fingerprint() -> None:
    normalizer = FailureNormalizer()

    f1 = FailureReport(
        trace_id="tr_1",
        category="retrieval",
        type="missing_context",
        message="Document 10042 at 2026-10-06 10:00:00 not found for user 998877.",
        metadata={"component": "vector_db"},
    )
    f2 = FailureReport(
        trace_id="tr_2",
        category="retrieval",
        type="missing_context",
        message="Document 55432 at 2026-10-06 11:00:00 not found for user 112233.",
        metadata={"component": "vector_db"},
    )

    n1 = normalizer.normalize(f1)
    n2 = normalizer.normalize(f2)

    # Volatile numeric IDs and timestamps are sanitized -> fingerprints match!
    assert n1.fingerprint == n2.fingerprint
    assert n1.category == "retrieval"
    assert n1.component == "vector_db"


def test_compute_fingerprint_distinct() -> None:
    fp1 = compute_fingerprint(
        category="retrieval",
        failure_type="missing_context",
        component="faiss",
        sanitized_message="missing context",
    )
    fp2 = compute_fingerprint(
        category="safety",
        failure_type="toxic_output",
        component="guardrail",
        sanitized_message="toxic content detected",
    )
    assert fp1 != fp2


def test_token_similarity_cases() -> None:
    assert token_similarity("hello world", "hello world") == 1.0
    assert token_similarity("hello world", "goodbye universe") == 0.0
    assert 0.0 < token_similarity("query failed timeout", "query timeout error") < 1.0
    assert token_similarity("", "") == 1.0


def test_failure_similarity() -> None:
    normalizer = FailureNormalizer()
    f1 = FailureReport(
        trace_id="t1",
        category="tool",
        type="wrong_argument",
        message="Argument schema violation",
    )
    f2 = FailureReport(
        trace_id="t2",
        category="tool",
        type="wrong_argument",
        message="Argument schema violation",
    )
    f3 = FailureReport(
        trace_id="t3",
        category="safety",
        type="harmful_content",
        message="Safety filter triggered",
    )

    n1 = normalizer.normalize(f1)
    n2 = normalizer.normalize(f2)
    n3 = normalizer.normalize(f3)

    assert failure_similarity(n1, n2) == 1.0
    assert failure_similarity(n1, n3) < 0.3


def test_failure_clusterer_empty_and_single() -> None:
    clusterer = FailureClusterer()
    assert clusterer.cluster([]) == []

    normalizer = FailureNormalizer()
    f = FailureReport(
        trace_id="t1",
        category="output",
        type="format_error",
        message="JSON decode error",
    )
    norm = normalizer.normalize(f)
    clusters = clusterer.cluster([norm])
    assert len(clusters) == 1
    assert clusters[0].frequency == 1
    assert clusters[0].dominant_category == "output"
    assert clusters[0].representative_failure_id == f.failure_id


def test_failure_clusterer_multi_grouping() -> None:
    normalizer = FailureNormalizer()
    clusterer = FailureClusterer()

    rc_retrieval = RootCause(
        category=RootCauseCategory.RETRIEVAL,
        type=RootCauseType.MISSING_CONTEXT,
        description="Vector search did not return relevant chunks",
    )

    failures: list[FailureReport] = []
    # 5 retrieval failures
    for i in range(5):
        failures.append(
            FailureReport(
                trace_id=f"tr_ret_{i}",
                category="retrieval",
                type="missing_context",
                message=f"Missing chunk {i} from index",
                metadata={"component": "retriever:chroma"},
            )
        )
    # 3 safety failures
    for i in range(3):
        failures.append(
            FailureReport(
                trace_id=f"tr_saf_{i}",
                category="safety",
                type="jailbreak",
                message="Adversarial prompt bypassed guard",
                metadata={"component": "guardrail:safety"},
            )
        )

    norm_failures = [
        normalizer.normalize(
            f, root_cause=rc_retrieval if f.category == "retrieval" else None
        )
        for f in failures
    ]

    clusters = clusterer.cluster(norm_failures)
    assert len(clusters) == 2
    # Sorted by frequency descending
    assert clusters[0].frequency == 5
    assert clusters[0].dominant_category == "retrieval"
    assert "retriever:chroma" in clusters[0].affected_components
    assert clusters[1].frequency == 3
    assert clusters[1].dominant_category == "safety"
