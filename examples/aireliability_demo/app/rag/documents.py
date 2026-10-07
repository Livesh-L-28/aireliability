"""Document loading and representation for demo RAG knowledge base."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aireliability_demo.app.config import DOCUMENTS_DIR


@dataclass
class DemoDocument:
    """Representation of an ingested knowledge base document."""

    document_id: str
    title: str
    text: str
    source: str = "demo_kb"
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


def load_documents(directory: Path | None = None) -> list[DemoDocument]:
    """Load all markdown documents from data/documents."""
    doc_dir = directory or DOCUMENTS_DIR
    documents: list[DemoDocument] = []

    if not doc_dir.exists():
        return documents

    for file_path in sorted(doc_dir.glob("*.md")):
        text = file_path.read_text(encoding="utf-8")
        title = file_path.stem.replace("_", " ").title()
        # Extract title from first line if header present
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if lines and lines[0].startswith("# "):
            title = lines[0][2:].strip()

        doc = DemoDocument(
            document_id=file_path.name,
            title=title,
            text=text,
            source=str(file_path.name),
            metadata={"file_name": file_path.name, "byte_size": len(text)},
        )
        documents.append(doc)

    return documents
