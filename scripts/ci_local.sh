#!/usr/bin/env bash
# AI Reliability Platform v1.4.0 — Local CI Pipeline Reproduction Script
# Executes the complete local continuous integration validation suite:
# 1. Version consistency check
# 2. Ruff lint & format check
# 3. Core unit, integration, and security tests
# 4. Real-world demo test suite
# 5. Full 17-step autonomous demo workflow
# 6. Performance smoke benchmark
# 7. Package build & Twine verification
# 8. Clean isolated environment wheel installation & CLI verification

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

echo "=========================================================="
echo "AIRELIABILITY v1.4.0 — LOCAL CI / CD VERIFICATION PIPELINE"
echo "=========================================================="

echo -e "\n[1/8] Checking Version Consistency across repository..."
python3 scripts/check_version.py

echo -e "\n[2/8] Running Ruff Static Analysis (lint & format)..."
ruff check .
ruff format --check .

echo -e "\n[3/8] Running Core Test Suite (Unit, Integration, Security)..."
python3 -m pytest tests -q

echo -e "\n[4/8] Running Real-World Demo Tests..."
python3 -m pytest examples/aireliability_demo/tests -q

echo -e "\n[5/8] Executing Full 17-Step Autonomous Demo Workflow..."
python3 scripts/run_full_workflow.py > /dev/null
echo "      [OK] 17/17 workflow steps executed successfully."

echo -e "\n[6/8] Executing Performance Benchmark (Smoke Mode)..."
python3 benchmarks/run_benchmarks.py --smoke > /dev/null
echo "      [OK] Performance smoke benchmark passed."

echo -e "\n[7/8] Building Package & Validating Metadata..."
python3 -m build
twine check dist/aireliability-*.whl dist/aireliability-*.tar.gz

echo -e "\n[8/8] Testing Isolated Clean Wheel Installation..."
TEMP_VENV=$(mktemp -d)/venv
python3 -m venv "${TEMP_VENV}"
"${TEMP_VENV}/bin/pip" install --quiet --upgrade pip
"${TEMP_VENV}/bin/pip" install --quiet dist/aireliability-1.4.0-py3-none-any.whl

# Test import and CLI from outside the repository
pushd /tmp > /dev/null
CLEAN_VER=$("${TEMP_VENV}/bin/python" -c "import aireliability; print(aireliability.__version__)")
CLI_VER=$("${TEMP_VENV}/bin/airel" --version)
popd > /dev/null

rm -rf "$(dirname "${TEMP_VENV}")"

if [ "${CLEAN_VER}" != "1.4.0" ]; then
    echo "Error: Installed package version '${CLEAN_VER}' != '1.4.0'"
    exit 1
fi
echo "      [OK] Isolated import verification: version ${CLEAN_VER}"
echo "      [OK] Isolated CLI entrypoint verification: ${CLI_VER}"

echo -e "\n=========================================================="
echo "SUCCESS: ALL LOCAL CI VALIDATION CHECKS PASSED (v1.4.0)"
echo "=========================================================="
