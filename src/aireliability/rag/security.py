"""Security & Prompt Injection Analyzer for retrieved RAG content."""

from __future__ import annotations

import re
from typing import Any

from aireliability.rag.models import (
    FailureSeverity,
    RAGFailure,
    RAGFailureCategory,
    RAGStage,
    RetrievedChunk,
)

# Known prompt injection signatures in context documents
INJECTION_SIGNATURES = [
    re.compile(r"\b(ignore\s+(?:all\s+)?previous\s+instructions)\b", re.I),
    re.compile(r"\b(disregard\s+(?:all\s+)?prior\s+rules)\b", re.I),
    re.compile(r"\b(system\s+override|admin\s+mode\s+enabled)\b", re.I),
    re.compile(r"\b(output\s+the\s+system\s+prompt)\b", re.I),
    re.compile(r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", re.I | re.DOTALL),
    re.compile(r"\b(eval\(|exec\(|os\.system)\b"),
]

# Sensitive secrets patterns
SECRET_PATTERNS = [
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bghp_[a-zA-Z0-9]{16,40}\b"),
    re.compile(r"-----BEGIN\s+PRIVATE\s+KEY-----"),
    re.compile(r"\b(sk-[a-zA-Z0-9]{20,64})\b"),
]


class RAGSecurityAnalyzer:
    """Detects prompt injection, malicious instructions, credentials, and poisoning in retrieved documents."""

    def scan_chunks(
        self,
        chunks: list[RetrievedChunk],
    ) -> tuple[float, bool, list[RAGFailure]]:
        """Scan chunks for security threats returning (security_score, is_safe, failures)."""
        is_secure, failures, _ = self.analyze_chunks(chunks)
        score = 1.0 if is_secure else 0.0
        return score, is_secure, failures

    def analyze_chunks(
        self,
        chunks: list[RetrievedChunk],
        metadata: dict[str, Any] | None = None,
    ) -> tuple[bool, list[RAGFailure], list[RetrievedChunk]]:
        """Scan retrieved chunks for security threats and return sanitized chunks.

        Returns (is_secure, failures, sanitized_chunks).
        """
        failures: list[RAGFailure] = []
        is_secure = True
        sanitized: list[RetrievedChunk] = []

        for chk in chunks:
            chunk_text = chk.text

            # 1. Prompt Injection Checks
            for sig in INJECTION_SIGNATURES:
                if sig.search(chunk_text):
                    is_secure = False
                    failures.append(
                        RAGFailure(
                            stage=RAGStage.SECURITY,
                            category=RAGFailureCategory.PROMPT_INJECTION,
                            severity=FailureSeverity.CRITICAL,
                            message=(
                                f"PROMPT_INJECTION_DETECTED: Retrieved chunk '{chk.chunk_id}' contains "
                                f"malicious instruction override tokens."
                            ),
                            affected_component=chk.chunk_id,
                            confidence=0.98,
                        )
                    )
                    break

            # 2. Secret & Credential Leakage
            for sec_pat in SECRET_PATTERNS:
                if sec_pat.search(chunk_text):
                    is_secure = False
                    failures.append(
                        RAGFailure(
                            stage=RAGStage.SECURITY,
                            category=RAGFailureCategory.SECRET_LEAKAGE,
                            severity=FailureSeverity.CRITICAL,
                            message=f"SECRET_LEAKAGE: Retrieved chunk '{chk.chunk_id}' contains exposed API key or certificate credentials.",
                            affected_component=chk.chunk_id,
                            confidence=1.0,
                        )
                    )
                    # Redact
                    chunk_text = sec_pat.sub("[REDACTED_SECRET]", chunk_text)

            # 3. Retrieval Poisoning heuristic: abnormally long repetitive text or source concentration
            if len(chunk_text) > 3000 and "important" in chunk_text.lower():
                word_counts = {}
                for w in chunk_text.lower().split():
                    word_counts[w] = word_counts.get(w, 0) + 1
                max_freq = max(word_counts.values()) if word_counts else 0
                if max_freq > 40:
                    failures.append(
                        RAGFailure(
                            stage=RAGStage.SECURITY,
                            category=RAGFailureCategory.POTENTIAL_POISONING,
                            severity=FailureSeverity.HIGH,
                            message=f"POTENTIAL_POISONING: Chunk '{chk.chunk_id}' shows high keyword stuffing repetition.",
                            affected_component=chk.chunk_id,
                            confidence=0.75,
                        )
                    )

            sanitized.append(chk.model_copy(update={"text": chunk_text}))

        return is_secure, failures, sanitized
