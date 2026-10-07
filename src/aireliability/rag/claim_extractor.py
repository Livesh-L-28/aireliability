"""Deterministic Claim Extractor segmenting answers into atomic propositions."""

from __future__ import annotations

import re

from aireliability.rag.models import Claim, ClaimImportance


class ClaimExtractor:
    """Extracts atomic factual claims from generative model answer text."""

    def extract_claims(self, answer_text: str) -> list[Claim]:
        """Extract atomic propositions with importance weighting."""
        cleaned = (answer_text or "").strip()
        if not cleaned:
            return []

        # Split into sentences
        raw_sentences = re.split(r"(?<=[.!?])\s+", cleaned)
        sentences = [s.strip() for s in raw_sentences if s.strip()]

        claims: list[Claim] = []
        for s_idx, sentence in enumerate(sentences):
            # Filter out pure conversational greetings or sign-offs
            if re.match(
                r"^(hello|hi|thanks|thank you|sure|here is the answer|in summary,?\s*$)",
                sentence,
                re.I,
            ):
                continue

            # Check if sentence has multiple independent clauses separated by semicolons or strong conjunctions
            clauses = self._split_into_clauses(sentence)
            for clause in clauses:
                if len(clause.split()) < 3:
                    continue

                importance = self._determine_importance(clause)
                claims.append(
                    Claim(
                        text=clause,
                        source_sentence=sentence,
                        sentence_index=s_idx,
                        importance=importance,
                    )
                )

        return claims

    def _split_into_clauses(self, sentence: str) -> list[str]:
        """Split complex compound sentences into atomic propositions."""
        # Clean citation markers from text when splitting e.g. [1], [doc_1]
        cleaned = re.sub(r"\[(?:\d+|[a-zA-Z0-9_\-]+)\]", "", sentence).strip()

        # Split on semicolons or conjunctions preceded by commas
        parts = re.split(r";|\s*,\s*(?:and|but|however|whereas|while)\s+", cleaned)
        res = [p.strip() for p in parts if len(p.strip()) > 5]
        return res if res else [cleaned]

    def _determine_importance(self, text: str) -> ClaimImportance:
        """Assign importance based on numerical, temporal, or key entity content."""
        # Critical if it contains numbers, dates, monetary values, or strong safety/medical terms
        if re.search(
            r"\b(\d{1,4}|20\d\d|\$\d+|\d+%\b|approved|rejected|lethal|strictly|never)\b",
            text,
            re.I,
        ):
            return ClaimImportance.CRITICAL

        # Minor if purely meta-discursive
        if re.search(
            r"\b(as mentioned|furthermore|additionally|in conclusion|note that)\b",
            text,
            re.I,
        ):
            return ClaimImportance.MINOR

        return ClaimImportance.STANDARD
