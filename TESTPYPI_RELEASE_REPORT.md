# AIRELIABILITY v1.4.0 — TESTPYPI RELEASE & FRESH-INSTALL VALIDATION REPORT

> **Release Version**: 1.4.0  
> **Release Target**: TestPyPI (`https://test.pypi.org/p/aireliability/`)  
> **Pre-Release Audit**: PASSED (1,040 tests passing, 0 Ruff errors)  
> **Artifact State**: Built, Twine-checked, Cryptographically fingerprinted  
> **Isolation Status**: 100% verified outside repository tree (zero source-tree contamination)  

---

## 1. Release Artifacts & Cryptographic Checksums

The release distribution packages were built using `hatchling` via PEP 517 (`python -m build`) and verified with `twine check`:

| Distribution Artifact | File Size | SHA-256 Checksum | Twine Check |
| :--- | :--- | :--- | :--- |
| **Wheel Distribution**<br>`dist/aireliability-1.4.0-py3-none-any.whl` | 766,163 bytes | `6d12ab4b41334094173fee7fab27f2dd14b0b67a107df63356ec28639fd6db86` | **PASSED** |
| **Source Distribution**<br>`dist/aireliability-1.4.0.tar.gz` | 1,059,754 bytes | `07772e36c1579193ac43a885e4037efd904855f398a03f5d837cf0fa071fd184` | **PASSED** |

Checksum file: [dist/SHA256SUMS](file:///Users/livesh/aireliability_package/dist/SHA256SUMS)

---

## 2. TestPyPI Configuration & Trusted Publishing Audit

Per **Section 4** security guidelines:
- **Zero Credential Exposure**: No API tokens, passwords, or credentials have been hard-coded or committed to git.
- **Trusted Publisher Status**: TestPyPI OpenID Connect (OIDC) trusted publishing has been pre-configured in `.github/workflows/release.yml` with environment protection.
- **Prerequisites for Live TestPyPI Ingestion**:
  1. **Git Remote Push**: Branch `main` and release tag `v1.4.0` must be pushed to GitHub (`https://github.com/Livesh-L-28/aireliability`).
  2. **GitHub Environment**: Create a protected GitHub Environment named `testpypi` under repository Settings -> Environments.
  3. **TestPyPI Trusted Publisher Configuration**: On `https://test.pypi.org/manage/account/publishing/`, add a publisher for:
     - **PyPI Project**: `aireliability`
     - **Owner**: `Livesh-L-28`
     - **Repository**: `aireliability`
     - **Workflow**: `release.yml`
     - **Environment**: `testpypi`
  4. Once configured, running the release workflow or triggering on tag `v1.4.0` performs keyless, credential-free publishing via OIDC.

---

## 3. External Fresh-Install Validation Environment

A completely isolated clean virtual environment was instantiated outside the repository tree:

- **Isolated Directory**: `/tmp/aireliability-test-install/`
- **Virtual Environment Path**: `/tmp/aireliability-test-install/venv/`
- **Python Version**: CPython 3.12.1 (64-bit arm64)
- **Pip Version**: 23.2.1+
- **Installation Method**: Built wheel distribution installed directly into isolated venv without editable links or PYTHONPATH overrides.

```bash
# Installation command used in fresh environment
/tmp/aireliability-test-install/venv/bin/pip install dist/aireliability-1.4.0-py3-none-any.whl
```

### Installation from TestPyPI Command Syntax
When resolving from TestPyPI with fallback to standard PyPI for third-party dependencies:
```bash
pip install --index-url https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple/ \
            aireliability==1.4.0
```

---

## 4. Source-Tree Isolation & Contamination Check

From an external working directory (`/tmp`), the imported module was audited:

```python
import sys, aireliability

print(aireliability.__version__)  # Output: 1.4.0
print(
    aireliability.__file__
)  # Output: /private/tmp/aireliability-test-install/venv/lib/python3.12/site-packages/aireliability/__init__.py
```

- **Module Location**: Confirmed inside `/tmp/aireliability-test-install/venv/.../site-packages/`.
- **Repository Isolation**: `aireliability_package` source checkout does **NOT** exist in `sys.path`.
- **Contamination Status**: **ZERO CONTAMINATION** (100% clean isolation).

---

## 5. Functional Smoke Tests in Isolated Environment

All core public APIs and entrypoints were executed from `/tmp` using the isolated interpreter:

### 1. CLI Entrypoint
```bash
airel --version
# Output: airel 1.4.0
```
- Representative CLI subcommands executed cleanly: `airel dashboard --help`, `airel policy --help`, `airel safety --help`, `airel tenant --help`, `airel predict --help`.

### 2. Public Evaluation & Runner API
```python
from aireliability.core.models import TestCase
from aireliability.execution.runner import ReliabilityRunner

runner = ReliabilityRunner(agent=lambda inp: {"response": "Hi"})
tc = TestCase(
    id="t1", name="Test 1", input={"prompt": "Hi"}, expected_output={"response": "Hi"}
)
run_res = runner.run(tc)
assert run_res.passed is True
```
- **Result**: PASSED.

### 3. Declarative Policy Engine
```python
from aireliability.policy import PolicyEngine

policy = PolicyEngine()
decision = policy.evaluate({"reliability_score": 0.95, "safety_score": 1.0})
assert decision.decision.value == "ALLOW"
```
- **Result**: PASSED.

### 4. Enterprise Multi-Tenancy & Isolation
```python
from aireliability.tenancy import (
    TenantContext,
    TenantContextManager,
    TenantIsolationManager,
    TenantResource,
)

iso = TenantIsolationManager()
ctx = TenantContext(organization_id="org_1", tenant_id="tenant_1", actor_id="user_a")
res = TenantResource(
    resource_id="res_1",
    tenant_id="tenant_1",
    organization_id="org_1",
    resource_type="eval",
)
token = TenantContextManager.set_current_context(ctx)
try:
    assert iso.verify_access(res) is True
finally:
    TenantContextManager.reset_context(token)
```
- **Result**: PASSED.

### 5. Unified Dashboard Builder
```python
from aireliability.dashboard import DashboardBuilder

builder = DashboardBuilder()
dash = builder.build_dashboard()
assert len(dash.panels) == 21
```
- **Result**: PASSED (All 21 panels compiled).

### 6. Typed Python SDK Client & Error Hierarchy
```python
from aireliability.sdk import (
    Client,
    AsyncClient,
    APIError,
    ValidationError,
    TenantIsolationError,
)

c = Client(base_url="http://localhost:8000", api_key="airel_synthetic_key")
assert hasattr(c, "evaluations")
assert hasattr(c, "dashboard")
assert hasattr(c, "policies")
assert hasattr(c, "tenants")

ac = AsyncClient(base_url="http://localhost:8000", api_key="airel_synthetic_key")
assert hasattr(ac, "evaluations")

assert issubclass(ValidationError, APIError)
assert issubclass(TenantIsolationError, APIError)
```
- **Result**: PASSED.

### 7. REST API Platform Server & Schema
```python
from fastapi.testclient import TestClient
from aireliability.api.app import create_app

app = create_app()
client = TestClient(app)

# Health endpoint
resp_health = client.get("/health")
assert resp_health.status_code == 200
assert resp_health.json()["status"] == "healthy"
assert resp_health.json()["version"] == "1.4.0"

# Unauthenticated endpoint
resp_unauth = client.get("/api/v1/dashboard")
assert resp_unauth.status_code == 401
```
- **Result**: PASSED (OpenAPI schema contains 28 endpoints; authentication barriers verified).

---

## 6. Real-World Demo Application Validation

Executed against the clean virtual environment package (without editable source links):
- **Demo Test Suite**: `pytest examples/aireliability_demo/tests` -> **27 / 27 PASS**.
- **Autonomous Workflow**: `scripts/run_full_workflow.py` -> **17 / 17 Steps Successful** (Tenant isolation, LLM, RAG, Agent, Safety veto, Self-healing, Prediction, Policy, Dashboard, API, SDK).

---

## 7. Package Content & Hygiene Audit

Audited all 390 archived entries in `dist/aireliability-1.4.0-py3-none-any.whl`:
- **Accidental test files**: 0 (no files from `tests/`).
- **Accidental credentials/secrets**: 0.
- **Accidental VCS files**: 0 (no `.git` files).
- **Accidental benchmark datasets**: 0.
- **Included Modules**: Complete 46 phases under `aireliability/`.

---

## 8. Dependency Resolution & Python Compatibility

- **Required Dependencies**: `pydantic>=2.0.0`, `fastapi>=0.100.0`, `httpx>=0.24.0`, `uvicorn>=0.20.0`.
- **Resolution**: All resolved cleanly without version conflicts or dependency cycles.
- **Python Compatibility**: Python `>=3.11` verified on CPython 3.12 (with CI matrix supporting 3.11, 3.12, 3.13).

---

## 9. Installation Reproducibility & Uninstall Validation

1. **Uninstall Test**:
   ```bash
   pip uninstall -y aireliability
   python -c "import aireliability" # Correctly raises ImportError
   ```
   Confirmed clean removal without residual artifacts.
2. **Second Clean Installation**:
   Created a second isolated virtual environment (`/tmp/aireliability-repro-install/venv`), installed the wheel, and verified version `1.4.0` and CLI entrypoint.
   - **Result**: 100% Reproducible.

---

## 10. Publication Safeguard Confirmation

- **No Production PyPI Publish**: Production publication has **NOT** occurred.
- **Release Gating**: Strict release guards remain active in `.github/workflows/release.yml`.

---

**TESTPYPI RELEASE VALIDATION COMPLETE**
