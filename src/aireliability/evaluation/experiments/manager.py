"""Experiment manager for A/B testing and model/prompt comparisons."""

from __future__ import annotations

from aireliability.evaluation.experiments.models import (
    ABComparisonResult,
    VariantConfig,
    _generate_exp_id,
)
from aireliability.evaluation.metrics.statistics import (
    cohens_d,
    mean,
    welchs_t_test,
)


class ExperimentManager:
    """Orchestrates A/B comparisons between models, prompts, retrievers, and pipelines."""

    def __init__(self, alpha: float = 0.05) -> None:
        self.alpha = alpha

    def compare(
        self,
        variant_a: VariantConfig,
        scores_a: dict[str, list[float]],
        variant_b: VariantConfig,
        scores_b: dict[str, list[float]],
        experiment_id: str | None = None,
    ) -> ABComparisonResult:
        """Statistically compare variant A vs variant B across evaluated metrics."""
        all_metrics = sorted(set(scores_a.keys()).union(set(scores_b.keys())))

        deltas: dict[str, float] = {}
        p_values: dict[str, float] = {}
        effect_sizes: dict[str, float] = {}
        significance: dict[str, bool] = {}

        wins_b = 0
        wins_a = 0

        for m in all_metrics:
            vals_a = scores_a.get(m, [])
            vals_b = scores_b.get(m, [])

            mean_a = mean(vals_a)
            mean_b = mean(vals_b)
            delta = round(mean_b - mean_a, 4)
            deltas[m] = delta

            if len(vals_a) >= 2 and len(vals_b) >= 2:
                _, p_val = welchs_t_test(vals_a, vals_b)
                d = cohens_d(vals_b, vals_a)
                is_sig = p_val < self.alpha
            else:
                p_val = 1.0
                d = 0.0
                is_sig = False

            p_values[m] = round(p_val, 4)
            effect_sizes[m] = round(d, 4)
            significance[m] = is_sig

            if delta > 0 and (is_sig or len(vals_a) < 2):
                wins_b += 1
            elif delta < 0 and (is_sig or len(vals_a) < 2):
                wins_a += 1

        overall_winner = None
        if wins_b > wins_a:
            overall_winner = variant_b.name
        elif wins_a > wins_b:
            overall_winner = variant_a.name

        summary = (
            f"Comparison {variant_a.name} vs {variant_b.name}: "
            f"Winner is {overall_winner or 'TIE'} (B won {wins_b} metrics, A won {wins_a} metrics)."
        )

        return ABComparisonResult(
            experiment_id=experiment_id or _generate_exp_id(),
            variant_a=variant_a,
            variant_b=variant_b,
            metric_deltas=deltas,
            p_values=p_values,
            effect_sizes=effect_sizes,
            statistically_significant=significance,
            overall_winner=overall_winner,
            summary=summary,
        )
