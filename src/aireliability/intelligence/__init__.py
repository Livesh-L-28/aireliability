"""Phase 34: AI Reliability Intelligence package.

Transforms raw evaluation, regression, and failure reports into actionable
intelligence: failure normalization, fingerprinting, clustering, longitudinal
pattern detection, cross-run correlation, risk impact assessment, historical trends,
explainable answers to 10 core questions, and evidence-backed remediation recommendations.
"""

from __future__ import annotations

from aireliability.intelligence.aggregation import (
    IntelligenceTelemetry,
    aggregate_summary,
)
from aireliability.intelligence.clustering import FailureClusterer
from aireliability.intelligence.confidence import ConfidenceEngine
from aireliability.intelligence.correlation import CorrelationAnalyzer
from aireliability.intelligence.engine import ReliabilityIntelligenceEngine
from aireliability.intelligence.evidence import (
    from_baseline,
    from_evaluation_report,
    from_execution_trace,
    from_failure_report,
    from_incident,
    from_metric_result,
    from_regression_test,
    from_root_cause,
)
from aireliability.intelligence.explain import IntelligenceExplainer
from aireliability.intelligence.impact import ImpactAnalyzer
from aireliability.intelligence.models import (
    ConfidenceLevel,
    CorrelationType,
    CrossRunCorrelation,
    EvidenceReference,
    FailureCluster,
    FailurePattern,
    ImpactAssessment,
    ImpactSeverity,
    IntelligenceAnalysis,
    IntelligenceConfidence,
    IntelligenceSummary,
    NormalizedFailure,
    PatternType,
    RecommendationPriority,
    ReliabilityRecommendation,
    ReliabilityTrend,
    TrendDirection,
)
from aireliability.intelligence.patterns import PatternDetector
from aireliability.intelligence.recommendations import RecommendationEngine
from aireliability.intelligence.registry import (
    IntelligenceRegistry,
    get_default_registry,
)
from aireliability.intelligence.similarity import (
    FailureNormalizer,
    compute_fingerprint,
    failure_similarity,
    token_similarity,
)
from aireliability.intelligence.trends import TrendAnalyzer

__all__ = [
    # Models & Enums
    "ConfidenceLevel",
    "CorrelationType",
    "CrossRunCorrelation",
    "EvidenceReference",
    "FailureCluster",
    "FailurePattern",
    "ImpactAssessment",
    "ImpactSeverity",
    "IntelligenceAnalysis",
    "IntelligenceConfidence",
    "IntelligenceSummary",
    "NormalizedFailure",
    "PatternType",
    "RecommendationPriority",
    "ReliabilityRecommendation",
    "ReliabilityTrend",
    "TrendDirection",
    # Core Engine & Registry
    "ReliabilityIntelligenceEngine",
    "IntelligenceRegistry",
    "get_default_registry",
    # Analyzers & Processors
    "FailureNormalizer",
    "compute_fingerprint",
    "failure_similarity",
    "token_similarity",
    "FailureClusterer",
    "PatternDetector",
    "CorrelationAnalyzer",
    "TrendAnalyzer",
    "ImpactAnalyzer",
    "RecommendationEngine",
    "ConfidenceEngine",
    "IntelligenceExplainer",
    "IntelligenceTelemetry",
    "aggregate_summary",
    # Evidence builders
    "from_evaluation_report",
    "from_failure_report",
    "from_root_cause",
    "from_execution_trace",
    "from_metric_result",
    "from_regression_test",
    "from_incident",
    "from_baseline",
]
