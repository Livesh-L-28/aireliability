"""Lightweight, deterministic in-memory retriever for RAG documents."""

from __future__ import annotations

import re

from aireliability.rag.models import RetrievedChunk, RetrievedDocument
from aireliability_demo.app.rag.chunker import chunk_document
from aireliability_demo.app.rag.documents import DemoDocument


def _tokenize(text: str) -> list[str]:
    return [w for w in re.findall(r"\w+", text.lower()) if len(w) > 2]


class DeterministicRetriever:
    """In-memory deterministic retriever matching queries against knowledge chunks."""

    def __init__(self, documents: list[DemoDocument] | None = None) -> None:
        self.documents: dict[str, DemoDocument] = {}
        self.chunks: list[RetrievedChunk] = []
        if documents is not None:
            self.index(documents)

    def index(self, documents: list[DemoDocument]) -> None:
        """Index a collection of documents into chunks."""
        self.documents = {d.document_id: d for d in documents}
        self.chunks = []
        for doc in documents:
            doc_chunks = chunk_document(doc)
            self.chunks.extend(doc_chunks)

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        min_threshold: float = 0.05,
    ) -> tuple[list[RetrievedDocument], list[RetrievedChunk]]:
        """Retrieve top-k chunks and corresponding documents deterministically."""
        query_tokens = set(_tokenize(query))
        if not query_tokens or not self.chunks:
            return [], []

        scored_chunks: list[tuple[float, RetrievedChunk]] = []
        for chk in self.chunks:
            chunk_tokens = set(_tokenize(chk.text))
            intersection = query_tokens.intersection(chunk_tokens)
            if not intersection:
                score = 0.0
            else:
                jaccard = len(intersection) / len(query_tokens.union(chunk_tokens))
                coverage = len(intersection) / len(query_tokens)
                score = round((0.4 * jaccard) + (0.6 * coverage), 4)

            if score >= min_threshold:
                scored_chunks.append((score, chk))

        # Sort descending by score, then stably by chunk_id
        scored_chunks.sort(key=lambda item: (-item[0], item[1].chunk_id))
        top_items = scored_chunks[:top_k]

        result_chunks: list[RetrievedChunk] = []
        doc_ids_seen: set[str] = set()
        result_docs: list[RetrievedDocument] = []

        for rank, (score, orig_chk) in enumerate(top_items, start=1):
            cloned_chk = RetrievedChunk(
                chunk_id=orig_chk.chunk_id,
                document_id=orig_chk.document_id,
                text=orig_chk.text,
                rank=rank,
                retrieval_score=score,
                metadata=dict(orig_chk.metadata),
            )
            result_chunks.append(cloned_chk)

            doc_id = orig_chk.document_id
            if doc_id in self.documents and doc_id not in doc_ids_seen:
                doc_ids_seen.add(doc_id)
                d = self.documents[doc_id]
                result_docs.append(
                    RetrievedDocument(
                        document_id=d.document_id,
                        title=d.title,
                        text=d.text,
                        source=d.source,
                        metadata=dict(d.metadata),
                    )
                )

        return result_docs, result_chunks
