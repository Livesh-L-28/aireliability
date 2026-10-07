"""Unit tests for Phase 35 GraphQuery API and high-level reliability lookups."""

import pytest

from aireliability.graph.graph import KnowledgeGraph
from aireliability.graph.models import (
    GraphEdge,
    GraphNode,
    GraphNodeType,
    GraphRelationship,
)


@pytest.fixture
def populated_query_graph() -> KnowledgeGraph:
    """Construct a connected KnowledgeGraph representing models, prompts, failures, and incidents."""
    kg = KnowledgeGraph()

    # Models & Prompts
    m1 = kg.add_node(GraphNode.create(GraphNodeType.MODEL, "gpt-4o", name="gpt-4o"))
    p1 = kg.add_node(
        GraphNode.create(GraphNodeType.PROMPT, "qa_prompt", name="qa_prompt")
    )
    tool1 = kg.add_node(
        GraphNode.create(GraphNodeType.TOOL, "calculator", name="calculator")
    )
    ret1 = kg.add_node(GraphNode.create(GraphNodeType.RETRIEVER, "bm25", name="bm25"))
    ds1 = kg.add_node(GraphNode.create(GraphNodeType.DATASET, "med_qa", name="med_qa"))

    # Evaluation
    eval1 = kg.add_node(GraphNode.create(GraphNodeType.EVALUATION, "eval_100"))
    kg.add_edge(
        GraphEdge.create(eval1.node_id, m1.node_id, GraphRelationship.USED_MODEL)
    )
    kg.add_edge(
        GraphEdge.create(eval1.node_id, p1.node_id, GraphRelationship.USED_PROMPT)
    )
    kg.add_edge(
        GraphEdge.create(eval1.node_id, ret1.node_id, GraphRelationship.USED_RETRIEVER)
    )

    # Failures & Root causes
    f1 = kg.add_node(
        GraphNode.create(
            GraphNodeType.FAILURE,
            "f1",
            name="Hallucinated symptom",
            metadata={"severity": "HIGH", "evidence": "Reference mismatch on token 45"},
        )
    )
    rc1 = kg.add_node(
        GraphNode.create(
            GraphNodeType.ROOT_CAUSE, "rc_retrieval", name="Retrieval Empty Context"
        )
    )

    kg.add_edge(GraphEdge.create(eval1.node_id, f1.node_id, GraphRelationship.FAILED))
    kg.add_edge(
        GraphEdge.create(
            f1.node_id,
            rc1.node_id,
            GraphRelationship.HAS_ROOT_CAUSE,
            confidence=0.9,
            evidence=["Empty chunks received from retriever"],
        )
    )

    # Regressions & Incidents
    reg1 = kg.add_node(
        GraphNode.create(GraphNodeType.REGRESSION, "reg_med_acc", name="Accuracy Drop")
    )
    kg.add_edge(
        GraphEdge.create(
            eval1.node_id, reg1.node_id, GraphRelationship.CAUSED_REGRESSION
        )
    )
    kg.add_edge(
        GraphEdge.create(ds1.node_id, eval1.node_id, GraphRelationship.CONTAINS)
    )

    inc1 = kg.add_node(
        GraphNode.create(
            GraphNodeType.INCIDENT,
            "inc_001",
            name="Production P0 Failure",
            metadata={"severity": "P0"},
        )
    )
    kg.add_edge(
        GraphEdge.create(rc1.node_id, inc1.node_id, GraphRelationship.TRIGGERED)
    )

    # Execution & Tools
    exec1 = kg.add_node(GraphNode.create(GraphNodeType.EXECUTION, "exec_001"))
    step1 = kg.add_node(GraphNode.create(GraphNodeType.TRACE_STEP, "step_001"))
    kg.add_edge(
        GraphEdge.create(exec1.node_id, step1.node_id, GraphRelationship.CONTAINS)
    )
    kg.add_edge(
        GraphEdge.create(step1.node_id, tool1.node_id, GraphRelationship.USED_TOOL)
    )
    kg.add_edge(GraphEdge.create(step1.node_id, f1.node_id, GraphRelationship.FAILED))

    return kg


def test_find_primitives(populated_query_graph: KnowledgeGraph) -> None:
    """Test primitive find_nodes, find_by_id, and find_neighbors."""
    q = populated_query_graph.query
    nodes = q.find_nodes(node_type=GraphNodeType.MODEL)
    assert len(nodes) == 1
    assert nodes[0].node_id == "model:gpt-4o"

    by_id = q.find_by_id("model:gpt-4o")
    assert by_id is not None
    assert by_id.name == "gpt-4o"

    nbrs = q.find_neighbors("evaluation:eval_100")
    assert len(nbrs) >= 4  # m1, p1, ret1, f1, reg1


def test_find_failures_for_components(populated_query_graph: KnowledgeGraph) -> None:
    """Test finding failures by model, prompt, tool, and retriever."""
    q = populated_query_graph.query

    f_model = q.find_failures_for_model("gpt-4o")
    assert len(f_model) == 1
    assert f_model[0].node_id == "failure:f1"

    f_prompt = q.find_failures_for_prompt("qa_prompt")
    assert len(f_prompt) == 1
    assert f_prompt[0].node_id == "failure:f1"

    f_retriever = q.find_failures_for_retriever("bm25")
    assert len(f_retriever) == 1
    assert f_retriever[0].node_id == "failure:f1"

    f_tool = q.find_failures_for_tool("calculator")
    assert len(f_tool) == 1
    assert f_tool[0].node_id == "failure:f1"


def test_find_regressions_and_incidents(populated_query_graph: KnowledgeGraph) -> None:
    """Test finding regressions for dataset and incidents for root cause."""
    q = populated_query_graph.query

    regs = q.find_regressions_for_dataset("med_qa")
    assert len(regs) == 1
    assert regs[0].node_id == "regression:reg_med_acc"

    incs = q.find_incidents_for_root_cause("rc_retrieval")
    assert len(incs) == 1
    assert incs[0].node_id == "incident:inc_001"


def test_find_evidence(populated_query_graph: KnowledgeGraph) -> None:
    """Test retrieving evidence attached to nodes and edges."""
    q = populated_query_graph.query

    ev_node = q.find_evidence("failure:f1")
    assert len(ev_node) >= 1

    edge_id = "edge:failure:f1->HAS_ROOT_CAUSE->root_cause:rc_retrieval"
    ev_edge = q.find_evidence(edge_id)
    assert len(ev_edge) == 1
    assert ev_edge[0]["evidence"] == ["Empty chunks received from retriever"]


def test_component_impact(populated_query_graph: KnowledgeGraph) -> None:
    """Test get_model_impact and blast radius calculations."""
    q = populated_query_graph.query
    report = q.get_model_impact("gpt-4o")
    assert report.root_node_id == "model:gpt-4o"
    assert report.impact_score >= 0.0


def test_root_cause_and_incident_context(populated_query_graph: KnowledgeGraph) -> None:
    """Test root cause history and incident context aggregation."""
    q = populated_query_graph.query
    rc_hist = q.get_root_cause_history("rc_retrieval")
    assert len(rc_hist) == 1
    assert rc_hist[0]["failure_id"] == "failure:f1"

    inc_ctx = q.get_incident_context("inc_001")
    assert inc_ctx["incident_id"] == "incident:inc_001"
    assert (
        "root_cause:rc_retrieval" in [rc for rc in inc_ctx["root_causes"]]
        or len(inc_ctx["root_causes"]) >= 1
    )
