"""Knowledge Freshness and Index Staleness Tracker."""

from __future__ import annotations

from datetime import UTC, datetime

from aireliability.rag.models import (
    FailureSeverity,
    RAGFailure,
    RAGFailureCategory,
    RAGStage,
    RetrievedChunk,
    RetrievedDocument,
)


class FreshnessTracker:
    """Tracks document and evidence freshness, staleness policies, and index version alignment."""

    def __init__(self, default_max_age_days: int = 90) -> None:
        self.default_max_age_days = default_max_age_days

    def evaluate_freshness(
        self,
        documents: list[RetrievedDocument],
        chunks: list[RetrievedChunk] | None = None,
        max_age_days: int | None = None,
        index_timestamp: datetime | None = None,
    ) -> tuple[float, float, list[RAGFailure], str]:
        """Evaluate document freshness and index staleness.

        Returns (freshness_score, stale_rate, list_of_failures, explanation).
        """
        failures: list[RAGFailure] = []
        now = datetime.now(UTC)
        allowed_days = max_age_days or self.default_max_age_days

        if not documents:
            return 1.0, 0.0, [], "No documents to evaluate for freshness."

        total_docs = len(documents)
        stale_docs = 0
        missing_meta_docs = 0
        index_stale_detected = False

        for doc in documents:
            # Check for missing timestamp metadata
            if doc.last_updated is None and doc.ingestion_timestamp is None:
                missing_meta_docs += 1
                continue

            doc_time = doc.last_updated or doc.ingestion_timestamp
            if doc_time.tzinfo is None:
                doc_time = doc_time.replace(tzinfo=UTC)

            age_days = (now - doc_time).total_seconds() / 86400.0

            if age_days > allowed_days:
                stale_docs += 1
                failures.append(
                    RAGFailure(
                        stage=RAGStage.FRESHNESS,
                        category=RAGFailureCategory.FRESHNESS_FAILURE,
                        severity=FailureSeverity.MEDIUM,
                        message=(
                            f"STALE_DOCUMENT: Document '{doc.document_id}' is {age_days:.1f} days old "
                            f"(exceeds max age of {allowed_days} days)."
                        ),
                        affected_component=doc.document_id,
                        confidence=0.95,
                    )
                )

            # Check index staleness: document was updated AFTER the vector index was built
            if index_timestamp:
                idx_time = (
                    index_timestamp
                    if index_timestamp.tzinfo
                    else index_timestamp.replace(tzinfo=UTC)
                )
                if doc_time > idx_time:
                    index_stale_detected = True
                    failures.append(
                        RAGFailure(
                            stage=RAGStage.FRESHNESS,
                            category=RAGFailureCategory.INDEX_STALENESS,
                            severity=FailureSeverity.HIGH,
                            message=(
                                f"INDEX_STALENESS: Document '{doc.document_id}' updated at {doc_time.isoformat()} "
                                f"after search index was built at {idx_time.isoformat()}."
                            ),
                            affected_component=doc.document_id,
                            confidence=0.95,
                        )
                    )

        if missing_meta_docs > 0:
            failures.append(
                RAGFailure(
                    stage=RAGStage.FRESHNESS,
                    category=RAGFailureCategory.FRESHNESS_FAILURE,
                    severity=FailureSeverity.LOW,
                    message=f"MISSING_METADATA: {missing_meta_docs} document(s) lack timestamps for freshness tracking.",
                    confidence=1.0,
                )
            )

        stale_rate = round(stale_docs / total_docs, 4)
        freshness_score = round(
            max(0.0, 1.0 - stale_rate - (0.1 if index_stale_detected else 0.0)), 4
        )
        if not index_stale_detected:
            freshness_score = round(max(0.0, 1.0 - stale_rate), 4)

        explanation = (
            f"Freshness Score: {freshness_score:.2f}, Stale rate: {stale_rate:.2f} "
            f"({stale_docs}/{total_docs} stale documents, policy: {allowed_days} days)."
        )

        return freshness_score, stale_rate, failures, explanation

    def detect_index_staleness(
        self,
        docs: list[RetrievedDocument],
        index_timestamp: datetime,
    ) -> list[RAGFailure]:
        """Detect documents updated after vector index timestamp."""
        failures: list[RAGFailure] = []
        idx_time = (
            index_timestamp
            if index_timestamp.tzinfo
            else index_timestamp.replace(tzinfo=UTC)
        )

        for doc in docs:
            doc_time = doc.last_updated or doc.updated_at or doc.ingestion_timestamp
            if doc_time:
                if doc_time.tzinfo is None:
                    doc_time = doc_time.replace(tzinfo=UTC)
                if doc_time > idx_time:
                    failures.append(
                        RAGFailure(
                            stage=RAGStage.FRESHNESS,
                            category=RAGFailureCategory.INDEX_STALENESS,
                            severity=FailureSeverity.HIGH,
                            message=(
                                f"INDEX_STALENESS: Document '{doc.document_id}' updated at {doc_time.isoformat()} "
                                f"after search index was built at {idx_time.isoformat()}."
                            ),
                            affected_component=doc.document_id,
                            confidence=0.95,
                        )
                    )
        return failures
