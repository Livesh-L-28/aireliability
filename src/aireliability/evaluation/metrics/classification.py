"""Classical ML classification metrics for AI evaluation."""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConfusionMatrix(BaseModel):
    """Confusion matrix representation for binary and multiclass evaluations."""

    model_config = ConfigDict(frozen=True)

    true_positive: int = 0
    false_positive: int = 0
    true_negative: int = 0
    false_negative: int = 0
    multiclass_matrix: dict[str, dict[str, int]] = Field(default_factory=dict)
    labels: list[str] = Field(default_factory=list)

    @property
    def total(self) -> int:
        """Total number of evaluated samples."""
        if self.multiclass_matrix:
            return sum(sum(row.values()) for row in self.multiclass_matrix.values())
        return (
            self.true_positive
            + self.false_positive
            + self.true_negative
            + self.false_negative
        )


def confusion_matrix(
    y_true: list[Any],
    y_pred: list[Any],
    labels: list[Any] | None = None,
    pos_label: Any = 1,
) -> ConfusionMatrix:
    """Compute confusion matrix to evaluate classification accuracy."""
    if len(y_true) != len(y_pred):
        raise ValueError(
            f"Length mismatch: len(y_true)={len(y_true)} vs len(y_pred)={len(y_pred)}"
        )

    unique_labels: list[str] = (
        [str(lbl) for lbl in labels]
        if labels is not None
        else sorted({str(x) for x in y_true} | {str(x) for x in y_pred})
    )

    # Multi-class table
    matrix: dict[str, dict[str, int]] = {
        lbl_t: {lbl_p: 0 for lbl_p in unique_labels} for lbl_t in unique_labels
    }

    tp = fp = tn = fn = 0
    pos_str = str(pos_label)

    for yt, yp in zip(y_true, y_pred, strict=False):
        st_yt = str(yt)
        st_yp = str(yp)
        if st_yt in matrix and st_yp in matrix[st_yt]:
            matrix[st_yt][st_yp] += 1

        is_true_pos = st_yt == pos_str
        is_pred_pos = st_yp == pos_str

        if is_true_pos and is_pred_pos:
            tp += 1
        elif not is_true_pos and is_pred_pos:
            fp += 1
        elif not is_true_pos and not is_pred_pos:
            tn += 1
        elif is_true_pos and not is_pred_pos:
            fn += 1

    return ConfusionMatrix(
        true_positive=tp,
        false_positive=fp,
        true_negative=tn,
        false_negative=fn,
        multiclass_matrix=matrix,
        labels=unique_labels,
    )


def accuracy(y_true: list[Any], y_pred: list[Any]) -> float:
    """Calculate accuracy classification score."""
    if not y_true:
        return 0.0
    if len(y_true) != len(y_pred):
        raise ValueError("Length mismatch between y_true and y_pred")
    correct = sum(1 for yt, yp in zip(y_true, y_pred, strict=False) if yt == yp)
    return correct / len(y_true)


def precision(
    y_true: list[Any],
    y_pred: list[Any],
    pos_label: Any = 1,
    zero_division: float = 0.0,
) -> float:
    """Calculate binary precision score."""
    cm = confusion_matrix(y_true, y_pred, pos_label=pos_label)
    denom = cm.true_positive + cm.false_positive
    if denom == 0:
        return float(zero_division)
    return cm.true_positive / denom


def recall(
    y_true: list[Any],
    y_pred: list[Any],
    pos_label: Any = 1,
    zero_division: float = 0.0,
) -> float:
    """Calculate binary recall score (sensitivity)."""
    cm = confusion_matrix(y_true, y_pred, pos_label=pos_label)
    denom = cm.true_positive + cm.false_negative
    if denom == 0:
        return float(zero_division)
    return cm.true_positive / denom


def sensitivity(
    y_true: list[Any],
    y_pred: list[Any],
    pos_label: Any = 1,
    zero_division: float = 0.0,
) -> float:
    """Calculate sensitivity (alias for recall)."""
    return recall(y_true, y_pred, pos_label=pos_label, zero_division=zero_division)


def specificity(
    y_true: list[Any],
    y_pred: list[Any],
    pos_label: Any = 1,
    zero_division: float = 0.0,
) -> float:
    """Calculate binary specificity (true negative rate)."""
    cm = confusion_matrix(y_true, y_pred, pos_label=pos_label)
    denom = cm.true_negative + cm.false_positive
    if denom == 0:
        return float(zero_division)
    return cm.true_negative / denom


def f_beta(
    y_true: list[Any],
    y_pred: list[Any],
    beta: float = 1.0,
    pos_label: Any = 1,
    zero_division: float = 0.0,
) -> float:
    """Calculate F-beta score."""
    p = precision(y_true, y_pred, pos_label=pos_label, zero_division=0.0)
    r = recall(y_true, y_pred, pos_label=pos_label, zero_division=0.0)
    beta_sq = beta**2
    denom = (beta_sq * p) + r
    if denom == 0.0:
        return float(zero_division)
    return (1.0 + beta_sq) * (p * r) / denom


def f1(
    y_true: list[Any],
    y_pred: list[Any],
    pos_label: Any = 1,
    zero_division: float = 0.0,
) -> float:
    """Calculate F1 score."""
    return f_beta(
        y_true, y_pred, beta=1.0, pos_label=pos_label, zero_division=zero_division
    )


def balanced_accuracy(
    y_true: list[Any],
    y_pred: list[Any],
    pos_label: Any = 1,
    zero_division: float = 0.0,
) -> float:
    """Calculate balanced accuracy = (sensitivity + specificity) / 2."""
    sens = sensitivity(y_true, y_pred, pos_label=pos_label, zero_division=zero_division)
    spec = specificity(y_true, y_pred, pos_label=pos_label, zero_division=zero_division)
    return (sens + spec) / 2.0


def matthews_correlation_coefficient(
    y_true: list[Any],
    y_pred: list[Any],
    pos_label: Any = 1,
    zero_division: float = 0.0,
) -> float:
    """Calculate Matthews Correlation Coefficient (MCC)."""
    cm = confusion_matrix(y_true, y_pred, pos_label=pos_label)
    tp, fp, tn, fn = (
        cm.true_positive,
        cm.false_positive,
        cm.true_negative,
        cm.false_negative,
    )
    numerator = (tp * tn) - (fp * fn)
    denom = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    if denom == 0.0:
        return float(zero_division)
    return numerator / denom


def macro_precision(
    y_true: list[Any],
    y_pred: list[Any],
    labels: list[Any] | None = None,
    zero_division: float = 0.0,
) -> float:
    """Calculate macro-averaged precision."""
    unique = labels or sorted({str(x) for x in y_true} | {str(x) for x in y_pred})
    if not unique:
        return 0.0
    scores = [
        precision(y_true, y_pred, pos_label=lbl, zero_division=zero_division)
        for lbl in unique
    ]
    return sum(scores) / len(scores)


def macro_recall(
    y_true: list[Any],
    y_pred: list[Any],
    labels: list[Any] | None = None,
    zero_division: float = 0.0,
) -> float:
    """Calculate macro-averaged recall."""
    unique = labels or sorted({str(x) for x in y_true} | {str(x) for x in y_pred})
    if not unique:
        return 0.0
    scores = [
        recall(y_true, y_pred, pos_label=lbl, zero_division=zero_division)
        for lbl in unique
    ]
    return sum(scores) / len(scores)


def macro_f1(
    y_true: list[Any],
    y_pred: list[Any],
    labels: list[Any] | None = None,
    zero_division: float = 0.0,
) -> float:
    """Calculate macro-averaged F1."""
    unique = labels or sorted({str(x) for x in y_true} | {str(x) for x in y_pred})
    if not unique:
        return 0.0
    scores = [
        f1(y_true, y_pred, pos_label=lbl, zero_division=zero_division) for lbl in unique
    ]
    return sum(scores) / len(scores)


def micro_f1(
    y_true: list[Any],
    y_pred: list[Any],
) -> float:
    """Calculate micro-averaged F1 (equivalent to accuracy in multi-class)."""
    return accuracy(y_true, y_pred)


def weighted_f1(
    y_true: list[Any],
    y_pred: list[Any],
    labels: list[Any] | None = None,
    zero_division: float = 0.0,
) -> float:
    """Calculate weighted F1 score by support for each class."""
    if not y_true:
        return 0.0
    unique = labels or sorted({str(x) for x in y_true} | {str(x) for x in y_pred})
    total = len(y_true)
    weighted_sum = 0.0
    for lbl in unique:
        support = sum(1 for yt in y_true if str(yt) == str(lbl))
        if support > 0:
            score = f1(y_true, y_pred, pos_label=lbl, zero_division=zero_division)
            weighted_sum += score * (support / total)
    return weighted_sum
