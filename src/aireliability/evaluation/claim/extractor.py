"""Claim extraction from generative text."""

from __future__ import annotations

import re
from collections.abc import Callable

from aireliability.evaluation.claim.models import Claim


class ClaimExtractor:
    """Extracts atomic factual claims from text."""

    def __init__(
        self,
        custom_extractor: Callable[[str], list[str]] | None = None,
    ) -> None:
        self.custom_extractor = custom_extractor

    def extract(self, text: str) -> list[Claim]:
        """Decompose text into atomic claim objects."""
        if not text or not text.strip():
            return []

        if self.custom_extractor is not None:
            raw_claims = self.custom_extractor(text)
            return [
                Claim(text=c.strip(), index=idx, source_sentence=c.strip())
                for idx, c in enumerate(raw_claims)
                if c.strip()
            ]

        # Standard deterministic decomposition:
        # 1. Clean markdown headers and bullet points
        cleaned = text.strip()
        lines = cleaned.splitlines()
        sentences: list[str] = []

        for line in lines:
            line_str = re.sub(r"^[\s*#\-0-9\.\)]+", "", line).strip()
            if not line_str:
                continue
            # Split line by sentence terminators
            parts = re.split(r"(?<=[.!?])\s+", line_str)
            for p in parts:
                p_clean = p.strip()
                if len(p_clean) > 3:
                    sentences.append(p_clean)

        claims: list[Claim] = []
        for idx, sentence in enumerate(sentences):
            # If compound sentence with semicolon or distinct clause, we can preserve as claim
            claims.append(
                Claim(
                    text=sentence,
                    index=idx,
                    source_sentence=sentence,
                )
            )

        return claims
