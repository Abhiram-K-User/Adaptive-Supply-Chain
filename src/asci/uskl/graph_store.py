"""
Corridor Graph Store (NetworkX) backed by JSON seed.
Enforces that every node is validated against the Canonical Entity Registry.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import networkx as nx

from asci.core.registry import CanonicalEntityRegistry, get_canonical_registry


class CorridorGraphStore:
    """
    Corridor Multigraph Store representing physical road, rail, and terminal infrastructure.
    All nodes and edge endpoints reference canonical registry IDs.
    """

    def __init__(
        self,
        graph: nx.MultiDiGraph,
        registry: CanonicalEntityRegistry | None = None,
    ) -> None:
        self._graph = graph
        self._registry = registry or get_canonical_registry()
        self._validate_all_nodes()

    def _validate_all_nodes(self) -> None:
        """Ensure every node in the graph exists in the canonical registry."""
        invalid_nodes = [node for node in self._graph.nodes if not self._registry.validate_id(str(node))]
        if invalid_nodes:
            raise ValueError(f"Corridor graph contains ungrounded node IDs: {invalid_nodes}")

    @classmethod
    def load_from_json(
        cls,
        seed_path: str | Path | None = None,
        registry: CanonicalEntityRegistry | None = None,
    ) -> CorridorGraphStore:
        """Load NetworkX MultiDiGraph from JSON seed file."""
        if seed_path is None:
            candidate = (
                Path(__file__).resolve().parents[3] / "data" / "seeds" / "corridor_graph_v0.json"
            )
            if not candidate.exists():
                candidate = Path.cwd() / "data" / "seeds" / "corridor_graph_v0.json"
                if not candidate.exists():
                    candidate = Path.cwd() / "asci-core" / "data" / "seeds" / "corridor_graph_v0.json"
            seed_path = candidate

        path_obj = Path(seed_path)
        if not path_obj.exists():
            raise FileNotFoundError(f"Corridor graph seed not found at {path_obj}")

        with open(path_obj, "r", encoding="utf-8") as f:
            data = json.load(f)

        g = nx.MultiDiGraph()
        for node in data.get("nodes", []):
            g.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})

        for link in data.get("links", []):
            u = link["source"]
            v = link["target"]
            key = link.get("key", "default")
            attrs = {k: v for k, v in link.items() if k not in ("source", "target", "key")}
            g.add_edge(u, v, key=key, **attrs)

        return cls(graph=g, registry=registry)

    @property
    def graph(self) -> nx.MultiDiGraph:
        """Return the underlying NetworkX MultiDiGraph."""
        return self._graph

    def get_k_hop_subgraph(self, center_nodes: list[str], k: int = 2) -> nx.MultiDiGraph:
        """Extract the k-hop neighborhood around one or more center nodes."""
        nodes_in_subgraph: set[str] = set()
        for node in center_nodes:
            if node in self._graph:
                # Undirected view for symmetric k-hop neighborhood discovery
                undirected = self._graph.to_undirected(as_view=True)
                lengths = nx.single_source_shortest_path_length(undirected, node, cutoff=k)
                nodes_in_subgraph.update(lengths.keys())

        return self._graph.subgraph(nodes_in_subgraph).copy()

    def find_candidate_paths(
        self,
        origin: str,
        destination: str,
        cutoff: int = 5,
    ) -> list[list[str]]:
        """Find simple directed paths between origin and destination."""
        if origin not in self._graph or destination not in self._graph:
            return []
        try:
            return list(nx.all_simple_paths(self._graph, origin, destination, cutoff=cutoff))
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def get_edge_attributes(self, source: str, target: str) -> list[dict[str, Any]]:
        """Retrieve all parallel edge attributes between source and target."""
        if not self._graph.has_edge(source, target):
            return []
        edge_data = self._graph.get_edge_data(source, target)
        return list(edge_data.values()) if edge_data else []

    def get_active_edges(self, source: str, target: str) -> list[tuple[str, dict[str, Any]]]:
        """Retrieve (key, attrs) for all active parallel edges between source and target."""
        if not self._graph.has_edge(source, target):
            return []
        edge_data = self._graph.get_edge_data(source, target) or {}
        return [
            (str(key), attrs)
            for key, attrs in edge_data.items()
            if attrs.get("active", True)
        ]

    def has_active_edge(self, source: str, target: str) -> bool:
        """Return True if at least one active directed edge exists from source to target."""
        return len(self.get_active_edges(source, target)) > 0

    def get_path_mode(self, path: list[str]) -> str:
        """
        Infer path transport mode from traversed MultiDiGraph edge attributes.
        Returns 'INTERMODAL' if any hop includes a RAIL edge, 'ROAD' if all hops are road,
        or 'UNKNOWN' if any hop is missing.
        """
        if len(path) < 2:
            return "UNKNOWN"
        saw_rail = False
        for u, v in zip(path, path[1:]):
            active_edges = self.get_active_edges(u, v)
            if not active_edges:
                return "UNKNOWN"
            if any(str(attrs.get("mode", "")).upper() == "RAIL" for _, attrs in active_edges):
                saw_rail = True
        return "INTERMODAL" if saw_rail else "ROAD"

    def find_ranked_paths(
        self,
        origin: str,
        destination: str,
        max_paths: int = 3,
        cutoff: int = 6,
    ) -> list[list[str]]:
        """Find simple directed paths ranked by nominal edge transit time."""
        raw_paths = self.find_candidate_paths(origin, destination, cutoff=cutoff)
        if not raw_paths:
            return []

        def _nominal_time(p: list[str]) -> float:
            total = 0.0
            for u, v in zip(p, p[1:]):
                edges = self.get_active_edges(u, v)
                if not edges:
                    return float("inf")
                total += min(float(attrs.get("transit_time_hrs", 2.0)) for _, attrs in edges)
            return total

        valid = [p for p in raw_paths if _nominal_time(p) < float("inf")]
        valid.sort(key=lambda p: (_nominal_time(p), len(p), p))
        return valid[:max_paths]

    def get_all_nodes(self) -> list[str]:
        return list(self._graph.nodes)

    def get_all_edges(self) -> list[tuple[str, str, dict[str, Any]]]:
        return [(u, v, data) for u, v, data in self._graph.edges(data=True)]

