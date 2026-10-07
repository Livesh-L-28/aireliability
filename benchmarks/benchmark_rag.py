"""Benchmark suite for RAG evaluation lifecycle (Phase 39) across retrieval, ranking, grounding, and scale."""

from __future__ import annotations

import sys
from pathlib import Path

# Path setup for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from aireliability.rag.citation_validator import CitationValidator
from aireliability.rag.claim_extractor import ClaimExtractor
from aireliability.rag.context_analyzer import ContextAnalyzer
from aireliability.rag.engine import AdvancedRAGReliabilityEngine
from aireliability.rag.evidence_aligner import EvidenceAligner
from aireliability.rag.freshness import FreshnessTracker
from aireliability.rag.grounding_evaluator import GroundingEvaluator
from aireliability.rag.models import (
    GeneratedAnswer,
    RAGQuery,
    RetrievedChunk,
    RetrievedDocument,
)
from aireliability.rag.query_analyzer import QueryAnalyzer
from aireliability.rag.ranking_evaluator import RankingEvaluator
from benchmarks.benchmark_config import BenchmarkConfig
from benchmarks.benchmark_utils import BenchmarkMetric, measure_benchmark


def make_sample_rag_data(
    num_docs: int = 10,
) -> tuple[RAGQuery, list[RetrievedDocument], list[RetrievedChunk], GeneratedAnswer]:
    query = RAGQuery(
        text="How does deterministic verification protect against regressions?"
    )
    docs: list[RetrievedDocument] = []
    chunks: list[RetrievedChunk] = []

    for i in range(num_docs):
        doc_id = f"doc_{i:04d}"
        docs.append(
            RetrievedDocument(
                document_id=doc_id,
                title=f"Reliability Guide Volume {i}",
                score=0.95 - (i * 0.001),
                rank=i + 1,
                metadata={"category": "testing", "created_at": "2026-10-01T00:00:00Z"},
            )
        )
        chunk_id = f"chk_{i:04d}"
        chunks.append(
            RetrievedChunk(
                chunk_id=chunk_id,
                document_id=doc_id,
                text=f"Deterministic verification invariants enforce strict ordering and semantic guarantees for item {i}. Cites [doc_{i:04d}].",
                score=0.92 - (i * 0.001),
                rank=i + 1,
            )
        )

    sample_claims = [
        "Deterministic verification enforces ordering",
        "Invariants hold across test suites",
    ]
    answer = GeneratedAnswer(
        text=f"Deterministic verification enforces ordering and invariants across test suites. Cites [{docs[0].document_id}].",
    )
    return query, docs, chunks, answer, sample_claims


def run_rag_benchmarks(config: BenchmarkConfig) -> list[BenchmarkMetric]:
    metrics: list[BenchmarkMetric] = []
    engine = AdvancedRAGReliabilityEngine()

    query_10, docs_10, chunks_10, answer_10, claims_10 = make_sample_rag_data(
        config.sizes.SMALL
    )
    _, docs_100, chunks_100, answer_100, _ = make_sample_rag_data(config.sizes.MEDIUM)
    _, docs_1000, chunks_1000, answer_1000, _ = make_sample_rag_data(
        min(1000, config.sizes.LARGE)
    )

    # 1. Query Analysis
    qa = QueryAnalyzer()

    def bench_query_analysis() -> None:
        _ = qa.analyze(query_text=query_10.text)

    metrics.append(
        measure_benchmark(
            operation="rag_query_analysis",
            target_func=bench_query_analysis,
            input_size="1 query",
            iterations=config.iterations * 3,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("rag_evaluation"),
            seed=config.seed,
        )
    )

    # 2. Ranking Evaluation
    re = RankingEvaluator()

    def bench_ranking() -> None:
        _ = re.evaluate(initial_chunks=chunks_10)

    metrics.append(
        measure_benchmark(
            operation="rag_ranking_evaluation",
            target_func=bench_ranking,
            input_size=f"{len(docs_10)} docs",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("rag_evaluation"),
            seed=config.seed,
        )
    )

    # 3. Context Construction & Analysis
    ca = ContextAnalyzer()

    def bench_context_analysis() -> None:
        _ = ca.analyze(chunks=chunks_10, query_text=query_10.text)

    metrics.append(
        measure_benchmark(
            operation="rag_context_analysis",
            target_func=bench_context_analysis,
            input_size=f"{len(chunks_10)} chunks",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("rag_evaluation"),
            seed=config.seed,
        )
    )

    # 4. Claim Extraction
    ce = ClaimExtractor()
    extracted_claims = ce.extract_claims(answer_10.text)

    def bench_claim_extraction() -> None:
        _ = ce.extract_claims(answer_10.text)

    metrics.append(
        measure_benchmark(
            operation="rag_claim_extraction",
            target_func=bench_claim_extraction,
            input_size=f"{len(extracted_claims)} claims",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("rag_evaluation"),
            seed=config.seed,
        )
    )

    # 5. Evidence Alignment
    ea = EvidenceAligner()
    aligned_claims, _, _, cov_metrics = ea.align_claims(
        claims=extracted_claims, chunks=chunks_10
    )

    def bench_evidence_alignment() -> None:
        _ = ea.align_claims(claims=extracted_claims, chunks=chunks_10)

    metrics.append(
        measure_benchmark(
            operation="rag_evidence_alignment",
            target_func=bench_evidence_alignment,
            input_size=f"{len(extracted_claims)} claims x {len(chunks_10)} chunks",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("rag_evaluation"),
            seed=config.seed,
        )
    )

    # 6. Citation Validation
    cv = CitationValidator()
    citations, _, _ = cv.validate_citations(
        answer_text=answer_10.text, claims=aligned_claims, chunks=chunks_10
    )

    def bench_citation_validation() -> None:
        _ = cv.validate_citations(
            answer_text=answer_10.text, claims=aligned_claims, chunks=chunks_10
        )

    metrics.append(
        measure_benchmark(
            operation="rag_citation_validation",
            target_func=bench_citation_validation,
            input_size="citation inline parsing",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("rag_evaluation"),
            seed=config.seed,
        )
    )

    # 7. Grounding Evaluation
    ge = GroundingEvaluator()

    def bench_grounding() -> None:
        _ = ge.evaluate(
            claims=aligned_claims,
            citations=citations,
            evidence_coverage_metrics=cov_metrics,
        )

    metrics.append(
        measure_benchmark(
            operation="rag_grounding_eval",
            target_func=bench_grounding,
            input_size=f"{len(chunks_10)} chunks",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("rag_evaluation"),
            seed=config.seed,
        )
    )

    # 8. Freshness Tracking
    ft = FreshnessTracker()

    def bench_freshness() -> None:
        _ = ft.evaluate_freshness(documents=docs_10, chunks=chunks_10)

    metrics.append(
        measure_benchmark(
            operation="rag_freshness_tracker",
            target_func=bench_freshness,
            input_size=f"{len(docs_10)} docs",
            iterations=config.iterations * 3,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("rag_evaluation"),
            seed=config.seed,
        )
    )

    # 9. Complete RAG Evaluation - Small (10 docs)
    def bench_complete_small() -> None:
        _ = engine.evaluate_run(
            query=query_10.text,
            retrieved_documents=docs_10,
            retrieved_chunks=chunks_10,
            generated_answer=answer_10.text,
        )

    metrics.append(
        measure_benchmark(
            operation="rag_complete_eval_small",
            target_func=bench_complete_small,
            input_size=f"{len(docs_10)} docs",
            iterations=config.iterations,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("rag_evaluation"),
            seed=config.seed,
        )
    )

    # 10. Complete RAG Evaluation - Medium (100 docs)
    def bench_complete_medium() -> None:
        _ = engine.evaluate_run(
            query=query_10.text,
            retrieved_documents=docs_100,
            retrieved_chunks=chunks_100,
            generated_answer=answer_100.text,
        )

    metrics.append(
        measure_benchmark(
            operation="rag_complete_eval_medium",
            target_func=bench_complete_medium,
            input_size=f"{len(docs_100)} docs",
            iterations=max(3, config.iterations // 2),
            warmup_iterations=1,
            budget=config.budgets.get("rag_evaluation"),
            seed=config.seed,
        )
    )

    # 11. Complete RAG Evaluation - Large (1,000 docs)
    def bench_complete_large() -> None:
        _ = engine.evaluate_run(
            query=query_10.text,
            retrieved_documents=docs_1000,
            retrieved_chunks=chunks_1000,
            generated_answer=answer_1000.text,
        )

    metrics.append(
        measure_benchmark(
            operation="rag_complete_eval_large",
            target_func=bench_complete_large,
            input_size=f"{len(docs_1000)} docs",
            iterations=max(2, config.iterations // 4),
            warmup_iterations=1,
            budget=config.budgets.get("rag_evaluation"),
            seed=config.seed,
        )
    )

    return metrics


if __name__ == "__main__":
    cfg = BenchmarkConfig.from_mode("quick")
    res = run_rag_benchmarks(cfg)
    for m in res:
        print(
            f"[{m.status}] {m.operation}: p50={m.median_latency_ms}ms, p95={m.p95_latency_ms}ms, throughput={m.throughput_ops} ops/s"
        )
