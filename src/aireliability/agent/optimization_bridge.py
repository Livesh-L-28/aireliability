"""Phase 38 Optimization Bridge for Phase 40 Advanced Agent Reliability.

Maps agent hyperparameters to Phase 38 multi-objective Pareto optimization:
Variables:
- max_steps, max_retries, retry_delay_seconds, tool_selection_threshold, timeout_seconds
Objectives:
- Maximize task success / reliability
- Minimize total cost
- Minimize execution latency
- Minimize redundant retries
Hard Constraints:
- Zero safety / security policy violations.
"""

from __future__ import annotations

import logging

from aireliability.optimization.engine import OptimizationEngine
from aireliability.optimization.fingerprint import create_configuration
from aireliability.optimization.models import (
    ComponentCategory,
    ConstraintOperator,
    ObjectiveDirection,
    OptimizationConstraint,
    OptimizationObjective,
    OptimizationProblem,
    OptimizationVariable,
    VariableDomain,
)

logger = logging.getLogger(__name__)


class AgentOptimizationBridge:
    """Connects agent trajectory hyperparameters to Phase 38 multi-objective Pareto optimization."""

    def __init__(self, engine: OptimizationEngine | None = None) -> None:
        self.engine = engine or OptimizationEngine()

    def create_agent_optimization_problem(
        self,
        name: str = "Agent Trajectory Optimization",
        agent_id: str = "default_agent",
        baseline_max_steps: int = 30,
        baseline_max_retries: int = 3,
        baseline_retry_delay: float = 1.0,
        min_reliability: float = 0.85,
        min_safety: float = 0.99,
    ) -> OptimizationProblem:
        """Create a multi-objective Pareto optimization problem targeting agent reliability."""
        base_vals = {
            "max_steps": baseline_max_steps,
            "max_retries": baseline_max_retries,
            "retry_delay": baseline_retry_delay,
            "tool_threshold": 0.75,
        }
        base_cfg = create_configuration(
            base_vals, description="Baseline Agent Trajectory Configuration"
        )

        objectives = [
            OptimizationObjective(
                objective_id="agent_reliability",
                metric="reliability",
                direction=ObjectiveDirection.MAXIMIZE,
                weight=1.0,
            ),
            OptimizationObjective(
                objective_id="execution_cost",
                metric="cost",
                direction=ObjectiveDirection.MINIMIZE,
                weight=0.6,
            ),
            OptimizationObjective(
                objective_id="execution_latency",
                metric="latency",
                direction=ObjectiveDirection.MINIMIZE,
                weight=0.5,
            ),
        ]

        constraints = [
            OptimizationConstraint(
                constraint_id="min_reliability_threshold",
                metric="reliability",
                operator=ConstraintOperator.GE,
                threshold=min_reliability,
                is_hard=True,
            ),
            OptimizationConstraint(
                constraint_id="safety_non_negotiable",
                metric="safety",
                operator=ConstraintOperator.GE,
                threshold=min_safety,
                is_hard=True,
            ),
        ]

        variables = [
            OptimizationVariable(
                variable_id="max_steps",
                name="Maximum Trajectory Steps",
                component=ComponentCategory.AGENT,
                category=ComponentCategory.AGENT,
                domain=VariableDomain.INT,
                min_value=5,
                max_value=100,
                step_size=5,
                default_value=baseline_max_steps,
            ),
            OptimizationVariable(
                variable_id="max_retries",
                name="Maximum Retries Ceiling",
                component=ComponentCategory.AGENT,
                category=ComponentCategory.AGENT,
                domain=VariableDomain.INT,
                min_value=1,
                max_value=10,
                step_size=1,
                default_value=baseline_max_retries,
            ),
            OptimizationVariable(
                variable_id="retry_delay",
                name="Retry Backoff Seconds",
                component=ComponentCategory.AGENT,
                category=ComponentCategory.AGENT,
                domain=VariableDomain.FLOAT,
                min_value=0.1,
                max_value=5.0,
                step_size=0.5,
                default_value=baseline_retry_delay,
            ),
        ]

        return OptimizationProblem(
            name=name,
            description=f"Optimization targeting agent {agent_id}",
            objectives=objectives,
            constraints=constraints,
            variables=variables,
            baseline_config=base_cfg,
            metadata={"target_agent": agent_id},
        )
