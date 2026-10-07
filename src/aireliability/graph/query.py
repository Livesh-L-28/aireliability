"""Graph query engine providing semantic, relational, and reliability-focused lookups."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from aireliability.graph.models import (
    GraphEdge,
    GraphImpactReport,
    GraphNode,
    GraphNodeType,
    GraphRelationship,
)

if TYPE_CHECKING:
    from aireliability.graph.graph import KnowledgeGraph


class GraphQuery:
    """High-level query interface answering complex AI reliability questions."""

    def __init__(self, graph: KnowledgeGraph) -> None:
        self.graph = graph

    # -------------------------------------------------------------------------
    # Primitive Lookups
    # -------------------------------------------------------------------------

    def find_nodes(
        self,
        node_type: GraphNodeType | None = None,
        tags: Sequence[str] | None = None,
        name: str | None = None,
        tenant_id: str | None = None,
    ) -> list[GraphNode]:
        """Query nodes matching type, tag, or substring name criteria within tenant boundary."""
        nodes = self.graph.list_nodes(
            node_type=node_type, tags=tags, tenant_id=tenant_id
        )
        if name is not None:
            name_lower = name.lower()
            return [n for n in nodes if name_lower in n.name.lower()]
        return nodes

    def find_by_id(
        self, node_id: str, tenant_id: str | None = None
    ) -> GraphNode | None:
        """Fetch node directly by ID, respecting tenant boundary."""
        return self.graph.get_node(node_id, tenant_id=tenant_id)

    def find_neighbors(
        self,
        node_id: str,
        direction: str = "both",
        relationship_type: GraphRelationship | None = None,
        tenant_id: str | None = None,
    ) -> list[GraphNode]:
        """Fetch neighboring nodes within tenant boundary."""
        return self.graph.neighbors(
            node_id=node_id,
            direction=direction,
            relationship_type=relationship_type,
            tenant_id=tenant_id,
        )

    def find_relationships(
        self,
        source_id: str | None = None,
        target_id: str | None = None,
        relationship_type: GraphRelationship | None = None,
        tenant_id: str | None = None,
    ) -> list[GraphEdge]:
        """Query edge relationships matching source, target, or type filters within tenant boundary."""
        edges = self.graph.list_edges(
            relationship_type=relationship_type,
            source_node_id=source_id,
            target_node_id=target_id,
        )
        if tenant_id:
            edges = [
                e
                for e in edges
                if (getattr(e, "tenant_id", None) or e.metadata.get("tenant_id"))
                == tenant_id
            ]
        return edges

    # -------------------------------------------------------------------------
    # Domain Reliability Lookups
    # -------------------------------------------------------------------------

    def _resolve_node_id(self, identifier: str, node_type: GraphNodeType) -> str | None:
        """Resolve a bare identifier or typed ID to an existing node_id in the graph."""
        if self.graph.has_node(identifier):
            return identifier

        typed_id = f"{node_type.value.lower()}:{identifier}"
        if self.graph.has_node(typed_id):
            return typed_id

        # Search by name or source_id
        for node in self.graph.list_nodes(node_type=node_type):
            if node.name == identifier or node.source_id == identifier:
                return node.node_id

        return None

    def find_failures_for_model(self, model: str) -> list[GraphNode]:
        """Identify all failure nodes associated with a model."""
        m_id = self._resolve_node_id(model, GraphNodeType.MODEL)
        if not m_id:
            return []

        # Follow evaluations associated with this model (USED_MODEL incoming, or EVALUATED outgoing/incoming)
        eval_ids: set[str] = set()
        for e in self.graph.list_edges(
            target_node_id=m_id, relationship_type=GraphRelationship.USED_MODEL
        ):
            eval_ids.add(e.source_node_id)
        for e in self.graph.list_edges(
            source_node_id=m_id, relationship_type=GraphRelationship.EVALUATED
        ):
            eval_ids.add(e.target_node_id)
        for e in self.graph.list_edges(
            target_node_id=m_id, relationship_type=GraphRelationship.EVALUATED
        ):
            eval_ids.add(e.source_node_id)

        failures: dict[str, GraphNode] = {}

        # 1. Direct failures from evaluations
        for eid in eval_ids:
            for f_node in self.graph.successors(
                eid, relationship_type=GraphRelationship.FAILED
            ):
                failures[f_node.node_id] = f_node
            for n in self.graph.traversal.bfs(eid, max_depth=2, direction="outgoing"):
                if n.node_type == GraphNodeType.FAILURE:
                    failures[n.node_id] = n

        # 2. Correlated or affected failures
        for edge in self.graph.list_edges(source_node_id=m_id):
            target = self.graph.get_node(edge.target_node_id)
            if target and target.node_type == GraphNodeType.FAILURE:
                failures[target.node_id] = target

        return list(failures.values())

    def find_failures_for_prompt(self, prompt: str) -> list[GraphNode]:
        """Identify all failure nodes associated with a prompt template or version."""
        p_id = self._resolve_node_id(prompt, GraphNodeType.PROMPT)
        if not p_id:
            return []

        eval_ids: set[str] = set()
        for e in self.graph.list_edges(
            target_node_id=p_id, relationship_type=GraphRelationship.USED_PROMPT
        ):
            eval_ids.add(e.source_node_id)
        for e in self.graph.list_edges(
            source_node_id=p_id, relationship_type=GraphRelationship.EVALUATED
        ):
            eval_ids.add(e.target_node_id)

        failures: dict[str, GraphNode] = {}
        for eid in eval_ids:
            for f_node in self.graph.successors(
                eid, relationship_type=GraphRelationship.FAILED
            ):
                failures[f_node.node_id] = f_node
            for n in self.graph.traversal.bfs(eid, max_depth=2, direction="outgoing"):
                if n.node_type == GraphNodeType.FAILURE:
                    failures[n.node_id] = n

        for edge in self.graph.list_edges(source_node_id=p_id):
            target = self.graph.get_node(edge.target_node_id)
            if target and target.node_type == GraphNodeType.FAILURE:
                failures[target.node_id] = target

        return list(failures.values())

    def find_failures_for_tool(self, tool: str) -> list[GraphNode]:
        """Identify failures occurring in evaluations or trace steps utilizing a tool."""
        t_id = self._resolve_node_id(tool, GraphNodeType.TOOL)
        if not t_id:
            return []

        users = self.graph.predecessors(
            t_id, relationship_type=GraphRelationship.USED_TOOL
        )
        failures: dict[str, GraphNode] = {}

        for user in users:
            # If user is trace step or trace, traverse to failure
            downstream = self.graph.traversal.bfs(
                user.node_id, max_depth=3, direction="outgoing"
            )
            for node in downstream:
                if node.node_type == GraphNodeType.FAILURE:
                    failures[node.node_id] = node

        return list(failures.values())

    def find_failures_for_retriever(self, retriever: str) -> list[GraphNode]:
        """Identify failures linked to a RAG retriever component."""
        r_id = self._resolve_node_id(retriever, GraphNodeType.RETRIEVER)
        if not r_id:
            return []

        users = self.graph.predecessors(
            r_id, relationship_type=GraphRelationship.USED_RETRIEVER
        )
        failures: dict[str, GraphNode] = {}

        for user in users:
            for f_node in self.graph.successors(
                user.node_id, relationship_type=GraphRelationship.FAILED
            ):
                failures[f_node.node_id] = f_node

        # Also check correlation edges
        for edge in self.graph.list_edges(source_node_id=r_id):
            target = self.graph.get_node(edge.target_node_id)
            if target and target.node_type == GraphNodeType.FAILURE:
                failures[target.node_id] = target

        return list(failures.values())

    def find_regressions_for_dataset(self, dataset: str) -> list[GraphNode]:
        """Find regression events associated with a dataset or its versions."""
        d_id = self._resolve_node_id(dataset, GraphNodeType.DATASET)
        regressions: dict[str, GraphNode] = {}
        if d_id:
            downstream = self.graph.traversal.bfs(
                d_id, max_depth=6, direction="outgoing"
            )
            for n in downstream:
                if n.node_type == GraphNodeType.REGRESSION:
                    regressions[n.node_id] = n

        # Also search by dataset reference in regression metadata or tags
        for n in self.graph.list_nodes(node_type=GraphNodeType.REGRESSION):
            meta = n.metadata or {}
            if (
                meta.get("dataset") == dataset
                or meta.get("dataset_id") == dataset
                or dataset in n.tags
            ):
                regressions[n.node_id] = n

        return list(regressions.values())

    def find_incidents_for_root_cause(self, root_cause: str) -> list[GraphNode]:
        """Find incidents triggered by or linked to a specific root cause."""
        rc_id = self._resolve_node_id(root_cause, GraphNodeType.ROOT_CAUSE)
        if not rc_id:
            return []

        downstream = self.graph.traversal.bfs(rc_id, max_depth=4, direction="outgoing")
        return [n for n in downstream if n.node_type == GraphNodeType.INCIDENT]

    def find_related_failures(self, failure_id: str) -> list[GraphNode]:
        """Find other failures sharing root causes, clusters, or patterns with failure_id."""
        f_id = self._resolve_node_id(failure_id, GraphNodeType.FAILURE)
        if not f_id:
            return []

        # Find root causes, clusters, or patterns of this failure
        intermediate = self.graph.traversal.bfs(f_id, max_depth=2, direction="both")
        connecting_ids = {
            n.node_id
            for n in intermediate
            if n.node_type
            in (
                GraphNodeType.ROOT_CAUSE,
                GraphNodeType.FAILURE_CLUSTER,
                GraphNodeType.PATTERN,
            )
        }

        related_failures: dict[str, GraphNode] = {}
        for cid in connecting_ids:
            for neighbor in self.graph.neighbors(cid):
                if (
                    neighbor.node_type == GraphNodeType.FAILURE
                    and neighbor.node_id != f_id
                ):
                    related_failures[neighbor.node_id] = neighbor

        return list(related_failures.values())

    def find_affected_components(self, source_id: str) -> list[GraphNode]:
        """Identify models, prompts, tools, or retrievers impacted by a source event/cluster."""
        reachable = self.graph.traversal.bfs(
            source_id, max_depth=4, direction="outgoing"
        )
        component_types = {
            GraphNodeType.MODEL,
            GraphNodeType.PROMPT,
            GraphNodeType.TOOL,
            GraphNodeType.RETRIEVER,
            GraphNodeType.RERANKER,
        }
        return [n for n in reachable if n.node_type in component_types]

    def find_evidence(self, identifier: str) -> list[dict[str, Any]]:
        """Retrieve evidence items recorded for a node or edge."""
        # 1. Edge lookup
        edge = self.graph.get_edge(identifier)
        if edge and edge.evidence:
            return [
                {
                    "type": "edge_evidence",
                    "evidence": edge.evidence,
                    "edge_id": edge.edge_id,
                }
            ]

        # 2. Node lookup
        node = self.graph.get_node(identifier)
        if node:
            evidence: list[dict[str, Any]] = []
            if "evidence" in node.metadata:
                evidence.append(
                    {"type": "node_metadata", "evidence": node.metadata["evidence"]}
                )
            if node.provenance:
                evidence.append(
                    {"type": "node_provenance", "provenance": node.provenance}
                )
            return evidence

        return []

    # -------------------------------------------------------------------------
    # High-Level Aggregated Queries
    # -------------------------------------------------------------------------

    def get_model_impact(self, model: str) -> GraphImpactReport:
        """Calculate blast radius and impact report for a model."""
        m_id = self._resolve_node_id(model, GraphNodeType.MODEL)
        if not m_id:
            raise KeyError(f"Model '{model}' not found in knowledge graph.")
        return self.graph.impact_analyzer.analyze(m_id)

    def get_prompt_impact(self, prompt: str) -> GraphImpactReport:
        """Calculate blast radius and impact report for a prompt."""
        p_id = self._resolve_node_id(prompt, GraphNodeType.PROMPT)
        if not p_id:
            raise KeyError(f"Prompt '{prompt}' not found in knowledge graph.")
        return self.graph.impact_analyzer.analyze(p_id)

    def get_retriever_impact(self, retriever: str) -> GraphImpactReport:
        """Calculate blast radius and impact report for a retriever."""
        r_id = self._resolve_node_id(retriever, GraphNodeType.RETRIEVER)
        if not r_id:
            raise KeyError(f"Retriever '{retriever}' not found in knowledge graph.")
        return self.graph.impact_analyzer.analyze(r_id)

    def get_root_cause_history(self, root_cause: str) -> list[dict[str, Any]]:
        """Return chronological timeline of evaluations and failures tied to a root cause."""
        rc_id = self._resolve_node_id(root_cause, GraphNodeType.ROOT_CAUSE)
        if not rc_id:
            return []

        failures = self.graph.predecessors(
            rc_id, relationship_type=GraphRelationship.HAS_ROOT_CAUSE
        )
        history: list[dict[str, Any]] = []

        for f in failures:
            history.append(
                {
                    "failure_id": f.node_id,
                    "failure_name": f.name,
                    "created_at": f.created_at.isoformat(),
                    "severity": f.metadata.get("severity", "MEDIUM"),
                    "environment": f.environment,
                }
            )

        history.sort(key=lambda x: str(x["created_at"]))
        return history

    def get_failure_history(self, failure: str) -> list[dict[str, Any]]:
        """Retrieve lineage and timeline for a recurring or individual failure."""
        f_id = self._resolve_node_id(failure, GraphNodeType.FAILURE)
        if not f_id:
            return []

        node = self.graph.get_node(f_id)
        if not node:
            return []

        evals = self.graph.predecessors(
            f_id, relationship_type=GraphRelationship.FAILED
        )
        root_causes = self.graph.successors(
            f_id, relationship_type=GraphRelationship.HAS_ROOT_CAUSE
        )

        return [
            {
                "failure_id": node.node_id,
                "name": node.name,
                "created_at": node.created_at.isoformat(),
                "evaluations": [e.node_id for e in evals],
                "root_causes": [rc.name for rc in root_causes],
                "metadata": node.metadata,
            }
        ]

    def get_execution_dependencies(self, execution_id: str) -> list[GraphNode]:
        """Fetch all models, prompts, tools, datasets, and retrievers used in an execution."""
        e_id = self._resolve_node_id(execution_id, GraphNodeType.EXECUTION)
        if not e_id:
            return []

        dep_types = {
            GraphNodeType.MODEL,
            GraphNodeType.PROMPT,
            GraphNodeType.TOOL,
            GraphNodeType.RETRIEVER,
            GraphNodeType.DATASET,
            GraphNodeType.TEST_CASE,
        }

        # Neighbors reachable within 2 steps
        neighbors = self.graph.traversal.bfs(e_id, max_depth=2, direction="both")
        return [n for n in neighbors if n.node_type in dep_types]

    def get_incident_context(self, incident: str) -> dict[str, Any]:
        """Aggregate upstream failures, root causes, traces, and recommendations for an incident."""
        inc_id = self._resolve_node_id(incident, GraphNodeType.INCIDENT)
        if not inc_id:
            return {}

        inc_node = self.graph.get_node(inc_id)
        if not inc_node:
            return {}

        upstream = self.graph.traversal.bfs(inc_id, max_depth=4, direction="incoming")
        downstream = self.graph.traversal.bfs(inc_id, max_depth=2, direction="outgoing")

        failures = [n.node_id for n in upstream if n.node_type == GraphNodeType.FAILURE]
        root_causes = [
            n.name for n in upstream if n.node_type == GraphNodeType.ROOT_CAUSE
        ]
        recommendations = [
            n.name for n in downstream if n.node_type == GraphNodeType.RECOMMENDATION
        ]

        return {
            "incident_id": inc_node.node_id,
            "title": inc_node.name,
            "created_at": inc_node.created_at.isoformat(),
            "metadata": inc_node.metadata,
            "associated_failures": failures,
            "root_causes": root_causes,
            "recommendations": recommendations,
        }
