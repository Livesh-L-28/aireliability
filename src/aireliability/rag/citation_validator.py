"""Citation Validator parsing inline citations and verifying chunk existence and evidence support."""

from __future__ import annotations

import re

from aireliability.rag.models import (
    Citation,
    CitationStatus,
    Claim,
    ClaimImportance,
    FailureSeverity,
    RAGFailure,
    RAGFailureCategory,
    RAGStage,
    RetrievedChunk,
)


class CitationValidator:
    """Validates citations in generated answers against retrieved context chunks and claims."""

    def __init__(self, min_citation_similarity: float = 0.35) -> None:
        self.min_citation_similarity = min_citation_similarity

    def validate_citations(
        self,
        answer_text: str,
        claims_or_chunks: list[Claim] | list[RetrievedChunk] | None = None,
        chunks: list[RetrievedChunk] | None = None,
        claims: list[Claim] | None = None,
    ) -> tuple[list[Citation], list[RAGFailure], float]:
        """Extract citations, check chunk references, verify support, and calculate citation score."""
        citations: list[Citation] = []
        failures: list[RAGFailure] = []

        effective_claims: list[Claim] = []
        effective_chunks: list[RetrievedChunk] = []

        if claims is not None:
            effective_claims = claims
        if chunks is not None:
            effective_chunks = chunks

        if (
            chunks is not None
            and claims_or_chunks is not None
            and not effective_claims
            and isinstance(claims_or_chunks, list)
        ):
            effective_claims = claims_or_chunks  # type: ignore
        elif (
            claims_or_chunks is not None
            and not effective_chunks
            and isinstance(claims_or_chunks, list)
        ):
            if claims_or_chunks and isinstance(claims_or_chunks[0], Claim):
                effective_claims = claims_or_chunks
            else:
                effective_chunks = claims_or_chunks  # type: ignore

        resolved_chunks = effective_chunks
        resolved_claims = effective_claims

        if not resolved_claims and answer_text:
            from aireliability.rag.claim_extractor import ClaimExtractor

            resolved_claims = ClaimExtractor().extract_claims(answer_text)

        chunk_by_id = {c.chunk_id: c for c in resolved_chunks}
        chunk_by_doc = {c.document_id: c for c in resolved_chunks}

        # 1. Regex pattern for bracketed citations: [1], [doc_1], [chk_abc123], [Document A]
        citation_pattern = re.compile(r"\[([a-zA-Z0-9_\-]+|\d+)\]")
        matches = list(citation_pattern.finditer(answer_text))

        for m in matches:
            marker_str = m.group(0)
            raw_target = m.group(1).strip()
            loc_idx = m.start()

            # Find closest preceding or surrounding claim
            nearest_claim = self._find_nearest_claim(
                loc_idx, answer_text, resolved_claims
            )

            # Resolve chunk
            resolved_chunk: RetrievedChunk | None = None
            if raw_target.isdigit():
                idx = int(raw_target) - 1
                if 0 <= idx < len(resolved_chunks):
                    resolved_chunk = resolved_chunks[idx]
            elif raw_target in chunk_by_id:
                resolved_chunk = chunk_by_id[raw_target]
            elif raw_target in chunk_by_doc:
                resolved_chunk = chunk_by_doc[raw_target]
            else:
                # Check case-insensitive prefix match
                for cid, c in chunk_by_id.items():
                    if (
                        raw_target.lower() in cid.lower()
                        or raw_target.lower() in c.document_id.lower()
                    ):
                        resolved_chunk = c
                        break

            if not resolved_chunk:
                citations.append(
                    Citation(
                        marker=marker_str,
                        cited_chunk_id=raw_target,
                        claim_id=nearest_claim.claim_id if nearest_claim else None,
                        status=CitationStatus.INVALID_CHUNK,
                        location_index=loc_idx,
                        reasoning=f"Cited chunk target '{raw_target}' does not exist in retrieved results.",
                    )
                )
                failures.append(
                    RAGFailure(
                        stage=RAGStage.CITATION,
                        category=RAGFailureCategory.INVALID_CITATION,
                        severity=FailureSeverity.MEDIUM,
                        message=f"MISSING_CHUNK: Citation '{marker_str}' references non-existent chunk '{raw_target}'.",
                        affected_component=marker_str,
                        confidence=1.0,
                    )
                )
                continue

            # Verify chunk actually contains evidence supporting the claim
            if nearest_claim:
                sim = self._token_similarity(nearest_claim.text, resolved_chunk.text)
                if sim < self.min_citation_similarity:
                    citations.append(
                        Citation(
                            marker=marker_str,
                            cited_chunk_id=resolved_chunk.chunk_id,
                            claim_id=nearest_claim.claim_id,
                            status=CitationStatus.UNSUPPORTED,
                            location_index=loc_idx,
                            reasoning=f"Cited chunk '{resolved_chunk.chunk_id}' lacks sufficient semantic overlap ({sim:.2f}) with claim.",
                        )
                    )
                    failures.append(
                        RAGFailure(
                            stage=RAGStage.CITATION,
                            category=RAGFailureCategory.UNSUPPORTED_CITATION,
                            severity=FailureSeverity.MEDIUM,
                            message=f"UNSUPPORTED_CITATION: Citation '{marker_str}' points to chunk '{resolved_chunk.chunk_id}' which does not support claim '{nearest_claim.text[:50]}...'.",
                            confidence=0.88,
                        )
                    )
                else:
                    citations.append(
                        Citation(
                            marker=marker_str,
                            cited_chunk_id=resolved_chunk.chunk_id,
                            claim_id=nearest_claim.claim_id,
                            status=CitationStatus.VALID,
                            location_index=loc_idx,
                            reasoning=f"Valid citation pointing to chunk '{resolved_chunk.chunk_id}' (overlap: {sim:.2f}).",
                        )
                    )
            else:
                citations.append(
                    Citation(
                        marker=marker_str,
                        cited_chunk_id=resolved_chunk.chunk_id,
                        claim_id=None,
                        status=CitationStatus.MISMATCH,
                        location_index=loc_idx,
                        reasoning="Citation not linked to any recognized factual proposition.",
                    )
                )

        # 2. Check for missing citations on critical claims
        for claim in resolved_claims:
            if claim.importance == ClaimImportance.CRITICAL:
                has_valid_cit = any(
                    c.claim_id == claim.claim_id and c.status == CitationStatus.VALID
                    for c in citations
                )
                if not has_valid_cit:
                    failures.append(
                        RAGFailure(
                            stage=RAGStage.CITATION,
                            category=RAGFailureCategory.MISSING_CITATION,
                            severity=FailureSeverity.MEDIUM,
                            message=f"MISSING_CITATION: Critical claim '{claim.text[:60]}...' lacks any valid inline citation.",
                            affected_component=claim.claim_id,
                            confidence=0.90,
                        )
                    )

        # 3. Compute citation score
        if not claims and not citations:
            return [], failures, 1.0

        valid_count = sum(1 for c in citations if c.status == CitationStatus.VALID)
        total_citations = len(citations)

        cit_precision = (valid_count / total_citations) if total_citations > 0 else 0.0
        # Check claim citation coverage:
        cited_claims = {
            c.claim_id
            for c in citations
            if c.status == CitationStatus.VALID and c.claim_id
        }
        claim_coverage = (len(cited_claims) / len(claims)) if claims else 1.0

        if total_citations == 0 and claims:
            citation_score = 0.20  # Heavily penalize answers lacking citations entirely
        else:
            citation_score = (0.5 * cit_precision) + (0.5 * claim_coverage)

        return citations, failures, round(max(0.0, min(1.0, citation_score)), 4)

    def _find_nearest_claim(
        self, char_idx: int, answer_text: str, claims: list[Claim]
    ) -> Claim | None:
        """Find the claim text that encompasses or immediately precedes the citation index."""
        if not claims:
            return None

        # Prefer claim whose source sentence contains char_idx
        for c in claims:
            pos = answer_text.find(c.source_sentence)
            if pos != -1 and pos <= char_idx <= (pos + len(c.source_sentence) + 20):
                return c

        return claims[0]

    def _token_similarity(self, text_a: str, text_b: str) -> float:
        """Calculate word token overlap ratio."""
        words_a = set(re.findall(r"\b\w{3,}\b", text_a.lower()))
        words_b = set(re.findall(r"\b\w{3,}\b", text_b.lower()))
        if not words_a:
            return 0.0
        return len(words_a & words_b) / len(words_a)
