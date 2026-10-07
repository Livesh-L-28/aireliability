# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.4.0] - 2026-10-07

### Added
- **Phase 41: AI Safety Validation (`aireliability.safety`)**
  - Defensive, sandboxed, deterministic-first automated safety evaluation and campaign runner.
  - Multi-category boundaries: prompt injection, boundary override, tool-use boundary, memory manipulation, multi-agent coordination, privacy & data leakage, and retrieved document trust.
  - Deterministic mutation engine: Unicode homoglyphs, zero-width spaces, token splitting, Base64/rot13/URL encodings, and framing prefixes.
  - Non-compensatory safety scoring: Hard veto constraint capping composite reliability at $\le 0.30$ upon critical safety violations.
  - Seamless bidirectional bridges to Failure Intelligence (Phase 34), Knowledge Graph (Phase 35), Test Generation (Phase 36), and Self-Healing AI (Phase 37).
  - CLI `airel safety` with 20 subcommands (`evaluate`, `campaign`, `scan`, `test`, `privacy`, `authorization`, `tools`, `rag`, `agent`, `memory`, `report`, `inspect`, `baseline`, `coverage`, `diagnose`, `regression`, `generate`, `mutate`, `tests`, `heal`).
- **Phase 42: Reliability Prediction (`aireliability.prediction`)**
  - Statistical & ML forecasting models: Exponential smoothing, linear trend regression, rolling mean / volatility, and Weibull/hazard estimation for time-to-failure.
  - Multi-horizon forecasting: `NEXT_EXECUTION`, `SHORT_TERM`, `MEDIUM_TERM`, `LONG_TERM`.
  - Feature extraction engine computing 19 predictive signals across reliability, failure trends, agent trajectory deviations, RAG grounding, and latency percentiles.
  - Dual-layer confidence engine incorporating sample size, signal volatility, and historical forecast accuracy.
  - Prediction accuracy evaluation via Mean Absolute Error (MAE) and Brier calibration score.
  - CLI `airel predict` with 4 subcommands (`forecast`, `features`, `evaluate`, `report`).
- **Phase 43: Reliability Intelligence Dashboard (`aireliability.dashboard`)**
  - Unified system-wide observability aggregation across all reliability dimensions (Phases 1–46).
  - 21 specialized intelligence panels across Reliability, Safety, Security, Agent, RAG, Regression, Prediction, Optimization, Self-Healing, Graph, Cost, Latency, and Throughput.
  - System health calculator with weighted composite score, degradation thresholds, and safety veto enforcement.
  - Multi-format exporters: JSON, Markdown, and CSV with cryptographic snapshot fingerprinting.
  - CLI `airel dashboard` with subcommands (`overview`, `export`, `snapshot`, `panels`).
- **Phase 44: Reliability Policy Engine (`aireliability.policy`)**
  - Declarative policy rule evaluation engine with strict priority order: `SECURITY > SAFETY > TENANT_ISOLATION > AUTHORIZATION > COMPLIANCE > RELIABILITY > PERFORMANCE > COST`.
  - Hard non-compensatory constraints guaranteeing immediate `BLOCK` on critical security, safety, or isolation violations.
  - Rich condition operators (`EQ`, `NEQ`, `LT`, `LTE`, `GT`, `GTE`, `IN`, `CONTAINS`, `REGEX_MATCH`).
  - Auditing, explanation trees, version tracking, and rollback capabilities.
  - CLI `airel policy` with 9 subcommands (`list`, `evaluate`, `explain`, `validate`, `enforce`, `simulate`, `compare`, `version`, `rollback`).
- **Phase 45: Enterprise Multi-Tenancy (`aireliability.tenancy`)**
  - Context isolation via Python `contextvars` for thread-safe asynchronous execution across concurrent tenants.
  - Role-Based Access Control (RBAC) with granular permissions and standard roles (`ADMIN`, `OPERATOR`, `DEVELOPER`, `AUDITOR`, `VIEWER`).
  - Resource isolation manager preventing cross-tenant data traversal with real-time audit event logging.
  - Usage tracker with quota enforcement for concurrent jobs, tokens, request rates, and workers.
  - CLI `airel tenant` with 5 subcommands (`list`, `get`, `quotas`, `usage`, `audit`).
- **Phase 46: Reliability API & SDK Platform (`aireliability.api` & `aireliability.sdk`)**
  - High-performance FastAPI application with 24 REST endpoints covering evaluations, safety validation, predictions, dashboards, policies, tenants, quotas, async jobs, and webhooks.
  - Multi-method authentication: API Key (`X-API-Key`), Bearer Token (`Authorization`), and Service Account headers.
  - Asynchronous background job manager with state transitions and webhook delivery featuring HMAC-SHA256 signature verification.
  - Typed Python SDK: Synchronous `Client` and asynchronous `AsyncClient` supporting context managers and complete resource operations.
  - Comprehensive custom error hierarchy (`APIError`, `ValidationError`, `AuthenticationError`, `AuthorizationError`, `NotFoundError`, `ConflictError`, `RateLimitError`, `PolicyBlockedError`, `TenantIsolationError`, `ServerError`).
  - CLI `airel api` with subcommands (`health`, `routes`, `serve`).
- **Security Hardening & Production Audit**
  - Completed comprehensive security audit with zero critical vulnerabilities or hardcoded secrets.
  - Added dedicated security test suite (`tests/security/`) covering API key hashing, authentication bypass defense, RBAC boundary enforcement, knowledge graph traversal containment, and cross-tenant isolation.
  - Sanitized CLI error formatting and SDK exception logging to prevent credentials or sensitive tokens from appearing in console traces or log streams.
- **Real-World Demo System (`examples/aireliability_demo/`)**
  - Production-style end-to-end multi-tenant enterprise simulation implementing a 17-step autonomous reliability lifecycle.
  - 27 automated demo tests covering Deterministic LLM, RAG chunking, Agent loop/runaway handling, Safety hard vetoes, Policy enforcement, and REST API/SDK clients.
  - Verified 100% offline, deterministic execution requiring 0 cloud credentials and 0 GPU dependencies.
- **Production Performance & Benchmark Suite (`benchmarks/`)**
  - Calibrated benchmark suite measuring 137 individual operations across memory profiling, cold-start latency, multi-threading concurrency, and subsystem execution.
  - Verified sub-millisecond execution across evaluation algorithms, RAG scoring, agent loop detection, safety gating, policy resolution, and multi-tenancy RBAC checks.
  - Established persistent performance baseline (`benchmarks/results/baseline.json`) and automated regression comparator (`benchmarks/compare.py`) confirming 0 performance regressions.


## [0.9.0] - 2026-10-06

### Added
- **Phase 40: Advanced Agent Reliability Engine (`aireliability.agent`)**
  - **Full 15-Stage Agent Lifecycle**: Production-grade evaluation, diagnosis, testing, monitoring, self-healing, and Pareto optimization for autonomous AI agents and multi-agent teams.
  - **Trajectory-First Evaluation**: Evaluates agents as structured temporal trajectories rather than simple input-output pairs; prevents successful final answers from masking tool failures, invalid parameters, redundant loops, or unsafe operations.
  - **Task & Decomposition Analysis**: Deterministically assesses task understanding, constraint extraction, ambiguity, subtask decomposition completeness, and dependency graphs (detecting circular or violated dependencies).
  - **Plan vs Execution Analysis**: Compares intended plans with actual execution trajectories, classifying deviations into `EXPECTED_ADAPTATION`, `BENIGN_DEVIATION`, `RISKY_DEVIATION`, and `FAILURE`.
  - **Tool & Argument Reliability**: Validates tool selection against benchmark requirements (reporting `UNKNOWN` without fabrication when ground truth is absent), validates parameter types and schemas, classifies execution errors (timeouts, rate limits, infrastructure faults), and flags unnecessary high-risk tool usage.
  - **Observation & Security Auditing**: Verifies faithful interpretation of external tool results; treats all tool outputs as untrusted inputs, detecting tool-output prompt injections, instruction overrides, and credential leaks.
  - **State & Memory Consistency**: Tracks state transitions across before/after boundaries and audits memory events (read/write/update/delete) for staleness, contradictions, and misses.
  - **Loop, Runaway & Retry Analysis**: Hash-based $O(N)$ loop detection distinguishing finite retries from runaway loops; runaway guardrails (steps, tool calls, costs, runtime); and retry efficacy metrics.
  - **Multi-Agent Coordination & Handoffs**: Evaluates cooperating agents, validating task handoffs, message completeness, role adherence, duplicate work, and inter-agent conflict.
  - **Independent Goal Verification**: Verifies completion criteria independently from final response text (`COMPLETED`, `PARTIALLY_COMPLETED`, `FAILED`, `BLOCKED`, `UNKNOWN`).
  - **Hard Non-Compensatory Safety/Security Vetoes**: Capping composite reliability scores at $\le 0.30$ upon any critical security or safety violation.
  - **Integration Bridges with Phases 34–39**:
    - **Phase 34 (Failure Intelligence)**: Failure clustering, correlation analysis, and automated agent remediation recommendations.
    - **Phase 35 (Knowledge Graph)**: Graph synchronization of runs, steps, tools, observations, and failures with bidirectional provenance traversal.
    - **Phase 36 (Automated Test Generation)**: Test synthesis translating trajectory failures into reproducible regression suites.
    - **Phase 37 (Self-Healing AI)**: Remediation proposals for agent prompts, configurations, and tool routing policies passing simulation and approval gates.
    - **Phase 38 (Multi-Objective Optimization)**: Pareto optimization balancing goal success against execution latency and token cost.
    - **Phase 39 (RAG Reliability)**: Cross-subsystem failure attribution distinguishing agent tool selection failures from RAG retrieval failures.
  - **CLI Command Suite (`airel agent`)**: 21 subcommands for end-to-end evaluation, trajectory inspection, loop detection, goal verification, and self-healing.

## [0.8.0] - 2026-10-06

### Added
- **Phase 39: Advanced RAG Reliability Engine (`aireliability.rag`)**
  - **Full 11-Stage RAG Lifecycle**: Production-grade evaluation, diagnosis, testing, monitoring, and self-healing across User Query, Query Analysis, Retrieval Analysis, Ranking/Reranking, Context Analysis, LLM Generation, Claim Extraction, Evidence Alignment, Citation Validation, Groundedness/Faithfulness Check, and Reliability Verification.
  - **Stage-Level Attribution & Isolation**: Prevents high final-answer scores from hiding retrieval failures, and ensures good retrievers are not blamed for generation hallucinations.
  - **Deterministic Query Classification & Quality**:
    - Classifies queries into 11 archetypes (`simple_factual`, `multi_hop`, `ambiguous`, `underspecified`, `conversational`, `entity_heavy`, `temporal`, `comparative`, `multi_document`, `long_context`, `adversarial`).
    - Computes completeness, ambiguity, complexity, and expected retrieval difficulty without requiring external LLMs.
  - **Retrieval & Ranking Evaluation**:
    - Ground-truth metrics (Recall, Precision, Hit@K, MRR, NDCG@K) and heuristic evidence coverage when ground truth is absent (strictly avoids fabricating ground truth).
    - Hybrid lexical (BM25) vs semantic (dense) retrieval contribution breakdown.
    - Buried evidence detection, rank position tracking, and Before vs After reranking delta analysis to detect reranker degradation.
  - **Context Window & Conflict Detection**:
    - Token estimation, context truncation, and Jaccard redundancy scoring.
    - Lost-in-the-middle potential position sensitivity analysis across beginning, middle, and end context sectors.
    - Bounded pairwise factual contradiction detection (`RESOLVED`, `UNRESOLVED`, `TEMPORAL_CONFLICT`, `SOURCE_PRIORITY_CONFLICT`).
  - **Atomic Claim Extraction & Evidence Alignment**:
    - Deterministic sentence/clause segmentation into atomic claims with importance weighting (`CRITICAL`, `STANDARD`, `MINOR`).
    - Fact verification against retrieved chunks across 4 states: `SUPPORTED`, `PARTIALLY_SUPPORTED`, `UNSUPPORTED`, `CONTRADICTED`.
  - **Inline Citation Validation**:
    - Resolves bracketed markers (`[1]`, `[doc_1]`), verifies target chunk existence, validates chunk overlap, and flags missing or dangling citations.
  - **Explainable Grounding & Faithfulness Scoring**:
    - Component-wise grounding score, faithfulness score, and hallucination rate with confidence ratings (`LOW`, `MEDIUM`, `HIGH`).
  - **Knowledge Base Health & Freshness Tracking**:
    - Configurable `max_age_days` document freshness audits and index staleness detection.
    - Knowledge base health report auditing chunk fragmentation, duplication rate, orphaned chunks, and source reliability.
  - **Statistical Drift & Multi-Hop Reasoning**:
    - Tracks query length, retrieval scores, grounding scores, and embedding model version drift.
    - Multi-hop reasoning chain validation detecting broken hops, missing intermediate entities, and unsupported final inferences.
  - **RAG Security & Non-Compensatory Vetoes**:
    - Untrusted document inspection detecting prompt injection overrides, credential leaks, and poisoning keyword stuffing.
    - Non-compensatory critical veto capping composite reliability score at $\le 0.30$ upon security violation or severe contradiction.
  - **Integration with Phases 34–38**:
    - `RAGIntelligenceBridge`: Ingests RAG failures into Phase 34 `FailureClusterer` and `RecommendationEngine`.
    - `RAGGraphBridge`: Maps RAG runs, claims, chunks, and failures into Phase 35 `KnowledgeGraph` and traces provenance chains.
    - `RAGTestBridge`: Synthesizes edge cases, adversarial context, and robustness tests via Phase 36 `TestGenerationEngine`.
    - `RAGHealingBridge`: Translates RAG failures into Phase 37 `RemediationProposal` via `RemediationEngine`.
    - `RAGOptimizationBridge`: Maps RAG metrics to Phase 38 `OptimizationProblem` for Pareto frontier tuning.
  - **Observability & Serialization**:
    - `RAGObservabilityBridge`: Emits Prometheus counters (`rag_runs_total`, `rag_failures_total`, `rag_retrieval_failures_total`, `rag_grounding_failures_total`, `rag_citation_failures_total`, `rag_hallucination_events_total`, `rag_conflicts_total`) and distributed trace spans.
    - `RAGSerializer`: Full round-trip serialization supporting JSON, JSON Lines, CSV, and Markdown audit reports.
  - **CLI Commands**: `airel rag` (`evaluate`, `analyze`, `retrieve`, `grounding`, `citations`, `claims`, `freshness`, `drift`, `knowledge`, `conflicts`, `failures`, `provenance`, `regression`, `monitor`, `report`, `inspect`).

## [0.7.0] - 2026-10-06

### Added
- **Phase 38: AI Reliability Optimization (`aireliability.optimization`)**
  - **Multi-Objective Reliability Optimization Architecture**: Production-grade search and Pareto analysis discovering optimal trade-offs across reliability, quality, groundedness, faithfulness, safety, security, latency, cost, throughput, and resource utilization without bypassing safety controls.
  - **Six Deterministic Search Strategies**:
    - `GridSearchStrategy`: Bounded Cartesian product exploration across discretized parameter dimensions.
    - `RandomSearchStrategy`: Seeded pseudo-random sampling ensuring 100% deterministic reproducibility.
    - `LocalSearchStrategy`: Neighborhood perturbation exploration stepping along adjacent parameter boundaries.
    - `HillClimbingStrategy`: Iterative gradient ascent/descent stepping towards non-dominated parameter improvements.
    - `BayesianOptimizationStrategy`: Lightweight provider-independent surrogate acquisition function balancing exploitation and exploration without external ML dependencies.
    - `EvolutionarySearchStrategy`: Bounded genetic search with tournament selection, uniform crossover, parameter mutation, and elite preservation.
  - **Multi-Objective Pareto Dominance & Frontier Analysis**:
    - Strict dominance verification ($A \succ B$) supporting `MAXIMIZE`, `MINIMIZE`, and `TARGET` directions.
    - Automatic min-max objective normalization and NSGA-II crowding distance diversity ranking.
    - Hard constraint pre-filtering: candidates violating safety, security, or regression thresholds are vetoed and can NEVER become Pareto-optimal.
    - Explainable `NO_FEASIBLE_CONFIGURATION` handling when all candidates fail non-negotiable gates.
  - **Configuration Fingerprinting & Security Registry**:
    - Deterministic SHA-256 fingerprinting ignoring volatile timestamps, run IDs, and execution metadata.
    - Explicit variable registry guarding `MODEL`, `GENERATION`, `RETRIEVAL`, `RAG`, `PROMPT`, `TOOL`, `AGENT`, and `INFRASTRUCTURE` parameters.
    - Strict security validation blocking unregistered keys, out-of-range parameters, and command injection attacks.
  - **Evaluation Loop & Multi-Tier Caching**:
    - Candidate evaluation with repeated sampling computing mean, median, variance, standard deviation, and statistical confidence.
    - Fine-grained baseline delta reporting (absolute, relative, and percentage changes).
    - Result caching keyed by configuration fingerprint, dataset ID, and model version.
  - **Reliability Quality Gates & Policy Selector**:
    - `OptimizationGateChecker` enforcing hard safety ($\ge 0.95$), security ($\ge 0.95$), and zero critical regression gates.
    - `OptimizationSelector` executing policy-driven selection (`balanced_score`, `highest_quality`, `lowest_cost`, `lowest_latency`, `weighted_preference`) with mandatory safety tie-breaking hierarchy.
  - **Phase 36 & Phase 37 Integration Bridges**:
    - `OptimizationTestBridge`: Synthesizes targeted validation tests via Phase 36 `TestGenerationEngine`.
    - `OptimizationDeploymentBridge`: Transforms selected candidate into Phase 37 `RemediationProposal`, routing deployment through `HealingPolicy`, `RolloutController` (`DIRECT`, `SHADOW`, `CANARY`), `RemediationVerifier`, and `PromotionManager`/`RollbackManager`.
  - **Knowledge Graph & Observability Bridges**:
    - `OptimizationGraphBridge`: Synchronizes runs, candidates, metrics, and Pareto frontiers into Phase 35 `KnowledgeGraph` and queries historical experiments for warm-starting.
    - `OptimizationObservabilityBridge`: Emits standard counters, histograms, and traces to `ObservabilityManager`.
  - **Multi-Format Serialization**:
    - `OptimizationSerializer`: Round-trip serialization for JSON, JSON Lines, CSV, and Markdown audit reports.
  - **CLI Optimization Commands**: `airel optimize` (`plan`, `run`, `evaluate`, `compare`, `pareto`, `history`, `inspect`, `select`, `validate`, `deploy`, `rollback`, `status`, `budget`).

## [0.6.0] - 2026-10-06

### Added
- **Phase 37: Self-Healing AI Reliability Engine (`aireliability.remediation`)**
  - **Closed-Loop Self-Healing Architecture**: Production-grade automated remediation transforming failure evidence into concrete repairs, generating Phase 36 verification tests, running sandbox simulation, evaluating safety gates, enforcing organizational healing policies, managing approvals, executing Direct/Shadow/Canary rollouts, monitoring live telemetry, and safely promoting or rolling back.
  - **Six Specialized Repair Domain Generators**:
    - `PromptRepairer`: Repairs formatting constraints (strict JSON enforcement), factuality/hallucination refusals, and instruction compliance.
    - `RetrievalRepairer`: RAG configuration tuning for recall expansion (increasing `top_k`), noise filtration (tightening similarity thresholds, neural reranking), and hybrid dense-sparse search.
    - `ToolRepairer`: Fixes parameter schemas, default fallbacks, timeout extensions, exponential retry policies, and safe fallback tools.
    - `AgentRepairer`: Guards against trajectory loops, step recursion, cycle limits, and recovery replanning.
    - `ConfigRepairer`: Model inference hyperparameter tuning (temperature reduction for determinism, `max_tokens` expansion to prevent truncation, timeout adjustments).
    - `SafetyRepairer`: Guards against secret/credential/PII exposure with regex redaction rules, and enables prompt injection defense barriers.
  - **Phase 36 Test Generation Integration**: `RemediationTestBridge` synthesizes regression, edge-case, and robustness validation suites directly against proposed repair patches.
  - **Isolated Simulation Sandbox**: `RemediationSimulator` performs dry-run sandbox execution against generated and golden baseline test suites.
  - **Quality & Release Gates**: `RemediationGateChecker` enforcing zero regressions, minimum recovery rates, zero safety violations, and bounded execution latency overhead.
  - **Autonomous Healing Policy & Governance**: `HealingPolicy` enforcing risk tiers (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), rollout rate limits, and approval requirements.
  - **HMAC-Tokenized Approval Workflow**: `ApprovalManager` for cryptographic human-in-the-loop sign-off and audit tracking.
  - **Progressive Rollout Controller**: `RolloutController` supporting `DIRECT`, `SHADOW` (mirrored traffic), and `CANARY` (stateless consistent hashing traffic routing).
  - **Live Verification & Automated Rollback**: `RemediationVerifier` monitoring error rates and telemetry deltas; `RollbackManager` restoring previous configurations automatically upon degradation.
  - **Permanent Baseline Promotion**: `PromotionManager` promoting verified canary patches to 100% active production baselines.
  - **Knowledge Graph & Observability Synchronization**: `RemediationGraphBridge` creating `RECOMMENDATION` nodes with `REMEDIES`, `AFFECTS`, and `SUPPORTED_BY` relationships; `RemediationObservabilityBridge` recording event metrics.
  - **Multi-Format Serialization**: `RemediationSerializer` supporting JSON, JSON Lines, CSV, and Markdown audit reports.
  - **CLI Self-Healing Commands**: `airel heal` (`plan`, `simulate`, `approve`, `apply`, `verify`, `promote`, `rollback`, `status`).

## [0.5.0] - 2026-10-06

### Added
- **Phase 36: Automated AI Test Generation**
  - **Deterministic-First Test Generation Architecture**: Full reliability pipeline transforming evidence into strongly typed `GeneratedTest` cases and safely promoting them to `EvaluationDataset` and `RegressionTest` suites.
  - **Comprehensive Generation Models**: `GeneratedTest`, `TestProvenance`, `TestQualityScore`, `TestGenerationConfig`, `TestGenerationRequest`, and `TestGenerationResult` with validated lifecycle states (`CANDIDATE`, `VALIDATING`, `VALIDATED`, `NEEDS_REVIEW`, `REJECTED`, `PROMOTED`).
  - **14 Test Generation Strategies**:
    - `FailureTestGenerator`: Failure-driven test synthesis from `FailureReport` and `EvaluationReport` guarding against output, tool, retrieval, prompt, and execution regressions.
    - `RegressionTestGenerator`: Regression-driven test generation from `RegressionTest` and `EvaluationComparisonResult` baseline degradations.
    - `GraphTestGenerator`: KnowledgeGraph-driven path traversal generating tests protecting unhedged and failing components.
    - `PatternTestGenerator`: Intelligence-driven generation targeting Phase 34 `FailurePattern`, `FailureCluster`, and remediation recommendations.
    - `IncidentTestGenerator`: Converts operational `IncidentRecord` entries into permanent regression guards with severity mapping.
    - `TraceTestGenerator`: Production-trace-driven synthesis converting sampled `ExecutionTrace` steps into replay tests with mandatory `SanitizationPolicy` credential redaction.
    - `EdgeCaseGenerator`: Bounded deterministic edge case synthesis for empty, null, unicode, whitespace, and extreme length inputs.
    - `MutationGenerator`: Controlled, bounded mutation testing targeting prompts, contexts, retrieval results, and tool definitions.
    - `AdversarialTestGenerator`: Offline adversarial probes for prompt injection overrides, instruction conflicts, and malformed outputs.
    - `SafetyTestGenerator`: Security and safety test generation probing secret leakage, credential exfiltration, PII exposure, and unauthorized tool calls.
    - `RAGTestGenerator`: RAG-focused test generation for retrieval grounding, chunk contradictions, distractor ranking noise, and citation accuracy.
    - `AgentTestGenerator`: Agent trajectory testing for tool selection, call ordering, recursion bounds, and error recovery.
    - `RobustnessTestGenerator`: Robustness testing for model invariance across casing, punctuation, and syntactic paraphrasing.
    - `ConsistencyTestGenerator`: Semantic test cluster generation verifying bounded variance across equivalent queries.
  - **Deterministic Content Fingerprinting & Deduplication**: Canonical payload normalization and SHA-256 fingerprinting (`compute_fingerprint`) with token Jaccard similarity near-duplicate pruning (`TestDeduplicator`).
  - **Explainable Multi-Dimensional Quality Scoring**: `TestQualityScorer` evaluating provenance strength, failure relevance, coverage, correctness confidence, reproducibility, novelty, and risk.
  - **Safe Golden Dataset & Regression Suite Promotion**: `TestPromotionManager` enforcing quality gates and authorization policies before admitting candidates into golden datasets or regression suites.
  - **Provider-Independent AI Generation Abstraction**: `TestGenerationProvider` interface with 100% offline `DeterministicFallbackProvider` and exception-safe `SafeProviderWrapper`.
  - **Knowledge Graph & Observability Synchronization**: `GraphIntegrationBridge` creating `TEST_CASE` nodes and provenance edges (`GENERATED`, `TRIGGERED`, `SUPPORTED_BY`, `DERIVED_FROM`, `BELONGS_TO`), and `ObservabilityIntegrationBridge` emitting telemetry.
  - **Round-Trip Serialization**: Formatters for JSON, JSON Lines, CSV, Markdown reports, and JUnit XML.
  - **CLI Generation Commands**: `airel generate` (`tests`, `regression`, `golden`, `adversarial`, `from-failure`, `from-trace`, `from-graph`, `mutations`) and `airel test-generation` (`inspect`, `validate`, `promote`).

## [0.4.0] - 2026-10-06

### Added
- **Phase 35: AI Reliability Knowledge Graph**
  - **Graph Architecture & Core Container**: Provider-independent, deterministic, in-memory `KnowledgeGraph` abstraction connecting datasets, test cases, executions, traces, models, prompts, tools, retrievers, evaluations, metrics, failures, root causes, regressions, incidents, and Phase 34 intelligence outputs.
  - **Typological Node Models**: `GraphNode` supporting 30 distinct `GraphNodeType` classifications (`DATASET`, `TEST_CASE`, `EXECUTION`, `TRACE`, `TRACE_STEP`, `MODEL`, `PROMPT`, `TOOL`, `RETRIEVER`, `RERANKER`, `EMBEDDING_MODEL`, `EVALUATION`, `METRIC`, `FAILURE`, `ROOT_CAUSE`, `REGRESSION`, `INCIDENT`, `EXPERIMENT`, `BASELINE`, `DEPLOYMENT`, `ENVIRONMENT`, `PRODUCTION_EVENT`, `PATTERN`, `FAILURE_CLUSTER`, `TREND`, `RECOMMENDATION`, etc.) with canonical IDs, versions, confidence ratings, tags, and provenance records.
  - **Typed Edge Models & Strict Causality Separation**: Directed `GraphEdge` with 30 `GraphRelationship` types (`CONTAINS`, `VERSION_OF`, `DERIVED_FROM`, `EXECUTED`, `PRODUCED`, `USED_MODEL`, `USED_PROMPT`, `USED_TOOL`, `USED_RETRIEVER`, `USED_RERANKER`, `USED_EMBEDDING`, `GENERATED`, `EVALUATED`, `MEASURED_BY`, `FAILED`, `HAS_ROOT_CAUSE`, `CAUSED_REGRESSION`, `LINKED_TO`, `TRIGGERED`, `OCCURRED_IN`, `BELONGS_TO`, `PART_OF`, `CORRELATED_WITH`, `AFFECTS`, `RECOMMENDS`, `SUPPORTED_BY`, `PRECEDED`, `FOLLOWED_BY`, `DEPENDS_ON`, `RELATED_TO`). Mandates explicit separation of `CORRELATED_WITH` (`is_causal=False`) from verified causal links (`is_causal=True`).
  - **High-Performance In-Memory Graph Store**: `InMemoryGraphStore` featuring $O(1)$ and $O(\text{degree})$ index structures for node IDs, node types, edge IDs, relationship types, out-edges, in-edges, and edge pairs with cascading deletion and duplicate edge avoidance.
  - **Pluggable Backend Registry**: `GraphStoreRegistry` supporting in-memory storage by default with extensible registration for optional external backends.
  - **Idempotent Graph Construction**: `KnowledgeGraphBuilder` synthesizing graph topologies from `EvaluationReport`, `ExecutionTrace`, `FailureReport`, `RootCause`, `IncidentRecord`, `RegressionTest`, `EvaluationBaseline`, `EvaluationComparisonResult`, `EvaluationDataset`, `ABComparisonResult`, and Phase 34 `IntelligenceAnalysis` without uncontrolled duplicates.
  - **Safe Traversal & Pathfinding Engine**: `GraphTraversal` implementing bounded BFS, DFS, cycle detection (`find_cycles`), shortest pathfinding (`find_path`), all acyclic paths (`find_all_paths`), and induced subgraph extraction with depth limits, node limits, and relationship/type filtering.
  - **High-Level Domain Query API**: `GraphQuery` providing primitive index lookups and high-level domain queries answering the 10 core reliability questions (`find_failures_for_model`, `find_failures_for_prompt`, `find_failures_for_tool`, `find_failures_for_retriever`, `find_regressions_for_dataset`, `find_incidents_for_root_cause`, `find_related_failures`, `find_affected_components`, `find_evidence`, `get_model_impact`, `get_root_cause_history`, `get_failure_history`, `get_execution_dependencies`, `get_incident_context`).
  - **Quantitative Impact Analysis**: `GraphImpactAnalyzer` computing downstream blast radius, affected component distributions, severity distributions, critical safety/security propagation flags, normalized impact scores, and structured `GraphImpactReport`.
  - **Provenance & Lineage Engine**: `ProvenanceTracer` providing node and edge provenance inspection, upstream origin tracing (`trace_origin`), explainable relationship summaries (`explain_relationship`), and multi-hop lineage mapping (`get_lineage`).
  - **Serialization & Structural Graph Diffing**: `GraphSerializer` supporting JSON snapshots, JSON Lines streaming, CSV edge list export, and `diff_graphs` detecting added, removed, and modified nodes and edges across runs.
  - **Security & Secret Sanitization**: Mandatory redaction of API keys, bearer tokens, passwords, private keys, and sensitive payloads during graph node and edge creation via `SanitizationPolicy`.
  - **Observability Instrumentation**: `GraphTelemetry` recording build, query, traversal, and serialization durations, errors, and counter metrics to `ObservabilityManager`.
  - **CLI Knowledge Graph Subcommands**: `airel graph` CLI with 12 subcommands: `build`, `inspect`, `query`, `neighbors`, `path`, `impact`, `failures`, `regressions`, `incidents`, `root-causes`, `export`, and `diff` with `--json` and `--output` options.

## [0.3.0] - 2026-10-06

### Added
- **Phase 34: AI Reliability Intelligence**
  - **Failure Intelligence & Normalization**: Deterministic normalization (`FailureNormalizer`) stripping volatile identifiers, memory pointers, timestamps, numeric counters, and redacting credentials/PII into stable 16-character SHA-256 failure fingerprints (`compute_fingerprint`).
  - **Deterministic Clustering**: `FailureClusterer` with $O(N)$ fingerprint grouping and secondary multi-attribute structural similarity (`failure_similarity`) calculating dominant categories, dominant root causes, and representative failure selections.
  - **Longitudinal Pattern Detection**: `PatternDetector` identifying recurring intra-run patterns, component-specific signatures (`TOOL_SPECIFIC`, `RETRIEVER_SPECIFIC`, `MODEL_SPECIFIC`), newly introduced regressions (`NEW`), resolved failures (`DISAPPEARING`), and historical trajectory shifts (`INCREASING`, `DECREASING`, `PERSISTENT`).
  - **Cross-Run Correlation Engine**: `CorrelationAnalyzer` correlating model version migrations, prompt revisions, and retriever configuration changes with quantitative metric drops and failure clusters while maintaining a strict empirical correlation vs. causation boundary (`is_causal=False`).
  - **Longitudinal Trend Analysis**: `TrendAnalyzer` computing slope (rate of change), relative change, volatility (standard deviation), and directional classification (`INCREASING`, `DECREASING`, `STABLE`, `VOLATILE`, `INSUFFICIENT_DATA`) over historical evaluation series and `EvaluationHistoryManager` runs.
  - **Operational & Risk Impact Assessment**: `ImpactAnalyzer` calculating risk severity (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), treating safety/security breaches as non-negotiable critical impacts, and producing explainable prioritized rankings with safety multipliers.
  - **Deterministic Recommendation Engine**: `RecommendationEngine` executing empirical rule-based policies linking failures, patterns, correlations, and trends to prioritized, evidence-backed remediation actions (release gate blocks, regression test additions, RAG coverage optimizations, tool schema audits).
  - **Evidence & Provenance System**: `EvidenceReference` linking intelligence findings directly to underlying evaluation reports, failure reports, diagnosed root causes, execution traces, baseline snapshots, regression tests, and operational incidents without duplicating payloads.
  - **Confidence Model**: `ConfidenceEngine` factoring evidence count, observation sample size, signal agreement, and data completeness into categorical ratings (`VERY_LOW`, `LOW`, `MEDIUM`, `HIGH`, `VERY_HIGH`) and calibrated scores.
  - **10 Core Questions Explainability**: `IntelligenceExplainer` structuring comprehensive human-readable terminal reports and JSON exports directly answering the 10 fundamental reliability intelligence questions.
  - **Telemetry & Production Integration**: `IntelligenceTelemetry` with tracing spans, metrics counters, and automated critical incident creation via `IncidentManager`.
  - **Pluggable Intelligence Registry**: `IntelligenceRegistry` for decoupled analyzer extension and registration.
  - **Top-Level Orchestrator**: `ReliabilityIntelligenceEngine` coordinating normalization, clustering, patterns, correlation, trends, impact, confidence, recommendations, and aggregated summaries (`IntelligenceSummary`, `IntelligenceAnalysis`).
  - **CLI Intelligence Subcommands**: `airel intelligence` with actions `analyze`, `failures`, `clusters`, `patterns`, `trends`, `impact`, `recommendations`, and `explain`.

## [0.2.0] - 2026-10-06

### Added
- **Phase 31: Evaluation Intelligence Engine**
  - Unified Metric Engine: Classification metrics (Accuracy, Precision, Recall, F1, F-beta, Specificity, Sensitivity, Balanced Accuracy, MCC, Confusion Matrix) and Ranking metrics (Precision@K, Recall@K, Hit@K, MRR, MAP, NDCG@K).
  - Generation Quality: Deterministic checks (JsonValid, RequiredFields, TypeValidation, FormatValidation, CitationPresence, CitationValidation, RegexMatch) and Semantic evaluators (Correctness, Relevance, Completeness, Coherence, Helpfulness, InstructionFollowing).
  - Claims & Hallucination: Atomic claim extraction, evidence matching, 3-state classification (Supported, Unsupported, Contradicted), and hallucination rate calculation.
  - RAG Evaluation: Separate retrieval, reranking, and context metrics (ContextRelevance, ContextPrecision, ContextRecall, Faithfulness) with diagnostic root-cause separation between retrieval and generation failures.
  - Agent & Trajectory Evaluation: TrajectoryEvaluator, ToolUsageEvaluator, AgentEvaluator assessing tool selection, ordering, arguments, looping detection, and task completion.
  - LLM-as-a-Judge: Provider adapters for Mock, OpenAI, Anthropic, Gemini, Ollama, local models, and custom callables with structured JSON schemas and confidence scoring.
  - Judge Reliability: JudgeReliabilityEvaluator measuring repeated consistency, Cohen's Kappa, Fleiss' Kappa, Brier calibration, length bias, and position bias.
  - Dataset Engine: EvaluationDataset model supporting versioning, splits (dev, val, test, regression, production, adversarial), schema validation, comparison, and import/export.
  - Regression Engine: EvaluationRegressionDetector calculating absolute, relative, and statistically significant degradation across all dimensions.
  - Robustness & Consistency: PerturbationGenerator (typo, casing, whitespace, noise, adversarial suffix) and ConsistencyEvaluator measuring output and score variance.
  - Safety, Security & Privacy: Modular evaluators for toxicity, prompt injection, jailbreaks, system prompt leakage, PII leakage, and credential/secret detection.
  - Performance & Cost: Latency distribution metrics (P50, P90, P95, P99), TTFT, throughput, token accounting, and configurable multi-provider pricing models.
  - Experiments & Statistics: ExperimentManager for A/B testing (confidence intervals, Welch's t-test, Mann-Whitney U, Cohen's d effect size) and drift detection (PSI).

- **Phase 32: Evaluation Operations & Governance**
  - ReliabilityScoringEngine: Configurable multidimensional reliability score with non-compensatory critical veto mechanism.
  - ReliabilityGateEngine: Configurable release gates (PASS, FAIL, BLOCK) with granular threshold policies and regression blocking.
  - Versioned Baselines: EvaluationBaseline and EvaluationBaselineManager for tracking versioned references across datasets, models, prompts, scores, latency, and cost.
  - History & Trend Analysis: EvaluationHistoryManager analyzing score slopes, directions, and historical quality drift across runs.
  - Multi-Format Reporting: EvaluationReporter supporting Terminal CLI, JSON, JSONL, CSV, Markdown, PR Comments, JUnit XML, and interactive standalone HTML dashboard with embedded SVG charts.

- **Phase 33: Developer Platform & Production Integration**
  - Evaluation Profiles: Reusable profiles (`rag`, `agent`, `classification`, `generation`, `safety`, `performance`, `cost`, `production`, `full`) in EvaluationProfileRegistry.
  - CLI Platform Extensions: New subcommands `airel evaluate [run|dataset]`, `airel dataset [create|validate|compare|inspect]`, `airel score`, `airel gate`, `airel report`, `airel experiment`, `airel dashboard`, `airel metrics`, `airel judge`, `airel safety`, `airel robustness`, `airel latency`, `airel cost`, and `airel regression [run|diff|list]`.
  - CI/CD & GitHub Actions: Native `.github/workflows/ai-eval.yml`, PR comment synthesis, JUnit XML reporting, and gate exit code enforcement.
  - Production Pipeline: ContinuousReliabilityMonitor for sliding-window live scoring, ProductionSampler, and ProductionRegressionHarvester automatically diagnosing production failures into golden regression datasets with IncidentManager integration.

### Added
- **Phase 1: Foundation & Setup**
  - Package structure, `pyproject.toml` configuration with Hatchling build backend.
  - Python 3.11+ requirement, Pydantic runtime dependency.
  - Development tools (`pytest`, `ruff`).
- **Phase 2: Core Data Models**
  - Implemented immutable Pydantic models: `TestCase`, `TraceStep`, `ExecutionTrace`, `EvaluationResult`, `FailureReport`, `RegressionTest`, and `RunResult`.
  - Added enums: `StepType`, `ExecutionStatus`, and `FailureSeverity`.
- **Phase 3: Core Protocols & Interfaces**
  - Added `runtime_checkable` protocols: `Traceable`, `ExecutionAdapter`, `Evaluator`, and `Expectation`.
- **Phase 4: Deterministic Assertions**
  - Implemented non-LLM, microsecond-level assertions: `ToolCalled`, `ToolNotCalled`, `ToolOrder`, `ToolArguments`, `OutputEquals`, `OutputContains`, `SchemaMatch`, `MaxLatency`, and `MaxCost`.
- **Phase 5: Execution Engine**
  - Implemented `ReliabilityRunner` orchestrating agent invocation, trace capture, evaluator execution, and failure compilation.
- **Phase 6: Failure Taxonomy & Analysis**
  - Implemented `FailureTaxonomy` across 6 categories (`TASK`, `TOOL`, `RETRIEVAL`, `OUTPUT`, `SAFETY`, `PERFORMANCE`).
  - Implemented deterministic `FailureAnalyzer` mapping evaluation outcomes into structured `FailureReports`.
- **Phase 7: Regression Generator & Baseline Management**
  - Implemented `RegressionGenerator` creating reproducible `RegressionTest` cases preserving provenance (`source_failure_id`).
  - Implemented `BaselineManager` with 5-state comparison logic (`PASSING`, `REGRESSION`, `KNOWN_FAILURE`, `FIXED`, `NEW`).
- **Phase 8: SQLite Storage Subsystem**
  - Implemented serverless, transactional `SQLiteStorage` implementing `StorageBackend`.
  - Added index optimization and safe schema initialization.
- **Phase 9: Command-Line Interface (`airel`)**
  - Implemented CLI commands: `airel init`, `airel test`, `airel failures`, `airel regressions`, and `airel compare`.
- **Phase 10: CI/CD Workflows & Packaging**
  - Added GitHub Actions workflow (`.github/workflows/ci.yml`) testing Python 3.11, 3.12, 3.13, Ruff linting, and package builds.
  - Implemented `--ci` strict exit code flag (`airel test --ci`).
  - Added executable CI script `examples/ci_pipeline.sh`.
- **Phase 11: Reproducible Benchmarks**
  - Created reproducible benchmark runner `benchmarks/run_benchmarks.py` and scenario definitions `benchmarks/scenarios.py`.
  - Empirical overhead verification (< 0.04 ms added per agent run; 500k–700k ops/sec assertion throughput).
- **Phase 12 (Documentation & Community Readiness)**
  - Comprehensive `README.md` covering architecture, deterministic vs semantic evaluation, CI/CD, and extension points.
  - Added `docs/architecture.md`, `docs/evaluation_concepts.md`, and `docs/README.md`.
  - Added practical runnable examples: `examples/end_to_end_workflow.py` and `examples/custom_evaluator_and_adapter.py`.
