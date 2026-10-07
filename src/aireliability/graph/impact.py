"""Graph-based impact analysis, blast radius calculation, and risk propagation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aireliability.graph.models import (
    GraphImpactReport,
    GraphNode,
    GraphNodeType,
)

if TYPE_CHECKING:
    from aireliability.graph.graph import KnowledgeGraph


class GraphImpactAnalyzer:
    """Computes downstream blast radius, affected components, and failure propagation from a node."""

    def __init__(self, graph: KnowledgeGraph) -> None:
        self.graph = graph

    def analyze(self, node_id: str, max_depth: int = 8) -> GraphImpactReport:
        """Perform comprehensive downstream impact assessment for the given root node."""
        root_node = self.graph.get_node(node_id)
        if not root_node:
            raise KeyError(f"Root node '{node_id}' not found in knowledge graph.")

        # Traverse downstream (outgoing edges) and dependent users
        reachable_map: dict[str, GraphNode] = {}
        for n in self.graph.traversal.bfs(
            node_id, max_depth=max_depth, direction="outgoing"
        ):
            reachable_map[n.node_id] = n

        # Also inspect incoming users (e.g., evaluations or executions using this component)
        users = self.graph.predecessors(node_id)
        for user in users:
            if user.node_id not in reachable_map:
                reachable_map[user.node_id] = user
                for downstream in self.graph.traversal.bfs(
                    user.node_id, max_depth=max(1, max_depth - 1), direction="outgoing"
                ):
                    reachable_map[downstream.node_id] = downstream

        reachable = list(reachable_map.values())

        affected_node_types: dict[str, int] = {}
        severity_dist: dict[str, int] = {}
        failures: int = 0
        regressions: int = 0
        incidents: int = 0
        safety_critical: bool = False
        security_critical: bool = False
        evidence_list: list[dict[str, Any]] = []
        recommendations: list[str] = []

        # Check root node metadata
        if root_node.metadata.get("severity"):
            sev = str(root_node.metadata.get("severity")).lower()
            severity_dist[sev] = severity_dist.get(sev, 0) + 1

        for node in reachable:
            ntype = node.node_type.value
            affected_node_types[ntype] = affected_node_types.get(ntype, 0) + 1

            meta = node.metadata or {}
            sev = meta.get("severity") or meta.get("priority")
            if sev:
                sev_key = str(sev).lower()
                severity_dist[sev_key] = severity_dist.get(sev_key, 0) + 1

            # Count special reliability entities
            if node.node_type == GraphNodeType.FAILURE:
                failures += 1
                is_crit = (
                    meta.get("critical")
                    or str(meta.get("severity", "")).upper() in ("CRITICAL", "HIGH")
                    or "critical" in node.tags
                    or "high" in node.tags
                )
                if is_crit:
                    if (
                        "security" in node.tags
                        or meta.get("category") == "security"
                        or "security" in meta
                    ):
                        security_critical = True
                    if (
                        "safety" in node.tags
                        or meta.get("category") == "safety"
                        or "safety" in meta
                    ):
                        safety_critical = True

            elif node.node_type == GraphNodeType.REGRESSION:
                regressions += 1

            elif node.node_type == GraphNodeType.INCIDENT:
                incidents += 1
                if meta.get("severity") in ("P0", "P1", "CRITICAL", "critical"):
                    safety_critical = True

            elif node.node_type == GraphNodeType.RECOMMENDATION:
                rec_title = node.name or meta.get("title") or "Recommended mitigation"
                if rec_title not in recommendations:
                    recommendations.append(str(rec_title))

            # Collect evidence references
            if "evidence" in meta:
                evidence_list.append(
                    {"node_id": node.node_id, "evidence": meta["evidence"]}
                )

        # Find paths to high-impact nodes (Failures, Regressions, Incidents)
        impact_paths: list[list[str]] = []
        target_types = {
            GraphNodeType.FAILURE,
            GraphNodeType.REGRESSION,
            GraphNodeType.INCIDENT,
        }
        high_impact_nodes = [n for n in reachable if n.node_type in target_types]

        for target in high_impact_nodes[:10]:  # Limit top 10 impact paths
            path = self.graph.traversal.find_path(
                node_id, target.node_id, max_depth=max_depth
            )
            if path:
                impact_paths.append(path)

        # Calculate normalized impact score [0.0, 1.0]
        # Weighting: incidents (0.4), failures (0.25), regressions (0.2), affected count (0.15)
        raw_score = (
            min(incidents * 0.35, 0.40)
            + min(failures * 0.05, 0.25)
            + min(regressions * 0.10, 0.20)
            + min(len(reachable) * 0.02, 0.15)
        )
        if safety_critical or security_critical:
            raw_score = min(1.0, raw_score + 0.25)
        impact_score = round(min(1.0, max(0.0, raw_score)), 3)

        return GraphImpactReport(
            root_node_id=root_node.node_id,
            root_node_type=root_node.node_type,
            affected_nodes_count=len(reachable),
            affected_node_types=affected_node_types,
            severity_distribution=severity_dist,
            failure_count=failures,
            regression_count=regressions,
            incident_count=incidents,
            safety_critical=safety_critical,
            security_critical=security_critical,
            impact_score=impact_score,
            impact_paths=impact_paths,
            supporting_evidence=evidence_list,
            recommendations=recommendations,
            metadata={"evaluation_depth": max_depth},
        )

    def compute_blast_radius(self, node_id: str, max_depth: int = 5) -> float:
        """Compute relative blast radius as proportion of total graph nodes reachable downstream."""
        total_nodes = self.graph.node_count
        if total_nodes <= 1:
            return 0.0

        reachable = self.graph.traversal.bfs(
            node_id, max_depth=max_depth, direction="outgoing"
        )
        return round(len(reachable) / (total_nodes - 1), 4)

    def find_critical_paths(self, node_id: str) -> list[list[str]]:
        """Identify paths leading to critical safety, security, or incident events."""
        critical_paths: list[list[str]] = []
        reachable = self.graph.traversal.bfs(node_id, max_depth=6, direction="outgoing")

        for node in reachable:
            if node.node_type in (GraphNodeType.INCIDENT, GraphNodeType.FAILURE):
                meta = node.metadata or {}
                if (
                    meta.get("severity") in ("CRITICAL", "P0", "P1")
                    or "security" in node.tags
                ):
                    path = self.graph.traversal.find_path(node_id, node.node_id)
                    if path:
                        critical_paths.append(path)

        return critical_paths
