"""Phase 35 Knowledge Graph Bridge synchronizing RAG entities, runs, and provenance."""

from __future__ import annotations

import logging
from typing import Any

from aireliability.graph.graph import KnowledgeGraph
from aireliability.graph.models import (
    GraphEdge,
    GraphNode,
    GraphNodeType,
    GraphRelationship,
)
from aireliability.rag.models import RAGRun

logger = logging.getLogger(__name__)


class RAGGraphBridge:
    """Synchronizes RAG execution runs, documents, claims, and failures into the Knowledge Graph."""

    def __init__(self, graph: KnowledgeGraph | None = None) -> None:
        self.graph = graph or KnowledgeGraph()

    def sync_run_to_graph(self, run: RAGRun) -> KnowledgeGraph:
        """Add RAG run nodes, document nodes, claim nodes, failure nodes, and relationships to KnowledgeGraph."""
        kg = self.graph

        # 1. RAG Run Node
        run_node = GraphNode(
            node_id=run.run_id,
            node_type=GraphNodeType.EVALUATION,
            name=f"RAG Run {run.run_id}",
            properties={
                "query": run.query.text,
                "overall_score": run.reliability_score.overall_score,
                "model": run.model,
                "retriever": run.retriever_name,
            },
        )
        kg.add_node(run_node)

        # 2. Query Node
        query_node = GraphNode(
            node_id=run.query.query_id,
            node_type=GraphNodeType.EVALUATION,
            name=f"Query: {run.query.text[:30]}",
            properties={"text": run.query.text},
        )
        kg.add_node(query_node)
        kg.add_edge(
            GraphEdge.create(
                source_node_id=run_node.node_id,
                target_node_id=query_node.node_id,
                relationship_type=GraphRelationship.EVALUATED,
            )
        )

        # 3. Retrieved Documents & Chunks
        for doc in run.retrieval_result.retrieved_documents:
            doc_node = GraphNode(
                node_id=doc.document_id,
                node_type=GraphNodeType.DATASET,
                name=doc.title or doc.document_id,
                properties={"source": doc.source, "version": doc.version},
            )
            kg.add_node(doc_node)
            kg.add_edge(
                GraphEdge.create(
                    source_node_id=run_node.node_id,
                    target_node_id=doc_node.node_id,
                    relationship_type=GraphRelationship.PRODUCED,
                )
            )

        for chk in run.retrieval_result.retrieved_chunks:
            chk_node = GraphNode(
                node_id=chk.chunk_id,
                node_type=GraphNodeType.DATASET,
                name=f"Chunk {chk.chunk_id}",
                properties={
                    "document_id": chk.document_id,
                    "retrieval_score": chk.retrieval_score,
                },
            )
            kg.add_node(chk_node)

        # 4. Failures
        for f in run.failures:
            f_node = GraphNode(
                node_id=f.failure_id,
                node_type=GraphNodeType.FAILURE,
                name=f.category.value,
                properties={
                    "message": f.message,
                    "stage": f.stage.value,
                    "severity": f.severity.value,
                },
            )
            kg.add_node(f_node)
            kg.add_edge(
                GraphEdge.create(
                    source_node_id=run_node.node_id,
                    target_node_id=f_node.node_id,
                    relationship_type=GraphRelationship.FAILED,
                )
            )

        return kg

    def sync_rag_run(
        self, run: RAGRun, graph: KnowledgeGraph | None = None
    ) -> KnowledgeGraph:
        """Alias for sync_run_to_graph with optional graph parameter."""
        if graph is not None:
            self.graph = graph
        return self.sync_run_to_graph(run)

    def trace_provenance(
        self, run: RAGRun, claim_id: str | None = None
    ) -> dict[str, Any]:
        """Explain the complete lineage and evidence supporting claims or attributing failures."""
        if claim_id:
            target_claim = next((c for c in run.claims if c.claim_id == claim_id), None)
            matched_links = [
                lnk for lnk in run.claim_evidence_links if lnk.claim_id == claim_id
            ]
            matched_citations = [
                cit for cit in run.citations if cit.claim_id == claim_id
            ]

            # Collect evidence chunks cited or linked
            cited_chunk_ids = {
                cit.cited_chunk_id for cit in matched_citations if cit.cited_chunk_id
            }
            for lnk in matched_links:
                cited_chunk_ids.add(lnk.chunk_id)

            evidence_chunks = [
                chk.model_dump()
                for chk in run.retrieval_result.retrieved_chunks
                if not cited_chunk_ids or chk.chunk_id in cited_chunk_ids
            ]
            if not evidence_chunks and run.retrieval_result.retrieved_chunks:
                evidence_chunks = [
                    chk.model_dump() for chk in run.retrieval_result.retrieved_chunks
                ]

            return {
                "run_id": run.run_id,
                "query": run.query.text,
                "claim_id": target_claim.claim_id if target_claim else claim_id,
                "claim_text": target_claim.text if target_claim else "",
                "support_status": target_claim.support_status.value
                if target_claim
                else "unknown",
                "confidence": target_claim.confidence if target_claim else 0.5,
                "evidence_chunks": evidence_chunks,
                "evidence_links": [lnk.model_dump() for lnk in matched_links],
                "citations": [cit.model_dump() for cit in matched_citations],
            }

        return {
            "run_id": run.run_id,
            "query": run.query.text,
            "overall_score": run.reliability_score.overall_score,
            "total_claims": len(run.claims),
            "total_citations": len(run.citations),
            "evidence_chunks": [
                c.model_dump() for c in run.retrieval_result.retrieved_chunks
            ],
            "failures": [f.model_dump() for f in run.failures],
        }
