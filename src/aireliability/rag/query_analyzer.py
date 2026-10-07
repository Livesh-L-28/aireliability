"""Query Analyzer evaluating query intent, complexity, ambiguity, and retrieval difficulty."""

from __future__ import annotations

import re
from typing import Any

from aireliability.rag.models import QueryType, RAGQuery

# Temporal indicator words and patterns
TEMPORAL_PATTERNS = [
    re.compile(
        r"\b(current|currently|now|today|yesterday|latest|recent|recently)\b", re.I
    ),
    re.compile(
        r"\b(in\s+20\d\d|since\s+20\d\d|before\s+20\d\d|as\s+of\s+20\d\d)\b", re.I
    ),
    re.compile(r"\b(historical|history|annual|quarterly|q[1-4]|20\d\d)\b", re.I),
]

# Comparative terms
COMPARATIVE_PATTERNS = [
    re.compile(
        r"\b(vs|versus|compare|compared\s+to|difference\s+between|better\s+than|worse\s+than)\b",
        re.I,
    ),
]

# Multi-hop indicators
MULTI_HOP_PATTERNS = [
    re.compile(
        r"\b(and\s+then|which\s+in\s+turn|whose\s+\w+\s+also|connected\s+to|relationship\s+between)\b",
        re.I,
    ),
    re.compile(
        r"\b(after\s+that|followed\s+by|originating\s+from\s+and\s+leading\s+to)\b",
        re.I,
    ),
]

# Multi-document indicators
MULTI_DOC_PATTERNS = [
    re.compile(
        r"\b(across\s+all|synthesize|combine\s+findings|multiple\s+sources|all\s+reports)\b",
        re.I,
    ),
]

# Adversarial prompt injection keywords
ADVERSARIAL_PATTERNS = [
    re.compile(
        r"\b(ignore\s+previous|disregard\s+all|system\s+prompt|system\s+override|jailbreak|dan\s+mode)\b",
        re.I,
    ),
    re.compile(r"\b(pretend\s+to\s+be|bypass\s+safety|output\s+all\s+secrets)\b", re.I),
]

# Vague / Underspecified keywords
UNDERSPECIFIED_PATTERNS = [
    re.compile(
        r"^(tell\s+me\s+about\s+it|what\s+about\s+it|how\s+much\?|give\s+details|info\??|details\??)$",
        re.I,
    ),
    re.compile(
        r"\b(tell\s+me\s+more|what\s+happened|explain\s+this|what\s+is\s+it)\b", re.I
    ),
]


class QueryAnalyzer:
    """Analyzes incoming RAG queries for classification, entity extraction, and retrieval difficulty."""

    def analyze(
        self, query_text: str, metadata: dict[str, Any] | None = None
    ) -> RAGQuery:
        """Analyze and classify a user query."""
        cleaned = (query_text or "").strip()
        meta = metadata or {}

        if not cleaned:
            return RAGQuery(
                text="",
                query_type=QueryType.UNDERSPECIFIED,
                completeness_score=0.0,
                ambiguity_score=1.0,
                specificity_score=0.0,
                complexity_score=0.1,
                expected_retrieval_difficulty=1.0,
                metadata=meta,
            )

        # 1. Adversarial Detection
        for pat in ADVERSARIAL_PATTERNS:
            if pat.search(cleaned):
                return RAGQuery(
                    text=cleaned,
                    query_type=QueryType.ADVERSARIAL,
                    completeness_score=0.8,
                    ambiguity_score=0.1,
                    specificity_score=0.9,
                    complexity_score=0.8,
                    expected_retrieval_difficulty=0.9,
                    metadata=meta,
                )

        # 2. Underspecified / Ambiguous
        for pat in UNDERSPECIFIED_PATTERNS:
            if pat.search(cleaned) or len(cleaned.split()) <= 2:
                # e.g., "tell me about it" or "info"
                return RAGQuery(
                    text=cleaned,
                    query_type=QueryType.UNDERSPECIFIED,
                    completeness_score=0.1,
                    ambiguity_score=0.95,
                    specificity_score=0.1,
                    complexity_score=0.1,
                    expected_retrieval_difficulty=0.9,
                    metadata=meta,
                )

        # 3. Entity extraction (Named entities, numbers, quotes, acronyms)
        entities = self._extract_entities(cleaned)
        time_reqs = self._extract_temporal(cleaned)
        constraints = self._extract_constraints(cleaned)

        # 4. Classification
        q_type = self._classify_type(cleaned, entities)

        # 5. Scores
        word_count = len(cleaned.split())
        specificity = min(1.0, max(0.1, (len(entities) * 0.25) + (word_count / 15.0)))
        ambiguity = max(0.0, min(1.0, 1.0 - specificity if len(entities) == 0 else 0.2))
        complexity = min(
            1.0,
            max(
                0.1,
                (word_count / 25.0)
                + (
                    0.3
                    if q_type in (QueryType.MULTI_HOP, QueryType.COMPARATIVE)
                    else 0.0
                ),
            ),
        )

        # Expected retrieval difficulty
        difficulty = 0.2
        if q_type == QueryType.MULTI_HOP:
            difficulty += 0.4
        elif q_type == QueryType.MULTI_DOCUMENT:
            difficulty += 0.35
        elif q_type == QueryType.COMPARATIVE:
            difficulty += 0.3
        elif q_type == QueryType.UNDERSPECIFIED:
            difficulty += 0.5
        elif q_type == QueryType.ENTITY_HEAVY:
            difficulty += 0.15
        difficulty = min(1.0, difficulty + (complexity * 0.2))

        expected_ans = self._infer_answer_type(cleaned)

        return RAGQuery(
            text=cleaned,
            query_type=q_type,
            entities=entities,
            concepts=self._extract_concepts(cleaned),
            constraints=constraints,
            time_requirements=time_reqs,
            expected_answer_type=expected_ans,
            completeness_score=round(1.0 - (ambiguity * 0.6), 4),
            ambiguity_score=round(ambiguity, 4),
            specificity_score=round(specificity, 4),
            complexity_score=round(complexity, 4),
            expected_retrieval_difficulty=round(difficulty, 4),
            metadata=meta,
        )

    def _classify_type(self, text: str, entities: list[str]) -> QueryType:
        """Classify query into appropriate archetype."""
        for pat in MULTI_HOP_PATTERNS:
            if pat.search(text):
                return QueryType.MULTI_HOP

        for pat in COMPARATIVE_PATTERNS:
            if pat.search(text):
                return QueryType.COMPARATIVE

        for pat in MULTI_DOC_PATTERNS:
            if pat.search(text):
                return QueryType.MULTI_DOCUMENT

        for pat in TEMPORAL_PATTERNS:
            if pat.search(text):
                return QueryType.TEMPORAL

        if len(text) > 250:
            return QueryType.LONG_CONTEXT

        if len(entities) >= 3:
            return QueryType.ENTITY_HEAVY

        if re.search(r"\b(hi|hello|hey|thanks|thank you)\b", text, re.I):
            return QueryType.CONVERSATIONAL

        return QueryType.SIMPLE_FACTUAL

    def _extract_entities(self, text: str) -> list[str]:
        """Extract quoted strings, capitalized sequences, and code words."""
        entities: list[str] = []
        # Quoted entities: "Product X"
        quoted = re.findall(r'"([^"]+)"', text)
        entities.extend(quoted)

        # Capitalized sequences: e.g. "San Francisco", "GPT-4o"
        cap_words = re.findall(
            r"\b[A-Z][a-zA-Z0-9_\-\.]+(?:\s+[A-Z][a-zA-Z0-9_\-\.]+)*\b", text
        )
        for w in cap_words:
            if w.lower() not in {
                "what",
                "who",
                "when",
                "where",
                "why",
                "how",
                "the",
                "a",
                "is",
                "tell",
            }:
                entities.append(w)

        return list(dict.fromkeys(entities))

    def _extract_temporal(self, text: str) -> list[str]:
        """Extract explicit temporal constraints."""
        found: list[str] = []
        for pat in TEMPORAL_PATTERNS:
            matches = pat.findall(text)
            for m in matches:
                found.append(m if isinstance(m, str) else m[0])
        return list(dict.fromkeys(found))

    def _extract_constraints(self, text: str) -> list[str]:
        """Extract explicit user constraints like limits, languages, formats."""
        constraints = []
        if re.search(
            r"\b(only|must|strictly|top\s+\d+|in\s+english|json\s+format)\b", text, re.I
        ):
            m = re.findall(
                r"\b(?:only|must|strictly|top\s+\d+|in\s+english|json\s+format)[^,\.]*",
                text,
                re.I,
            )
            constraints.extend([c.strip() for c in m])
        return list(dict.fromkeys(constraints))

    def _extract_concepts(self, text: str) -> list[str]:
        """Extract noun-like tokens representing core topics."""
        tokens = re.findall(r"\b[a-zA-Z]{4,}\b", text.lower())
        stopwords = {
            "what",
            "when",
            "where",
            "which",
            "about",
            "there",
            "their",
            "could",
            "would",
            "should",
        }
        return [t for t in tokens if t not in stopwords][:8]

    def _infer_answer_type(self, text: str) -> str:
        """Infer expected answer type."""
        t_low = text.lower()
        if re.search(
            r"\b(how\s+many|how\s+much|number\s+of|percentage|count)\b", t_low
        ):
            return "numeric"
        if re.search(r"\b(when|what\s+year|what\s+date|time)\b", t_low):
            return "date_time"
        if re.search(r"\b(is\s+it|does\s+it|can\s+it|true\s+or\s+false)\b", t_low):
            return "boolean"
        if re.search(r"\b(who|which\s+company|which\s+person|which\s+author)\b", t_low):
            return "entity"
        return "text"
