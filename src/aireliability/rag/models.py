"""Strongly typed domain models for Phase 39 Advanced RAG Reliability Engine."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _generate_id(prefix: str = "rag") -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RAGStage(StrEnum):
    """Lifecycle stages of a Retrieval-Augmented Generation execution."""

    QUERY = "query"
    RETRIEVAL = "retrieval"
    RANKING = "ranking"
    RERANKING = "reranking"
    CONTEXT = "context"
    GENERATION = "generation"
    GROUNDING = "grounding"
    FAITHFULNESS = "faithfulness"
    CITATION = "citation"
    FRESHNESS = "freshness"
    SECURITY = "security"
    OVERALL = "overall"


class QueryType(StrEnum):
    """Categorical taxonomy for incoming RAG user queries."""

    SIMPLE_FACTUAL = "simple_factual"
    MULTI_HOP = "multi_hop"
    AMBIGUOUS = "ambiguous"
    UNDERSPECIFIED = "underspecified"
    CONVERSATIONAL = "conversational"
    ENTITY_HEAVY = "entity_heavy"
    TEMPORAL = "temporal"
    COMPARATIVE = "comparative"
    MULTI_DOCUMENT = "multi_document"
    LONG_CONTEXT = "long_context"
    ADVERSARIAL = "adversarial"


class ClaimImportance(StrEnum):
    """Importance weighting for factual claims."""

    CRITICAL = "critical"
    STANDARD = "standard"
    MINOR = "minor"


class ClaimSupportStatus(StrEnum):
    """Alignment classification of a claim against retrieved evidence."""

    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    UNKNOWN = "unknown"


class CitationStatus(StrEnum):
    """Validity status of an inline citation."""

    VALID = "valid"
    MISSING_CHUNK = "missing_chunk"
    INVALID_CHUNK = "invalid_chunk"
    UNSUPPORTED = "unsupported"
    WRONG_SOURCE = "wrong_source"
    MISMATCH = "mismatch"


class ConflictStatus(StrEnum):
    """Resolution and classification status of contradictory evidence."""

    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    LOW_CONFIDENCE = "low_confidence"
    TEMPORAL_CONFLICT = "temporal_conflict"
    SOURCE_PRIORITY_CONFLICT = "source_priority_conflict"


class RAGFailureCategory(StrEnum):
    """Granular failure taxonomy covering the entire RAG pipeline."""

    QUERY_FAILURE = "query_failure"
    RETRIEVAL_FAILURE = "retrieval_failure"
    RANKING_FAILURE = "ranking_failure"
    RERANKING_FAILURE = "reranking_failure"
    CONTEXT_FAILURE = "context_failure"
    FRESHNESS_FAILURE = "freshness_failure"
    KNOWLEDGE_CONFLICT = "knowledge_conflict"
    INDEX_STALENESS = "index_staleness"
    EMBEDDING_DRIFT = "embedding_drift"
    RETRIEVAL_DRIFT = "retrieval_drift"
    GROUNDING_FAILURE = "grounding_failure"
    FAITHFULNESS_FAILURE = "faithfulness_failure"
    CITATION_FAILURE = "citation_failure"
    HALLUCINATION = "hallucination"
    GENERATION_FAILURE = "generation_failure"
    PERFORMANCE_FAILURE = "performance_failure"
    COST_FAILURE = "cost_failure"
    SECURITY_VIOLATION = "security_violation"
    POTENTIAL_POISONING = "potential_poisoning"

    # Specific Failure Subtypes (Section 9, 24, 42, 45)
    NO_RESULTS = "no_results"
    LOW_RECALL = "low_recall"
    LOW_PRECISION = "low_precision"
    WRONG_DOCUMENT = "wrong_document"
    WRONG_CHUNK = "wrong_chunk"
    MISSING_EVIDENCE = "missing_evidence"
    DUPLICATE_RESULTS = "duplicate_results"
    STALE_DOCUMENT = "stale_document"
    CONFLICTING_DOCUMENTS = "conflicting_documents"
    QUERY_DOCUMENT_MISMATCH = "query_document_mismatch"
    CONTEXT_OVERFLOW = "context_overflow"
    MISSING_CITATION = "missing_citation"
    INVALID_CITATION = "invalid_citation"
    UNSUPPORTED_CITATION = "unsupported_citation"
    WRONG_SOURCE = "wrong_source"
    CITATION_MISMATCH = "citation_mismatch"
    PROMPT_INJECTION = "prompt_injection"
    SECRET_LEAKAGE = "secret_leakage"
    BROKEN_MULTIHOP_CHAIN = "broken_multihop_chain"
    MISSING_HOP = "missing_hop"

    UNKNOWN = "unknown"


class FailureSeverity(StrEnum):
    """Severity classification for RAG failures."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class KBHealthStatus(StrEnum):
    """Overall knowledge base health status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"


class ConfidenceLevel(StrEnum):
    """Confidence classification for evidence judgments."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RAGQuery(BaseModel):
    """Represents a structured user query entering the RAG pipeline."""

    model_config = ConfigDict(frozen=True)

    query_id: str = Field(default_factory=lambda: _generate_id("qry"))
    text: str
    query_type: QueryType = QueryType.SIMPLE_FACTUAL
    entities: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    time_requirements: list[str] = Field(default_factory=list)
    expected_answer_type: str = "text"
    completeness_score: float = 1.0
    ambiguity_score: float = 0.0
    specificity_score: float = 1.0
    complexity_score: float = 0.2
    expected_retrieval_difficulty: float = 0.3
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievedDocument(BaseModel):
    """Source document retrieved or stored in the knowledge base."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    document_id: str
    title: str = ""
    text: str = ""
    source: str = ""
    ingestion_timestamp: datetime = Field(default_factory=_utc_now)
    last_updated: datetime = Field(default_factory=_utc_now)
    updated_at: datetime | None = None
    version: str = "1.0.0"
    score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _sync_updated_at(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if (
                "updated_at" in data
                and data["updated_at"] is not None
                and "last_updated" not in data
            ):
                data["last_updated"] = data["updated_at"]
            elif "last_updated" in data and (
                "updated_at" not in data or data.get("updated_at") is None
            ):
                data["updated_at"] = data["last_updated"]
        return data


class RetrievedChunk(BaseModel):
    """Granular context chunk extracted from a source document."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str = Field(default_factory=lambda: _generate_id("chk"))
    document_id: str
    text: str
    chunk_index: int = 0
    start_char: int = 0
    end_char: int = 0
    retrieval_score: float = 0.0
    rerank_score: float | None = None
    timestamp: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    """Complete output and metrics of the retrieval stage."""

    model_config = ConfigDict(frozen=True)

    query_id: str = Field(default_factory=lambda: _generate_id("qry"))
    retrieved_documents: list[RetrievedDocument] = Field(default_factory=list)
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)
    lexical_contribution: float = 0.5
    semantic_contribution: float = 0.5
    hybrid_overlap_ratio: float = 0.5
    execution_time_ms: float = 0.0
    total_candidates_examined: int = 0
    ground_truth_available: bool = False
    exact_metrics: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RankingResult(BaseModel):
    """Output and metrics of ranking and neural reranking stages."""

    model_config = ConfigDict(frozen=True)

    ranked_chunk_ids: list[str] = Field(default_factory=list)
    original_positions: dict[str, int] = Field(default_factory=dict)
    reranked_positions: dict[str, int] = Field(default_factory=dict)
    rank_flips_count: int = 0
    mrr: float = 0.0
    ndcg_at_k: float = 0.0
    precision_at_k: float = 0.0
    recall_at_k: float = 0.0
    buried_evidence_detected: bool = False
    reranking_degraded: bool = False
    deltas_from_reranking: dict[str, float] = Field(default_factory=dict)

    @property
    def reranker_degradation(self) -> bool:
        return self.reranking_degraded

    @property
    def ndcg_change(self) -> float:
        return self.deltas_from_reranking.get("ndcg_delta", 0.0)


class ContextWindow(BaseModel):
    """Constructed context fed into the generative model."""

    model_config = ConfigDict(frozen=True)

    context_text: str = ""
    included_chunks: list[RetrievedChunk] = Field(default_factory=list)
    token_count: int = 0
    max_tokens: int = 4096
    is_truncated: bool = False
    redundancy_score: float = 0.0
    conflict_count: int = 0
    beginning_chunks_count: int = 0
    middle_chunks_count: int = 0
    ending_chunks_count: int = 0
    potential_position_sensitivity: float = 0.0
    lost_in_the_middle_detected: bool = False

    @model_validator(mode="before")
    @classmethod
    def _remap_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "chunks" in data and "included_chunks" not in data:
                data["included_chunks"] = data.pop("chunks")
            if "total_tokens" in data and "token_count" not in data:
                data["token_count"] = data.pop("total_tokens")
        return data


class GeneratedAnswer(BaseModel):
    """Raw and structured generative model answer."""

    model_config = ConfigDict(frozen=True)

    text: str
    model_name: str = "default-rag-model"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_seconds: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class Claim(BaseModel):
    """Atomic proposition extracted from generative text."""

    model_config = ConfigDict(frozen=True)

    claim_id: str = Field(default_factory=lambda: _generate_id("clm"))
    text: str
    source_sentence: str = ""
    sentence_index: int = 0
    importance: ClaimImportance = ClaimImportance.STANDARD
    support_status: ClaimSupportStatus = ClaimSupportStatus.UNKNOWN
    confidence: float = 1.0
    evidence_ids: list[str] = Field(default_factory=list)
    citation_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Evidence(BaseModel):
    """Evidence snippet from a retrieved chunk relevant to claims."""

    model_config = ConfigDict(frozen=True)

    evidence_id: str = Field(default_factory=lambda: _generate_id("evi"))
    chunk_id: str
    document_id: str
    text: str
    relevance_score: float = 1.0
    timestamp: datetime = Field(default_factory=_utc_now)


class ClaimEvidenceLink(BaseModel):
    """Verification link mapping a claim to supporting or contradicting evidence."""

    model_config = ConfigDict(frozen=True)

    link_id: str = Field(default_factory=lambda: _generate_id("lnk"))
    claim_id: str
    evidence_id: str
    status: ClaimSupportStatus
    similarity: float = 1.0
    confidence: float = 1.0
    reasoning: str = ""


class Citation(BaseModel):
    """Inline citation mapping an answer claim to cited evidence."""

    model_config = ConfigDict(frozen=True)

    citation_id: str = Field(default_factory=lambda: _generate_id("cit"))
    marker: str  # e.g. "[1]" or "[doc_42]"
    cited_chunk_id: str
    claim_id: str | None = None
    status: CitationStatus = CitationStatus.VALID
    location_index: int = 0
    reasoning: str = ""


class ContextConflict(BaseModel):
    """Detected factual contradiction between two retrieved evidence pieces."""

    model_config = ConfigDict(frozen=True)

    conflict_id: str = Field(default_factory=lambda: _generate_id("cnf"))
    doc_a_id: str
    doc_b_id: str
    chunk_a_id: str = ""
    chunk_b_id: str = ""
    statement_a: str = ""
    statement_b: str = ""
    status: ConflictStatus = ConflictStatus.UNRESOLVED
    conflict_type: str = "factual"
    description: str = ""
    confidence: float = 0.85


class RAGFailure(BaseModel):
    """Specific failure event identified during RAG evaluation."""

    model_config = ConfigDict(frozen=True)

    failure_id: str = Field(default_factory=lambda: _generate_id("fail"))
    stage: RAGStage
    category: RAGFailureCategory
    severity: FailureSeverity = FailureSeverity.MEDIUM
    message: str
    affected_component: str = ""
    evidence_summary: str = ""
    confidence: float = 0.90
    timestamp: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RAGStageScore(BaseModel):
    """Independent score and metrics for a single RAG pipeline stage."""

    model_config = ConfigDict(frozen=True)

    stage: RAGStage
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metrics: dict[str, float] = Field(default_factory=dict)
    failures: list[RAGFailure] = Field(default_factory=list)
    explanation: str = ""


class RAGReliabilityScore(BaseModel):
    """Multidimensional overall RAG reliability score."""

    model_config = ConfigDict(frozen=True)

    overall_score: float = Field(ge=0.0, le=1.0)
    stage_scores: dict[str, RAGStageScore] = Field(default_factory=dict)
    safety_passed: bool = True
    security_passed: bool = True
    critical_veto: bool = False
    explanation: str = ""


class RAGDriftResult(BaseModel):
    """Statistical measurement of drift across queries, embeddings, or retrieval."""

    model_config = ConfigDict(frozen=True)

    drift_type: str
    metric_name: str
    baseline_value: float
    observed_value: float
    delta: float
    drift_detected: bool
    trend: str = "STABLE"
    confidence: float = 1.0
    details: dict[str, Any] = Field(default_factory=dict)


class KnowledgeBaseHealthReport(BaseModel):
    """Health audit report of a knowledge base repository."""

    model_config = ConfigDict(frozen=True)

    document_count: int = 0
    chunk_count: int = 0
    empty_document_count: int = 0
    duplicate_chunk_rate: float = 0.0
    stale_document_rate: float = 0.0
    conflict_rate: float = 0.0
    metadata_completeness_rate: float = 1.0
    orphaned_chunks_count: int = 0
    status: KBHealthStatus = KBHealthStatus.HEALTHY
    recommendations: list[str] = Field(default_factory=list)


class RAGRun(BaseModel):
    """Comprehensive, immutable record of an end-to-end RAG execution."""

    model_config = ConfigDict(frozen=True)

    run_id: str = Field(default_factory=lambda: _generate_id("run"))
    query: RAGQuery
    retrieval_result: RetrievalResult = Field(default_factory=RetrievalResult)
    ranking_result: RankingResult = Field(default_factory=RankingResult)
    context_window: ContextWindow = Field(default_factory=ContextWindow)
    generated_answer: GeneratedAnswer = Field(
        default_factory=lambda: GeneratedAnswer(text="")
    )
    claims: list[Claim] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    claim_evidence_links: list[ClaimEvidenceLink] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    conflicts: list[ContextConflict] = Field(default_factory=list)
    stage_scores: dict[str, RAGStageScore] = Field(default_factory=dict)
    reliability_score: RAGReliabilityScore = Field(
        default_factory=lambda: RAGReliabilityScore(overall_score=1.0)
    )
    failures: list[RAGFailure] = Field(default_factory=list)
    model: str = "rag-default-model"
    embedding_model: str = "rag-default-embedding"
    retriever_name: str = "hybrid-retriever"
    reranker_name: str = "default-reranker"
    dataset_id: str = "rag-eval-dataset"
    knowledge_base_version: str = "1.0.0"
    created_at: datetime = Field(default_factory=_utc_now)
    environment: str = "production"
    metadata: dict[str, Any] = Field(default_factory=dict)


class RAGEvaluationResult(BaseModel):
    """Output of batch or single evaluation across RAG test cases."""

    model_config = ConfigDict(frozen=True)

    evaluation_id: str = Field(default_factory=lambda: _generate_id("eval"))
    runs: list[RAGRun] = Field(default_factory=list)
    mean_stage_scores: dict[str, float] = Field(default_factory=dict)
    overall_score: float = 1.0
    total_failures: int = 0
    failure_counts_by_stage: dict[str, int] = Field(default_factory=dict)
    critical_failures_count: int = 0
    passed_release_gates: bool = True
    summary: str = ""
    created_at: datetime = Field(default_factory=_utc_now)

    @property
    def total_runs(self) -> int:
        """Return the number of evaluated RAG runs in this batch."""
        return len(self.runs)


__all__ = [
    "Citation",
    "CitationStatus",
    "Claim",
    "ClaimEvidenceLink",
    "ClaimImportance",
    "ClaimSupportStatus",
    "ConfidenceLevel",
    "ConflictStatus",
    "ContextConflict",
    "ContextWindow",
    "Evidence",
    "FailureSeverity",
    "GeneratedAnswer",
    "KBHealthStatus",
    "KnowledgeBaseHealthReport",
    "QueryType",
    "RAGDriftResult",
    "RAGEvaluationResult",
    "RAGFailure",
    "RAGFailureCategory",
    "RAGQuery",
    "RAGReliabilityScore",
    "RAGRun",
    "RAGStage",
    "RAGStageScore",
    "RankingResult",
    "RetrievalResult",
    "RetrievedChunk",
    "RetrievedDocument",
]
