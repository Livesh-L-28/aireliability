"""Judge evaluation, calibration, bias analysis, and inter-rater agreement."""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from aireliability.evaluation.metrics.statistics import mean, variance


class JudgeReliabilityReport(BaseModel):
    """Assessment of judge reliability, biases, and agreement."""

    model_config = ConfigDict(frozen=True)

    judge_name: str
    agreement_score: float
    consistency_rate: float
    score_variance: float
    length_bias_correlation: float
    position_bias_delta: float
    self_preference_delta: float
    calibration_brier_score: float
    human_agreement_rate: float
    metadata: dict[str, Any] = Field(default_factory=dict)


def cohens_kappa(rater_a: list[Any], rater_b: list[Any]) -> float:
    """Calculate Cohen's Kappa for inter-rater agreement between two judges."""
    if len(rater_a) != len(rater_b) or not rater_a:
        return 0.0

    n = len(rater_a)
    categories = sorted({str(x) for x in rater_a} | {str(x) for x in rater_b})
    cat_to_idx = {c: i for i, c in enumerate(categories)}
    num_cats = len(categories)

    if num_cats <= 1:
        return 1.0

    # Build agreement table
    table = [[0] * num_cats for _ in range(num_cats)]
    for a, b in zip(rater_a, rater_b, strict=False):
        table[cat_to_idx[str(a)]][cat_to_idx[str(b)]] += 1

    observed_agreement = sum(table[i][i] for i in range(num_cats)) / n

    # Marginal probabilities
    row_sums = [sum(row) / n for row in table]
    col_sums = [sum(table[r][c] for r in range(num_cats)) / n for c in range(num_cats)]
    chance_agreement = sum(r * c for r, c in zip(row_sums, col_sums, strict=False))

    if chance_agreement >= 1.0:
        return 1.0
    return (observed_agreement - chance_agreement) / (1.0 - chance_agreement)


def fleiss_kappa(ratings_matrix: list[list[int]]) -> float:
    """Calculate Fleiss' Kappa for inter-rater agreement among fixed number of raters.

    ratings_matrix[i][j] is the number of raters who assigned category j to subject i.
    """
    n_subjects = len(ratings_matrix)
    if n_subjects == 0:
        return 0.0
    n_categories = len(ratings_matrix[0])
    n_raters = sum(ratings_matrix[0])
    if n_raters <= 1:
        return 1.0

    # p_j: proportion of all assignments to category j
    total_assignments = n_subjects * n_raters
    p_j = [
        sum(ratings_matrix[i][j] for i in range(n_subjects)) / total_assignments
        for j in range(n_categories)
    ]
    p_e = sum(p**2 for p in p_j)

    # P_i: extent of agreement among raters for subject i
    p_i: list[float] = []
    for i in range(n_subjects):
        sum_sq = sum(ratings_matrix[i][j] ** 2 for j in range(n_categories))
        p_i.append((sum_sq - n_raters) / (n_raters * (n_raters - 1)))

    p_bar = sum(p_i) / n_subjects

    if p_e >= 1.0:
        return 1.0
    return (p_bar - p_e) / (1.0 - p_e)


def calculate_length_bias(scores: list[float], lengths: list[int]) -> float:
    """Calculate Pearson correlation between candidate output length and judge score."""
    if len(scores) < 2 or len(scores) != len(lengths):
        return 0.0
    mean_s = mean(scores)
    float_lengths = [float(x) for x in lengths]
    mean_l = mean(float_lengths)

    cov = sum(
        (s - mean_s) * (length_val - mean_l)
        for s, length_val in zip(scores, float_lengths, strict=False)
    ) / len(scores)
    std_s = math.sqrt(variance(scores, sample=False))
    std_l = math.sqrt(variance(float_lengths, sample=False))

    if std_s == 0.0 or std_l == 0.0:
        return 0.0
    return max(-1.0, min(1.0, cov / (std_s * std_l)))


def calculate_position_bias(
    pairwise_results: list[dict[str, Any]],
) -> float:
    """Calculate position bias in pairwise evaluation (delta in win-rate between position 1 and 2)."""
    if not pairwise_results:
        return 0.0
    pos1_wins = sum(1 for r in pairwise_results if r.get("winner") == 1)
    total = len(pairwise_results)
    pos1_win_rate = pos1_wins / total
    # 0.5 is perfectly neutral; return absolute deviation from 0.5
    return round(abs(pos1_win_rate - 0.5) * 2.0, 4)


def calculate_self_preference_bias(
    judge_model: str,
    evaluations: list[dict[str, Any]],
) -> float:
    """Calculate score delta when candidate model matches judge model vs different model."""
    same_model_scores: list[float] = []
    diff_model_scores: list[float] = []

    for ev in evaluations:
        cand_model = str(ev.get("candidate_model", ""))
        score = float(ev.get("score", 0.0))
        if cand_model == judge_model:
            same_model_scores.append(score)
        else:
            diff_model_scores.append(score)

    if not same_model_scores or not diff_model_scores:
        return 0.0
    return round(mean(same_model_scores) - mean(diff_model_scores), 4)


def calculate_brier_score(
    predicted_probabilities: list[float],
    ground_truth_binary: list[int | bool],
) -> float:
    """Calculate Brier calibration score (mean squared error of probabilistic predictions)."""
    if (
        len(predicted_probabilities) != len(ground_truth_binary)
        or not predicted_probabilities
    ):
        return 0.0
    diffs = [
        (p - (1.0 if y else 0.0)) ** 2
        for p, y in zip(predicted_probabilities, ground_truth_binary, strict=False)
    ]
    return sum(diffs) / len(diffs)


class JudgeReliabilityEvaluator:
    """Evaluates the reliability, calibration, agreement, and biases of an LLM judge."""

    def __init__(self, judge_name: str = "JudgeUnderTest") -> None:
        self.judge_name = judge_name

    def evaluate(
        self,
        judge_scores: list[float],
        human_scores: list[float] | None = None,
        output_lengths: list[int] | None = None,
        retest_scores: list[float] | None = None,
        pairwise_positions: list[dict[str, Any]] | None = None,
        candidate_evaluations: list[dict[str, Any]] | None = None,
    ) -> JudgeReliabilityReport:
        score_var = variance(judge_scores) if len(judge_scores) > 1 else 0.0

        # Consistency across re-test
        consistency_rate = 1.0
        if retest_scores and len(retest_scores) == len(judge_scores):
            diffs = [
                abs(a - b) for a, b in zip(judge_scores, retest_scores, strict=False)
            ]
            consistency_rate = max(0.0, 1.0 - mean(diffs))

        # Length bias
        length_bias = 0.0
        if output_lengths and len(output_lengths) == len(judge_scores):
            length_bias = calculate_length_bias(judge_scores, output_lengths)

        # Position bias
        pos_bias = 0.0
        if pairwise_positions:
            pos_bias = calculate_position_bias(pairwise_positions)

        # Self preference
        self_pref = 0.0
        if candidate_evaluations:
            self_pref = calculate_self_preference_bias(
                self.judge_name, candidate_evaluations
            )

        # Human agreement & calibration
        human_agreement = 1.0
        brier = 0.0
        kappa = 1.0
        if human_scores and len(human_scores) == len(judge_scores):
            human_bins = [1 if h >= 0.70 else 0 for h in human_scores]
            judge_bins = [1 if j >= 0.70 else 0 for j in judge_scores]
            human_agreement = sum(
                1 for h, j in zip(human_bins, judge_bins, strict=False) if h == j
            ) / len(judge_scores)
            kappa = cohens_kappa(judge_bins, human_bins)
            brier = calculate_brier_score(judge_scores, human_bins)

        return JudgeReliabilityReport(
            judge_name=self.judge_name,
            agreement_score=round(kappa, 4),
            consistency_rate=round(consistency_rate, 4),
            score_variance=round(score_var, 4),
            length_bias_correlation=round(length_bias, 4),
            position_bias_delta=round(pos_bias, 4),
            self_preference_delta=round(self_pref, 4),
            calibration_brier_score=round(brier, 4),
            human_agreement_rate=round(human_agreement, 4),
        )

    def evaluate_judge(
        self,
        judge: Any,
        test_cases: list[Any],
        outputs: list[str],
        human_scores: list[float] | None = None,
    ) -> JudgeReliabilityReport:
        """Run judge on test cases and outputs to produce a JudgeReliabilityReport."""
        judge_scores: list[float] = []
        lengths: list[int] = []
        for tc, out in zip(test_cases, outputs, strict=False):
            prompt = str(getattr(tc, "input", tc))
            reference = (
                str(getattr(tc, "expected_output", None))
                if getattr(tc, "expected_output", None)
                else None
            )
            res = judge.judge(
                prompt=prompt,
                output=str(out),
                reference=reference,
            )
            judge_scores.append(
                res.score if res.score is not None else (1.0 if res.passed else 0.0)
            )
            lengths.append(len(str(out)))

        name = getattr(judge, "name", self.judge_name)
        rep = self.evaluate(
            judge_scores=judge_scores,
            human_scores=human_scores,
            output_lengths=lengths,
        )
        return JudgeReliabilityReport(
            judge_name=name,
            agreement_score=rep.agreement_score,
            consistency_rate=rep.consistency_rate,
            score_variance=rep.score_variance,
            length_bias_correlation=rep.length_bias_correlation,
            position_bias_delta=rep.position_bias_delta,
            self_preference_delta=rep.self_preference_delta,
            calibration_brier_score=rep.calibration_brier_score,
            human_agreement_rate=rep.human_agreement_rate,
            metadata=rep.metadata,
        )
