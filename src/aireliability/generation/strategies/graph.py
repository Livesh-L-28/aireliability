"""KnowledgeGraph-driven test generation identifying failing paths and high-impact components."""

from __future__ import annotations

from typing import Any

from aireliability.generation.models import (
    GeneratedTest,
    GenerationSourceType,
    GenerationStrategy,
    TestGenerationConfig,
    TestPriority,
    TestProvenance,
    TestRiskLevel,
    TestType,
)
from aireliability.graph.graph import KnowledgeGraph
from aireliability.graph.models import GraphNodeType


class GraphTestGenerator:
    """Generates tests targeting high-impact failure paths and unhedged components in KnowledgeGraph."""

    strategy = GenerationStrategy.GRAPH_DRIVEN

    def generate(
        self,
        source: Any,
        config: TestGenerationConfig,
    ) -> list[GeneratedTest]:
        if not isinstance(source, KnowledgeGraph):
            return []

        tests: list[GeneratedTest] = []
        graph: KnowledgeGraph = source

        # 1. Inspect failure nodes and their connected components
        failure_nodes = graph.list_nodes(node_type=GraphNodeType.FAILURE)
        for f_node in failure_nodes:
            if len(tests) >= config.max_candidates:
                break

            # Find incident / connected paths
            neighbors = graph.neighbors(f_node.node_id, direction="both")
            path = [f_node.node_id] + [
                n.node_id for n in neighbors[: config.max_graph_depth]
            ]

            comp_names = [
                n.name or n.node_id
                for n in neighbors
                if n.node_type
                in (
                    GraphNodeType.MODEL,
                    GraphNodeType.PROMPT,
                    GraphNodeType.TOOL,
                    GraphNodeType.RETRIEVER,
                )
            ]
            target_desc = ", ".join(comp_names) if comp_names else f_node.name

            prov = TestProvenance(
                source_type=GenerationSourceType.GRAPH_PATH,
                source_id=f_node.node_id,
                source_failure_id=f_node.source_id,
                source_graph_node=f_node.node_id,
                source_graph_path=path,
                generator_name="GraphTestGenerator",
                deterministic_seed=config.deterministic_seed,
                rationale=f"Graph path through {len(path)} nodes targeting failing component '{target_desc}'",
                metadata={"neighbors_count": len(neighbors)},
            )

            test_type = TestType.INTEGRATION
            if any(n.node_type == GraphNodeType.TOOL for n in neighbors):
                test_type = TestType.AGENT
            elif any(n.node_type == GraphNodeType.RETRIEVER for n in neighbors):
                test_type = TestType.RAG

            criteria = [
                f"must prevent cascading failure along path: {' -> '.join(path[:3])}",
                f"must verify health of component '{target_desc}'",
            ]

            t = GeneratedTest(
                name=f"graph_guard_{f_node.node_id.replace(':', '_')}",
                test_type=test_type,
                strategy=self.strategy,
                input=f"End-to-end traversal query validating path: {' -> '.join(path[:3])}",
                expected_output=None,
                expected_criteria=criteria,
                reference_answer=None,
                has_ground_truth=False,
                provenance=prov,
                confidence=f_node.confidence,
                risk_level=TestRiskLevel.HIGH
                if "critical" in f_node.tags
                else TestRiskLevel.MEDIUM,
                priority=TestPriority.HIGH,
                tags=["graph_driven"] + [f"component:{c}" for c in comp_names],
                metadata={"graph_path": path, "target_components": comp_names},
                deterministic_seed=config.deterministic_seed,
            )
            tests.append(t)

        return tests
