"""Advanced RAG Reliability Engine orchestrating the 11-stage RAG evaluation lifecycle."""

from __future__ import annotations

import logging
import time
from typing import Any

from aireliability.graph.graph import KnowledgeGraph
from aireliability.rag.citation_validator import CitationValidator
from aireliability.rag.claim_extractor import ClaimExtractor
from aireliability.rag.context_analyzer import ContextAnalyzer
from aireliability.rag.evidence_aligner import EvidenceAligner
from aireliability.rag.freshness import FreshnessTracker
from aireliability.rag.graph_bridge import RAGGraphBridge
from aireliability.rag.grounding_evaluator import GroundingEvaluator
from aireliability.rag.intelligence_bridge import RAGIntelligenceBridge
from aireliability.rag.models import (
    GeneratedAnswer,
    RAGEvaluationResult,
    RAGFailure,
    RAGQuery,
    RAGRun,
    RAGStage,
    RAGStageScore,
    RetrievedChunk,
    RetrievedDocument,
)
from aireliability.rag.observability_bridge import RAGObservabilityBridge
from aireliability.rag.query_analyzer import QueryAnalyzer
from aireliability.rag.ranking_evaluator import RankingEvaluator
from aireliability.rag.retrieval_evaluator import RetrievalEvaluator
from aireliability.rag.security import RAGSecurityAnalyzer
from aireliability.rag.taxonomy import RAGReliabilityScorer

logger = logging.getLogger(__name__)


class AdvancedRAGReliabilityEngine:
    """Production-grade RAG Reliability Engine executing stage-level analysis across the RAG lifecycle."""

    def __init__(
        self,
        query_analyzer: QueryAnalyzer | None = None,
        retrieval_evaluator: RetrievalEvaluator | None = None,
        ranking_evaluator: RankingEvaluator | None = None,
        context_analyzer: ContextAnalyzer | None = None,
        security_analyzer: RAGSecurityAnalyzer | None = None,
        claim_extractor: ClaimExtractor | None = None,
        evidence_aligner: EvidenceAligner | None = None,
        citation_validator: CitationValidator | None = None,
        grounding_evaluator: GroundingEvaluator | None = None,
        freshness_tracker: FreshnessTracker | None = None,
        scorer: RAGReliabilityScorer | None = None,
        observability_bridge: RAGObservabilityBridge | None = None,
        graph_bridge: RAGGraphBridge | None = None,
        intelligence_bridge: RAGIntelligenceBridge | None = None,
    ) -> None:
        self.query_analyzer = query_analyzer or QueryAnalyzer()
        self.retrieval_evaluator = retrieval_evaluator or RetrievalEvaluator()
        self.ranking_evaluator = ranking_evaluator or RankingEvaluator()
        self.context_analyzer = context_analyzer or ContextAnalyzer()
        self.security_analyzer = security_analyzer or RAGSecurityAnalyzer()
        self.claim_extractor = claim_extractor or ClaimExtractor()
        self.evidence_aligner = evidence_aligner or EvidenceAligner()
        self.citation_validator = citation_validator or CitationValidator()
        self.grounding_evaluator = grounding_evaluator or GroundingEvaluator()
        self.freshness_tracker = freshness_tracker or FreshnessTracker()
        self.scorer = scorer or RAGReliabilityScorer()
        self.obs_bridge = observability_bridge or RAGObservabilityBridge()
        self.graph_bridge = graph_bridge or RAGGraphBridge()
        self.intelligence_bridge = intelligence_bridge or RAGIntelligenceBridge()

    def evaluate_run(
        self,
        query: str | RAGQuery,
        retrieved_documents: list[RetrievedDocument],
        retrieved_chunks: list[RetrievedChunk],
        generated_answer: str | GeneratedAnswer,
        reranked_chunks: list[RetrievedChunk] | None = None,
        expected_document_ids: list[str] | None = None,
        expected_chunk_ids: list[str] | None = None,
        model_name: str = "default-model",
        retriever_name: str = "hybrid-retriever",
        reranker_name: str = "cross-encoder-reranker",
        dataset_id: str = "rag-eval-dataset",
        sync_to_graph: bool = False,
        graph: KnowledgeGraph | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RAGRun:
        """Execute end-to-end stage-isolated evaluation of a single RAG execution."""
        t_start = time.perf_counter()
        all_failures: list[RAGFailure] = []
        stage_scores: dict[str, RAGStageScore] = {}

        # 1. Query Analysis
        if isinstance(query, str):
            rag_query = self.query_analyzer.analyze(query, metadata=metadata)
        else:
            rag_query = query

        q_score = rag_query.completeness_score
        stage_scores[RAGStage.QUERY.value] = RAGStageScore(
            stage=RAGStage.QUERY,
            score=q_score,
            confidence=1.0,
            metrics={
                "completeness": rag_query.completeness_score,
                "ambiguity": rag_query.ambiguity_score,
                "complexity": rag_query.complexity_score,
                "retrieval_difficulty": rag_query.expected_retrieval_difficulty,
            },
            explanation=f"Query Type: {rag_query.query_type.value}, Completeness: {q_score:.2f}",
        )

        # 2. Security Analysis on retrieved content
        is_secure, sec_failures, sanitized_chunks = (
            self.security_analyzer.analyze_chunks(retrieved_chunks)
        )
        all_failures.extend(sec_failures)
        sec_score = 1.0 if is_secure else 0.0
        stage_scores[RAGStage.SECURITY.value] = RAGStageScore(
            stage=RAGStage.SECURITY,
            score=sec_score,
            confidence=1.0,
            failures=sec_failures,
            explanation="Passed all security and prompt injection audits"
            if is_secure
            else "Security violations detected in retrieved documents",
        )

        # 3. Retrieval Evaluation
        ret_result, ret_failures, ret_score = self.retrieval_evaluator.evaluate(
            query_id=rag_query.query_id,
            retrieved_documents=retrieved_documents,
            retrieved_chunks=sanitized_chunks,
            expected_document_ids=expected_document_ids,
            expected_chunk_ids=expected_chunk_ids,
        )
        all_failures.extend(ret_failures)
        stage_scores[RAGStage.RETRIEVAL.value] = RAGStageScore(
            stage=RAGStage.RETRIEVAL,
            score=ret_score,
            confidence=1.0 if ret_result.ground_truth_available else 0.70,
            metrics=ret_result.exact_metrics,
            failures=ret_failures,
            explanation=f"Retrieval score: {ret_score:.2f} (Ground truth: {ret_result.ground_truth_available})",
        )

        # 4. Ranking & Reranking Evaluation
        rank_result, rank_failures, rank_score = self.ranking_evaluator.evaluate(
            initial_chunks=sanitized_chunks,
            reranked_chunks=reranked_chunks,
            expected_chunk_ids=expected_chunk_ids,
            expected_doc_ids=expected_document_ids,
        )
        all_failures.extend(rank_failures)
        stage_scores[RAGStage.RANKING.value] = RAGStageScore(
            stage=RAGStage.RANKING,
            score=rank_score,
            confidence=0.90,
            metrics={"mrr": rank_result.mrr, "ndcg": rank_result.ndcg_at_k},
            failures=rank_failures,
            explanation=f"Ranking MRR: {rank_result.mrr:.2f}, NDCG: {rank_result.ndcg_at_k:.2f}",
        )

        # 5. Context Construction Analysis
        effective_chunks = (
            reranked_chunks if reranked_chunks is not None else sanitized_chunks
        )
        context_win, conflicts, ctx_failures, ctx_score = self.context_analyzer.analyze(
            chunks=effective_chunks,
            query_text=rag_query.text,
            expected_chunk_ids=expected_chunk_ids,
        )
        all_failures.extend(ctx_failures)
        stage_scores[RAGStage.CONTEXT.value] = RAGStageScore(
            stage=RAGStage.CONTEXT,
            score=ctx_score,
            confidence=0.90,
            metrics={
                "redundancy": context_win.redundancy_score,
                "conflicts": float(len(conflicts)),
                "tokens": float(context_win.token_count),
            },
            failures=ctx_failures,
            explanation=f"Context tokens: {context_win.token_count}, Redundancy: {context_win.redundancy_score:.2f}, Conflicts: {len(conflicts)}",
        )

        # 6. Generated Answer
        if isinstance(generated_answer, str):
            ans_model = GeneratedAnswer(
                text=generated_answer,
                model_name=model_name,
                latency_seconds=round(time.perf_counter() - t_start, 4),
            )
        else:
            ans_model = generated_answer

        # 7. Claim Extraction
        claims = self.claim_extractor.extract_claims(ans_model.text)

        # 8. Evidence Alignment
        aligned_claims, evidence_list, links, cov_metrics = (
            self.evidence_aligner.align_claims(
                claims=claims,
                chunks=effective_chunks,
            )
        )

        # 9. Citation Validation
        citations, cit_failures, cit_score = self.citation_validator.validate_citations(
            answer_text=ans_model.text,
            claims=aligned_claims,
            chunks=effective_chunks,
        )
        all_failures.extend(cit_failures)
        stage_scores[RAGStage.CITATION.value] = RAGStageScore(
            stage=RAGStage.CITATION,
            score=cit_score,
            confidence=0.90,
            metrics={
                "citation_score": cit_score,
                "citations_count": float(len(citations)),
            },
            failures=cit_failures,
            explanation=f"Citation validity & coverage score: {cit_score:.2f}",
        )

        # 10. Grounding & Faithfulness Evaluation
        grounding_score, faithfulness_score, hallucination_rate, g_failures, g_expl = (
            self.grounding_evaluator.evaluate(
                claims=aligned_claims,
                citations=citations,
                evidence_coverage_metrics=cov_metrics,
            )
        )
        all_failures.extend(g_failures)
        stage_scores[RAGStage.GROUNDING.value] = RAGStageScore(
            stage=RAGStage.GROUNDING,
            score=grounding_score,
            confidence=0.95,
            metrics={
                "grounding_score": grounding_score,
                "evidence_coverage": cov_metrics.get("evidence_coverage", 0.0),
            },
            failures=[f for f in g_failures if f.stage == RAGStage.GROUNDING],
            explanation=f"Grounding score: {grounding_score:.2f}",
        )
        stage_scores[RAGStage.FAITHFULNESS.value] = RAGStageScore(
            stage=RAGStage.FAITHFULNESS,
            score=faithfulness_score,
            confidence=0.95,
            metrics={
                "faithfulness_score": faithfulness_score,
                "hallucination_rate": hallucination_rate,
            },
            failures=[
                f
                for f in g_failures
                if f.stage in (RAGStage.FAITHFULNESS, RAGStage.GENERATION)
            ],
            explanation=f"Faithfulness score: {faithfulness_score:.2f}, Hallucination rate: {hallucination_rate:.2f}",
        )

        # 11. Freshness Evaluation
        fresh_score, stale_rate, fresh_failures, fresh_expl = (
            self.freshness_tracker.evaluate_freshness(
                documents=retrieved_documents,
                chunks=effective_chunks,
            )
        )
        all_failures.extend(fresh_failures)
        stage_scores[RAGStage.FRESHNESS.value] = RAGStageScore(
            stage=RAGStage.FRESHNESS,
            score=fresh_score,
            confidence=0.95,
            metrics={"freshness_score": fresh_score, "stale_rate": stale_rate},
            failures=fresh_failures,
            explanation=fresh_expl,
        )

        # 12. Aggregate Multidimensional Score
        rel_score = self.scorer.compute_score(
            stage_scores=stage_scores,
            failures=all_failures,
            security_passed=is_secure,
        )

        run = RAGRun(
            query=rag_query,
            retrieval_result=ret_result,
            ranking_result=rank_result,
            context_window=context_win,
            generated_answer=ans_model,
            claims=aligned_claims,
            evidence=evidence_list,
            claim_evidence_links=links,
            citations=citations,
            conflicts=conflicts,
            stage_scores=stage_scores,
            reliability_score=rel_score,
            failures=all_failures,
            model=model_name,
            retriever_name=retriever_name,
            reranker_name=reranker_name,
            dataset_id=dataset_id,
            metadata=metadata or {},
        )

        # Observability & Graph Sync
        self.obs_bridge.record_run(run)
        if sync_to_graph:
            self.graph_bridge.sync_rag_run(run, graph=graph)

        return run

    def evaluate_batch(
        self,
        test_cases: list[dict[str, Any]],
        sync_to_graph: bool = False,
        min_grounding_score: float = 0.70,
        min_overall_score: float = 0.75,
    ) -> RAGEvaluationResult:
        """Evaluate a batch of RAG executions and compute aggregate statistics."""
        runs: list[RAGRun] = []
        for tc in test_cases:
            raw_docs = tc.get("documents") or tc.get("retrieved_documents") or []
            parsed_docs = [
                d
                if isinstance(d, RetrievedDocument)
                else RetrievedDocument.model_validate(d)
                for d in raw_docs
            ]
            raw_chunks = tc.get("chunks") or tc.get("retrieved_chunks") or []
            parsed_chunks = [
                c if isinstance(c, RetrievedChunk) else RetrievedChunk.model_validate(c)
                for c in raw_chunks
            ]
            ans = (
                tc.get("answer")
                or tc.get("generated_answer")
                or tc.get("expected_answer")
                or ""
            )

            run = self.evaluate_run(
                query=tc["query"],
                retrieved_documents=parsed_docs,
                retrieved_chunks=parsed_chunks,
                generated_answer=ans,
                expected_document_ids=tc.get("expected_document_ids"),
                expected_chunk_ids=tc.get("expected_chunk_ids"),
                model_name=tc.get("model", "default-model"),
                retriever_name=tc.get("retriever", "default-retriever"),
                sync_to_graph=sync_to_graph,
            )
            runs.append(run)

        # Compute mean stage scores
        stage_totals: dict[str, float] = {}
        stage_counts: dict[str, int] = {}
        failure_counts: dict[str, int] = {}
        total_failures = 0
        critical_failures = 0

        for r in runs:
            total_failures += len(r.failures)
            for f in r.failures:
                if f.severity.value == "critical":
                    critical_failures += 1
                stage_key = f.stage.value
                failure_counts[stage_key] = failure_counts.get(stage_key, 0) + 1

            for st_name, st_res in r.stage_scores.items():
                stage_totals[st_name] = stage_totals.get(st_name, 0.0) + st_res.score
                stage_counts[st_name] = stage_counts.get(st_name, 0) + 1

        mean_scores = {
            st: round(stage_totals[st] / max(1, stage_counts[st]), 4)
            for st in stage_totals
        }

        overall_mean = sum(r.reliability_score.overall_score for r in runs) / max(
            1, len(runs)
        )

        passed_gates = (
            critical_failures == 0
            and overall_mean >= min_overall_score
            and mean_scores.get("grounding", 1.0) >= min_grounding_score
        )

        return RAGEvaluationResult(
            runs=runs,
            mean_stage_scores=mean_scores,
            overall_score=round(overall_mean, 4),
            total_failures=total_failures,
            failure_counts_by_stage=failure_counts,
            critical_failures_count=critical_failures,
            passed_release_gates=passed_gates,
            summary=(
                f"Evaluated {len(runs)} RAG runs. Mean overall score: {overall_mean:.2f}. "
                f"Total failures: {total_failures} (Critical: {critical_failures}). "
                f"Status: {'PASSED' if passed_gates else 'FAILED GATES'}."
            ),
        )
