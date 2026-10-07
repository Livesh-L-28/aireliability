"""Knowledge Base Health Auditor evaluating documents, chunk quality, and source reliability."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from aireliability.rag.models import (
    KBHealthStatus,
    KnowledgeBaseHealthReport,
    RetrievedChunk,
    RetrievedDocument,
)


class KnowledgeBaseAuditor:
    """Audits knowledge base documents and chunks for health, quality, duplication, and staleness."""

    def __init__(self, max_doc_age_days: int = 90) -> None:
        self.max_doc_age_days = max_doc_age_days

    def audit_knowledge_base(
        self,
        documents: list[RetrievedDocument],
        chunks: list[RetrievedChunk] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> KnowledgeBaseHealthReport:
        """Execute comprehensive health check over documents and chunks."""
        doc_count = len(documents)
        chunk_list = chunks or []
        chunk_count = len(chunk_list)

        if doc_count == 0 and chunk_count == 0:
            return KnowledgeBaseHealthReport(
                document_count=0,
                chunk_count=0,
                status=KBHealthStatus.DEGRADED,
                recommendations=["Knowledge base is empty. Ingest source documents."],
            )

        now = datetime.now(UTC)
        recommendations: list[str] = []

        # 1. Document-level checks
        empty_docs = 0
        missing_meta = 0
        stale_docs = 0

        for doc in documents:
            if not doc.text or len(doc.text.strip()) < 10:
                empty_docs += 1
            if not doc.title or not doc.source:
                missing_meta += 1

            ts = doc.last_updated or doc.ingestion_timestamp
            if ts:
                ts_utc = ts if ts.tzinfo else ts.replace(tzinfo=UTC)
                age = (now - ts_utc).total_seconds() / 86400.0
                if age > self.max_doc_age_days:
                    stale_docs += 1
            else:
                missing_meta += 1

        # 2. Chunk-level checks: Duplication & Orphaned Chunks
        doc_id_set = {d.document_id for d in documents}
        orphaned_count = 0
        dup_chunks_count = 0
        fragmented_chunks = 0

        seen_chunk_hashes = set()
        for c in chunk_list:
            if documents and c.document_id not in doc_id_set:
                orphaned_count += 1

            # Simple hash for exact/near duplication
            norm = " ".join(c.text.lower().split()[:30])
            if norm in seen_chunk_hashes:
                dup_chunks_count += 1
            else:
                seen_chunk_hashes.add(norm)

            # Check sentence boundary fragmentation: chunk starts mid-word or ends mid-word
            if len(c.text) > 20 and not c.text.strip().endswith(
                (".", "!", "?", '"', ":", ";")
            ):
                fragmented_chunks += 1

        # Compute rates
        stale_rate = round(stale_docs / max(1, doc_count), 4)
        meta_completeness = round(max(0.0, 1.0 - (missing_meta / max(1, doc_count))), 4)
        dup_rate = (
            round(dup_chunks_count / max(1, chunk_count), 4) if chunk_count else 0.0
        )

        # Formulate recommendations
        if empty_docs > 0:
            recommendations.append(
                f"Purge or re-ingest {empty_docs} empty or near-empty document(s)."
            )
        if stale_rate > 0.30:
            recommendations.append(
                f"High staleness: {stale_docs} document(s) exceed {self.max_doc_age_days}-day limit."
            )
        if dup_rate > 0.15:
            recommendations.append(
                f"High duplication: {dup_chunks_count} redundant chunk(s) detected. Enable deduplication."
            )
        if orphaned_count > 0:
            recommendations.append(
                f"Found {orphaned_count} orphaned chunk(s) referencing non-existent document IDs."
            )
        if fragmented_chunks > max(1, chunk_count // 3):
            recommendations.append(
                "High sentence boundary fragmentation: adjust chunking window with sentence-aware delimiters."
            )

        # Determine health status
        status = KBHealthStatus.HEALTHY
        if stale_rate > 0.50 or dup_rate > 0.40 or empty_docs > (doc_count // 2):
            status = KBHealthStatus.CRITICAL
        elif (
            stale_rate > 0.20
            or dup_rate > 0.10
            or orphaned_count > 0
            or meta_completeness < 0.70
        ):
            status = KBHealthStatus.DEGRADED

        return KnowledgeBaseHealthReport(
            document_count=doc_count,
            chunk_count=chunk_count,
            empty_document_count=empty_docs,
            duplicate_chunk_rate=dup_rate,
            stale_document_rate=stale_rate,
            conflict_rate=0.0,
            metadata_completeness_rate=meta_completeness,
            orphaned_chunks_count=orphaned_count,
            status=status,
            recommendations=recommendations,
        )
