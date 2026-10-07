"""Information Retrieval and ranking metrics for AI evaluation."""

from __future__ import annotations

import math
from typing import Any


def precision_at_k(
    relevant: list[Any] | set[Any],
    retrieved: list[Any],
    k: int,
) -> float:
    """Calculate Precision@K: proportion of top-K retrieved items that are relevant."""
    if k <= 0:
        return 0.0
    cutoff = retrieved[:k]
    if not cutoff:
        return 0.0
    rel_set = set(relevant)
    hits = sum(1 for item in cutoff if item in rel_set)
    return hits / k


def recall_at_k(
    relevant: list[Any] | set[Any],
    retrieved: list[Any],
    k: int,
) -> float:
    """Calculate Recall@K: proportion of relevant items retrieved in top-K."""
    if not relevant or k <= 0:
        return 0.0
    rel_set = set(relevant)
    cutoff = retrieved[:k]
    hits = sum(1 for item in cutoff if item in rel_set)
    return hits / len(rel_set)


def hit_at_k(
    relevant: list[Any] | set[Any],
    retrieved: list[Any],
    k: int,
) -> float:
    """Calculate Hit@K: 1.0 if at least one relevant item is in top-K, else 0.0."""
    if k <= 0:
        return 0.0
    rel_set = set(relevant)
    cutoff = retrieved[:k]
    return 1.0 if any(item in rel_set for item in cutoff) else 0.0


def reciprocal_rank(
    relevant: list[Any] | set[Any],
    retrieved: list[Any],
) -> float:
    """Calculate Reciprocal Rank (RR): reciprocal of the 1-based rank of the first relevant item."""
    rel_set = set(relevant)
    for idx, item in enumerate(retrieved, start=1):
        if item in rel_set:
            return 1.0 / idx
    return 0.0


def mean_reciprocal_rank(
    queries_relevant: list[list[Any] | set[Any]],
    queries_retrieved: list[list[Any]],
) -> float:
    """Calculate Mean Reciprocal Rank (MRR) across multiple queries."""
    if not queries_relevant:
        return 0.0
    rrs = [
        reciprocal_rank(rel, ret)
        for rel, ret in zip(queries_relevant, queries_retrieved, strict=False)
    ]
    return sum(rrs) / len(rrs)


def average_precision(
    relevant: list[Any] | set[Any],
    retrieved: list[Any],
    k: int | None = None,
) -> float:
    """Calculate Average Precision (AP) for a single ranked list."""
    if not relevant:
        return 0.0
    rel_set = set(relevant)
    cutoff = retrieved[:k] if k is not None else retrieved
    if not cutoff:
        return 0.0

    running_hits = 0
    precisions: list[float] = []

    for rank, item in enumerate(cutoff, start=1):
        if item in rel_set:
            running_hits += 1
            precisions.append(running_hits / rank)

    if not precisions:
        return 0.0

    denom = min(len(rel_set), len(cutoff)) if k is not None else len(rel_set)
    return sum(precisions) / max(1, denom)


def mean_average_precision(
    queries_relevant: list[list[Any] | set[Any]],
    queries_retrieved: list[list[Any]],
    k: int | None = None,
) -> float:
    """Calculate Mean Average Precision (MAP) across queries."""
    if not queries_relevant:
        return 0.0
    aps = [
        average_precision(rel, ret, k=k)
        for rel, ret in zip(queries_relevant, queries_retrieved, strict=False)
    ]
    return sum(aps) / len(aps)


def dcg_at_k(relevances: list[float], k: int) -> float:
    """Calculate Discounted Cumulative Gain at rank K."""
    if k <= 0:
        return 0.0
    cutoff = relevances[:k]
    gain = 0.0
    for idx, rel in enumerate(cutoff, start=1):
        gain += (2.0**rel - 1.0) / math.log2(idx + 1)
    return gain


def ndcg_at_k(
    actual_relevances: list[float],
    predicted_relevances: list[float],
    k: int,
) -> float:
    """Calculate Normalized Discounted Cumulative Gain (NDCG) at K."""
    if k <= 0:
        return 0.0
    actual_dcg = dcg_at_k(predicted_relevances, k)
    ideal_relevances = sorted(actual_relevances, reverse=True)
    ideal_dcg = dcg_at_k(ideal_relevances, k)
    if ideal_dcg == 0.0:
        return 0.0
    return actual_dcg / ideal_dcg


def ndcg_from_ranking(
    relevant_items: list[Any] | set[Any],
    ranked_retrieved: list[Any],
    k: int,
) -> float:
    """Calculate binary NDCG@K given set of relevant item IDs and ranked list of retrieved item IDs."""
    if k <= 0 or not ranked_retrieved:
        return 0.0
    rel_set = set(relevant_items)
    pred_rel = [1.0 if item in rel_set else 0.0 for item in ranked_retrieved[:k]]
    actual_rel = [1.0] * min(len(rel_set), k)
    return ndcg_at_k(actual_rel, pred_rel, k)
