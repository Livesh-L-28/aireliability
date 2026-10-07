"""Automated AI Test Generation (Phase 36) package."""

from __future__ import annotations

from aireliability.generation.deduplication import TestDeduplicator
from aireliability.generation.engine import TestGenerationEngine
from aireliability.generation.fingerprint import (
    compute_fingerprint,
    compute_token_similarity,
)
from aireliability.generation.integrations import (
    GraphIntegrationBridge,
    ObservabilityIntegrationBridge,
)
from aireliability.generation.models import (
    GeneratedTest,
    GenerationSourceType,
    GenerationStrategy,
    TestGenerationConfig,
    TestGenerationRequest,
    TestGenerationResult,
    TestGenerationStatus,
    TestPriority,
    TestProvenance,
    TestQualityScore,
    TestRiskLevel,
    TestType,
)
from aireliability.generation.promotion import TestPromotionManager
from aireliability.generation.provider import (
    DeterministicFallbackProvider,
    SafeProviderWrapper,
    TestGenerationProvider,
)
from aireliability.generation.registry import GenerationRegistry, get_default_registry
from aireliability.generation.scoring import TestQualityScorer
from aireliability.generation.serialization import (
    export_junit_xml,
    export_markdown_report,
    export_tests_csv,
    export_tests_json,
    export_tests_jsonl,
    import_tests_json,
    import_tests_jsonl,
    test_from_dict,
    test_to_dict,
)
from aireliability.generation.strategies import (
    AdversarialTestGenerator,
    AgentTestGenerator,
    BaseTestGenerator,
    ConsistencyTestGenerator,
    EdgeCaseGenerator,
    FailureTestGenerator,
    GraphTestGenerator,
    IncidentTestGenerator,
    MutationGenerator,
    PatternTestGenerator,
    RAGTestGenerator,
    RegressionTestGenerator,
    RobustnessTestGenerator,
    SafetyTestGenerator,
    TraceTestGenerator,
)
from aireliability.generation.validators import TestValidator

__all__ = [
    # Core Orchestration
    "TestGenerationEngine",
    "TestGenerationRequest",
    "TestGenerationResult",
    "TestGenerationConfig",
    "GenerationRegistry",
    "get_default_registry",
    # Data Models
    "GeneratedTest",
    "GenerationStrategy",
    "GenerationSourceType",
    "TestGenerationStatus",
    "TestType",
    "TestRiskLevel",
    "TestPriority",
    "TestProvenance",
    "TestQualityScore",
    # Pipeline Components
    "TestValidator",
    "TestDeduplicator",
    "TestQualityScorer",
    "TestPromotionManager",
    "compute_fingerprint",
    "compute_token_similarity",
    # Providers
    "TestGenerationProvider",
    "DeterministicFallbackProvider",
    "SafeProviderWrapper",
    # Bridges
    "GraphIntegrationBridge",
    "ObservabilityIntegrationBridge",
    # Serialization
    "test_to_dict",
    "test_from_dict",
    "export_tests_json",
    "import_tests_json",
    "export_tests_jsonl",
    "import_tests_jsonl",
    "export_tests_csv",
    "export_markdown_report",
    "export_junit_xml",
    # Generators
    "BaseTestGenerator",
    "FailureTestGenerator",
    "RegressionTestGenerator",
    "GraphTestGenerator",
    "PatternTestGenerator",
    "IncidentTestGenerator",
    "TraceTestGenerator",
    "EdgeCaseGenerator",
    "MutationGenerator",
    "AdversarialTestGenerator",
    "SafetyTestGenerator",
    "RAGTestGenerator",
    "AgentTestGenerator",
    "RobustnessTestGenerator",
    "ConsistencyTestGenerator",
]
