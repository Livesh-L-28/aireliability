#!/usr/bin/env python3
"""Full Workflow Runner for AI Reliability Platform Demo.

Executes the complete 17-step autonomous enterprise reliability lifecycle
from examples/aireliability_demo/scripts/run_full_workflow.py.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
TARGET_SCRIPT = (
    ROOT_DIR / "examples" / "aireliability_demo" / "scripts" / "run_full_workflow.py"
)


def main() -> int:
    if not TARGET_SCRIPT.exists():
        print(
            f"Error: Demo runner script not found at {TARGET_SCRIPT}", file=sys.stderr
        )
        return 1

    proc = subprocess.run([sys.executable, str(TARGET_SCRIPT)], cwd=str(ROOT_DIR))
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
