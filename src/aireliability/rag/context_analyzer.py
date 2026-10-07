"""Context Analyzer evaluating context relevance, redundancy, truncation, lost-in-the-middle, and conflicts."""

from __future__ import annotations

import re
from typing import Any

from aireliability.rag.models import (
    ConflictStatus,
    ContextConflict,
    ContextWindow,
    FailureSeverity,
    RAGFailure,
    RAGFailureCategory,
    RAGStage,
    RetrievedChunk,
)


class ContextAnalyzer:
    """Analyzes prompt context construction, positioning, truncation, and evidence conflicts."""

    def __init__(self, max_context_tokens: int = 4096) -> None:
        self.max_context_tokens = max_context_tokens

    def analyze_context(
        self,
        chunks: list[RetrievedChunk],
        query_text: str = "",
        max_tokens: int | None = None,
        expected_chunk_ids: list[str] | None = None,
        critical_chunk_ids: list[str] | None = None,
        answer_text: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[ContextWindow, list[ContextConflict], list[RAGFailure]]:
        """Convenience method returning (ContextWindow, conflicts, failures)."""
        res, cnf, fails, _ = self.analyze(
            chunks=chunks,
            query_text=query_text,
            max_tokens=max_tokens,
            expected_chunk_ids=expected_chunk_ids or critical_chunk_ids,
            metadata=metadata,
        )
        return res, cnf, fails

    def analyze(
        self,
        chunks: list[RetrievedChunk],
        query_text: str = "",
        max_tokens: int | None = None,
        expected_chunk_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[ContextWindow, list[ContextConflict], list[RAGFailure], float]:
        """Analyze context construction, position sensitivity, and evidence contradictions."""
        failures: list[RAGFailure] = []
        conflicts: list[ContextConflict] = []
        cap = max_tokens or self.max_context_tokens

        # Format context text
        full_text = "\n\n".join(f"[{c.chunk_id}] {c.text}" for c in chunks)
        token_count = max(1, len(full_text.split()) * 4 // 3)

        # 1. Truncation and Overflow Checks
        is_truncated = token_count > cap or (
            len(full_text) > 0
            and not full_text.rstrip().endswith((".", "!", "?", '"', "}", "]"))
        )
        if token_count > cap:
            failures.append(
                RAGFailure(
                    stage=RAGStage.CONTEXT,
                    category=RAGFailureCategory.CONTEXT_OVERFLOW,
                    severity=FailureSeverity.HIGH,
                    message=f"CONTEXT_OVERFLOW: Context size ({token_count} tokens) exceeds maximum allowance ({cap} tokens).",
                    confidence=1.0,
                )
            )

        # 2. Redundancy (Jaccard token overlap between adjacent chunks)
        redundancy_score = self._compute_redundancy(chunks)
        if redundancy_score > 0.40:
            failures.append(
                RAGFailure(
                    stage=RAGStage.CONTEXT,
                    category=RAGFailureCategory.CONTEXT_FAILURE,
                    severity=FailureSeverity.MEDIUM,
                    message=f"CONTEXT_REDUNDANCY: High chunk overlap ({redundancy_score:.2f}) consuming excessive context budget.",
                    confidence=0.85,
                )
            )

        # 3. Position Distribution and Lost-in-the-Middle Assessment
        n = len(chunks)
        beg_count = n // 3
        mid_count = n // 3
        end_count = n - beg_count - mid_count

        potential_sensitivity = 0.0
        if expected_chunk_ids and n >= 3:
            # Check if all critical target chunks fall exclusively into the middle partition
            targets = set(expected_chunk_ids)
            mid_chunks = chunks[beg_count : beg_count + mid_count]
            mid_targets = [c.chunk_id for c in mid_chunks if c.chunk_id in targets]

            outside_targets = [
                c.chunk_id
                for c in (chunks[:beg_count] + chunks[beg_count + mid_count :])
                if c.chunk_id in targets
            ]

            if mid_targets and not outside_targets:
                potential_sensitivity = 0.75
                failures.append(
                    RAGFailure(
                        stage=RAGStage.CONTEXT,
                        category=RAGFailureCategory.CONTEXT_FAILURE,
                        severity=FailureSeverity.LOW,
                        message=(
                            "LOST_IN_THE_MIDDLE_RISK: Critical evidence chunks are positioned exclusively in the "
                            "middle 33%-66% zone of the context window. Monitor for position sensitivity."
                        ),
                        confidence=0.70,
                    )
                )

        # 4. Conflict / Contradiction Detection across chunks
        conflicts = self._detect_conflicts(chunks)
        for cnf in conflicts:
            failures.append(
                RAGFailure(
                    stage=RAGStage.CONTEXT,
                    category=RAGFailureCategory.KNOWLEDGE_CONFLICT,
                    severity=FailureSeverity.HIGH,
                    message=f"EVIDENCE_CONFLICT: Contradiction between documents '{cnf.doc_a_id}' and '{cnf.doc_b_id}': {cnf.description}",
                    confidence=cnf.confidence,
                )
            )

        # 5. Context Score Computation
        base_score = 1.0
        if token_count > cap:
            base_score -= 0.35
        if redundancy_score > 0.3:
            base_score -= redundancy_score * 0.3
        if conflicts:
            base_score -= min(0.4, len(conflicts) * 0.15)
        if potential_sensitivity > 0.5:
            base_score -= 0.05
        context_score = max(0.0, min(1.0, base_score))

        window = ContextWindow(
            context_text=full_text,
            included_chunks=chunks,
            token_count=token_count,
            max_tokens=cap,
            is_truncated=is_truncated,
            redundancy_score=round(redundancy_score, 4),
            conflict_count=len(conflicts),
            beginning_chunks_count=beg_count,
            middle_chunks_count=mid_count,
            ending_chunks_count=end_count,
            potential_position_sensitivity=round(potential_sensitivity, 2),
            lost_in_the_middle_detected=(potential_sensitivity > 0.5),
        )

        return window, conflicts, failures, round(context_score, 4)

    def _compute_redundancy(self, chunks: list[RetrievedChunk]) -> float:
        """Compute average pairwise Jaccard similarity across retrieved chunks."""
        if len(chunks) < 2:
            return 0.0

        overlaps: list[float] = []
        token_sets = [set(c.text.lower().split()) for c in chunks if c.text]

        for i in range(len(token_sets)):
            for j in range(
                i + 1, min(len(token_sets), i + 4)
            ):  # Bound checks to nearby chunks
                set_a = token_sets[i]
                set_b = token_sets[j]
                if set_a and set_b:
                    jaccard = len(set_a & set_b) / len(set_a | set_b)
                    overlaps.append(jaccard)

        return sum(overlaps) / len(overlaps) if overlaps else 0.0

    def _detect_conflicts(self, chunks: list[RetrievedChunk]) -> list[ContextConflict]:
        """Detect factual contradictions (e.g. date mismatches, opposite assertions) between chunks."""
        conflicts: list[ContextConflict] = []
        if len(chunks) < 2:
            return conflicts

        seen_pairs = set()

        # Check pairwise chunks across different documents with high keyword overlap and conflicting years
        for i in range(min(len(chunks), 12)):
            c_a = chunks[i]
            for j in range(i + 1, min(len(chunks), 12)):
                c_b = chunks[j]
                if c_a.document_id == c_b.document_id:
                    continue
                words_a = set(re.findall(r"\b\w{3,}\b", c_a.text.lower()))
                words_b = set(re.findall(r"\b\w{3,}\b", c_b.text.lower()))
                shared = words_a & words_b
                years_a = set(re.findall(r"\b(1\d{3}|20\d{2})\b", c_a.text))
                years_b = set(re.findall(r"\b(1\d{3}|20\d{2})\b", c_b.text))
                if len(shared) >= 2 and years_a and years_b and years_a != years_b:
                    pair_key = tuple(sorted([c_a.document_id, c_b.document_id]))
                    if pair_key not in seen_pairs:
                        seen_pairs.add(pair_key)
                        conflicts.append(
                            ContextConflict(
                                doc_a_id=c_a.document_id,
                                doc_b_id=c_b.document_id,
                                chunk_a_id=c_a.chunk_id,
                                chunk_b_id=c_b.chunk_id,
                                statement_a=c_a.text[:120],
                                statement_b=c_b.text[:120],
                                status=ConflictStatus.UNRESOLVED,
                                conflict_type="temporal_date_conflict",
                                description=f"Conflicting dates between {c_a.document_id} and {c_b.document_id}",
                                confidence=0.90,
                            )
                        )

        # Opposite assertion check: e.g. "is approved" vs "is rejected" or "is safe" vs "is unsafe"
        polar_opposites = [
            (
                re.compile(r"\b(approved|authorized)\b", re.I),
                re.compile(r"\b(rejected|denied|disapproved)\b", re.I),
            ),
            (
                re.compile(r"\b(effective|successful)\b", re.I),
                re.compile(r"\b(ineffective|failed|unsuccessful)\b", re.I),
            ),
            (
                re.compile(r"\b(compliant|legal)\b", re.I),
                re.compile(r"\b(non-compliant|illegal)\b", re.I),
            ),
        ]

        for i in range(min(len(chunks), 8)):
            c_a = chunks[i]
            for j in range(i + 1, min(len(chunks), 8)):
                c_b = chunks[j]
                if c_a.document_id == c_b.document_id:
                    continue
                # If both mention the same subject entity
                words_a = set(c_a.text.lower().split())
                words_b = set(c_b.text.lower().split())
                shared = words_a & words_b
                if len(shared) >= 4:
                    for pos_pat, neg_pat in polar_opposites:
                        if (pos_pat.search(c_a.text) and neg_pat.search(c_b.text)) or (
                            neg_pat.search(c_a.text) and pos_pat.search(c_b.text)
                        ):
                            conflicts.append(
                                ContextConflict(
                                    doc_a_id=c_a.document_id,
                                    doc_b_id=c_b.document_id,
                                    chunk_a_id=c_a.chunk_id,
                                    chunk_b_id=c_b.chunk_id,
                                    statement_a=c_a.text[:100],
                                    statement_b=c_b.text[:100],
                                    status=ConflictStatus.UNRESOLVED,
                                    conflict_type="polarity_contradiction",
                                    description=f"Contradictory assertions detected between {c_a.document_id} and {c_b.document_id}",
                                    confidence=0.82,
                                )
                            )
                            break

        return conflicts
