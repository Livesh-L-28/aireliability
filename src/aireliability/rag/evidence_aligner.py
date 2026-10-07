"""Evidence Aligner evaluating factual alignment between claims and retrieved context."""

from __future__ import annotations

import re

from aireliability.rag.models import (
    Claim,
    ClaimEvidenceLink,
    ClaimImportance,
    ClaimSupportStatus,
    Evidence,
    RetrievedChunk,
)


class EvidenceAligner:
    """Verifies and aligns atomic claims against retrieved evidence chunks."""

    def __init__(
        self,
        support_similarity_threshold: float = 0.55,
        partial_similarity_threshold: float = 0.35,
    ) -> None:
        self.support_similarity_threshold = support_similarity_threshold
        self.partial_similarity_threshold = partial_similarity_threshold

    def align_claims(
        self,
        claims: list[Claim],
        chunks: list[RetrievedChunk],
    ) -> tuple[list[Claim], list[Evidence], list[ClaimEvidenceLink], dict[str, float]]:
        """Align claims to evidence chunks and compute coverage metrics."""
        aligned_claims: list[Claim] = []
        evidence_list: list[Evidence] = []
        links: list[ClaimEvidenceLink] = []

        # Build evidence pool from chunks
        for chk in chunks:
            evidence_list.append(
                Evidence(
                    chunk_id=chk.chunk_id,
                    document_id=chk.document_id,
                    text=chk.text,
                    relevance_score=chk.retrieval_score or 1.0,
                    timestamp=chk.timestamp,
                )
            )

        if not claims:
            metrics = {
                "evidence_coverage": 1.0,
                "important_evidence_coverage": 1.0,
                "unsupported_claim_rate": 0.0,
                "contradiction_rate": 0.0,
            }
            return [], evidence_list, [], metrics

        if not chunks:
            # All claims are unsupported if no chunks were retrieved
            unsupported_claims = [
                claim.model_copy(
                    update={"support_status": ClaimSupportStatus.UNSUPPORTED}
                )
                for claim in claims
            ]
            metrics = {
                "evidence_coverage": 0.0,
                "important_evidence_coverage": 0.0,
                "unsupported_claim_rate": 1.0,
                "contradiction_rate": 0.0,
            }
            return unsupported_claims, evidence_list, [], metrics

        for claim in claims:
            best_status = ClaimSupportStatus.UNSUPPORTED
            best_sim = 0.0
            best_evi: Evidence | None = None
            matched_evidence_ids: list[str] = []

            for evi in evidence_list:
                status, sim = self._check_claim_against_evidence(claim.text, evi.text)
                if sim > best_sim:
                    best_sim = sim
                    best_status = status
                    best_evi = evi

                if status in (
                    ClaimSupportStatus.SUPPORTED,
                    ClaimSupportStatus.PARTIALLY_SUPPORTED,
                ):
                    matched_evidence_ids.append(evi.evidence_id)

            if best_evi and best_sim > 0.20:
                links.append(
                    ClaimEvidenceLink(
                        claim_id=claim.claim_id,
                        evidence_id=best_evi.evidence_id,
                        status=best_status,
                        similarity=round(best_sim, 4),
                        confidence=0.90
                        if best_status != ClaimSupportStatus.UNKNOWN
                        else 0.50,
                        reasoning=f"Matched evidence chunk '{best_evi.chunk_id}' with similarity {best_sim:.2f}",
                    )
                )

            updated_claim = claim.model_copy(
                update={
                    "support_status": best_status,
                    "evidence_ids": matched_evidence_ids
                    or (
                        [best_evi.evidence_id]
                        if best_evi and best_status == ClaimSupportStatus.CONTRADICTED
                        else []
                    ),
                    "confidence": round(max(0.5, best_sim), 2),
                }
            )
            aligned_claims.append(updated_claim)

        # Compute coverage metrics
        total = len(aligned_claims)
        supported_count = sum(
            1
            for c in aligned_claims
            if c.support_status == ClaimSupportStatus.SUPPORTED
        )
        partial_count = sum(
            1
            for c in aligned_claims
            if c.support_status == ClaimSupportStatus.PARTIALLY_SUPPORTED
        )
        contradicted_count = sum(
            1
            for c in aligned_claims
            if c.support_status == ClaimSupportStatus.CONTRADICTED
        )
        unsupported_count = sum(
            1
            for c in aligned_claims
            if c.support_status == ClaimSupportStatus.UNSUPPORTED
        )

        critical_claims = [
            c for c in aligned_claims if c.importance == ClaimImportance.CRITICAL
        ]
        crit_supported = sum(
            1
            for c in critical_claims
            if c.support_status == ClaimSupportStatus.SUPPORTED
        )
        crit_coverage = (
            (crit_supported / len(critical_claims)) if critical_claims else 1.0
        )

        metrics = {
            "evidence_coverage": round(
                (supported_count + 0.5 * partial_count) / total, 4
            ),
            "supported_claims_ratio": round(supported_count / total, 4),
            "important_evidence_coverage": round(crit_coverage, 4),
            "unsupported_claim_rate": round(unsupported_count / total, 4),
            "contradiction_rate": round(contradicted_count / total, 4),
        }

        return aligned_claims, evidence_list, links, metrics

    def _check_claim_against_evidence(
        self, claim_text: str, evidence_text: str
    ) -> tuple[ClaimSupportStatus, float]:
        """Evaluate token overlap and polarity contradictions."""
        c_words = set(re.findall(r"\b\w{3,}\b", claim_text.lower()))
        e_words = set(re.findall(r"\b\w{3,}\b", evidence_text.lower()))

        if not c_words or not e_words:
            return ClaimSupportStatus.UNSUPPORTED, 0.0

        overlap = c_words & e_words
        sim = len(overlap) / len(c_words)

        # Contradiction check: negation or opposite numbers
        has_claim_neg = bool(
            re.search(r"\b(not|never|no|neither|cannot|denied)\b", claim_text, re.I)
        )
        has_evi_neg = bool(
            re.search(r"\b(not|never|no|neither|cannot|denied)\b", evidence_text, re.I)
        )

        # Check conflicting numbers on shared entity
        c_nums = re.findall(r"\b\d+\b", claim_text)
        e_nums = re.findall(r"\b\d+\b", evidence_text)
        if c_nums and e_nums and not (set(c_nums) & set(e_nums)) and sim >= 0.20:
            return ClaimSupportStatus.CONTRADICTED, sim
        if c_nums and not any(n in evidence_text for n in c_nums) and sim >= 0.20:
            return ClaimSupportStatus.CONTRADICTED, sim

        if sim > 0.40 and (has_claim_neg != has_evi_neg):
            return ClaimSupportStatus.CONTRADICTED, sim

        # Check year mismatch e.g., claim says 2050, evidence says 1991 on same topic
        c_years = re.findall(r"\b(1\d{3}|20\d{2})\b", claim_text)
        e_years = re.findall(r"\b(1\d{3}|20\d{2})\b", evidence_text)
        if c_years and e_years and set(c_years) != set(e_years) and sim >= 0.30:
            return ClaimSupportStatus.CONTRADICTED, sim

        if sim >= self.support_similarity_threshold:
            return ClaimSupportStatus.SUPPORTED, sim
        if sim >= self.partial_similarity_threshold:
            return ClaimSupportStatus.PARTIALLY_SUPPORTED, sim

        return ClaimSupportStatus.UNSUPPORTED, sim
