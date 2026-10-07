"""Retrieval Evaluator evaluating exact ground-truth and heuristic retrieval reliability."""

from __future__ import annotations

import math
from typing import Any

from aireliability.rag.models import (
    FailureSeverity,
    RAGFailure,
    RAGFailureCategory,
    RAGStage,
    RetrievalResult,
    RetrievedChunk,
    RetrievedDocument,
)


class RetrievalEvaluator:
    """Evaluates information retrieval stages against ground truth or empirical heuristics."""

    def __init__(
        self,
        min_recall: float = 0.70,
        min_precision: float = 0.50,
        top_k: int = 5,
    ) -> None:
        self.min_recall = min_recall
        self.min_precision = min_precision
        self.top_k = top_k

    def evaluate_retrieval(
        self,
        retrieved_documents: list[RetrievedDocument] | None = None,
        retrieved_chunks: list[RetrievedChunk] | None = None,
        expected_document_ids: list[str] | None = None,
        expected_chunk_ids: list[str] | None = None,
        query_id: str = "eval_query",
        execution_time_ms: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[RetrievalResult, list[RAGFailure]]:
        """Convenience method returning (RetrievalResult, failures)."""
        res, fails, _ = self.evaluate(
            query_id=query_id,
            retrieved_documents=retrieved_documents or [],
            retrieved_chunks=retrieved_chunks or [],
            expected_document_ids=expected_document_ids,
            expected_chunk_ids=expected_chunk_ids,
            execution_time_ms=execution_time_ms,
            metadata=metadata,
        )
        return res, fails

    def evaluate(
        self,
        query_id: str = "eval_query",
        retrieved_documents: list[RetrievedDocument] | None = None,
        retrieved_chunks: list[RetrievedChunk] | None = None,
        expected_document_ids: list[str] | None = None,
        expected_chunk_ids: list[str] | None = None,
        execution_time_ms: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[RetrievalResult, list[RAGFailure], float]:
        """Evaluate retrieval performance and attribute specific retrieval failures.

        Returns (RetrievalResult, list_of_failures, retrieval_stage_score).
        """
        meta = metadata or {}
        failures: list[RAGFailure] = []
        effective_docs = retrieved_documents or []
        effective_chunks = retrieved_chunks or []

        # 1. Check for zero results
        if not effective_docs and not effective_chunks:
            failures.append(
                RAGFailure(
                    stage=RAGStage.RETRIEVAL,
                    category=RAGFailureCategory.NO_RESULTS,
                    severity=FailureSeverity.CRITICAL,
                    message="NO_RESULTS: Retriever returned zero candidate documents or chunks.",
                    confidence=1.0,
                )
            )
            res = RetrievalResult(
                query_id=query_id,
                retrieved_documents=[],
                retrieved_chunks=[],
                execution_time_ms=execution_time_ms,
                ground_truth_available=bool(
                    expected_document_ids or expected_chunk_ids
                ),
                exact_metrics={
                    "recall": 0.0,
                    "precision": 0.0,
                    "hit_rate": 0.0,
                    "mrr": 0.0,
                    "ndcg": 0.0,
                },
                metadata=meta,
            )
            return res, failures, 0.0

        # 2. Check for duplicate results
        dup_count = self._count_duplicates(effective_chunks)
        if dup_count > 0:
            failures.append(
                RAGFailure(
                    stage=RAGStage.RETRIEVAL,
                    category=RAGFailureCategory.DUPLICATE_RESULTS,
                    severity=FailureSeverity.LOW,
                    message=f"DUPLICATE_RESULTS: Found {dup_count} duplicate or highly redundant chunks in retrieval pool.",
                    confidence=0.90,
                )
            )

        # 3. Ground Truth Evaluation
        exact_metrics: dict[str, float] = {}
        ground_truth_available = False
        stage_score = 1.0

        if expected_document_ids or expected_chunk_ids:
            ground_truth_available = True
            metrics = self._compute_exact_metrics(
                retrieved_documents=effective_docs,
                retrieved_chunks=effective_chunks,
                expected_doc_ids=expected_document_ids or [],
                expected_chunk_ids=expected_chunk_ids or [],
                k=self.top_k,
            )
            exact_metrics = metrics
            recall = metrics.get("recall", 0.0)
            precision = metrics.get("precision", 0.0)
            hit_rate = metrics.get("hit_rate", 0.0)
            ndcg = metrics.get("ndcg", 0.0)

            # Stage score is harmonic balance of recall, precision, ndcg
            stage_score = round((0.4 * recall) + (0.3 * precision) + (0.3 * ndcg), 4)

            # Failure attribution
            if hit_rate == 0.0:
                failures.append(
                    RAGFailure(
                        stage=RAGStage.RETRIEVAL,
                        category=RAGFailureCategory.WRONG_DOCUMENT,
                        severity=FailureSeverity.CRITICAL,
                        message="WRONG_DOCUMENT: None of the expected ground-truth documents were retrieved.",
                        confidence=0.95,
                    )
                )
            if recall < self.min_recall:
                failures.append(
                    RAGFailure(
                        stage=RAGStage.RETRIEVAL,
                        category=RAGFailureCategory.LOW_RECALL,
                        severity=FailureSeverity.HIGH,
                        message=f"LOW_RECALL: Retrieval recall {recall:.3f} is below minimum threshold {self.min_recall:.3f}.",
                        confidence=0.90,
                    )
                )

            if precision < self.min_precision:
                failures.append(
                    RAGFailure(
                        stage=RAGStage.RETRIEVAL,
                        category=RAGFailureCategory.LOW_PRECISION,
                        severity=FailureSeverity.MEDIUM,
                        message=f"LOW_PRECISION: Retrieval precision {precision:.3f} is below minimum threshold {self.min_precision:.3f}.",
                        confidence=0.85,
                    )
                )

            # Check chunk-level specificity failure
            if expected_chunk_ids and expected_document_ids:
                ret_chunk_ids = {c.chunk_id for c in effective_chunks}
                has_doc = any(
                    d.document_id in expected_document_ids for d in effective_docs
                )
                has_chunk = any(c_id in ret_chunk_ids for c_id in expected_chunk_ids)
                if has_doc and not has_chunk:
                    failures.append(
                        RAGFailure(
                            stage=RAGStage.RETRIEVAL,
                            category=RAGFailureCategory.WRONG_CHUNK,
                            severity=FailureSeverity.MEDIUM,
                            message="WRONG_CHUNK: Expected document was retrieved, but relevant specific chunk was omitted.",
                            confidence=0.85,
                        )
                    )
        else:
            # NO GROUND TRUTH: Never fabricate recall!
            ground_truth_available = False
            # Estimate heuristic score based on retrieval confidence and chunk relevance scores
            scores = [
                c.retrieval_score for c in retrieved_chunks if c.retrieval_score > 0.0
            ]
            avg_score = sum(scores) / len(scores) if scores else 0.70
            exact_metrics = {
                "heuristic_confidence": round(avg_score, 4),
                "retrieved_count": float(len(retrieved_chunks)),
            }
            stage_score = round(max(0.3, min(1.0, avg_score)), 4)

        # 4. Hybrid breakdown analysis
        lex_contrib, sem_contrib, overlap = self._analyze_hybrid(retrieved_chunks)

        result = RetrievalResult(
            query_id=query_id,
            retrieved_documents=retrieved_documents,
            retrieved_chunks=retrieved_chunks,
            lexical_contribution=lex_contrib,
            semantic_contribution=sem_contrib,
            hybrid_overlap_ratio=overlap,
            execution_time_ms=execution_time_ms,
            total_candidates_examined=len(retrieved_chunks),
            ground_truth_available=ground_truth_available,
            exact_metrics=exact_metrics,
            metadata=meta,
        )

        return result, failures, stage_score

    def _count_duplicates(self, chunks: list[RetrievedChunk]) -> int:
        """Count near-duplicate chunks via token set similarity."""
        dup_count = 0
        seen_texts: list[set[str]] = []
        for chk in chunks:
            tokens = set(chk.text.lower().split())
            if not tokens:
                continue
            is_dup = False
            for prev in seen_texts:
                jaccard = len(tokens & prev) / len(tokens | prev)
                if jaccard > 0.85:
                    is_dup = True
                    break
            if is_dup:
                dup_count += 1
            else:
                seen_texts.append(tokens)
        return dup_count

    def _compute_exact_metrics(
        self,
        retrieved_documents: list[RetrievedDocument],
        retrieved_chunks: list[RetrievedChunk],
        expected_doc_ids: list[str],
        expected_chunk_ids: list[str],
        k: int,
    ) -> dict[str, float]:
        """Compute standard ranking and retrieval metrics."""
        ret_doc_ids = [d.document_id for d in retrieved_documents]
        if not ret_doc_ids and retrieved_chunks:
            ret_doc_ids = list(dict.fromkeys(c.document_id for c in retrieved_chunks))

        targets = set(expected_doc_ids if expected_doc_ids else expected_chunk_ids)
        observed = ret_doc_ids[:k]

        if not targets:
            return {
                "recall": 1.0,
                "precision": 1.0,
                "hit_rate": 1.0,
                "mrr": 1.0,
                "ndcg": 1.0,
            }

        retrieved_relevant = [doc_id for doc_id in observed if doc_id in targets]
        hits = len(retrieved_relevant)

        recall = hits / len(targets)
        precision = hits / len(observed) if observed else 0.0
        hit_rate = 1.0 if hits > 0 else 0.0

        # MRR
        mrr = 0.0
        for rank_idx, doc_id in enumerate(observed, start=1):
            if doc_id in targets:
                mrr = 1.0 / rank_idx
                break

        # NDCG@K
        dcg = 0.0
        for rank_idx, doc_id in enumerate(observed, start=1):
            rel = 1.0 if doc_id in targets else 0.0
            dcg += (2.0**rel - 1.0) / math.log2(rank_idx + 1.0)

        idcg = sum(
            (1.0 / math.log2(i + 1.0)) for i in range(1, min(len(targets), k) + 1)
        )
        ndcg = (dcg / idcg) if idcg > 0 else 0.0

        return {
            "recall": round(recall, 4),
            "precision": round(precision, 4),
            "document_recall": round(recall, 4),
            "document_precision": round(precision, 4),
            "hit_rate": round(hit_rate, 4),
            "mrr": round(mrr, 4),
            "ndcg": round(ndcg, 4),
            "ndcg_at_k": round(ndcg, 4),
            "top_k_recall": round(recall, 4),
        }

    def _analyze_hybrid(
        self, chunks: list[RetrievedChunk]
    ) -> tuple[float, float, float]:
        """Compute lexical vs semantic contributions from metadata."""
        if not chunks:
            return 0.5, 0.5, 0.5

        lex_count = 0
        sem_count = 0
        both_count = 0

        for chk in chunks:
            has_lex = (
                chk.metadata.get("lexical_score") is not None
                or chk.metadata.get("source") == "bm25"
            )
            has_sem = (
                chk.metadata.get("dense_score") is not None
                or chk.metadata.get("source") == "dense"
            )
            if has_lex and has_sem:
                both_count += 1
            elif has_lex:
                lex_count += 1
            elif has_sem:
                sem_count += 1
            else:
                both_count += 1

        total = float(len(chunks))
        lex_ratio = (lex_count + 0.5 * both_count) / total
        sem_ratio = (sem_count + 0.5 * both_count) / total
        overlap = both_count / total

        return round(lex_ratio, 3), round(sem_ratio, 3), round(overlap, 3)
