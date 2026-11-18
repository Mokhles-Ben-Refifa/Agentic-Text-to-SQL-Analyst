"""Foreign-key graph expansion to bridge tables and prevent join hallucinations."""

import logging
from collections import deque

from semantic.manager import semantic_manager

logger = logging.getLogger(__name__)


class ForeignKeyExpander:
    """Builds an adjacency graph of table relationships and finds bridge tables."""

    def __init__(self, manager=semantic_manager):
        self.manager = manager
        self.adj: dict[str, set[str]] = {}
        self.build_graph()

    def build_graph(self):
        """Constructs an undirected graph of tables connected by foreign keys."""
        self.adj.clear()
        for table_name, table in self.manager.tables.items():
            if table_name not in self.adj:
                self.adj[table_name] = set()

            for col in table.columns:
                if col.foreign_key:
                    target_table = col.foreign_key.split(".")[0]
                    if target_table in self.manager.tables:
                        self.adj[table_name].add(target_table)
                        if target_table not in self.adj:
                            self.adj[target_table] = set()
                        self.adj[target_table].add(table_name)

    def find_all_shortest_paths(self, start: str, target: str) -> list[list[str]]:
        """Finds all shortest paths connecting start and target using BFS."""
        if start == target or start not in self.adj or target not in self.adj:
            return []

        queue = deque([[start]])
        shortest_paths: list[list[str]] = []
        min_len: int | None = None

        while queue:
            path = queue.popleft()
            if min_len is not None and len(path) > min_len:
                break

            node = path[-1]
            if node == target:
                if min_len is None:
                    min_len = len(path)
                shortest_paths.append(path)
                continue

            for neighbor in self.adj.get(node, []):
                if neighbor not in path:
                    queue.append(path + [neighbor])

        return shortest_paths

    def expand_tables(self, seed_tables: list[str]) -> list[str]:
        """Expands a list of seed tables by adding all intermediate bridge tables required to join them."""
        valid_seeds = [t.lower() for t in seed_tables if t.lower() in self.adj]
        if len(valid_seeds) <= 1:
            return seed_tables

        expanded_set = set(valid_seeds)

        # For every pair in seed tables, connect them via all shortest paths
        for i in range(len(valid_seeds)):
            for j in range(i + 1, len(valid_seeds)):
                u, v = valid_seeds[i], valid_seeds[j]
                paths = self.find_all_shortest_paths(u, v)
                for path in paths:
                    expanded_set.update(path)

        # Maintain original order of seeds, followed by newly added bridge tables
        result = list(valid_seeds)
        for t in sorted(expanded_set):
            if t not in result:
                result.append(t)

        return result


fk_expander = ForeignKeyExpander()
