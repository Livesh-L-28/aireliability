"""AI Reliability Optimization Engine (Phase 38)."""

from __future__ import annotations

from aireliability.optimization.deployment_bridge import OptimizationDeploymentBridge
from aireliability.optimization.engine import OptimizationEngine
from aireliability.optimization.evaluator import OptimizationEvaluator
from aireliability.optimization.fingerprint import (
    compute_configuration_fingerprint,
    create_configuration,
)
from aireliability.optimization.gates import OptimizationGateChecker
from aireliability.optimization.generator import CandidateGenerator
from aireliability.optimization.graph_bridge import OptimizationGraphBridge
from aireliability.optimization.models import (
    CandidateStatus,
    ComponentCategory,
    ConstraintOperator,
    ObjectiveDirection,
    OptimizationBudget,
    OptimizationCandidate,
    OptimizationConfiguration,
    OptimizationConstraint,
    OptimizationDecision,
    OptimizationExperiment,
    OptimizationObjective,
    OptimizationPolicy,
    OptimizationProblem,
    OptimizationResult,
    OptimizationVariable,
    ParetoFrontier,
    ParetoPoint,
    SelectionStrategy,
    StoppingReason,
    VariableDomain,
)
from aireliability.optimization.observability_bridge import (
    OptimizationObservabilityBridge,
)
from aireliability.optimization.pareto import (
    calculate_crowding_distance,
    check_dominance,
    find_pareto_frontier,
    normalize_objectives,
)
from aireliability.optimization.selector import OptimizationSelector
from aireliability.optimization.serialization import OptimizationSerializer
from aireliability.optimization.strategies import (
    BaseSearchStrategy,
    BayesianOptimizationStrategy,
    EvolutionarySearchStrategy,
    GridSearchStrategy,
    HillClimbingStrategy,
    LocalSearchStrategy,
    RandomSearchStrategy,
    get_strategy,
)
from aireliability.optimization.test_bridge import OptimizationTestBridge
from aireliability.optimization.variables import (
    STANDARD_VARIABLES,
    VariableRegistry,
    get_default_variable_registry,
)

__all__ = [
    "STANDARD_VARIABLES",
    "BaseSearchStrategy",
    "BayesianOptimizationStrategy",
    "CandidateGenerator",
    "CandidateStatus",
    "ComponentCategory",
    "ConstraintOperator",
    "EvolutionarySearchStrategy",
    "GridSearchStrategy",
    "HillClimbingStrategy",
    "LocalSearchStrategy",
    "ObjectiveDirection",
    "OptimizationBudget",
    "OptimizationCandidate",
    "OptimizationConfiguration",
    "OptimizationConstraint",
    "OptimizationDecision",
    "OptimizationDeploymentBridge",
    "OptimizationEngine",
    "OptimizationEvaluator",
    "OptimizationExperiment",
    "OptimizationGateChecker",
    "OptimizationGraphBridge",
    "OptimizationObjective",
    "OptimizationObservabilityBridge",
    "OptimizationPolicy",
    "OptimizationProblem",
    "OptimizationResult",
    "OptimizationSelector",
    "OptimizationSerializer",
    "OptimizationTestBridge",
    "OptimizationVariable",
    "ParetoFrontier",
    "ParetoPoint",
    "RandomSearchStrategy",
    "SelectionStrategy",
    "StoppingReason",
    "VariableDomain",
    "VariableRegistry",
    "calculate_crowding_distance",
    "check_dominance",
    "compute_configuration_fingerprint",
    "create_configuration",
    "find_pareto_frontier",
    "get_default_variable_registry",
    "get_strategy",
    "normalize_objectives",
]
