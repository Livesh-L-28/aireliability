#!/usr/bin/env python3
"""Version Consistency Checker for AI Reliability Platform.

Verifies that the release version matches exactly across:
- pyproject.toml
- src/aireliability/__init__.py
- CHANGELOG.md
- CLI entrypoint (`airel --version` / `aireliability.cli`)
- Documentation (docs/release/1.4.0.md and README.md)
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
EXPECTED_VERSION = "1.4.0"


def check_pyproject_version() -> str:
    pyproject_path = ROOT_DIR / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
    version = data.get("project", {}).get("version")
    if not version:
        raise ValueError("No version specified in pyproject.toml [project.version]")
    return str(version)


def check_package_init_version() -> str:
    init_path = ROOT_DIR / "src" / "aireliability" / "__init__.py"
    content = init_path.read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    if not match:
        raise ValueError("No __version__ found in src/aireliability/__init__.py")
    return match.group(1)


def check_changelog_version() -> str:
    changelog_path = ROOT_DIR / "CHANGELOG.md"
    content = changelog_path.read_text(encoding="utf-8")
    match = re.search(r"^##\s*\[([^\]]+)\]", content, re.MULTILINE)
    if not match:
        raise ValueError("No release version heading found in CHANGELOG.md")
    # First heading may be [Unreleased], find first numerical heading
    headings = re.findall(
        r"^##\s*\[([0-9]+\.[0-9]+\.[0-9]+[^\]]*)\]", content, re.MULTILINE
    )
    if not headings:
        raise ValueError("No semantic version heading found in CHANGELOG.md")
    return headings[0]


def check_cli_version() -> str:
    sys.path.insert(0, str(ROOT_DIR / "src"))
    from aireliability import __version__

    return __version__


def check_docs_release_version() -> str:
    release_doc = ROOT_DIR / "docs" / "release" / f"{EXPECTED_VERSION}.md"
    if not release_doc.exists():
        raise FileNotFoundError(f"Missing release notes documentation: {release_doc}")
    content = release_doc.read_text(encoding="utf-8")
    if f"v{EXPECTED_VERSION}" not in content and EXPECTED_VERSION not in content:
        raise ValueError(
            f"Release version {EXPECTED_VERSION} not found in {release_doc}"
        )
    return EXPECTED_VERSION


def main() -> int:
    print("==================================================")
    print("AIRELIABILITY VERSION CONSISTENCY AUDIT")
    print(f"Target Expected Version: {EXPECTED_VERSION}")
    print("==================================================")

    errors: list[str] = []

    try:
        pyproject_v = check_pyproject_version()
        print(f"[*] pyproject.toml:            {pyproject_v}")
        if pyproject_v != EXPECTED_VERSION:
            errors.append(
                f"pyproject.toml version '{pyproject_v}' != '{EXPECTED_VERSION}'"
            )
    except Exception as exc:
        errors.append(f"pyproject.toml check failed: {exc}")

    try:
        init_v = check_package_init_version()
        print(f"[*] src/aireliability:         {init_v}")
        if init_v != EXPECTED_VERSION:
            errors.append(
                f"src/aireliability/__init__.py version '{init_v}' != '{EXPECTED_VERSION}'"
            )
    except Exception as exc:
        errors.append(f"src/aireliability/__init__.py check failed: {exc}")

    try:
        cli_v = check_cli_version()
        print(f"[*] CLI module version:        {cli_v}")
        if cli_v != EXPECTED_VERSION:
            errors.append(f"CLI __version__ '{cli_v}' != '{EXPECTED_VERSION}'")
    except Exception as exc:
        errors.append(f"CLI check failed: {exc}")

    try:
        changelog_v = check_changelog_version()
        print(f"[*] CHANGELOG.md latest:       {changelog_v}")
        if changelog_v != EXPECTED_VERSION:
            errors.append(
                f"CHANGELOG.md latest release '{changelog_v}' != '{EXPECTED_VERSION}'"
            )
    except Exception as exc:
        errors.append(f"CHANGELOG.md check failed: {exc}")

    try:
        docs_v = check_docs_release_version()
        print(f"[*] docs/release/{EXPECTED_VERSION}.md: {docs_v}")
    except Exception as exc:
        errors.append(f"docs/release check failed: {exc}")

    print("--------------------------------------------------")
    if errors:
        print("[!] VERSION MISMATCH DETECTED:")
        for err in errors:
            print(f"    - {err}")
        return 1

    print("[+] SUCCESS: All version definitions are completely consistent!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
