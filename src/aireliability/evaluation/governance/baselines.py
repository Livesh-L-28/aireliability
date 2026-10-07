"""Evaluation baselines, historical tracking, comparison, and trend analysis."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from aireliability.evaluation.governance.scoring import (
    ReliabilityScoringEngine,
    UnifiedReliabilityScore,
)
from aireliability.evaluation.models import EvaluationReport


class MetricDelta(BaseModel):
    """Delta calculation between a baseline and current evaluation metric value."""

    model_config = ConfigDict(frozen=True)

    name: str
    baseline_value: float
    current_value: float
    absolute_delta: float
    relative_delta: float
    is_regression: bool
    is_improvement: bool
    statistically_significant: bool | None = None


class EvaluationBaseline(BaseModel):
    """Versioned baseline snapshot across evaluation scores, metrics, latency, and cost."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: f"base_{uuid4().hex[:10]}")
    name: str = "default"
    version: str = "1.0.0"
    dataset_id: str = ""
    dataset_version: str = "1.0.0"
    model_version: str = ""
    prompt_version: str = ""
    evaluator_version: str = "0.2.0"
    configuration: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    composite_score: float = 1.0
    dimensional_scores: dict[str, float] = Field(default_factory=dict)
    metric_values: dict[str, float] = Field(default_factory=dict)
    passed_test_cases: int = 0
    failed_test_cases: int = 0
    total_test_cases: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationComparisonResult(BaseModel):
    """Comparative report between a current evaluation run and a reference baseline."""

    model_config = ConfigDict(frozen=True)

    baseline_name: str
    baseline_version: str
    current_report_id: str
    composite_score_delta: MetricDelta | None = None
    dimensional_deltas: dict[str, MetricDelta] = Field(default_factory=dict)
    metric_deltas: dict[str, MetricDelta] = Field(default_factory=dict)
    regressions: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    has_regressions: bool = False
    summary: str = ""


class EvaluationBaselineManager:
    """Manages creation, serialization, comparison, and storage of versioned baselines."""

    def __init__(self, baselines_dir: Path | str | None = None) -> None:
        self.baselines_dir = Path(baselines_dir) if baselines_dir else None
        self._memory_baselines: dict[str, EvaluationBaseline] = {}

    def create_baseline(
        self,
        report: EvaluationReport,
        score: UnifiedReliabilityScore | None = None,
        name: str = "default",
        version: str = "1.0.0",
        dataset_version: str = "1.0.0",
        model_version: str = "",
        prompt_version: str = "",
        configuration: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EvaluationBaseline:
        """Create a versioned baseline from an EvaluationReport and optional score."""
        if score is None:
            scorer = ReliabilityScoringEngine()
            score = scorer.calculate(report)

        dim_scores = {
            (dim.value if hasattr(dim, "value") else str(dim)): ds.score
            for dim, ds in score.dimensional_scores.items()
        }
        metric_vals = {m_name: m.value for m_name, m in report.metrics.items()}

        baseline = EvaluationBaseline(
            name=name,
            version=version,
            dataset_id=report.dataset_id,
            dataset_version=dataset_version,
            model_version=model_version,
            prompt_version=prompt_version,
            configuration=configuration or {},
            composite_score=score.composite_score,
            dimensional_scores=dim_scores,
            metric_values=metric_vals,
            passed_test_cases=report.passed_test_cases,
            failed_test_cases=report.failed_test_cases,
            total_test_cases=report.total_test_cases,
            metadata=metadata or {},
        )

        self._memory_baselines[name] = baseline
        if self.baselines_dir:
            self.save_baseline(baseline)

        return baseline

    def save_baseline(
        self, baseline: EvaluationBaseline, file_path: Path | str | None = None
    ) -> Path:
        """Persist an EvaluationBaseline to disk as JSON."""
        if file_path:
            target = Path(file_path)
        elif self.baselines_dir:
            self.baselines_dir.mkdir(parents=True, exist_ok=True)
            target = self.baselines_dir / f"{baseline.name}_v{baseline.version}.json"
        else:
            target = Path(f"baseline_{baseline.name}.json")

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(baseline.model_dump_json(indent=2), encoding="utf-8")
        return target

    def load_baseline(self, path_or_name: Path | str) -> EvaluationBaseline:
        """Load an EvaluationBaseline from file path or in-memory cache."""
        path = Path(path_or_name)
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            return EvaluationBaseline.model_validate(data)

        # Check in memory
        name = str(path_or_name)
        if name in self._memory_baselines:
            return self._memory_baselines[name]

        # Check directory if configured
        if self.baselines_dir:
            cand = self.baselines_dir / f"{name}.json"
            if cand.is_file():
                return EvaluationBaseline.model_validate_json(
                    cand.read_text(encoding="utf-8")
                )

        raise FileNotFoundError(f"Baseline not found: {path_or_name}")

    def compare(
        self,
        current_report: EvaluationReport,
        baseline: EvaluationBaseline,
        current_score: UnifiedReliabilityScore | None = None,
        degradation_threshold: float = 0.05,
    ) -> EvaluationComparisonResult:
        """Compare a current evaluation report against a baseline snapshot."""
        if current_score is None:
            scorer = ReliabilityScoringEngine()
            current_score = scorer.calculate(current_report)

        # 1. Composite score delta
        score_diff = current_score.composite_score - baseline.composite_score
        rel_diff = (
            score_diff / baseline.composite_score
            if baseline.composite_score > 0
            else 0.0
        )
        comp_delta = MetricDelta(
            name="composite_score",
            baseline_value=baseline.composite_score,
            current_value=current_score.composite_score,
            absolute_delta=round(score_diff, 4),
            relative_delta=round(rel_diff, 4),
            is_regression=score_diff < -degradation_threshold,
            is_improvement=score_diff > degradation_threshold,
        )

        regressions: list[str] = []
        improvements: list[str] = []

        if comp_delta.is_regression:
            regressions.append("composite_score")
        elif comp_delta.is_improvement:
            improvements.append("composite_score")

        # 2. Dimensional score deltas
        dim_deltas: dict[str, MetricDelta] = {}
        for dim, ds in current_score.dimensional_scores.items():
            dim_key = dim.value if hasattr(dim, "value") else str(dim)
            if dim_key in baseline.dimensional_scores:
                base_val = baseline.dimensional_scores[dim_key]
                diff = ds.score - base_val
                rel = diff / base_val if base_val > 0 else 0.0
                is_reg = diff < -degradation_threshold
                is_imp = diff > degradation_threshold
                delta = MetricDelta(
                    name=dim_key,
                    baseline_value=base_val,
                    current_value=ds.score,
                    absolute_delta=round(diff, 4),
                    relative_delta=round(rel, 4),
                    is_regression=is_reg,
                    is_improvement=is_imp,
                )
                dim_deltas[dim_key] = delta
                if is_reg:
                    regressions.append(f"dimension:{dim_key}")
                elif is_imp:
                    improvements.append(f"dimension:{dim_key}")

        # 3. Metric deltas
        metric_deltas: dict[str, MetricDelta] = {}
        for m_name, m_res in current_report.metrics.items():
            if m_name in baseline.metric_values:
                base_val = baseline.metric_values[m_name]
                diff = m_res.value - base_val
                rel = diff / base_val if base_val != 0 else 0.0
                is_reg = diff < -degradation_threshold
                is_imp = diff > degradation_threshold
                m_delta = MetricDelta(
                    name=m_name,
                    baseline_value=base_val,
                    current_value=m_res.value,
                    absolute_delta=round(diff, 4),
                    relative_delta=round(rel, 4),
                    is_regression=is_reg,
                    is_improvement=is_imp,
                )
                metric_deltas[m_name] = m_delta
                if is_reg:
                    regressions.append(f"metric:{m_name}")
                elif is_imp:
                    improvements.append(f"metric:{m_name}")

        has_reg = len(regressions) > 0
        summary = (
            f"Comparison vs {baseline.name} (v{baseline.version}): "
            f"{len(regressions)} regressions, {len(improvements)} improvements. "
            f"Composite delta: {comp_delta.absolute_delta:+.4f}"
        )

        return EvaluationComparisonResult(
            baseline_name=baseline.name,
            baseline_version=baseline.version,
            current_report_id=current_report.report_id,
            composite_score_delta=comp_delta,
            dimensional_deltas=dim_deltas,
            metric_deltas=metric_deltas,
            regressions=regressions,
            improvements=improvements,
            has_regressions=has_reg,
            summary=summary,
        )


class EvaluationHistoryManager:
    """Historical evaluation tracking and trend analysis over successive runs."""

    def __init__(self, history_file: Path | str | None = None) -> None:
        self.history_file = Path(history_file) if history_file else None
        self._history: list[dict[str, Any]] = []
        if self.history_file and self.history_file.is_file():
            self.load()

    def record(
        self,
        report: EvaluationReport,
        score: UnifiedReliabilityScore | None = None,
    ) -> dict[str, Any]:
        """Record an evaluation run in history."""
        if score is None:
            scorer = ReliabilityScoringEngine()
            score = scorer.calculate(report)

        entry = {
            "report_id": report.report_id,
            "target_name": report.target_name,
            "dataset_id": report.dataset_id,
            "timestamp": report.timestamp.isoformat(),
            "composite_score": score.composite_score,
            "veto_triggered": score.veto_triggered,
            "passed_test_cases": report.passed_test_cases,
            "failed_test_cases": report.failed_test_cases,
            "total_test_cases": report.total_test_cases,
            "metrics": {k: v.value for k, v in report.metrics.items()},
        }
        self._history.append(entry)
        if self.history_file:
            self.save()
        return entry

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return history entries up to limit."""
        return self._history[-limit:]

    def compute_trends(self, metric_names: list[str] | None = None) -> dict[str, Any]:
        """Analyze historical trends for composite score and specified metrics."""
        if not self._history:
            return {"runs": 0, "status": "insufficient_data"}

        scores = [h["composite_score"] for h in self._history]
        runs = len(scores)

        # Compute simple linear slope for composite score
        if runs >= 2:
            slope = (scores[-1] - scores[0]) / (runs - 1)
            direction = (
                "improving"
                if slope > 0.01
                else ("degrading" if slope < -0.01 else "stable")
            )
        else:
            slope = 0.0
            direction = "stable"

        trends: dict[str, Any] = {
            "runs": runs,
            "composite_score": {
                "latest": scores[-1],
                "min": min(scores),
                "max": max(scores),
                "mean": round(sum(scores) / runs, 4),
                "slope": round(slope, 4),
                "direction": direction,
            },
            "metrics": {},
        }

        # Analyze individual metrics
        target_metrics = metric_names or []
        if not target_metrics and self._history:
            target_metrics = list(self._history[-1].get("metrics", {}).keys())

        for m in target_metrics:
            vals = [
                h.get("metrics", {}).get(m)
                for h in self._history
                if m in h.get("metrics", {})
            ]
            if vals:
                m_slope = (
                    (vals[-1] - vals[0]) / (len(vals) - 1) if len(vals) >= 2 else 0.0
                )
                m_dir = (
                    "improving"
                    if m_slope > 0.01
                    else ("degrading" if m_slope < -0.01 else "stable")
                )
                trends["metrics"][m] = {
                    "latest": vals[-1],
                    "min": min(vals),
                    "max": max(vals),
                    "mean": round(sum(vals) / len(vals), 4),
                    "slope": round(m_slope, 4),
                    "direction": m_dir,
                }

        return trends

    def save(self, file_path: Path | str | None = None) -> None:
        """Save history to JSON file."""
        target = Path(file_path) if file_path else self.history_file
        if target:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(self._history, indent=2), encoding="utf-8")

    def load(self, file_path: Path | str | None = None) -> None:
        """Load history from JSON file."""
        target = Path(file_path) if file_path else self.history_file
        if target and target.is_file():
            self._history = json.loads(target.read_text(encoding="utf-8"))
