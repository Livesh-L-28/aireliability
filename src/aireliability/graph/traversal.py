"""Graph traversal engine supporting safe BFS, DFS, path finding, and cycle detection."""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from typing import TYPE_CHECKING

from aireliability.graph.models import GraphNode, GraphNodeType, GraphRelationship

if TYPE_CHECKING:
    from aireliability.graph.graph import KnowledgeGraph


class GraphTraversal:
    """Provides bounded, cycle-safe traversal algorithms over a KnowledgeGraph."""

    def __init__(self, graph: KnowledgeGraph) -> None:
        self.graph = graph

    def bfs(
        self,
        start_node_id: str,
        max_depth: int = 10,
        direction: str = "outgoing",
        relationship_types: Sequence[GraphRelationship] | None = None,
        node_types: Sequence[GraphNodeType] | None = None,
        max_nodes: int = 1000,
    ) -> list[GraphNode]:
        """Perform Breadth-First Search from start_node_id with bounded depth and node limits."""
        start_node = self.graph.get_node(start_node_id)
        if start_node is None:
            return []

        rel_filter = set(relationship_types) if relationship_types else None
        type_filter = set(node_types) if node_types else None

        visited: set[str] = {start_node_id}
        queue: deque[tuple[str, int]] = deque([(start_node_id, 0)])
        result: list[GraphNode] = []

        while queue and len(result) < max_nodes:
            curr_id, depth = queue.popleft()
            curr_node = self.graph.get_node(curr_id)

            if (
                curr_node
                and curr_id != start_node_id
                and (type_filter is None or curr_node.node_type in type_filter)
            ):
                result.append(curr_node)

            if depth >= max_depth:
                continue

            for neighbor in self._get_filtered_neighbors(
                curr_id, direction, rel_filter
            ):
                if neighbor.node_id not in visited:
                    visited.add(neighbor.node_id)
                    queue.append((neighbor.node_id, depth + 1))

        return result

    def dfs(
        self,
        start_node_id: str,
        max_depth: int = 10,
        direction: str = "outgoing",
        relationship_types: Sequence[GraphRelationship] | None = None,
        node_types: Sequence[GraphNodeType] | None = None,
        max_nodes: int = 1000,
    ) -> list[GraphNode]:
        """Perform Depth-First Search from start_node_id with bounded depth and node limits."""
        start_node = self.graph.get_node(start_node_id)
        if start_node is None:
            return []

        rel_filter = set(relationship_types) if relationship_types else None
        type_filter = set(node_types) if node_types else None

        visited: set[str] = {start_node_id}
        stack: list[tuple[str, int]] = [(start_node_id, 0)]
        result: list[GraphNode] = []

        while stack and len(result) < max_nodes:
            curr_id, depth = stack.pop()
            curr_node = self.graph.get_node(curr_id)

            if (
                curr_node
                and curr_id != start_node_id
                and (type_filter is None or curr_node.node_type in type_filter)
            ):
                result.append(curr_node)

            if depth >= max_depth:
                continue

            for neighbor in reversed(
                self._get_filtered_neighbors(curr_id, direction, rel_filter)
            ):
                if neighbor.node_id not in visited:
                    visited.add(neighbor.node_id)
                    stack.append((neighbor.node_id, depth + 1))

        return result

    def find_path(
        self,
        source_node_id: str,
        target_node_id: str,
        max_depth: int = 10,
        direction: str = "outgoing",
        relationship_types: Sequence[GraphRelationship] | None = None,
    ) -> list[str] | None:
        """Find the shortest path (sequence of node_ids) from source to target using BFS."""
        if source_node_id == target_node_id:
            return [source_node_id] if self.graph.has_node(source_node_id) else None

        if not self.graph.has_node(source_node_id) or not self.graph.has_node(
            target_node_id
        ):
            return None

        rel_filter = set(relationship_types) if relationship_types else None
        visited: set[str] = {source_node_id}
        queue: deque[tuple[str, list[str]]] = deque(
            [(source_node_id, [source_node_id])]
        )

        while queue:
            curr_id, path = queue.popleft()

            if len(path) - 1 >= max_depth:
                continue

            for neighbor in self._get_filtered_neighbors(
                curr_id, direction, rel_filter
            ):
                nid = neighbor.node_id
                if nid == target_node_id:
                    return path + [nid]
                if nid not in visited:
                    visited.add(nid)
                    queue.append((nid, path + [nid]))

        return None

    def find_all_paths(
        self,
        source_node_id: str,
        target_node_id: str,
        max_depth: int = 8,
        direction: str = "outgoing",
        relationship_types: Sequence[GraphRelationship] | None = None,
        max_paths: int = 50,
    ) -> list[list[str]]:
        """Find all acyclic paths between source and target up to max_depth."""
        if not self.graph.has_node(source_node_id) or not self.graph.has_node(
            target_node_id
        ):
            return []

        rel_filter = set(relationship_types) if relationship_types else None
        paths: list[list[str]] = []

        def _dfs_paths(curr_id: str, current_path: list[str]) -> None:
            if len(paths) >= max_paths:
                return

            if curr_id == target_node_id:
                paths.append(list(current_path))
                return

            if len(current_path) - 1 >= max_depth:
                return

            for neighbor in self._get_filtered_neighbors(
                curr_id, direction, rel_filter
            ):
                nid = neighbor.node_id
                if nid not in current_path:  # Prevent cycles
                    current_path.append(nid)
                    _dfs_paths(nid, current_path)
                    current_path.pop()

        _dfs_paths(source_node_id, [source_node_id])
        return paths

    def find_cycles(self, max_depth: int = 8, max_cycles: int = 20) -> list[list[str]]:
        """Detect cycles within the directed graph using DFS up to max_depth."""
        cycles: list[list[str]] = []
        visited_global: set[str] = set()

        nodes = self.graph.list_nodes()

        for node in nodes:
            if node.node_id in visited_global or len(cycles) >= max_cycles:
                continue

            path: list[str] = [node.node_id]
            visited_in_path: set[str] = {node.node_id}

            def _detect(
                curr_id: str, current_path: list[str], current_visited: set[str]
            ) -> None:
                if len(cycles) >= max_cycles or len(current_path) > max_depth:
                    return

                for succ in self.graph.successors(curr_id):
                    sid = succ.node_id
                    if sid in current_visited:
                        # Cycle found!
                        cycle_idx = current_path.index(sid)
                        cycle = current_path[cycle_idx:] + [sid]
                        if cycle not in cycles:
                            cycles.append(cycle)
                        return
                    if sid not in visited_global:
                        current_visited.add(sid)
                        current_path.append(sid)
                        _detect(sid, current_path, current_visited)
                        current_path.pop()
                        current_visited.remove(sid)

            _detect(node.node_id, path, visited_in_path)
            visited_global.add(node.node_id)

        return cycles

    def get_reachable_subgraph(
        self,
        start_node_id: str,
        max_depth: int = 5,
        direction: str = "outgoing",
    ) -> KnowledgeGraph:
        """Extract a new KnowledgeGraph induced by all nodes reachable from start_node_id."""
        reachable_nodes = self.bfs(
            start_node_id, max_depth=max_depth, direction=direction
        )
        node_ids = [start_node_id] + [n.node_id for n in reachable_nodes]
        return self.graph.subgraph(node_ids)

    # -------------------------------------------------------------------------
    # Helper Filtering
    # -------------------------------------------------------------------------

    def _get_filtered_neighbors(
        self,
        node_id: str,
        direction: str,
        relationship_types: set[GraphRelationship] | None,
    ) -> list[GraphNode]:
        """Fetch neighbors along edges respecting direction and relationship type filters."""
        neighbors: list[GraphNode] = []
        seen: set[str] = set()

        if direction in ("outgoing", "both"):
            out_edges = self.graph.list_edges(source_node_id=node_id)
            for edge in out_edges:
                if (
                    relationship_types
                    and edge.relationship_type not in relationship_types
                ):
                    continue
                tgt = self.graph.get_node(edge.target_node_id)
                if tgt and tgt.node_id not in seen:
                    seen.add(tgt.node_id)
                    neighbors.append(tgt)

        if direction in ("incoming", "both"):
            in_edges = self.graph.list_edges(target_node_id=node_id)
            for edge in in_edges:
                if (
                    relationship_types
                    and edge.relationship_type not in relationship_types
                ):
                    continue
                src = self.graph.get_node(edge.source_node_id)
                if src and src.node_id not in seen:
                    seen.add(src.node_id)
                    neighbors.append(src)

        return neighbors
