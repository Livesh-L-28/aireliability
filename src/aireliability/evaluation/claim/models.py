"""Data models for claim extraction, verification, and hallucination evaluation."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class ClaimClassification(StrEnum):
    """Classification status for a verified factual claim."""

    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"


def _generate_id(prefix: str = "clm") -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class Claim(BaseModel):
    """Represents an atomic proposition extracted from generative text."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=_generate_id)
    text: str
    index: int = 0
    source_sentence: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClaimVerification(BaseModel):
    """Result of verifying an individual claim against reference context."""

    model_config = ConfigDict(frozen=True)

    claim: Claim
    status: ClaimClassification
    confidence: float = 1.0
    reasoning: str = ""
    matched_context_doc: str | None = None
    evidence_snippet: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClaimEvaluationSummary(BaseModel):
    """Aggregated metrics summary for claim-level verification."""

    model_config = ConfigDict(frozen=True)

    total_claims: int
    supported_claims: int
    unsupported_claims: int
    contradicted_claims: int
    hallucination_rate: float
    grounded_claim_rate: float
    contradiction_rate: float
    unsupported_claim_rate: float
    claim_coverage: float = 1.0
    evidence_coverage: float = 1.0
    verifications: list[ClaimVerification] = Field(default_factory=list)
