"""Benchmark suite for Knowledge Graph (Phase 35) across insertion, traversal, queries, and diffs."""

from __future__ import annotations

import sys
from pathlib import Path

# Path setup for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aireliability.graph.graph import KnowledgeGraph
from aireliability.graph.models import (
    GraphEdge,
    GraphNode,
    GraphNodeType,
    GraphRelationship,
)
from aireliability.graph.serialization import GraphSerializer, diff_graphs
from benchmarks.benchmark_config import BenchmarkConfig
from benchmarks.benchmark_utils import BenchmarkMetric, measure_benchmark


def create_populated_graph(node_count: int) -> KnowledgeGraph:
    """Generate a deterministic synthetic graph with nodes and directed edges."""
    kg = KnowledgeGraph()
    types = [
        GraphNodeType.MODEL,
        GraphNodeType.PROMPT,
        GraphNodeType.FAILURE,
        GraphNodeType.EVALUATION,
        GraphNodeType.AGENT,
    ]
    # Insert nodes
    for i in range(node_count):
        node = GraphNode(
            node_id=f"node_{i:06d}",
            node_type=types[i % len(types)],
            name=f"Node {i}",
            metadata={"index": i, "cluster": i % 10},
        )
        kg.add_node(node)

    # Insert edges (each node connects to the next and to a cluster hub)
    for i in range(node_count - 1):
        edge1 = GraphEdge(
            edge_id=f"edge_seq_{i:06d}",
            source_node_id=f"node_{i:06d}",
            target_node_id=f"node_{i + 1:06d}",
            relationship_type=GraphRelationship.DEPENDS_ON,
        )
        kg.add_edge(edge1)

        hub_id = (i // 10) * 10
        if hub_id != i:
            edge2 = GraphEdge(
                edge_id=f"edge_hub_{i:06d}",
                source_node_id=f"node_{i:06d}",
                target_node_id=f"node_{hub_id:06d}",
                relationship_type=GraphRelationship.CAUSED,
            )
            kg.add_edge(edge2)

    return kg


def run_graph_benchmarks(config: BenchmarkConfig) -> list[BenchmarkMetric]:
    metrics: list[BenchmarkMetric] = []

    # 1. Node Insertion (1,000 nodes into fresh graph)
    def bench_node_insertion_1000() -> None:
        kg = KnowledgeGraph()
        for i in range(1000):
            node = GraphNode(
                node_id=f"bench_node_{i}",
                node_type=GraphNodeType.MODEL,
                name=f"Component {i}",
            )
            kg.add_node(node)

    metrics.append(
        measure_benchmark(
            operation="graph_node_insertion_1000",
            target_func=bench_node_insertion_1000,
            input_size="1,000 nodes",
            iterations=config.iterations,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("graph_insertion"),
            seed=config.seed,
        )
    )

    # Pre-build graph instances for queries, lookups, and traversals
    kg_100 = create_populated_graph(100)
    kg_1000 = create_populated_graph(1000)

    # 2. Indexed Node Lookup (1,000 lookups in kg_1000)
    def bench_indexed_lookup_1000() -> None:
        for i in range(1000):
            _ = kg_1000.get_node(f"node_{i:06d}")

    metrics.append(
        measure_benchmark(
            operation="graph_indexed_lookup_1000",
            target_func=bench_indexed_lookup_1000,
            input_size="1,000 lookups in 1k-node graph",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("graph_traversal"),
            seed=config.seed,
        )
    )

    # 3. Graph Traversal (Breadth-First search from root)
    def bench_traversal_bfs_1000() -> None:
        _ = kg_1000.traversal.bfs(start_node_id="node_000000", max_depth=5)

    metrics.append(
        measure_benchmark(
            operation="graph_bfs_traversal_depth5",
            target_func=bench_traversal_bfs_1000,
            input_size="1,000-node graph bfs max_depth=5",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("graph_traversal"),
            seed=config.seed,
        )
    )

    # 4. Filtered Graph Query
    def bench_graph_query() -> None:
        _ = kg_1000.query.find_nodes(node_type=GraphNodeType.MODEL)

    metrics.append(
        measure_benchmark(
            operation="graph_filtered_query",
            target_func=bench_graph_query,
            input_size="1,000 nodes filter by type",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("graph_traversal"),
            seed=config.seed,
        )
    )

    # 5. Impact Analysis (blast radius traversal)
    def bench_graph_impact() -> None:
        _ = kg_1000.impact_analyzer.analyze(node_id="node_000000", max_depth=4)

    metrics.append(
        measure_benchmark(
            operation="graph_impact_analysis",
            target_func=bench_graph_impact,
            input_size="1,000 nodes blast radius depth 4",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("graph_traversal"),
            seed=config.seed,
        )
    )

    # 6. Provenance Tracing
    def bench_provenance_trace() -> None:
        _ = kg_1000.provenance.trace_origin(node_id="node_000050", max_depth=5)

    metrics.append(
        measure_benchmark(
            operation="graph_provenance_trace",
            target_func=bench_provenance_trace,
            input_size="1,000 nodes trace origin depth 5",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("graph_traversal"),
            seed=config.seed,
        )
    )

    # 7. Serialization (100 nodes to JSON)
    def bench_serialization_100() -> None:
        _ = GraphSerializer.to_json(kg_100)

    metrics.append(
        measure_benchmark(
            operation="graph_serialization_100",
            target_func=bench_serialization_100,
            input_size="100 nodes graph serialization",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("graph_serialization"),
            seed=config.seed,
        )
    )

    # 8. Graph Diff
    kg_100_modified = create_populated_graph(100)
    kg_100_modified.add_node(
        GraphNode(
            node_id="node_extra",
            node_type=GraphNodeType.FAILURE,
            name="Extra Failure",
        )
    )

    def bench_graph_diff_100() -> None:
        _ = diff_graphs(kg_100, kg_100_modified)

    metrics.append(
        measure_benchmark(
            operation="graph_diff_100",
            target_func=bench_graph_diff_100,
            input_size="100 vs 101 nodes diff",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("graph_traversal"),
            seed=config.seed,
        )
    )

    return metrics


if __name__ == "__main__":
    cfg = BenchmarkConfig.from_mode("quick")
    res = run_graph_benchmarks(cfg)
    for m in res:
        print(
            f"[{m.status}] {m.operation}: p50={m.median_latency_ms}ms, p95={m.p95_latency_ms}ms, throughput={m.throughput_ops} ops/s"
        )
