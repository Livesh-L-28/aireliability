"""Knowledge Graph synchronization and historical experiment retrieval for Phase 38."""

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
from aireliability.optimization.models import (
    OptimizationProblem,
    OptimizationResult,
)

logger = logging.getLogger(__name__)


class OptimizationGraphBridge:
    """Synchronizes optimization runs, candidates, and Pareto solutions with the Knowledge Graph."""

    def __init__(self, graph: KnowledgeGraph | None = None) -> None:
        self.graph = graph

    def sync_optimization_result(
        self,
        result: OptimizationResult,
        graph: KnowledgeGraph | None = None,
    ) -> None:
        """Persist the optimization run, candidates, and relationships into KnowledgeGraph."""
        target_graph = graph or self.graph
        if not target_graph:
            return

        run_id = result.optimization_id

        # 1. Optimization Run Node (EXPERIMENT)
        run_node = GraphNode.create(
            node_type=GraphNodeType.EXPERIMENT,
            source_id=run_id,
            name=f"Optimization Run {run_id}",
            tags=["type:optimization_run", f"reason:{result.stopping_reason.value}"],
            metadata={
                "duration_seconds": result.duration_seconds,
                "confidence": result.confidence,
                "candidates_count": len(result.candidates),
                "pareto_size": len(result.pareto_frontier.non_dominated_candidate_ids),
                "dataset_id": result.problem.dataset_id,
                "model_version": result.problem.model_version,
            },
        )
        target_graph.add_node(run_node)

        # 2. Baseline Node
        base_fp = result.baseline_config.fingerprint or "default_baseline"
        base_node = GraphNode.create(
            node_type=GraphNodeType.BASELINE,
            source_id=base_fp,
            name=f"Baseline {base_fp}",
            tags=["type:baseline"],
            metadata={"configuration": result.baseline_config.values},
        )
        target_graph.add_node(base_node)

        # Edge: Baseline -> CONTAINS -> Run
        target_graph.add_edge(
            GraphEdge.create(
                source_node_id=base_node.node_id,
                target_node_id=run_node.node_id,
                relationship_type=GraphRelationship.CONTAINS,
                metadata={"role": "baseline_for_run"},
            )
        )

        # 3. Synchronize Candidates and Edges
        for cand in result.candidates:
            cand_node = GraphNode.create(
                node_type=GraphNodeType.EXPERIMENT,
                source_id=cand.candidate_id,
                name=f"Candidate {cand.candidate_id}",
                tags=[
                    "type:candidate",
                    f"pareto:{cand.is_pareto}",
                    f"feasible:{cand.is_feasible}",
                    f"strategy:{cand.generation_strategy}",
                ],
                confidence=cand.confidence,
                metadata={
                    "fingerprint": cand.fingerprint,
                    "configuration": cand.configuration.values,
                    "objective_values": cand.objective_values,
                    "crowding_distance": cand.crowding_distance,
                    "is_selected": cand.candidate_id
                    == (
                        result.selected_candidate.candidate_id
                        if result.selected_candidate
                        else None
                    ),
                },
            )
            target_graph.add_node(cand_node)

            # Edge: Run -> PRODUCED -> Candidate
            target_graph.add_edge(
                GraphEdge.create(
                    source_node_id=run_node.node_id,
                    target_node_id=cand_node.node_id,
                    relationship_type=GraphRelationship.PRODUCED,
                    metadata={"strategy": cand.generation_strategy},
                )
            )

            # Edge: Candidate -> DERIVED_FROM -> Baseline
            target_graph.add_edge(
                GraphEdge.create(
                    source_node_id=cand_node.node_id,
                    target_node_id=base_node.node_id,
                    relationship_type=GraphRelationship.DERIVED_FROM,
                )
            )

            # Link candidate to metrics
            for metric_name, val in cand.objective_values.items():
                m_node = GraphNode.create(
                    node_type=GraphNodeType.METRIC,
                    source_id=metric_name,
                    name=f"Metric: {metric_name}",
                    tags=["type:metric"],
                )
                target_graph.add_node(m_node)

                target_graph.add_edge(
                    GraphEdge.create(
                        source_node_id=cand_node.node_id,
                        target_node_id=m_node.node_id,
                        relationship_type=GraphRelationship.MEASURED_BY,
                        metadata={"value": val},
                    )
                )

        logger.info(
            "Synchronized optimization run %s (%d candidates) into KnowledgeGraph",
            run_id,
            len(result.candidates),
        )

    def query_historical_candidates(
        self,
        problem: OptimizationProblem,
        graph: KnowledgeGraph | None = None,
    ) -> list[dict[str, Any]]:
        """Query knowledge graph for past successful candidate configurations."""
        target_graph = graph or self.graph
        if not target_graph:
            return []

        historical: list[dict[str, Any]] = []
        for node in target_graph.list_nodes():
            if "type:candidate" in node.tags and any(
                "pareto:true" in t.lower() for t in node.tags
            ):
                cfg = node.metadata.get("configuration")
                if cfg:
                    historical.append(
                        {
                            "node_id": node.node_id,
                            "configuration": cfg,
                            "confidence": node.confidence,
                            "objective_values": node.metadata.get(
                                "objective_values", {}
                            ),
                        }
                    )

        return historical
