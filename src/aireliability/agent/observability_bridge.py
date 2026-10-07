"""Observability Bridge for Phase 40 Advanced Agent Reliability.

Registers and increments Prometheus counters, gauges, and distributed trace spans
for monitoring agent trajectories in development and production environments.
"""

from __future__ import annotations

import logging

from aireliability.agent.models import AgentRun, AgentStage, GoalStatus
from aireliability.observability.manager import ObservabilityManager

logger = logging.getLogger(__name__)


class AgentObservabilityBridge:
    """Emits production observability metrics and trace spans for agent executions."""

    def __init__(self, manager: ObservabilityManager | None = None) -> None:
        self.manager = manager or ObservabilityManager()
        self._init_metrics()

    def _init_metrics(self) -> None:
        """Initialize standard Agent observability counters and gauges."""
        metrics = self.manager.metrics
        self.c_runs = metrics.register_counter(
            "agent_runs_total", "Total agent runs evaluated"
        )
        self.c_failures = metrics.register_counter(
            "agent_failures_total", "Total diagnosed agent failures"
        )
        self.c_goal_success = metrics.register_counter(
            "agent_goal_success_total", "Total successfully completed goals"
        )
        self.c_tool_calls = metrics.register_counter(
            "agent_tool_calls_total", "Total external tool invocations"
        )
        self.c_tool_failures = metrics.register_counter(
            "agent_tool_failures_total", "Total failed tool executions"
        )
        self.c_tool_selection_failures = metrics.register_counter(
            "agent_tool_selection_failures_total", "Tool selection defect count"
        )
        self.c_argument_failures = metrics.register_counter(
            "agent_argument_failures_total", "Invalid argument count"
        )
        self.c_loops = metrics.register_counter(
            "agent_loop_events_total", "Trajectory loop events"
        )
        self.c_runaway = metrics.register_counter(
            "agent_runaway_events_total", "Runaway budget exceed events"
        )
        self.c_replan = metrics.register_counter(
            "agent_replan_total", "Replanning attempts count"
        )
        self.c_goal_drift = metrics.register_counter(
            "agent_goal_drift_total", "Goal drift event count"
        )
        self.c_memory_fails = metrics.register_counter(
            "agent_memory_failures_total", "Memory operation failures"
        )
        self.c_handoff_fails = metrics.register_counter(
            "agent_handoff_failures_total", "Multi-agent handoff defects"
        )
        self.c_safety_fails = metrics.register_counter(
            "agent_safety_failures_total", "Safety policy failures"
        )
        self.c_security_fails = metrics.register_counter(
            "agent_security_failures_total", "Security injection and breach events"
        )

        self.g_reliability_score = metrics.register_gauge(
            "agent_reliability_score", "Most recent composite agent score"
        )
        self.g_latency = metrics.register_gauge(
            "agent_latency_seconds", "Trajectory latency in seconds"
        )
        self.g_cost = metrics.register_gauge(
            "agent_cost_total", "Cumulative trajectory cost in USD"
        )

    def record_run(self, run: AgentRun) -> None:
        """Record telemetry and metrics for an evaluated AgentRun."""
        self.c_runs.increment()

        if run.goal_verification.overall_status == GoalStatus.COMPLETED:
            self.c_goal_success.increment()

        # Record tools and failures
        for step in run.trajectory.steps:
            if step.tool_call is not None:
                self.c_tool_calls.increment()
            if step.tool_result is not None and not step.tool_result.success:
                self.c_tool_failures.increment()

        for f in run.failures:
            self.c_failures.increment()
            st = f.stage
            if st == AgentStage.TOOL_SELECTION:
                self.c_tool_selection_failures.increment()
            elif st == AgentStage.TOOL_ARGUMENTS:
                self.c_argument_failures.increment()
            elif st == AgentStage.LOOP:
                self.c_loops.increment()
            elif st == AgentStage.RUNAWAY:
                self.c_runaway.increment()
            elif st == AgentStage.REPLANNING:
                self.c_replan.increment()
            elif st == AgentStage.MEMORY:
                self.c_memory_fails.increment()
            elif st == AgentStage.MULTI_AGENT:
                self.c_handoff_fails.increment()
            elif st == AgentStage.SECURITY:
                self.c_security_fails.increment()

            if "drift" in f.category.value:
                self.c_goal_drift.increment()

        # Update gauges
        self.g_reliability_score.set(run.reliability_score.overall_score)
        self.g_latency.set(run.trajectory.total_latency_seconds)
        self.g_cost.set(run.trajectory.total_cost)
