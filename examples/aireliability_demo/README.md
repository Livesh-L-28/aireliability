# AI Reliability v1.4.0 — Real-World Enterprise Demonstration

A complete, self-contained, and production-grade reference demonstration showcasing how to integrate the **aireliability v1.4.0** platform into a real-world AI application.

The demo operates 100% locally and in-memory without requiring paid API tokens, dedicated GPUs, cloud subscriptions, or external database infrastructure.

---

## What the Demo Demonstrates

This demo exercises the unified 17-stage reliability loop across all completed phases (Phases 1–46):

```
AI Application
      ↓
Observability
      ↓
Evaluation (Phases 39 & 40)
      ↓
Failure Detection
      ↓
Root Cause & Intelligence (Phase 34)
      ↓
Safety Validation & Hard Veto (Phase 41)
      ↓
Reliability Prediction (Phase 42)
      ↓
Policy Governance (Phase 44)
      ↓
Self-Healing Remediation (Phase 37)
      ↓
Verification & Test Generation (Phase 36)
      ↓
Intelligence Dashboard (Phase 43)
```

1. **LLM Evaluation**: Deterministic assertion testing, hallucination checks, and schema validation.
2. **RAG Evaluation (Phase 39)**: 11-stage evaluation (retrieval quality, context quality, claim grounding, citation coverage, freshness, and conflict detection).
3. **Agent Trajectory Auditing (Phase 40)**: Trajectory-based audits checking tool selection, argument validity, loop detection (finite vs runaway), memory integrity, and goal criteria verification.
4. **Safety Validation & Hard Veto (Phase 41)**: Synthetic adversarial probes (`TEST_SECRET_123`, `DEMO_TOKEN_ABC`), automated leak prevention, and non-bypassable hard safety veto capping overall reliability score at 0.30.
5. **Failure Intelligence (Phase 34)**: Fingerprinting, clustering, recurring pattern detection, impact assessment, and automated remediation recommendations.
6. **Provenance Knowledge Graph (Phase 35)**: Cryptographically traceable provenance linking `Dataset -> Evaluation -> Execution -> Failure -> Root Cause -> Safety Finding -> Prediction -> Policy -> Remediation`.
7. **Automated Test Generation (Phase 36)**: Synthesizes reusable regression tests directly from detected failures.
8. **Self-Healing Remediation (Phase 37)**: Proposes targeted configuration/retrieval/prompt patches, simulates them in an isolated sandbox, and verifies effectiveness before promotion.
9. **Controlled Optimization (Phase 38)**: Multi-objective Pareto optimization across reliability, quality, latency, and cost.
10. **Predictive Reliability (Phase 42)**: Empirical time-series forecasting, risk scoring, trend classification (`STABLE`, `DEGRADING`), and confidence interval computation.
11. **Enterprise Policy Governance (Phase 44)**: Non-bypassable rule engine enforcing strict hierarchy: `SECURITY > SAFETY > TENANT_ISOLATION > RELIABILITY > PERFORMANCE`.
12. **Multi-Tenancy Isolation (Phase 45)**: Strict boundary enforcement between `tenant_alpha` and `tenant_beta` with automated audit event logging on unauthorized cross-tenant requests.
13. **Unified Dashboard (Phase 43)**: Multi-panel operational health monitoring with JSON, Markdown, and HTML exports.
14. **Platform REST API & Python SDK (Phase 46)**: Direct FastAPI endpoints and synchronous (`Client`) / asynchronous (`AsyncClient`) SDK usage.

---

## Architecture

```
examples/aireliability_demo/
├── app/
│   ├── main.py                  # FastAPI server integrating platform API & demo routes
│   ├── config.py                # Configuration and environment defaults
│   ├── llm/                     # Deterministic & optional local LLM providers
│   ├── rag/                     # In-memory document loading, chunking, retriever & pipeline
│   ├── agent/                   # Controlled autonomous agent with safe deterministic tools
│   ├── scenarios/               # Normal, LLM failure, RAG failure, agent failure, safety, regression
│   ├── reliability/             # Wrappers for Phases 34–45 engines and 17-step workflow
│   ├── api/                     # FastAPI demo router (/api/v1/demo/*)
│   └── dashboard/               # Phase 43 dashboard data generator and HTML viewer
├── data/
│   ├── documents/               # Markdown knowledge base
│   └── datasets/                # Sample RAG queries, agent tasks, and safety probes
├── scripts/
│   ├── run_demo.py              # CLI scenario runner
│   ├── run_evaluation.py        # Standalone LLM, RAG, and Agent evaluation
│   ├── run_safety.py            # Safety campaigns and hard veto demo
│   ├── run_prediction.py        # Forecasting and risk analysis demo
│   └── run_full_workflow.py     # Complete 17-step end-to-end workflow runner
└── tests/                       # 27 comprehensive deterministic tests
```

---

## Installation

From the project root:

```bash
# Editable install of aireliability
pip install -e .

# Install demo dependencies
pip install -r examples/aireliability_demo/requirements.txt
```

---

## Configuration

Copy `.env.example` to `.env` (optional):

```bash
cp examples/aireliability_demo/.env.example examples/aireliability_demo/.env
```

| Environment Variable | Default | Description |
|---|---|---|
| `DEMO_API_HOST` | `127.0.0.1` | Local host to bind FastAPI server |
| `DEMO_API_PORT` | `8000` | Port to bind FastAPI server |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Optional local Ollama inference server |
| `OLLAMA_MODEL` | `llama3` | Optional Ollama model name |

> **Note**: If an external LLM server is offline or unspecified, `DeterministicLLM` is automatically utilized, guaranteeing 100% test reproducibility.

---

## Quick Start & Running Scenarios

### 1. Run Complete 17-Step Workflow

Execute the full end-to-end lifecycle:

```bash
python examples/aireliability_demo/scripts/run_full_workflow.py
```

For machine-readable JSON output:

```bash
python examples/aireliability_demo/scripts/run_full_workflow.py --json
```

### 2. Run Controlled Scenarios via CLI

The scenario runner (`scripts/run_demo.py`) allows testing individual failure modes:

```bash
# Normal healthy execution
python examples/aireliability_demo/scripts/run_demo.py --scenario normal

# LLM hallucination and quality degradation
python examples/aireliability_demo/scripts/run_demo.py --scenario llm_failure

# RAG grounding failure and citation mismatch
python examples/aireliability_demo/scripts/run_demo.py --scenario rag_failure

# Agent runaway loop (4 consecutive identical calls)
python examples/aireliability_demo/scripts/run_demo.py --scenario agent_failure

# Adversarial probe with synthetic secret disclosure (demonstrating hard veto)
python examples/aireliability_demo/scripts/run_demo.py --scenario safety_failure

# Historical regression comparison (candidate accuracy drop)
python examples/aireliability_demo/scripts/run_demo.py --scenario regression
```

Add `--json` to any scenario command to print structured JSON output.

### 3. Run Standalone Component Demos

```bash
# Standalone evaluation of LLM, RAG, and Agent
python examples/aireliability_demo/scripts/run_evaluation.py

# Standalone Safety validation & hard veto demo
python examples/aireliability_demo/scripts/run_safety.py

# Standalone Reliability prediction and forecasting
python examples/aireliability_demo/scripts/run_prediction.py
```

### 4. Run Interactive Web Server & API

Start the demo server:

```bash
python examples/aireliability_demo/app/main.py
```

- **Interactive API Documentation (Swagger)**: `http://127.0.0.1:8000/docs`
- **ReDoc Documentation**: `http://127.0.0.1:8000/redoc`
- **Live HTML Reliability Dashboard**: `http://127.0.0.1:8000/api/v1/demo/dashboard/view`

---

## Using the Python SDK

The demo platform exposes both synchronous and asynchronous SDK access:

```python
from aireliability.sdk.client import Client
from aireliability_demo.app.main import app

# Connect to in-memory application without opening network ports
with Client(app=app) as client:
    # Health check
    health = client.health()
    print(health["status"])  # "healthy"

    # Create and evaluate an execution trace
    eval_record = client.evaluations.create(
        input_text="What is Phase 41 safety veto?",
        output_text="A critical safety violation caps overall reliability at 0.30.",
    )
    print("Passed:", eval_record["passed"])

    # Query operational health
    dash = client.dashboard.get_health()
    print("Overall Health:", dash["overall_health"])
```

Asynchronous SDK usage:

```python
import asyncio
from aireliability.sdk.async_client import AsyncClient
from aireliability_demo.app.main import app


async def main():
    async with AsyncClient(app=app) as client:
        health = await client.health()
        print("Async Status:", health["status"])


asyncio.run(main())
```

---

## Controlled Failure Scenarios Summary

| Scenario | Trigger / Cause | Detection Mechanism | Platform Action |
|---|---|---|---|
| `normal` | Clean input & context | Deterministic Assertions | `ALLOW` release gate, Healthy score |
| `llm_failure` | Fabricated historical claims | Hallucination Evaluator | Fingerprinted into cluster; prompt repair proposed |
| `rag_failure` | Unsupported claim in answer | Phase 39 Grounding Evaluator | Flagged ungrounded; synthesized regression test; retrieval patch |
| `agent_failure` | 4 identical consecutive tool calls | Phase 40 Loop Detector | Classified as `RUNAWAY_LOOP`; goal verification failed |
| `safety_failure` | Synthetic secret disclosure (`TEST_SECRET_123`) | Phase 41 Adversarial Analyzer | **HARD VETO**: Capped reliability score $\le 0.30$; policy `BLOCK` |
| `regression` | 18% accuracy drop vs baseline | Evaluation Baseline Comparator | Flagged `REGRESSION_DETECTED`; release gate blocked |

---

## Running the Test Suite

Run the 27 dedicated demo tests:

```bash
pytest examples/aireliability_demo/tests -v
```

Run the entire platform regression test suite (1,040 tests):

```bash
pytest tests examples/aireliability_demo/tests
```

---

## Troubleshooting

- **Import errors when running scripts**: Ensure workspace root and `examples/` are in your `PYTHONPATH` or install in editable mode with `pip install -e .`.
- **Port 8000 already in use**: Set `DEMO_API_PORT=8080` in your environment or `.env` file.
- **Ollama connection warning**: By default, `DeterministicLLM` is used. If Ollama is running on `http://localhost:11434`, `OptionalLocalLLM` connects automatically; if offline, it falls back seamlessly without errors.
