#!/usr/bin/env python3
"""Run complete 17-step end-to-end AI Reliability workflow.

Usage:
    python scripts/run_full_workflow.py
    python scripts/run_full_workflow.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from aireliability_demo.app.reliability.workflows import run_full_workflow


def main() -> None:
    parser = argparse.ArgumentParser(description="Full AI Reliability Workflow Runner")
    parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON output"
    )
    args = parser.parse_args()

    result = run_full_workflow(verbose=not args.json)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("\nWorkflow Execution Summary:")
        print(f"Total Steps Executed:   {result['total_steps']}")
        print(f"All Steps Passed:       {result['all_steps_passed']}")
        print(f"Final Status:           {result['workflow_status']}")


if __name__ == "__main__":
    main()
