"""Deterministic text chunking for RAG documents."""

from __future__ import annotations

import re

from aireliability.rag.models import RetrievedChunk
from aireliability_demo.app.rag.documents import DemoDocument


def chunk_document(
    document: DemoDocument, max_chunk_chars: int = 500
) -> list[RetrievedChunk]:
    """Chunk document text deterministically into paragraphs or sections."""
    raw_sections = re.split(r"\n\n+", document.text.strip())
    chunks: list[RetrievedChunk] = []
    chunk_index = 0

    for section in raw_sections:
        clean_section = section.strip()
        if not clean_section:
            continue

        # If section is small enough, make it a single chunk
        if len(clean_section) <= max_chunk_chars:
            chunk_index += 1
            chunks.append(
                RetrievedChunk(
                    chunk_id=f"{document.document_id}_c{chunk_index}",
                    document_id=document.document_id,
                    text=clean_section,
                    rank=chunk_index,
                    retrieval_score=1.0,
                    metadata={
                        "title": document.title,
                        "source": document.source,
                        "char_count": len(clean_section),
                    },
                )
            )
        else:
            # Sub-split by sentences
            sentences = re.split(r"(?<=[.!?])\s+", clean_section)
            current_batch: list[str] = []
            current_len = 0

            for sent in sentences:
                if current_len + len(sent) > max_chunk_chars and current_batch:
                    chunk_index += 1
                    chunk_text = " ".join(current_batch)
                    chunks.append(
                        RetrievedChunk(
                            chunk_id=f"{document.document_id}_c{chunk_index}",
                            document_id=document.document_id,
                            text=chunk_text,
                            rank=chunk_index,
                            retrieval_score=1.0,
                            metadata={
                                "title": document.title,
                                "char_count": len(chunk_text),
                            },
                        )
                    )
                    current_batch = [sent]
                    current_len = len(sent)
                else:
                    current_batch.append(sent)
                    current_len += len(sent)

            if current_batch:
                chunk_index += 1
                chunk_text = " ".join(current_batch)
                chunks.append(
                    RetrievedChunk(
                        chunk_id=f"{document.document_id}_c{chunk_index}",
                        document_id=document.document_id,
                        text=chunk_text,
                        rank=chunk_index,
                        retrieval_score=1.0,
                        metadata={
                            "title": document.title,
                            "char_count": len(chunk_text),
                        },
                    )
                )

    return chunks
