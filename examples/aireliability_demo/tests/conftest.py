"""Pytest fixtures and configuration for aireliability_demo tests."""

from __future__ import annotations

import sys
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = DEMO_DIR.parent
WORKSPACE_ROOT = EXAMPLES_DIR.parent

for p in (
    str(WORKSPACE_ROOT / "src"),
    str(WORKSPACE_ROOT),
    str(EXAMPLES_DIR),
):
    if p not in sys.path:
        sys.path.append(p)
