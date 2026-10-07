"""Demo configuration and environment constants."""

from __future__ import annotations

import os
from pathlib import Path

DEMO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = DEMO_ROOT / "data"
DOCUMENTS_DIR = DATA_DIR / "documents"
DATASETS_DIR = DATA_DIR / "datasets"

# Multi-tenancy defaults
TENANT_ALPHA = "tenant_alpha"
TENANT_BETA = "tenant_beta"
DEFAULT_ORG = "org_demo"
DEFAULT_PROJECT = "demo_project"

# Default API Configuration
DEFAULT_API_HOST = os.getenv("DEMO_API_HOST", "127.0.0.1")
DEFAULT_API_PORT = int(os.getenv("DEMO_API_PORT", "8000"))
