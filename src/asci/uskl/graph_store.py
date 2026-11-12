"""
Corridor Graph Store (NetworkX) backed by JSON seed.
Enforces that every node is validated against the Canonical Entity Registry.
"""

from __future__ import annotations

from collections import OrderedDict
import itertools
import json
from pathlib import Path
from typing import Any

import networkx as nx

from asci.core.registry import CanonicalEntityRegistry, get_canonical_registry

# Bounded pure-topology cache keyed by exact sorted (nodes, active edges & weights).
# Eliminates redundant Yen k-shortest-path and centrality recalculations across runs
# while automatically invalidating whenever any node/edge/active flag/transit weight changes.
_MAX_TOPOLOGY_CACHE_ENTRIES = 8
_TOPOLOGY_CACHE: OrderedDict[tuple[Any, ...], dict[str, Any]] = OrderedDict()


def _get_or_init_topology_slot(sig: tuple[Any, ...]) -> dict[str, Any]:
    slot = _TOPOLOGY_CACHE.get(sig)
    if slot is None:
        slot = {
            "simple_digraph": None,
            "ranked_paths": {},
            "betweenness": None,
            "edge_betweenness": None,
        }
        _TOPOLOGY_CACHE[sig] = slot
        while len(_TOPOLOGY_CACHE) > _MAX_TOPOLOGY_CACHE_ENTRIES:
            _TOPOLOGY_CACHE.popitem(last=False)
    else:
        _TOPOLOGY_CACHE.move_to_end(sig)
    return slot


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
        self._cached_sig: tuple[Any, ...] | None = None
        self._cached_slot: dict[str, Any] | None = None

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
        network_scale: str = "v0_core",
    ) -> CorridorGraphStore:
        """Load NetworkX MultiDiGraph from JSON seed file for the specified network scale."""
        filename = (
            "corridor_graph_v1.json"
            if network_scale == "v1_corridor"
            else "corridor_graph_v0.json"
        )
        if seed_path is None:
            candidate = Path(__file__).resolve().parents[3] / "data" / "seeds" / filename
            if not candidate.exists():
                candidate = Path.cwd() / "data" / "seeds" / filename
                if not candidate.exists():
                    candidate = Path.cwd() / "asci-core" / "data" / "seeds" / filename
            seed_path = candidate

        reg = registry or get_canonical_registry(network_scale=network_scale)

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

        return cls(graph=g, registry=reg)

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

    def active_topology_signature(self) -> tuple[Any, ...]:
        """Exact hashable snapshot of nodes, active edges, and nominal routing weights."""
        nodes_sig = tuple(sorted(self._graph.nodes()))
        edges_sig = tuple(
            sorted(
                (
                    u,
                    v,
                    str(k),
                    bool(attrs.get("active", True)),
                    float(attrs.get("transit_time_hrs", 2.0)),
                    float(attrs.get("base_cost_per_teu", 100.0)),
                )
                for u, v, k, attrs in self._graph.edges(keys=True, data=True)
            )
        )
        return (nodes_sig, edges_sig)

    def _topology_slot(self) -> dict[str, Any]:
        sig = self.active_topology_signature()
        if self._cached_sig != sig or self._cached_slot is None:
            self._cached_sig = sig
            self._cached_slot = _get_or_init_topology_slot(sig)
        return self._cached_slot

    def build_simple_active_digraph(self) -> nx.DiGraph:
        """
        Build (or return cached) simple directed graph over active links, weighted by
        minimum nominal transit time across parallel multiedges for fast k-shortest path enumeration.
        """
        slot = self._topology_slot()
        cached_dg = slot["simple_digraph"]
        if cached_dg is not None:
            return cached_dg

        dg = nx.DiGraph()
        dg.add_nodes_from(self._graph.nodes())
        for u, v, attrs in self._graph.edges(data=True):
            if not attrs.get("active", True):
                continue
            t = max(0.01, float(attrs.get("transit_time_hrs", 2.0)))
            c = max(1.0, float(attrs.get("base_cost_per_teu", 100.0)))
            if dg.has_edge(u, v):
                if t < dg[u][v]["transit_time_hrs"]:
                    dg[u][v]["transit_time_hrs"] = t
                if c < dg[u][v]["base_cost_per_teu"]:
                    dg[u][v]["base_cost_per_teu"] = c
            else:
                dg.add_edge(u, v, transit_time_hrs=t, base_cost_per_teu=c)
        slot["simple_digraph"] = dg
        return dg

    def get_centrality_metrics(
        self,
        simple_graph: nx.DiGraph | None = None,
    ) -> tuple[dict[str, float], dict[tuple[str, str], float]]:
        """Return cached (node_betweenness, symmetric_edge_betweenness) for active topology."""
        if (
            simple_graph is not None
            and self._cached_slot is not None
            and simple_graph is self._cached_slot.get("simple_digraph")
        ):
            slot = self._cached_slot
            use_cache = True
        else:
            slot = self._topology_slot()
            use_cache = simple_graph is None or simple_graph is slot.get("simple_digraph")

        if use_cache:
            if slot["betweenness"] is not None and slot["edge_betweenness"] is not None:
                return slot["betweenness"], slot["edge_betweenness"]
            dg = simple_graph if simple_graph is not None else self.build_simple_active_digraph()
            betweenness = nx.betweenness_centrality(dg)
            edge_betw_raw = nx.edge_betweenness_centrality(dg.to_undirected())
            edge_betweenness: dict[tuple[str, str], float] = {}
            for (u, v), val in edge_betw_raw.items():
                edge_betweenness[(u, v)] = val
                edge_betweenness[(v, u)] = val
            slot["betweenness"] = betweenness
            slot["edge_betweenness"] = edge_betweenness
            return betweenness, edge_betweenness

        betweenness = nx.betweenness_centrality(simple_graph)
        edge_betw_raw = nx.edge_betweenness_centrality(simple_graph.to_undirected())
        edge_betweenness = {}
        for (u, v), val in edge_betw_raw.items():
            edge_betweenness[(u, v)] = val
            edge_betweenness[(v, u)] = val
        return betweenness, edge_betweenness

    def find_ranked_paths(
        self,
        origin: str,
        destination: str,
        max_paths: int = 3,
        cutoff: int = 6,
        simple_graph: nx.DiGraph | None = None,
    ) -> list[list[str]]:
        """Find simple directed paths ranked by nominal edge transit time in polynomial time."""
        if origin not in self._graph or destination not in self._graph or max_paths <= 0:
            return []

        if (
            simple_graph is not None
            and self._cached_slot is not None
            and simple_graph is self._cached_slot.get("simple_digraph")
        ):
            slot = self._cached_slot
            use_cache = True
            dg = simple_graph
        else:
            slot = self._topology_slot()
            use_cache = simple_graph is None or simple_graph is slot.get("simple_digraph")
            dg = self.build_simple_active_digraph() if use_cache else simple_graph

        cache_dict: dict[tuple[str, str, int, int], list[list[str]]] = slot["ranked_paths"]
        if use_cache:
            cache_key = (origin, destination, max_paths, cutoff)
            if cache_key in cache_dict:
                return [list(p) for p in cache_dict[cache_key]]
            for larger_k in (2, 3, 4):
                if larger_k >= max_paths and (origin, destination, larger_k, cutoff) in cache_dict:
                    return [list(p) for p in cache_dict[(origin, destination, larger_k, cutoff)][:max_paths]]

        if origin not in dg or destination not in dg:
            return []

        try:
            # Fast hop-reachability screen avoids scanning expensive Yen paths when min hops > cutoff
            if nx.shortest_path_length(dg, origin, destination) > cutoff:
                if use_cache:
                    cache_dict[(origin, destination, max_paths, cutoff)] = []
                return []
            gen = nx.shortest_simple_paths(dg, origin, destination, weight="transit_time_hrs")
            candidates: list[tuple[float, int, list[str]]] = []
            max_probe = max(max_paths * 6, 12)
            for p in itertools.islice(gen, max_probe):
                if len(p) - 1 > cutoff:
                    continue
                total = sum(float(dg[u][v]["transit_time_hrs"]) for u, v in zip(p, p[1:]))
                candidates.append((total, len(p), list(p)))
                if len(candidates) >= max_paths * 2:
                    break
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            if use_cache:
                cache_dict[(origin, destination, max_paths, cutoff)] = []
            return []

        candidates.sort(key=lambda item: (item[0], item[1], item[2]))
        result = [p for _, _, p in candidates[:max_paths]]
        if use_cache:
            cache_dict[(origin, destination, max_paths, cutoff)] = result
        return [list(p) for p in result]

    def get_all_nodes(self) -> list[str]:
        return list(self._graph.nodes)

    def get_all_edges(self) -> list[tuple[str, str, dict[str, Any]]]:
        return [(u, v, data) for u, v, data in self._graph.edges(data=True)]

