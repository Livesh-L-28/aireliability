"""Claim classification against reference context."""

from __future__ import annotations

import re

from aireliability.evaluation.claim.models import (
    Claim,
    ClaimClassification,
    ClaimVerification,
)
from aireliability.evaluation.semantic.base import SemanticJudge


class ClaimClassifier:
    """Classifies extracted claims as SUPPORTED, UNSUPPORTED, or CONTRADICTED by context."""

    def __init__(
        self,
        judge: SemanticJudge | None = None,
        min_overlap_threshold: float = 0.60,
    ) -> None:
        self.judge = judge
        self.min_overlap_threshold = min_overlap_threshold

    def classify_claim(
        self,
        claim: Claim,
        context_docs: list[str] | dict[str, str] | str,
    ) -> ClaimVerification:
        """Verify an individual claim against context."""
        docs: dict[str, str] = {}
        if isinstance(context_docs, str):
            docs = {"context_0": context_docs}
        elif isinstance(context_docs, list):
            docs = {f"doc_{idx}": doc for idx, doc in enumerate(context_docs)}
        elif isinstance(context_docs, dict):
            docs = context_docs

        if not docs:
            return ClaimVerification(
                claim=claim,
                status=ClaimClassification.UNSUPPORTED,
                confidence=1.0,
                reasoning="No reference context provided to verify claim.",
            )

        # If semantic judge is provided, use it
        if self.judge is not None:
            combined_context = "\n---\n".join(
                f"[{doc_id}]: {text}" for doc_id, text in docs.items()
            )
            criteria = [
                f"verify if statement '{claim.text}' is directly supported by context",
                "check for direct contradiction",
            ]
            res = self.judge.judge(
                prompt=f"Verify claim: {claim.text}",
                output=claim.text,
                criteria=criteria,
                context={"reference_context": combined_context},
            )
            status = (
                ClaimClassification.SUPPORTED
                if res.passed
                else ClaimClassification.UNSUPPORTED
            )
            # Check for contradiction indicators in reasoning
            r_lower = res.reasoning.lower()
            if (
                "contradict" in r_lower
                or "conflict" in r_lower
                or "opposite" in r_lower
            ):
                status = ClaimClassification.CONTRADICTED

            return ClaimVerification(
                claim=claim,
                status=status,
                confidence=res.confidence or 0.9,
                reasoning=res.reasoning or "Evaluated with semantic judge",
                evidence_snippet=combined_context[:300],
            )

        # Deterministic verification based on text overlap and negation analysis
        claim_words = set(re.findall(r"\w+", claim.text.lower()))
        # Remove common stopwords
        stopwords = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "and",
            "or",
            "to",
            "in",
            "on",
            "at",
            "by",
            "for",
            "with",
            "about",
            "of",
            "it",
            "this",
            "that",
            "be",
            "been",
            "has",
            "have",
            "had",
        }
        filtered_claim_words = claim_words - stopwords
        if not filtered_claim_words:
            filtered_claim_words = claim_words

        best_doc_id: str | None = None
        best_overlap = 0.0
        best_snippet = ""
        is_contradicted = False

        negation_terms = {
            "not",
            "never",
            "no",
            "cannot",
            "hardly",
            "neither",
            "scarcely",
        }
        claim_has_negation = bool(claim_words.intersection(negation_terms))

        for doc_id, text in docs.items():
            text_lower = text.lower()
            doc_words = set(re.findall(r"\w+", text_lower))
            overlap = (
                len(filtered_claim_words.intersection(doc_words))
                / len(filtered_claim_words)
                if filtered_claim_words
                else 0.0
            )

            if overlap > best_overlap:
                best_overlap = overlap
                best_doc_id = doc_id
                best_snippet = text[:300]

                # Check contradiction: topic overlap high, but negation mismatch
                doc_has_negation = bool(doc_words.intersection(negation_terms))
                if overlap >= 0.35 and (claim_has_negation != doc_has_negation):
                    is_contradicted = True

        if is_contradicted and best_overlap >= 0.35:
            status = ClaimClassification.CONTRADICTED
            reasoning = (
                f"Claim contradicts context in [{best_doc_id}] (polarity mismatch)."
            )
        elif best_overlap >= self.min_overlap_threshold:
            status = ClaimClassification.SUPPORTED
            reasoning = f"Claim supported by [{best_doc_id}] with {best_overlap:.2f} content overlap."
        else:
            status = ClaimClassification.UNSUPPORTED
            reasoning = f"No context document provided sufficient evidence (best overlap {best_overlap:.2f})."

        return ClaimVerification(
            claim=claim,
            status=status,
            confidence=round(min(1.0, max(0.5, best_overlap)), 2),
            reasoning=reasoning,
            matched_context_doc=best_doc_id,
            evidence_snippet=best_snippet,
        )

    def classify_all(
        self,
        claims: list[Claim],
        context_docs: list[str] | dict[str, str] | str,
    ) -> list[ClaimVerification]:
        """Classify a list of claims against context."""
        return [self.classify_claim(c, context_docs) for c in claims]
