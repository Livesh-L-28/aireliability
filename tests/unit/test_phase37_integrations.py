"""Unit tests for Phase 37 integrations with KnowledgeGraph, Observability, and TestGen."""

from aireliability.core.models import FailureReport
from aireliability.graph.graph import KnowledgeGraph
from aireliability.graph.models import GraphNode, GraphNodeType, GraphRelationship
from aireliability.remediation.integrations import (
    RemediationGraphBridge,
    RemediationObservabilityBridge,
)
from aireliability.remediation.models import (
    RemediationLifecycleState,
    RemediationPatch,
    RemediationProposal,
    RemediationProvenance,
    RepairType,
)
from aireliability.remediation.test_bridge import RemediationTestBridge


def test_remediation_graph_bridge_sync() -> None:
    """RemediationGraphBridge links proposal node and causal edges into KnowledgeGraph."""
    graph = KnowledgeGraph()
    bridge = RemediationGraphBridge()

    # Create source failure node in graph
    fail_node = GraphNode.create(
        node_type=GraphNodeType.FAILURE,
        source_id="fail_123",
        name="Failure 123",
    )
    graph.add_node(fail_node)

    proposal = RemediationProposal(
        title="Prompt Patch",
        repair_type=RepairType.PROMPT,
        state=RemediationLifecycleState.APPROVED,
        patches=[
            RemediationPatch(
                repair_type=RepairType.PROMPT,
                target_component_id="llm_prompt",
                target_component_type="prompt",
            )
        ],
        provenance=RemediationProvenance(source_failure_id="fail_123"),
        generated_test_ids=["gen_test_1"],
    )

    node = bridge.record_remediation(graph, proposal)
    assert node.node_id == f"recommendation:{proposal.proposal_id}"
    assert node.node_type == GraphNodeType.RECOMMENDATION
    assert graph.has_node(node.node_id) is True

    # Check edge from failure to remediation
    edges = graph.list_edges(
        source_node_id=fail_node.node_id, target_node_id=node.node_id
    )
    assert len(edges) == 1
    assert edges[0].relationship_type == GraphRelationship.RECOMMENDS


def test_observability_bridge_records_metrics() -> None:
    """RemediationObservabilityBridge updates metric counters across lifecycle steps."""
    bridge = RemediationObservabilityBridge()
    proposal = RemediationProposal(
        title="Test Proposal",
        repair_type=RepairType.TOOL,
    )

    bridge.record_proposal_created(proposal)
    assert bridge.metrics["proposals_total"] == 1

    bridge.record_approval(proposal)
    assert bridge.metrics["approvals_total"] == 1

    bridge.record_rollout(proposal)
    assert bridge.metrics["rollouts_total"] == 1

    bridge.record_promotion(proposal)
    assert bridge.metrics["promotions_total"] == 1


def test_test_generation_bridge_synthesizes_tests() -> None:
    """RemediationTestBridge generates Phase 36 verification test cases."""
    bridge = RemediationTestBridge()
    proposal = RemediationProposal(
        title="RAG Retrieval Fix",
        description="Top-k increased to fix missing documentation",
        repair_type=RepairType.RETRIEVAL,
        patches=[
            RemediationPatch(
                repair_type=RepairType.RETRIEVAL,
                target_component_id="doc_retriever",
                target_component_type="retriever",
            )
        ],
    )
    evidence = FailureReport(
        failure_id="fail_ret_1",
        trace_id="tr_ret_1",
        category="retrieval",
        message="retrieval failure: doc not found",
    )

    tests = bridge.generate_verification_tests(proposal, evidence=evidence, max_tests=3)
    assert len(tests) > 0
    assert len(proposal.generated_test_ids) == len(tests)
    assert proposal.generated_test_ids[0] == tests[0].test_id
