#!/usr/bin/env bash
# ==============================================================================
# AI Reliability Engine (aireliability) - CI Example Script
# Demonstrates running `airel test --ci` in continuous integration workflows.
# Returns non-zero exit code (1) when regressions or test failures occur.
# ==============================================================================

set -euo pipefail

CI_DIR="$(mktemp -d -t airel_ci_example_XXXXXX)"
cleanup() {
    rm -rf "$CI_DIR"
}
trap cleanup EXIT

echo "=== 1. Initializing clean project in ${CI_DIR} ==="
airel init --dir "${CI_DIR}"

echo ""
echo "=== 2. Establishing baseline with initial passing run ==="
airel test --save-baseline --dir "${CI_DIR}"

echo ""
echo "=== 3. Executing CI gate (airel test --ci) with matching baseline ==="
# Should exit with 0 (clean run, no regressions)
airel test --ci --dir "${CI_DIR}"
echo "✓ CI Gate passed cleanly (exit code: $?)"

echo ""
echo "=== 4. Simulating a regression in agent logic ==="
# Modify agent to fail the expected output assertion ("Hello")
cat << 'EOF' > "${CI_DIR}/agent.py"
def app(user_input: str) -> str:
    # Regression: unexpected greeting format causing expectation failure
    return f"Goodbye, {user_input}!"
EOF

echo ""
echo "=== 5. Running airel test --ci on regressed code (expecting non-zero exit) ==="
set +e
airel test --ci --dir "${CI_DIR}"
EXIT_CODE=$?
set -e

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "✓ Success: 'airel test --ci' returned non-zero exit code (${EXIT_CODE}) upon regression detection."
    exit 0
else
    echo ""
    echo "✗ Error: Expected non-zero exit code on regression, got 0."
    exit 1
fi
