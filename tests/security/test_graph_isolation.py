"""Knowledge graph boundary and multi-tenant traversal isolation tests."""

from __future__ import annotations

from aireliability.graph.graph import KnowledgeGraph
from aireliability.graph.models import (
    GraphEdge,
    GraphNode,
    GraphNodeType,
    GraphRelationship,
)
from aireliability.graph.query import GraphQuery


def test_graph_node_and_edge_direct_lookup_isolation():
    """Verify get_node and has_node prevent direct ID lookup across tenant boundaries."""
    kg = KnowledgeGraph()

    node_a = GraphNode(
        node_id="prompt_template_A",
        name="Tenant A Prompt",
        node_type=GraphNodeType.PROMPT,
        tenant_id="tenant_A",
        metadata={"content": "Top secret prompt for Tenant A"},
    )
    node_b = GraphNode(
        node_id="prompt_template_B",
        name="Tenant B Prompt",
        node_type=GraphNodeType.PROMPT,
        tenant_id="tenant_B",
        metadata={"content": "Top secret prompt for Tenant B"},
    )

    kg.add_node(node_a)
    kg.add_node(node_b)

    # 1. Tenant A accesses its own node
    assert kg.get_node("prompt_template_A", tenant_id="tenant_A") is not None
    assert kg.has_node("prompt_template_A", tenant_id="tenant_A") is True

    # 2. Tenant A attempts direct ID access to Tenant B node -> Blocked (None / False)
    assert kg.get_node("prompt_template_B", tenant_id="tenant_A") is None
    assert kg.has_node("prompt_template_B", tenant_id="tenant_A") is False

    # 3. Tenant B accesses its own node
    assert kg.get_node("prompt_template_B", tenant_id="tenant_B") is not None


def test_graph_traversal_cannot_cross_boundaries():
    """Verify traversal (neighbors, successors, predecessors) stops at tenant boundary."""
    kg = KnowledgeGraph()

    # Create nodes
    a1 = GraphNode(
        node_id="a1", name="A1", node_type=GraphNodeType.AGENT, tenant_id="tenant_A"
    )
    a2 = GraphNode(
        node_id="a2", name="A2", node_type=GraphNodeType.TOOL, tenant_id="tenant_A"
    )
    b1 = GraphNode(
        node_id="b1", name="B1", node_type=GraphNodeType.AGENT, tenant_id="tenant_B"
    )

    kg.add_node(a1)
    kg.add_node(a2)
    kg.add_node(b1)

    # Edge within Tenant A
    edge_a = GraphEdge(
        source_node_id="a1",
        target_node_id="a2",
        relationship_type=GraphRelationship.USED_TOOL,
        tenant_id="tenant_A",
    )
    kg.add_edge(edge_a)

    # Cross-tenant edge linking A1 -> B1
    edge_ab = GraphEdge(
        source_node_id="a1",
        target_node_id="b1",
        relationship_type=GraphRelationship.RELATED_TO,
        tenant_id="tenant_B",
    )
    kg.add_edge(edge_ab)

    # 1. Neighbors query for Tenant A from a1 must ONLY yield A2, NEVER B1
    neighbors_a = [n.node_id for n in kg.neighbors("a1", tenant_id="tenant_A")]
    assert "a2" in neighbors_a
    assert "b1" not in neighbors_a

    # 2. Successors query for Tenant A from a1
    successors_a = [n.node_id for n in kg.successors("a1", tenant_id="tenant_A")]
    assert "a2" in successors_a
    assert "b1" not in successors_a

    # 3. Predecessors query for Tenant B from b1
    predecessors_b = [n.node_id for n in kg.predecessors("b1", tenant_id="tenant_B")]
    assert "a1" not in predecessors_b


def test_graph_query_engine_filtering():
    """Verify GraphQueryEngine filters all searches strictly by tenant boundary."""
    kg = KnowledgeGraph()

    kg.add_node(
        GraphNode(
            node_id="a_eval",
            name="Eval A",
            node_type=GraphNodeType.EVALUATION,
            tenant_id="tenant_A",
        )
    )
    kg.add_node(
        GraphNode(
            node_id="b_eval",
            name="Eval B",
            node_type=GraphNodeType.EVALUATION,
            tenant_id="tenant_B",
        )
    )

    query = GraphQuery(kg)

    # Query for all evaluation nodes as Tenant A
    results_a = query.find_nodes(
        node_type=GraphNodeType.EVALUATION, tenant_id="tenant_A"
    )
    assert len(results_a) == 1
    assert results_a[0].node_id == "a_eval"

    # Query for all evaluation nodes as Tenant B
    results_b = query.find_nodes(
        node_type=GraphNodeType.EVALUATION, tenant_id="tenant_B"
    )
    assert len(results_b) == 1
    assert results_b[0].node_id == "b_eval"


def test_subgraph_and_serialization_isolation():
    """Verify subgraph extraction does not contain nodes from foreign tenants."""
    kg = KnowledgeGraph()

    kg.add_node(
        GraphNode(
            node_id="n1",
            name="Node 1",
            node_type=GraphNodeType.DATASET,
            tenant_id="tenant_alpha",
        )
    )
    kg.add_node(
        GraphNode(
            node_id="n2",
            name="Node 2",
            node_type=GraphNodeType.DATASET,
            tenant_id="tenant_beta",
        )
    )

    # Extract subgraph for tenant alpha
    sub = kg.subgraph(["n1", "n2"], tenant_id="tenant_alpha")
    assert sub.has_node("n1") is True
    assert sub.has_node("n2") is False
    assert len(sub.list_nodes(tenant_id="tenant_alpha")) == 1
