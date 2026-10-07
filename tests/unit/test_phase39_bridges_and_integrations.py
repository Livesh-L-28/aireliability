"""Unit tests for Phase 39 integration bridges with Phases 34–38."""

from __future__ import annotations

from aireliability.rag.graph_bridge import RAGGraphBridge
from aireliability.rag.healing_bridge import RAGHealingBridge
from aireliability.rag.intelligence_bridge import RAGIntelligenceBridge
from aireliability.rag.models import (
    Citation,
    CitationStatus,
    Claim,
    ClaimImportance,
    ClaimSupportStatus,
    GeneratedAnswer,
    RAGFailure,
    RAGFailureCategory,
    RAGQuery,
    RAGRun,
    RAGStage,
    RetrievalResult,
    RetrievedChunk,
    RetrievedDocument,
)
from aireliability.rag.observability_bridge import RAGObservabilityBridge
from aireliability.rag.optimization_bridge import RAGOptimizationBridge
from aireliability.rag.test_bridge import RAGTestBridge


def _create_sample_run(has_failures: bool = True) -> RAGRun:
    q = RAGQuery(text="Sample query")
    doc = RetrievedDocument(
        document_id="doc_1", title="Doc 1", text="Sample text", source="kb_test"
    )
    chk = RetrievedChunk(
        chunk_id="chk_1",
        document_id="doc_1",
        text="Sample text",
        rank=1,
        retrieval_score=0.9,
    )
    claim = Claim(
        claim_id="clm_1",
        text="Sample text",
        importance=ClaimImportance.CRITICAL,
        support_status=ClaimSupportStatus.SUPPORTED,
    )
    cit = Citation(
        citation_id="cit_1",
        marker="[1]",
        cited_chunk_id="chk_1",
        status=CitationStatus.VALID,
    )

    fails = []
    if has_failures:
        fails.append(
            RAGFailure(
                stage=RAGStage.RETRIEVAL,
                category=RAGFailureCategory.LOW_RECALL,
                message="Retrieval candidate pool recall below threshold",
                affected_component="vector_retriever",
            )
        )

    return RAGRun(
        query=q,
        retrieval_result=RetrievalResult(
            retrieved_documents=[doc], retrieved_chunks=[chk]
        ),
        generated_answer=GeneratedAnswer(text="Sample text [1]."),
        claims=[claim],
        citations=[cit],
        failures=fails,
    )


def test_rag_intelligence_bridge() -> None:
    """Test Phase 34 failure clustering and recommendation generation."""
    bridge = RAGIntelligenceBridge()
    run = _create_sample_run(has_failures=True)

    clusters, recommendations = bridge.process_rag_failures([run])
    assert len(clusters) >= 1
    assert any(
        "retrieval" in c.cluster_id.lower() or "rag" in c.cluster_id.lower()
        for c in clusters
    )
    assert len(recommendations) >= 1


def test_rag_graph_bridge_and_provenance() -> None:
    """Test Phase 35 Knowledge Graph synchronization and provenance tracing."""
    bridge = RAGGraphBridge()
    run = _create_sample_run(has_failures=True)

    bridge.sync_run_to_graph(run)
    graph = bridge.graph

    # Verify query and run nodes were added
    assert graph.get_node(run.run_id) is not None
    assert graph.get_node(run.query.query_id) is not None
    assert graph.get_node("doc_1") is not None

    # Test provenance trace
    prov = bridge.trace_provenance(run, claim_id="clm_1")
    assert prov["run_id"] == run.run_id
    assert prov["query"] == run.query.text
    assert len(prov["evidence_chunks"]) >= 1


def test_rag_test_bridge() -> None:
    """Test Phase 36 automated RAG test generation from failures."""
    test_bridge = RAGTestBridge()
    run = _create_sample_run(has_failures=True)

    suite = test_bridge.generate_rag_tests([run])
    assert suite is not None
    assert len(suite.test_cases) >= 1


def test_rag_healing_bridge() -> None:
    """Test Phase 37 remediation proposal creation."""
    healing_bridge = RAGHealingBridge()
    run = _create_sample_run(has_failures=True)

    proposals = healing_bridge.propose_remediations(run.failures)
    assert len(proposals) >= 1
    assert any(
        "top_k" in p.title.lower() or "retrieval" in p.title.lower() for p in proposals
    )


def test_rag_optimization_bridge() -> None:
    """Test Phase 38 multi-objective optimization problem creation."""
    opt_bridge = RAGOptimizationBridge()
    problem = opt_bridge.create_rag_optimization_problem(target_component="retriever")

    assert problem.problem_id is not None
    assert len(problem.objectives) >= 2
    assert any(v.name == "top_k" for v in problem.variables)


def test_rag_observability_bridge() -> None:
    """Test Prometheus counter incrementing upon RAG run completion."""
    obs_bridge = RAGObservabilityBridge()
    run = _create_sample_run(has_failures=True)

    obs_bridge.record_run(run)
    assert obs_bridge.c_runs.value >= 1
    assert obs_bridge.c_retrieval_fail.value >= 1
