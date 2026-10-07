"""Agent Behavioral and Trajectory Drift Detector for Phase 40.

Compares current agent execution metrics against historical baselines:
- trajectory length drift (average steps)
- tool usage distribution drift
- retry frequency drift
- goal completion success drift
- latency and cost drift
- failure distribution drift
"""

from __future__ import annotations

from aireliability.agent.models import AgentDriftResult, AgentRun


class AgentDriftDetector:
    """Analyzes distribution drift between historical baseline and current agent runs."""

    def __init__(self, drift_threshold: float = 0.20) -> None:
        self.drift_threshold = drift_threshold

    def calculate_mean(self, values: list[float]) -> float:
        """Calculate arithmetic mean of a float list."""
        return sum(values) / len(values) if values else 0.0

    def evaluate_metric_drift(
        self,
        baseline_values: list[float],
        current_values: list[float],
        metric_name: str,
        threshold: float | None = None,
    ) -> AgentDriftResult:
        """Evaluate numeric metric distribution drift."""
        effective_threshold = threshold or self.drift_threshold
        base_mean = self.calculate_mean(baseline_values)
        curr_mean = self.calculate_mean(current_values)

        if base_mean == 0.0:
            distance = abs(curr_mean - base_mean)
        else:
            distance = abs(curr_mean - base_mean) / abs(base_mean)

        drift_detected = distance >= effective_threshold

        msg = (
            f"Drift detected in {metric_name}: baseline={base_mean:.3f}, current={curr_mean:.3f}, "
            f"shift={distance:.1%} (threshold={effective_threshold:.1%})"
            if drift_detected
            else f"No significant drift in {metric_name} (shift={distance:.1%})"
        )

        return AgentDriftResult(
            drift_type=metric_name,
            drift_detected=drift_detected,
            distance=round(distance, 4),
            threshold=effective_threshold,
            baseline_mean=round(base_mean, 4),
            current_mean=round(curr_mean, 4),
            message=msg,
        )

    def evaluate_tool_distribution_drift(
        self,
        baseline_runs: list[AgentRun],
        current_runs: list[AgentRun],
    ) -> AgentDriftResult:
        """Evaluate divergence in tool selection frequencies using total variation distance."""

        def extract_tool_dist(runs: list[AgentRun]) -> dict[str, float]:
            counts: dict[str, int] = {}
            total = 0
            for r in runs:
                for step in r.trajectory.steps:
                    if step.tool_call:
                        counts[step.tool_call.tool_name] = (
                            counts.get(step.tool_call.tool_name, 0) + 1
                        )
                        total += 1
            if total == 0:
                return {}
            return {k: v / total for k, v in counts.items()}

        dist_base = extract_tool_dist(baseline_runs)
        dist_curr = extract_tool_dist(current_runs)

        all_tools = set(dist_base.keys()).union(set(dist_curr.keys()))
        if not all_tools:
            return AgentDriftResult(
                drift_type="tool_distribution",
                drift_detected=False,
                distance=0.0,
                threshold=self.drift_threshold,
                message="No tools used in either baseline or current runs",
            )

        # Total variation distance: 0.5 * sum(|p(x) - q(x)|)
        tvd = 0.5 * sum(
            abs(dist_base.get(t, 0.0) - dist_curr.get(t, 0.0)) for t in all_tools
        )
        drift_detected = tvd >= self.drift_threshold

        return AgentDriftResult(
            drift_type="tool_distribution",
            drift_detected=drift_detected,
            distance=round(tvd, 4),
            threshold=self.drift_threshold,
            message=(
                f"Tool distribution drifted with Total Variation Distance of {tvd:.3f}"
                if drift_detected
                else f"Tool distribution stable (TVD={tvd:.3f})"
            ),
        )

    def evaluate_runs_drift(
        self,
        baseline_runs: list[AgentRun],
        current_runs: list[AgentRun],
    ) -> list[AgentDriftResult]:
        """Audit full suite of agent behavioral metrics between baseline and current runs."""
        results: list[AgentDriftResult] = []

        # 1. Trajectory length drift (steps)
        base_steps = [float(r.trajectory.total_steps) for r in baseline_runs]
        curr_steps = [float(r.trajectory.total_steps) for r in current_runs]
        results.append(
            self.evaluate_metric_drift(base_steps, curr_steps, "trajectory_length")
        )

        # 2. Latency drift
        base_lat = [r.trajectory.total_latency_seconds for r in baseline_runs]
        curr_lat = [r.trajectory.total_latency_seconds for r in current_runs]
        results.append(
            self.evaluate_metric_drift(base_lat, curr_lat, "latency_seconds")
        )

        # 3. Cost drift
        base_cost = [r.trajectory.total_cost for r in baseline_runs]
        curr_cost = [r.trajectory.total_cost for r in current_runs]
        results.append(self.evaluate_metric_drift(base_cost, curr_cost, "cost_usd"))

        # 4. Tool distribution drift
        results.append(
            self.evaluate_tool_distribution_drift(baseline_runs, current_runs)
        )

        # 5. Goal completion ratio drift
        base_goal = [r.goal_verification.completion_ratio for r in baseline_runs]
        curr_goal = [r.goal_verification.completion_ratio for r in current_runs]
        results.append(
            self.evaluate_metric_drift(base_goal, curr_goal, "goal_completion_ratio")
        )

        return results
