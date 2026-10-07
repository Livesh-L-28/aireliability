# Phase 39 Architecture Specification: Advanced RAG Reliability Engine

This document details the system design, stage decomposition, formal models, evaluation metrics, security checks, and cross-phase bridges of the **Advanced RAG Reliability Engine** (`aireliability.rag`) in version `0.8.0`.

---

## 1. Overview & Objective

Retrieval-Augmented Generation (RAG) is prone to complex, compounding failure modes spanning information retrieval, context engineering, and language generation:
- **Retrieval Failures**: Low recall, buried evidence, irrelevant context, stale documents.
- **Context Failures**: Context truncation, lost-in-the-middle positioning sensitivity, contradictory evidence.
- **Generation Failures**: Unsupported claims, hallucinated propositions, distorted facts.
- **Citation Failures**: Missing citations, invalid document IDs, citations that contradict claims.
- **Operational Failures**: Embedding drift, retrieval drift, index staleness, prompt injection poisoning.

The **Advanced RAG Reliability Engine** decomposes the RAG lifecycle into 11 isolated, measurable stages:

```text
QUERY ──▶ QUERY ANALYSIS ──▶ RETRIEVAL ──▶ RANKING / RERANKING ──▶ CONTEXT CONSTRUCTION ──▶
GENERATION ──▶ CLAIMS ──▶ EVIDENCE ──▶ CITATIONS ──▶ FINAL ANSWER ──▶ RELIABILITY VERIFICATION
```

### Core Architectural Principle: Stage-Level Isolation & Attribution
- A correct final answer must **NEVER** mask a retrieval failure (e.g. retriever retrieved useless documents, but LLM relied on parametric memory).
- A perfect retriever must **NEVER** take the blame for generation hallucinations (e.g. retriever provided gold evidence, but LLM ignored it).
- Every RAG run produces **independent stage scores** and deterministic root-cause attributions.
- **Never fabricate ground truth**: When expected reference documents are unavailable, exact recall is not faked; instead, evidence coverage and heuristic alignment are clearly reported with `ground_truth_available = False`.

---

## 2. Component Architecture

```text
                               ┌────────────────────────────────────────────────┐
                               │           AdvancedRAGReliabilityEngine         │
                               └───────────────────────┬────────────────────────┘
                                                       │
         ┌───────────────────┬─────────────────────────┼─────────────────────────┬───────────────────┐
         │                   │                         │                         │                   │
         ▼                   ▼                         ▼                         ▼                   ▼
┌─────────────────┐ ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐ ┌─────────────────┐
│  QueryAnalyzer  │ │RetrievalEvaluator│      │ RankingEvaluator│       │ ContextAnalyzer │ │ClaimExtractor & │
│ (Intent, Types, │ │ (Exact/Heuristic│      │(MRR, NDCG@K,    │       │(Relevance, Lost-│ │EvidenceAligner  │
│  Difficulty)    │ │  Recall/Prec)   │      │ Reranker Delta) │       │ in-the-Middle)  │ │(Claims/Evidence)│
└─────────────────┘ └─────────────────┘       └─────────────────┘       └─────────────────┘ └────────┬────────┘
                                                                                                     │
         ┌───────────────────┬─────────────────────────┬─────────────────────────┬───────────────────┘
         │                   │                         │                         │
         ▼                   ▼                         ▼                         ▼
┌─────────────────┐ ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│CitationValidator│ │GroundingEvaluator│      │FreshnessTracker │       │  DriftDetector  │
│(Format, Chunk   │ │(Grounding, Faith-│      │(Document Stale- │       │(Query, Embedding│
│ Mapping, Match) │ │  fulness, Halluc)│      │ ness, Versions) │       │ Retrieval Drift)│
└─────────────────┘ └─────────────────┘       └─────────────────┘       └─────────────────┘
                                                       │
         ┌───────────────────┬─────────────────────────┼─────────────────────────┬───────────────────┐
         │                   │                         │                         │                   │
         ▼                   ▼                         ▼                         ▼                   ▼
┌─────────────────┐ ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐ ┌─────────────────┐
│ KnowledgeBase-  │ │ RAGSecurity-    │       │ Phase 34/35     │       │ Phase 36/37     │ │   Phase 38      │
│ Analyzer (Health│ │ Analyzer        │       │ Intelligence &  │       │ Test Generation │ │ Optimization    │
│ & Chunks)       │ │(Poisoning/Inject│       │ Knowledge Graph │       │ & Self-Healing  │ │ Pareto Frontier │
└─────────────────┘ └─────────────────┘       └─────────────────┘       └─────────────────┘ └─────────────────┘
```

---

## 3. Data Models (`src/aireliability/rag/models.py`)

- `RAGQuery`: Query ID, text, classified query type (`SIMPLE_FACTUAL`, `MULTI_HOP`, `AMBIGUOUS`, `UNDERSPECIFIED`, `TEMPORAL`, `COMPARATIVE`, `ADVERSARIAL`), extracted entities, constraints, complexity score, completeness score.
- `RetrievedDocument`: Document ID, title, text, source domain, ingestion timestamp, last updated timestamp, version, score.
- `RetrievedChunk`: Chunk ID, document ID, content, chunk index, start/end char, retrieval score, rerank score, metadata.
- `RetrievalResult`: Query ID, retrieved documents, retrieved chunks, hybrid breakdown (lexical vs semantic weight), latency ms, total candidate count.
- `RankingResult`: Ranked items, original rank vs reranked rank, rank flips, MRR, NDCG@K, buried evidence detected.
- `ContextWindow`: Formatted prompt context, included chunks, token count, context truncation detected, position distribution (beginning/middle/end), redundancy score, conflict count.
- `GeneratedAnswer`: Text, model name, tokens used, latency seconds.
- `Claim`: Claim ID, proposition text, source sentence index, importance tier (`CRITICAL`, `STANDARD`, `MINOR`), support status (`SUPPORTED`, `PARTIALLY_SUPPORTED`, `UNSUPPORTED`, `CONTRADICTED`, `UNKNOWN`), confidence.
- `Evidence`: Evidence ID, chunk ID, document ID, snippet text, relevance score.
- `ClaimEvidenceLink`: Claim ID, evidence ID, status, similarity, explanation.
- `Citation`: Citation ID, marker text (e.g. `[1]`, `[doc_1]`), cited chunk ID, target claim ID, validity (`VALID`, `MISSING_CHUNK`, `UNSUPPORTED`, `WRONG_SOURCE`, `MISMATCH`).
- `RAGFailure`: Failure ID, stage (`QUERY`, `RETRIEVAL`, `RANKING`, `RERANKING`, `CONTEXT`, `GENERATION`, `GROUNDING`, `CITATION`, `FRESHNESS`, `SECURITY`), category, severity, message, confidence, evidence.
- `RAGStageScore`: Stage enum, score (0.0–1.0), confidence, metrics, failures, explanation.
- `RAGReliabilityScore`: Overall score (0.0–1.0), stage breakdown, veto triggered (safety/security violation), summary.
- `RAGRun`: Complete end-to-end trace encapsulating query, retrieval, ranking, context, generation, claims, evidence, citations, stage scores, overall score, and failures.
- `RAGDriftResult`: Drift metric, baseline value, observed value, delta, drift detected, trend.
- `KnowledgeBaseHealthReport`: Document count, chunk count, duplicate rate, stale rate, conflict rate, status (`HEALTHY`, `DEGRADED`, `CRITICAL`).

---

## 4. Subsystems & Logic

### 4.1 Query Analysis (`query_analyzer.py`)
- Analyzes incoming queries deterministically without external LLM calls.
- Classifies into 11 distinct query archetypes (`SIMPLE_FACTUAL`, `MULTI_HOP`, `AMBIGUOUS`, `UNDERSPECIFIED`, `TEMPORAL`, etc.).
- Evaluates query quality: completeness, ambiguity, specificity, expected retrieval difficulty.
- Distinguishes poor queries (e.g. "Tell me about it") from retrieval failures.

### 4.2 Retrieval & Hybrid Evaluation (`retrieval_evaluator.py`)
- Evaluates retrieval quality against ground-truth document IDs when available: Recall@K, Precision@K, Hit@K, MRR, NDCG@K.
- When ground truth is unavailable: computes evidence coverage heuristics, reporting `ground_truth_available = False`. Never fabricates ground truth.
- Analyzes hybrid retrieval pipelines: lexical (BM25 token overlap) vs dense semantic similarity contribution, ranking correlation, and lexical-semantic disagreement.

### 4.3 Ranking & Reranking Evaluation (`ranking_evaluator.py`)
- Detects buried relevant evidence (relevant chunk ranked behind noise).
- Evaluates reranker efficacy: Before vs After reranking deltas ($\Delta \text{Recall}$, $\Delta \text{Precision}$, $\Delta \text{NDCG}$).
- Detects `RERANKING_DEGRADATION` when reranking harms retrieval.

### 4.4 Context Reliability & Conflict Detection (`context_analyzer.py`)
- Measures context relevance, redundancy (Jaccard similarity between chunks), and context truncation.
- **Lost-in-the-Middle Analysis**: Assesses whether evidence in the middle third $[0.33, 0.66]$ is utilized vs beginnings and endings. Reports `potential_position_sensitivity`.
- **Conflict Detection**: Bounded pairwise contradiction analysis detecting dates, numerical assertions, and contradictory claims.

### 4.5 Claim Extraction & Evidence Alignment (`claim_extractor.py`, `evidence_aligner.py`)
- Breaks answer into atomic propositions and sentences.
- Evaluates claim importance: `CRITICAL` vs `STANDARD` vs `MINOR`.
- Aligns claims with retrieved evidence chunks: checks token overlap, negation handling, semantic similarity.
- Classifies alignment: `SUPPORTED`, `PARTIALLY_SUPPORTED`, `UNSUPPORTED`, `CONTRADICTED`, `UNKNOWN`.

### 4.6 Citation Validation (`citation_validator.py`)
- Extracts inline citations (`[1]`, `[doc_1]`, `[chunk_foo]`).
- Validates chunk existence, citation target mapping, and checks whether the cited chunk contains the necessary factual support.
- Flags `MISSING_CITATION`, `INVALID_CITATION`, `UNSUPPORTED_CITATION`, `WRONG_SOURCE`.

### 4.7 Grounding, Faithfulness & Hallucination (`grounding_evaluator.py`)
- Grounding Score: weighted combination of supported claim ratio, evidence coverage, citation validity, and contradiction penalty.
- Faithfulness: checks whether generated answer strictly adheres to retrieved facts.
- Hallucination Rate: proportion of unsupported or contradicted propositions.

### 4.8 Freshness & Drift Monitoring (`freshness.py`, `drift.py`)
- Enforces freshness policies based on document timestamps, detecting stale evidence and `INDEX_STALENESS`.
- Monitors distributional shifts in query vocabulary, retrieval score distributions, embedding vector norms, and grounding scores.

### 4.9 Knowledge Base Health & Multi-Hop Chains (`knowledge_base.py`, `multihop.py`)
- Audits knowledge bases for duplicate chunks, orphaned entries, and fragmentation.
- Validates multi-hop reasoning chains (Query $\rightarrow$ Doc A $\rightarrow$ Fact $\rightarrow$ Doc B $\rightarrow$ Answer), flagging missing hops or broken reasoning links.

### 4.10 Security & Poisoning Defense (`security.py`)
- Scans retrieved content for prompt injection payloads (`Ignore previous instructions`, `SYSTEM OVERRIDE`, `<script>`, credential leakage patterns).
- Detects retrieval poisoning spikes (abnormal similarity clustering from single untrusted source).

---

## 5. Cross-Phase Integrations

- **Phase 34 (`intelligence_bridge.py`)**: RAG failures flow into `FailureNormalizer` and `FailureClusterer`.
- **Phase 35 (`graph_bridge.py`)**: Knowledge Graph representation of RAG runs, documents, chunks, claims, citations, and evidence links.
- **Phase 36 (`test_bridge.py`)**: Generates targeted RAG edge cases (distractors, paraphrases, conflicting evidence).
- **Phase 37 (`healing_bridge.py`)**: Routes retrieval and context failures to `RetrievalRepairer` and remediation proposals.
- **Phase 38 (`optimization_bridge.py`)**: Optimizes RAG variables (`top_k`, `similarity_threshold`, `chunk_size`) across competing Pareto objectives.

---

## 6. CLI Commands (`airel rag`)

```bash
# Evaluate end-to-end RAG run
airel rag evaluate run.json

# Analyze query classification and complexity
airel rag analyze "What is the revenue for Q3 2024?"

# Evaluate retrieval metrics (Recall, Precision, MRR, NDCG)
airel rag retrieve query.json --dataset dataset.json --top-k 5

# Inspect grounding and faithfulness
airel rag grounding run.json

# Validate inline citations against chunks
airel rag citations run.json

# Extract and align atomic claims
airel rag claims "AI Reliability is vital. It prevents hallucinations." --context "AI Reliability is vital."

# Audit knowledge freshness and staleness
airel rag freshness documents.json --max-age-days 30

# Monitor statistical RAG drift
airel rag drift current_runs.json --baseline baseline_runs.json

# Audit knowledge base health
airel rag knowledge kb_documents.json

# Detect contradictory evidence in context
airel rag conflicts documents.json

# List diagnosed RAG failures
airel rag failures run.json

# Trace provenance of claims and evidence
airel rag provenance run.json --claim-id clm_123

# Export RAG evaluation reports in JSON, Markdown, or CSV
airel rag report run.json --format markdown
```
