"""
Tier-1 Hop-Decay Disruption Propagation Engine (PRD Sec. 5.2 / Operator PROPAGATE).
Models k-hop cascading queue delays and soft capacity attenuation from directly
impacted nodes into adjacent inland corridor terminals and highways.
"""

from __future__ import annotations

import random
import time
from collections import defaultdict, deque
from datetime import UTC, datetime

import networkx as nx

from asci.core.contracts import OperatorResult, PipelineConfig
from asci.core.registry import CanonicalEntityRegistry, EntityType, get_canonical_registry
from asci.core.state import (
    OperatorTraceItem,
    OperatorType,
    PipelineState,
)
from asci.uskl.graph_store import CorridorGraphStore


def propagate_graph_context(
    graph_store: CorridorGraphStore,
    registry: CanonicalEntityRegistry,
    affected_nodes: list[str],
    severity: float,
    k_hops: int,
    base_node_multipliers: dict[str, float],
    base_edge_multipliers: dict[str, float],
    decay_gamma: float = 0.45,
) -> tuple[dict[str, float], dict[str, float], dict[str, float], list[str]]:
    """
    Execute deterministic Tier-1 BFS hop-decay propagation from directly affected nodes.

    Returns:
        (node_multipliers, edge_multipliers, propagated_node_delays_hrs, impacted_nodes)
    """
    node_mults = dict(base_node_multipliers)
    edge_mults = dict(base_edge_multipliers)
    delays_hrs: dict[str, float] = {}

    active_simple = nx.DiGraph()
    for u, v, attrs in graph_store.get_all_edges():
        if attrs.get("active", True):
            active_simple.add_edge(u, v)

    undirected = active_simple.to_undirected(as_view=True)

    # Deterministic BFS up to k_hops seeded with hop-0 affected nodes
    hop_distance: dict[str, int] = {}
    queue: deque[str] = deque()
    for nid in sorted(dict.fromkeys(affected_nodes)):
        if nid in active_simple or nid in graph_store.get_all_nodes():
            hop_distance[nid] = 0
            queue.append(nid)

    while queue:
        curr = queue.popleft()
        curr_hop = hop_distance[curr]
        if curr_hop >= k_hops:
            continue
        neighbors = sorted(undirected.neighbors(curr)) if curr in undirected else []
        for nbr in neighbors:
            if nbr not in hop_distance:
                hop_distance[nbr] = curr_hop + 1
                queue.append(nbr)

    # Apply hop-decay dwell delays and soft spillover attenuation on non-gateway intermediate nodes/edges
    for nid, hop in sorted(hop_distance.items()):
        decay_factor = decay_gamma ** hop
        dwell_hrs = round(max(0.0, severity) * decay_factor * 12.0, 2)
        if dwell_hrs > 0.0:
            delays_hrs[nid] = dwell_hrs

        if hop == 0:
            continue

        ent = registry.get(nid)
        # Preserve alternate un-impacted ocean ports and assembly plants so healthy rerouting remains viable;
        # apply bounded soft congestion squeeze to downstream/adjacent intermediate transshipment hubs.
        if ent.entity_type not in (EntityType.PORT, EntityType.PLANT):
            soft_mult = max(0.88, round(1.0 - (severity * 0.12 * (decay_gamma ** (hop - 1))), 2))
            if nid in node_mults:
                node_mults[nid] = min(node_mults[nid], soft_mult)
            else:
                node_mults[nid] = soft_mult

    # Propagate soft congestion squeeze across edges incident to hop-1..k nodes
    affected_set = set(affected_nodes)
    for u, v, attrs in graph_store.get_all_edges():
        if not attrs.get("active", True):
            continue
        key = f"{u}->{v}"
        if u in affected_set or v in affected_set:
            continue
        h_u = hop_distance.get(u)
        h_v = hop_distance.get(v)
        if h_u is not None and h_v is not None:
            min_hop = min(h_u, h_v)
            if 1 <= min_hop <= k_hops:
                soft_edge_mult = max(0.88, round(1.0 - (severity * 0.12 * (decay_gamma ** (min_hop - 1))), 2))
                edge_mults[key] = min(edge_mults.get(key, 1.0), soft_edge_mult)

    impacted_nodes = sorted(hop_distance.keys())
    return node_mults, edge_mults, delays_hrs, impacted_nodes


def propagate_graph_context_tier2(
    graph_store: CorridorGraphStore,
    registry: CanonicalEntityRegistry,
    affected_nodes: list[str],
    severity: float,
    k_hops: int,
    base_node_multipliers: dict[str, float],
    base_edge_multipliers: dict[str, float],
    decay_gamma: float = 0.45,
    simple_graph: nx.DiGraph | None = None,
) -> tuple[
    dict[str, float],
    dict[str, float],
    dict[str, float],
    list[str],
    dict[str, float],
    dict[str, float],
]:
    """
    Execute Tier-2 Dynamic Congestion Load Redistribution Propagation (PRD Sec. 5.2).

    Combines Tier-1 BFS hop-decay with baseline demand flow shifting onto healthy
    k-hop diversion corridors and BPR nonlinear volume-delay dwell spillover.

    Returns:
        (
            node_multipliers,
            edge_multipliers,
            propagated_node_delays_hrs,
            impacted_nodes,
            redistributed_edge_loads_teu,
            edge_congestion_ratios,
        )
    """
    node_mults, edge_mults, delays_hrs, impacted_nodes = propagate_graph_context(
        graph_store=graph_store,
        registry=registry,
        affected_nodes=affected_nodes,
        severity=severity,
        k_hops=k_hops,
        base_node_multipliers=base_node_multipliers,
        base_edge_multipliers=base_edge_multipliers,
        decay_gamma=decay_gamma,
    )

    dg = simple_graph if simple_graph is not None else graph_store.build_simple_active_digraph()
    affected_set = set(affected_nodes)

    # Compute per-link aggregate nominal capacity and minimum transit time
    link_nom_caps: dict[str, float] = defaultdict(float)
    link_times: dict[str, float] = {}
    for u, v, attrs in graph_store.get_all_edges():
        if not attrs.get("active", True):
            continue
        key = f"{u}->{v}"
        link_nom_caps[key] += float(attrs.get("capacity_teu_per_day", 1000.0))
        t_val = float(attrs.get("transit_time_hrs", 2.0))
        link_times[key] = min(link_times.get(key, float("inf")), t_val)

    ports = [e.id for e in registry.get_by_type(EntityType.PORT)]
    plants = registry.get_by_type(EntityType.PLANT)
    cutoff = 6 if len(registry) <= 40 else 8

    # Step 1: Collect candidate port-to-plant routes per plant and assign baseline demand loads
    plant_routes: dict[str, list[tuple[float, list[str]]]] = {}
    for plant in plants:
        routes: list[tuple[float, list[str]]] = []
        for port_id in ports:
            for path in graph_store.find_ranked_paths(
                port_id, plant.id, max_paths=1, cutoff=cutoff, simple_graph=dg
            ):
                t_sum = sum(
                    float(dg[u][v]["transit_time_hrs"])
                    for u, v in zip(path, path[1:], strict=False)
                )
                routes.append((t_sum, path))
        routes.sort(key=lambda item: (item[0], len(item[1]), item[1]))
        plant_routes[plant.id] = routes

    redistributed_loads: dict[str, float] = defaultdict(float)
    for plant in plants:
        routes = plant_routes.get(plant.id, [])
        if not routes:
            continue
        demand = float(plant.daily_demand_teu or 500.0)
        # Baseline flow splits across top-2 shortest corridors for each plant
        primary_routes = routes[:2]
        inv_costs = [1.0 / max(0.5, t) for t, _ in primary_routes]
        inv_sum = sum(inv_costs) or 1.0

        surviving_routes = [
            (t, p)
            for t, p in routes
            if not any(node in affected_set for node in p)
        ]
        diverted_total = 0.0
        for (_t, path), w in zip(primary_routes, inv_costs, strict=False):
            alloc = demand * (w / inv_sum)
            path_affected = any(node in affected_set for node in path)
            if path_affected:
                retain_frac = max(0.05, 1.0 - max(0.0, severity))
                kept = alloc * retain_frac
                diverted_total += alloc - kept
                for u, v in zip(path, path[1:], strict=False):
                    redistributed_loads[f"{u}->{v}"] += kept
            else:
                for u, v in zip(path, path[1:], strict=False):
                    redistributed_loads[f"{u}->{v}"] += alloc

        if diverted_total > 0.0 and surviving_routes:
            alt_pool = surviving_routes[:3]
            alt_weights = [1.0 / max(0.5, t) for t, _ in alt_pool]
            alt_sum = sum(alt_weights) or 1.0
            for (_, alt_path), w_alt in zip(alt_pool, alt_weights, strict=True):
                share = diverted_total * (w_alt / alt_sum)
                for u, v in zip(alt_path, alt_path[1:], strict=False):
                    redistributed_loads[f"{u}->{v}"] += share

    # Step 2: Evaluate link utilization & BPR congestion dwell spillover across diversion corridors
    edge_congestion_ratios: dict[str, float] = {}
    impacted_set = set(impacted_nodes)
    for key, nom_cap in sorted(link_nom_caps.items()):
        u, v = key.split("->", 1)
        mult = min(edge_mults.get(key, 1.0), node_mults.get(u, 1.0), node_mults.get(v, 1.0))
        res_cap = max(1.0, nom_cap * mult)
        load = float(redistributed_loads.get(key, 0.0))
        ratio = round(min(2.5, load / res_cap), 4)
        if ratio > 0.0:
            edge_congestion_ratios[key] = ratio

        # Apply BPR dynamic dwell delta when corridor experiences diverted load or local impact
        if load > 0.0 and (u in impacted_set or v in impacted_set or ratio > 0.35):
            t0 = link_times.get(key, 2.0)
            bpr_dwell = round(
                t0 * 0.35 * (min(2.0, ratio) ** 2.5) * max(0.25, severity),
                2,
            )
            if bpr_dwell > 0.0:
                delays_hrs[v] = round(delays_hrs.get(v, 0.0) + bpr_dwell, 2)

            # Bounded secondary effective capacity compression on congested inland diversion links
            # (preserve unaffected gateway PORTs and destination PLANTs for feasible Stage D flow)
            if ratio > 0.75 and u not in affected_set and v not in affected_set:
                ent_u = registry.get(u)
                ent_v = registry.get(v)
                if (
                    ent_u.entity_type not in (EntityType.PORT, EntityType.PLANT)
                    and ent_v.entity_type != EntityType.PORT
                ):
                    squeeze = max(0.80, round(1.0 - 0.14 * min(1.0, ratio - 0.75), 2))
                    edge_mults[key] = min(edge_mults.get(key, 1.0), squeeze)

    rounded_loads = {k: round(float(v), 2) for k, v in sorted(redistributed_loads.items()) if v > 0.0}
    return (
        node_mults,
        edge_mults,
        delays_hrs,
        impacted_nodes,
        rounded_loads,
        edge_congestion_ratios,
    )


class Tier1PropagationSimulator:
    """
    Standalone Operator conforming to PRD OperatorType.PROPAGATE (Tier-1 Hop-Decay).
    Can run independently in modular agentic traces or via Stage B integration.
    """

    def __init__(
        self,
        graph_store: CorridorGraphStore | None = None,
        registry: CanonicalEntityRegistry | None = None,
        decay_gamma: float = 0.45,
    ) -> None:
        self.registry = registry or get_canonical_registry()
        self.graph_store = graph_store or CorridorGraphStore.load_from_json(registry=self.registry)
        self.decay_gamma = decay_gamma

    def run(
        self,
        state: PipelineState,
        cfg: PipelineConfig,
        rng: random.Random,
    ) -> tuple[PipelineState, OperatorResult]:
        """Execute deterministic Tier-1 hop-decay propagation over GraphContext."""
        _ = rng
        t0 = time.perf_counter()

        if not state.event or not state.graph_context:
            err = "PROPAGATE prerequisite failure: event or graph_context missing in PipelineState."
            return state, OperatorResult(
                operator_type=OperatorType.PROPAGATE,
                success=False,
                message=err,
                error=err,
            )

        ctx = state.graph_context
        event = state.event

        if ctx.hop_decay_applied:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            trace_item = OperatorTraceItem(
                step_index=state.step_count + 1,
                operator_type=OperatorType.PROPAGATE,
                input_summary=f"Event {event.event_id} (propagation already applied)",
                output_summary=f"Reused existing hop-decay across {len(ctx.propagated_node_delays_hrs)} nodes",
                duration_ms=round(duration_ms, 2),
                cost=0.0005,
                seed=cfg.random_seed,
                timestamp=datetime.now(UTC),
            )
            new_state = state.transition(updates={}, trace_item=trace_item)
            return new_state, OperatorResult(
                operator_type=OperatorType.PROPAGATE,
                success=True,
                message="Tier-1 hop-decay propagation already applied on GraphContext.",
                duration_ms=round(duration_ms, 2),
                cost=0.0005,
            )

        affected_nodes = [event.primary_entity_id] + [
            nid for nid in event.affected_entity_ids if nid != event.primary_entity_id
        ]
        node_mults, edge_mults, delays_hrs, impacted_nodes = propagate_graph_context(
            graph_store=self.graph_store,
            registry=self.registry,
            affected_nodes=affected_nodes,
            severity=event.severity,
            k_hops=ctx.k_hops,
            base_node_multipliers=ctx.node_capacity_multipliers,
            base_edge_multipliers=ctx.edge_capacity_multipliers,
            decay_gamma=self.decay_gamma,
        )

        updated_ctx = ctx.model_copy(
            update={
                "impacted_nodes": impacted_nodes,
                "node_capacity_multipliers": node_mults,
                "edge_capacity_multipliers": edge_mults,
                "propagated_node_delays_hrs": delays_hrs,
                "hop_decay_applied": True,
                "propagation_tier": 1,
            }
        )

        duration_ms = (time.perf_counter() - t0) * 1000.0
        op_cost = 0.0015
        trace_item = OperatorTraceItem(
            step_index=state.step_count + 1,
            operator_type=OperatorType.PROPAGATE,
            input_summary=f"Hop-decay k={ctx.k_hops}, gamma={self.decay_gamma} from {event.primary_entity_id}",
            output_summary=f"Updated {len(delays_hrs)} nodes with cascade dwell delays",
            duration_ms=round(duration_ms, 2),
            cost=op_cost,
            seed=cfg.random_seed,
            timestamp=datetime.now(UTC),
        )
        new_state = state.transition(updates={"graph_context": updated_ctx}, trace_item=trace_item)
        return new_state, OperatorResult(
            operator_type=OperatorType.PROPAGATE,
            success=True,
            message=f"Tier-1 PROPAGATE completed across {len(delays_hrs)} impacted corridor nodes.",
            duration_ms=round(duration_ms, 2),
            cost=op_cost,
            artifacts={"propagated_nodes": len(delays_hrs), "decay_gamma": self.decay_gamma},
        )


class Tier2DynamicCongestionSimulator:
    """
    Tier-2 PROPAGATE Operator (PRD Sec. 5.2): Executes dynamic diverted load
    redistribution and BPR volume-delay congestion spillover over GraphContext.
    """

    def __init__(
        self,
        graph_store: CorridorGraphStore | None = None,
        registry: CanonicalEntityRegistry | None = None,
        decay_gamma: float = 0.45,
    ) -> None:
        self.registry = registry or get_canonical_registry()
        self.graph_store = graph_store or CorridorGraphStore.load_from_json(registry=self.registry)
        self.decay_gamma = decay_gamma

    def run(
        self,
        state: PipelineState,
        cfg: PipelineConfig,
        rng: random.Random,
    ) -> tuple[PipelineState, OperatorResult]:
        """Execute deterministic Tier-2 dynamic congestion propagation over GraphContext."""
        _ = rng
        t0 = time.perf_counter()

        if not state.event or not state.graph_context:
            err = "Tier-2 PROPAGATE prerequisite failure: event or graph_context missing in PipelineState."
            return state, OperatorResult(
                operator_type=OperatorType.PROPAGATE,
                success=False,
                message=err,
                error=err,
            )

        ctx = state.graph_context
        event = state.event

        if ctx.hop_decay_applied and ctx.propagation_tier >= 2:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            trace_item = OperatorTraceItem(
                step_index=state.step_count + 1,
                operator_type=OperatorType.PROPAGATE,
                input_summary=f"Event {event.event_id} (Tier-2 propagation already applied)",
                output_summary=f"Reused Tier-2 congestion delays across {len(ctx.propagated_node_delays_hrs)} nodes",
                duration_ms=round(duration_ms, 2),
                cost=0.0005,
                seed=cfg.random_seed,
                timestamp=datetime.now(UTC),
            )
            new_state = state.transition(updates={}, trace_item=trace_item)
            return new_state, OperatorResult(
                operator_type=OperatorType.PROPAGATE,
                success=True,
                message="Tier-2 dynamic congestion propagation already applied on GraphContext.",
                duration_ms=round(duration_ms, 2),
                cost=0.0005,
            )

        affected_nodes = [event.primary_entity_id] + [
            nid for nid in event.affected_entity_ids if nid != event.primary_entity_id
        ]
        node_mults, edge_mults, delays_hrs, impacted_nodes, loads_teu, ratios = (
            propagate_graph_context_tier2(
                graph_store=self.graph_store,
                registry=self.registry,
                affected_nodes=affected_nodes,
                severity=event.severity,
                k_hops=ctx.k_hops,
                base_node_multipliers=ctx.node_capacity_multipliers,
                base_edge_multipliers=ctx.edge_capacity_multipliers,
                decay_gamma=self.decay_gamma,
            )
        )

        updated_ctx = ctx.model_copy(
            update={
                "impacted_nodes": impacted_nodes,
                "node_capacity_multipliers": node_mults,
                "edge_capacity_multipliers": edge_mults,
                "propagated_node_delays_hrs": delays_hrs,
                "hop_decay_applied": True,
                "propagation_tier": 2,
                "redistributed_edge_loads_teu": loads_teu,
                "edge_congestion_ratios": ratios,
            }
        )

        duration_ms = (time.perf_counter() - t0) * 1000.0
        op_cost = 0.0020
        trace_item = OperatorTraceItem(
            step_index=state.step_count + 1,
            operator_type=OperatorType.PROPAGATE,
            input_summary=f"Tier-2 BPR load redistribution from {event.primary_entity_id} (k={ctx.k_hops})",
            output_summary=(
                f"Updated {len(delays_hrs)} nodes; redistributed load across {len(loads_teu)} active links"
            ),
            duration_ms=round(duration_ms, 2),
            cost=op_cost,
            seed=cfg.random_seed,
            timestamp=datetime.now(UTC),
        )
        new_state = state.transition(updates={"graph_context": updated_ctx}, trace_item=trace_item)
        return new_state, OperatorResult(
            operator_type=OperatorType.PROPAGATE,
            success=True,
            message=f"Tier-2 PROPAGATE redistributed demand across {len(loads_teu)} links.",
            duration_ms=round(duration_ms, 2),
            cost=op_cost,
            artifacts={
                "propagated_nodes": len(delays_hrs),
                "redistributed_links": len(loads_teu),
                "propagation_tier": 2,
            },
        )
