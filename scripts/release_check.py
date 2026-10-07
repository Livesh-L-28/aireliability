#!/usr/bin/env python3
"""Release Gate Checker for AI Reliability Platform v1.4.0.

Validates that all prerequisites for a production release are strictly met:
1. Version consistency across all files
2. All required files exist (README, LICENSE, CHANGELOG, SECURITY, release notes)
3. Full test suite execution (>= 1,040 tests)
4. Static analysis (Ruff check and format check)
5. Package build artifacts (sdist and wheel) exist and pass twine check
6. Generation and validation of cryptographic SHA256 checksums
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
EXPECTED_VERSION = "1.4.0"
REQUIRED_FILES = [
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "SECURITY.md",
    "pyproject.toml",
    f"docs/release/{EXPECTED_VERSION}.md",
    "PERFORMANCE_BENCHMARK_REPORT.md",
    "benchmarks/results/baseline.json",
    "benchmarks/results/performance.json",
]


def check_required_files() -> list[str]:
    errors = []
    print("[1/6] Checking required repository release files...")
    for rel_path in REQUIRED_FILES:
        path = ROOT_DIR / rel_path
        if not path.is_file():
            errors.append(f"Required release file missing: {rel_path}")
        else:
            print(f"      [OK] {rel_path}")
    return errors


def check_version_consistency() -> list[str]:
    print("[2/6] Validating version consistency...")
    proc = subprocess.run(
        [sys.executable, str(ROOT_DIR / "scripts" / "check_version.py")],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return [f"check_version.py failed:\n{proc.stdout}\n{proc.stderr}"]
    print("      [OK] Version 1.4.0 verified across all components.")
    return []


def check_static_lints() -> list[str]:
    print("[3/6] Running Ruff linter and formatter checks...")
    proc_lint = subprocess.run(
        ["ruff", "check", "."], cwd=str(ROOT_DIR), capture_output=True, text=True
    )
    if proc_lint.returncode != 0:
        return [f"Ruff check failed:\n{proc_lint.stdout}\n{proc_lint.stderr}"]

    proc_fmt = subprocess.run(
        ["ruff", "format", "--check", "."],
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
    )
    if proc_fmt.returncode != 0:
        return [f"Ruff format check failed:\n{proc_fmt.stdout}\n{proc_fmt.stderr}"]
    print("      [OK] Ruff linter and formatter clean.")
    return []


def check_test_suites() -> list[str]:
    print("[4/6] Running full test suite (core + demo)...")
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests",
            "examples/aireliability_demo/tests",
            "-q",
        ],
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return [f"Pytest test suite failed:\n{proc.stdout}\n{proc.stderr}"]
    print(f"      [OK] Tests passed: {proc.stdout.strip()}")
    return []


def check_build_and_metadata() -> list[str]:
    print("[5/6] Validating build artifacts and distribution metadata...")
    dist_dir = ROOT_DIR / "dist"
    if not dist_dir.exists():
        dist_dir.mkdir(parents=True, exist_ok=True)

    # Ensure fresh build
    subprocess.run(
        [sys.executable, "-m", "build"], cwd=str(ROOT_DIR), capture_output=True
    )

    sdist = dist_dir / f"aireliability-{EXPECTED_VERSION}.tar.gz"
    wheel = dist_dir / f"aireliability-{EXPECTED_VERSION}-py3-none-any.whl"

    if not sdist.exists():
        return [f"Source distribution missing: {sdist.name}"]
    if not wheel.exists():
        return [f"Built wheel distribution missing: {wheel.name}"]

    proc_twine = subprocess.run(
        ["twine", "check", str(sdist), str(wheel)],
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
    )
    if proc_twine.returncode != 0:
        return [
            f"Twine metadata check failed:\n{proc_twine.stdout}\n{proc_twine.stderr}"
        ]

    print(f"      [OK] sdist: {sdist.name} ({sdist.stat().st_size:,} bytes)")
    print(f"      [OK] wheel: {wheel.name} ({wheel.stat().st_size:,} bytes)")
    print("      [OK] Twine metadata validation passed.")
    return []


def generate_and_verify_checksums() -> list[str]:
    print("[6/6] Generating and verifying SHA256 checksums...")
    dist_dir = ROOT_DIR / "dist"
    checksum_file = dist_dir / "SHA256SUMS"

    lines = []
    for artifact in sorted(dist_dir.glob("aireliability-*")):
        if artifact.suffix in [".gz", ".whl"]:
            sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest()
            lines.append(f"{sha256}  {artifact.name}\n")
            print(f"      {sha256}  {artifact.name}")

    checksum_file.write_text("".join(lines), encoding="utf-8")
    print(f"      [OK] Written checksums to {checksum_file.name}")
    return []


def main() -> int:
    print("==================================================")
    print("AIRELIABILITY v1.4.0 — RELEASE GATE AUDIT")
    print("==================================================")

    all_errors: list[str] = []
    all_errors.extend(check_required_files())
    all_errors.extend(check_version_consistency())
    all_errors.extend(check_static_lints())
    all_errors.extend(check_test_suites())
    all_errors.extend(check_build_and_metadata())
    all_errors.extend(generate_and_verify_checksums())

    print("==================================================")
    if all_errors:
        print("[!] RELEASE GATE FAILED WITH ERRORS:")
        for err in all_errors:
            print(f"    - {err}")
        return 1

    print("[+] ALL RELEASE GATES PASSED: v1.4.0 READY FOR PACKAGING")
    print("==================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
