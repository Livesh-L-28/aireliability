"""Unit tests for Phase 31 Metrics Engine (classification, ranking, statistics)."""

import pytest

from aireliability.evaluation.metrics import (
    accuracy,
    average_precision,
    balanced_accuracy,
    bootstrap_confidence_interval,
    cohens_d,
    compute_statistical_summary,
    confidence_interval,
    confusion_matrix,
    dcg_at_k,
    f1,
    hit_at_k,
    macro_f1,
    macro_precision,
    macro_recall,
    mann_whitney_u,
    matthews_correlation_coefficient,
    mean,
    mean_average_precision,
    mean_reciprocal_rank,
    median,
    micro_f1,
    ndcg_at_k,
    ndcg_from_ranking,
    percentile,
    precision,
    precision_at_k,
    recall,
    recall_at_k,
    reciprocal_rank,
    sensitivity,
    specificity,
    standard_deviation,
    variance,
    weighted_f1,
    welchs_t_test,
)


def test_classification_binary_metrics():
    y_true = [1, 1, 0, 0, 1, 0, 1, 0]
    y_pred = [1, 0, 0, 0, 1, 1, 1, 0]

    cm = confusion_matrix(y_true, y_pred, pos_label=1)
    assert cm.true_positive == 3
    assert cm.false_positive == 1
    assert cm.false_negative == 1
    assert cm.true_negative == 3

    acc = accuracy(y_true, y_pred)
    assert acc == 6 / 8

    prec = precision(y_true, y_pred, pos_label=1)
    assert prec == 3 / 4

    rec = recall(y_true, y_pred, pos_label=1)
    assert rec == 3 / 4
    assert sensitivity(y_true, y_pred, pos_label=1) == rec

    spec = specificity(y_true, y_pred, pos_label=1)
    assert spec == 3 / 4

    f1_score = f1(y_true, y_pred, pos_label=1)
    assert f1_score == 0.75

    bal_acc = balanced_accuracy(y_true, y_pred, pos_label=1)
    assert bal_acc == 0.75

    mcc = matthews_correlation_coefficient(y_true, y_pred, pos_label=1)
    assert mcc == pytest.approx(0.5, 0.01)


def test_classification_macro_micro_weighted():
    y_true = ["cat", "dog", "cat", "bird", "dog", "dog"]
    y_pred = ["cat", "cat", "cat", "bird", "dog", "dog"]

    acc = accuracy(y_true, y_pred)
    assert acc == pytest.approx(5 / 6)
    assert micro_f1(y_true, y_pred) == acc

    macro_f = macro_f1(y_true, y_pred)
    assert 0.0 <= macro_f <= 1.0

    macro_p = macro_precision(y_true, y_pred)
    assert 0.0 <= macro_p <= 1.0

    macro_r = macro_recall(y_true, y_pred)
    assert 0.0 <= macro_r <= 1.0

    wt_f1 = weighted_f1(y_true, y_pred)
    assert 0.0 <= wt_f1 <= 1.0


def test_classification_edge_cases():
    # Empty inputs
    assert accuracy([], []) == 0.0
    assert precision([], [], zero_division=0.0) == 0.0
    assert recall([], [], zero_division=0.0) == 0.0
    assert f1([], [], zero_division=0.0) == 0.0

    # Zero positive predictions
    y_true = [1, 1, 1]
    y_pred = [0, 0, 0]
    assert precision(y_true, y_pred, zero_division=0.0) == 0.0
    assert recall(y_true, y_pred) == 0.0
    assert f1(y_true, y_pred) == 0.0

    # Mismatched lengths
    with pytest.raises(ValueError):
        accuracy([1, 0], [1])


def test_ranking_metrics():
    relevant = ["doc1", "doc3", "doc5"]
    retrieved = ["doc1", "doc2", "doc3", "doc4", "doc6"]

    assert precision_at_k(relevant, retrieved, 1) == 1.0
    assert precision_at_k(relevant, retrieved, 2) == 0.5
    assert recall_at_k(relevant, retrieved, 2) == pytest.approx(1 / 3)
    assert hit_at_k(relevant, retrieved, 1) == 1.0
    assert hit_at_k(relevant, ["doc2", "doc4"], 2) == 0.0

    # MRR
    assert reciprocal_rank(relevant, retrieved) == 1.0
    assert reciprocal_rank(relevant, ["doc2", "doc3"]) == 0.5
    assert reciprocal_rank(relevant, ["doc2", "doc4"]) == 0.0

    mrr = mean_reciprocal_rank(
        [relevant, relevant],
        [retrieved, ["doc2", "doc3"]],
    )
    assert mrr == 0.75

    # MAP
    ap = average_precision(relevant, retrieved, k=3)
    assert ap > 0.0
    map_score = mean_average_precision([relevant], [retrieved], k=3)
    assert map_score == ap

    # NDCG
    ndcg = ndcg_from_ranking(relevant, retrieved, 3)
    assert 0.0 <= ndcg <= 1.0

    # Zero k edge cases
    assert precision_at_k(relevant, retrieved, 0) == 0.0
    assert recall_at_k(relevant, retrieved, 0) == 0.0
    assert hit_at_k(relevant, retrieved, 0) == 0.0
    assert dcg_at_k([], 0) == 0.0
    assert ndcg_at_k([], [], 0) == 0.0


def test_statistical_primitives():
    values = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
    assert mean(values) == 5.0
    assert median(values) == 4.5
    assert min(values) == 2.0
    assert max(values) == 9.0
    assert variance(values, sample=True) == pytest.approx(4.5714, 0.01)
    assert standard_deviation(values, sample=True) == pytest.approx(2.138, 0.01)
    assert percentile(values, 0.50) == 4.5

    # Confidence intervals
    low, high = confidence_interval(values, confidence=0.95)
    assert low < mean(values) < high

    # Bootstrap
    b_low, b_high = bootstrap_confidence_interval(values, num_resamples=500, seed=123)
    assert b_low < mean(values) < b_high

    # Statistical Summary
    summary = compute_statistical_summary(values)
    assert summary.count == 8
    assert summary.mean == 5.0
    assert summary.min == 2.0
    assert summary.max == 9.0


def test_hypothesis_testing_welch_and_mann_whitney():
    group_a = [10.0, 11.0, 12.0, 10.5, 11.5]
    group_b = [20.0, 21.0, 22.0, 20.5, 21.5]

    t_stat, p_val = welchs_t_test(group_a, group_b)
    assert t_stat < 0
    assert p_val < 0.001

    d = cohens_d(group_b, group_a)
    assert d > 1.0  # Large positive effect size

    u_stat, u_pval = mann_whitney_u(group_a, group_b)
    assert u_stat == 0.0
    assert u_pval < 0.05
