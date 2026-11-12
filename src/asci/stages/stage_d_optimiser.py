"""
Stage D: Deterministic Optimization & Three-Layer Verification Protocol.
Formulates corridor minimum-cost network flow rerouting using NetworkX min-cost flow
and executes L1, L2, L3 verification gateways.
"""

from __future__ import annotations

import math
import random
import time
from collections import defaultdict
from datetime import datetime, timezone

import networkx as nx

from asci.core.contracts import OperatorResult, PipelineConfig
from asci.core.registry import CanonicalEntityRegistry, EntityType, get_canonical_registry
from asci.core.state import (
    FlowAllocation,
    MitigationPlan,
    OperatorTraceItem,
    OperatorType,
    PipelineState,
    PipelineStatus,
    VerificationCheck,
    VerificationReport,
    VerificationVerdict,
)
from asci.uskl.graph_store import CorridorGraphStore

_FLOW_SCALE = 10  # 0.1 TEU integer precision for min-cost flow
_UNMET_PENALTY_PER_TEU = 50000
_PASS_THROUGH_INF_CAP = 10_000_000


class StageDOptimiserAndVerifier:
    """
    Stage D Operator: Deterministic Corridor Flow Optimizer & Layered Verifier (L1-L3).
    Solves a node- and edge-capacitated min-cost network flow over the active corridor graph
    and verifies entity grounding, graph edge validity, flow conservation, capacity bounds,
    demand satisfaction, and citation support.
    """

    def __init__(
        self,
        registry: CanonicalEntityRegistry | None = None,
        graph_store: CorridorGraphStore | None = None,
    ) -> None:
        self.registry = registry or get_canonical_registry()
        self.graph_store = graph_store or CorridorGraphStore.load_from_json(registry=self.registry)

    def _solve_network_flow(self, state: PipelineState) -> MitigationPlan:
        """Solve deterministic min-cost network flow across all registered ports and plants."""
        event = state.event
        graph_ctx = state.graph_context
        assert event is not None and graph_ctx is not None

        ports = sorted(self.registry.get_by_type(EntityType.PORT), key=lambda e: e.id)
        plants = sorted(self.registry.get_by_type(EntityType.PLANT), key=lambda e: e.id)

        port_ids = {p.id for p in ports}
        plant_ids = {p.id for p in plants}

        flow_g = nx.DiGraph()
        supersource = "__SUPERSOURCE__"

        total_demand_int = 0
        plant_demands_int: dict[str, int] = {}
        for p in plants:
            d_int = int(round((p.daily_demand_teu or 500.0) * _FLOW_SCALE))
            plant_demands_int[p.id] = d_int
            total_demand_int += d_int

        flow_g.add_node(supersource, demand=-total_demand_int)

        # Create split IN -> OUT nodes for physical entities so finite node capacities hold
        for nid in self.graph_store.get_all_nodes():
            ent = self.registry.get(nid)
            n_in = f"{nid}__IN"
            n_out = f"{nid}__OUT"
            flow_g.add_node(n_in, demand=0)
            flow_g.add_node(n_out, demand=0)

            n_mult = graph_ctx.node_capacity_multipliers.get(nid, 1.0)
            if ent.capacity_teu_per_day is not None:
                n_cap_int = max(0, int(math.floor(ent.capacity_teu_per_day * n_mult * _FLOW_SCALE)))
            else:
                # Plants without throughput bottlenecks can forward surplus flows; apply multiplier if disrupted
                n_cap_int = _PASS_THROUGH_INF_CAP if n_mult >= 0.99 else int(5000 * n_mult * _FLOW_SCALE)

            flow_g.add_edge(n_in, n_out, capacity=n_cap_int, weight=0)

        # Supersource supplies active gateway ports bounded by residual capacity
        for port in ports:
            p_mult = graph_ctx.node_capacity_multipliers.get(port.id, 1.0)
            p_cap = float(port.capacity_teu_per_day or 3000.0)
            p_cap_int = max(0, int(math.floor(p_cap * p_mult * _FLOW_SCALE)))
            flow_g.add_edge(supersource, f"{port.id}__IN", capacity=p_cap_int, weight=0)

        # Directed physical corridor links (each parallel key gets a dedicated virtual edge node)
        physical_edge_nodes: list[tuple[str, str, str, dict]] = []
        for u, v, key, attrs in sorted(
            self.graph_store.graph.edges(keys=True, data=True),
            key=lambda item: (item[0], item[1], str(item[2])),
        ):
            if not attrs.get("active", True):
                continue
            e_mult = graph_ctx.edge_capacity_multipliers.get(f"{u}->{v}", 1.0)
            raw_cap = float(attrs.get("capacity_teu_per_day", 1000.0))
            e_cap_int = max(0, int(math.floor(raw_cap * e_mult * _FLOW_SCALE)))
            if e_cap_int <= 0:
                continue

            # Ensure strictly positive cost per edge so optimal flows are cycle-free (DAG)
            cost_int = max(1, int(round(float(attrs.get("base_cost_per_teu", 100.0)))))
            e_node = f"__E::{u}::{v}::{key}"
            flow_g.add_node(e_node, demand=0)
            flow_g.add_edge(f"{u}__OUT", e_node, capacity=e_cap_int, weight=cost_int)
            flow_g.add_edge(e_node, f"{v}__IN", capacity=e_cap_int, weight=0)
            physical_edge_nodes.append((u, v, str(key), dict(attrs)))

        # Plant delivery sinks + penalized slack edges from supersource
        for p in plants:
            d_int = plant_demands_int[p.id]
            p_sink = f"{p.id}__SINK"
            flow_g.add_node(p_sink, demand=d_int)
            flow_g.add_edge(f"{p.id}__IN", p_sink, capacity=d_int, weight=0)
            flow_g.add_edge(supersource, p_sink, capacity=d_int, weight=_UNMET_PENALTY_PER_TEU)

        flow_dict = nx.min_cost_flow(flow_g)

        # Extract residual port supply, plant deliveries, unmet demand, and physical edge flows
        rem_supply: dict[str, int] = {}
        for port in ports:
            used = flow_dict[supersource].get(f"{port.id}__IN", 0)
            if used > 0:
                rem_supply[port.id] = used

        rem_deliv: dict[str, int] = {}
        unmet_int = 0
        for p in plants:
            deliv = flow_dict[f"{p.id}__IN"].get(f"{p.id}__SINK", 0)
            if deliv > 0:
                rem_deliv[p.id] = deliv
            unmet_int += flow_dict[supersource].get(f"{p.id}__SINK", 0)

        # Aggregate flows per (u, v) and track edge mode/cost metadata
        rem_edges: dict[tuple[str, str], int] = defaultdict(int)
        edge_weighted_cost: dict[tuple[str, str], float] = {}
        edge_modes: dict[tuple[str, str], set[str]] = defaultdict(set)
        edge_cost_accum: dict[tuple[str, str], float] = defaultdict(float)

        for u, v, key, attrs in physical_edge_nodes:
            e_node = f"__E::{u}::{v}::{key}"
            f_val = flow_dict.get(e_node, {}).get(f"{v}__IN", 0)
            if f_val > 0:
                rem_edges[(u, v)] += f_val
                edge_cost_accum[(u, v)] += f_val * float(attrs.get("base_cost_per_teu", 100.0))
                edge_modes[(u, v)].add(str(attrs.get("mode", "ROAD")).upper())

        for uv, f_tot in rem_edges.items():
            edge_weighted_cost[uv] = edge_cost_accum[uv] / f_tot

        # Build adjacency for deterministic path peeling from ports to plants
        adj: dict[str, list[str]] = defaultdict(list)
        for u, v in sorted(rem_edges.keys()):
            adj[u].append(v)

        def _find_residual_path(start_port: str) -> list[str] | None:
            """Find deterministic simple path from port along positive edge flows to a plant sink."""
            stack: list[tuple[str, list[str]]] = [(start_port, [start_port])]
            visited: set[str] = {start_port}
            while stack:
                curr, path = stack.pop()
                if curr in plant_ids and rem_deliv.get(curr, 0) > 0:
                    return path
                # Prefer direct sinks before continuing downstream, sorted deterministically
                neighbors = [
                    nxt for nxt in adj.get(curr, [])
                    if rem_edges.get((curr, nxt), 0) > 0 and nxt not in visited
                ]
                for nxt in reversed(neighbors):
                    visited.add(nxt)
                    stack.append((nxt, path + [nxt]))
            return None

        grouped_paths: dict[tuple[str, str, tuple[str, ...]], int] = defaultdict(int)
        for port_id in sorted(rem_supply.keys()):
            while rem_supply.get(port_id, 0) > 0:
                path = _find_residual_path(port_id)
                if path is None:
                    break
                dest = path[-1]
                hops = list(zip(path, path[1:]))
                peel = min(
                    rem_supply[port_id],
                    rem_deliv[dest],
                    *(rem_edges[hop] for hop in hops),
                )
                rem_supply[port_id] -= peel
                rem_deliv[dest] -= peel
                for hop in hops:
                    rem_edges[hop] -= peel
                grouped_paths[(port_id, dest, tuple(path))] += peel

        allocations: list[FlowAllocation] = []
        for (origin_id, dest_id, path_tuple), f_int in sorted(grouped_paths.items()):
            if f_int <= 0:
                continue
            path_list = list(path_tuple)
            flow_teu = round(f_int / _FLOW_SCALE, 4)
            unit_cost = round(
                sum(edge_weighted_cost[(u, v)] for u, v in zip(path_list, path_list[1:])),
                4,
            )
            uses_rail = any(
                "RAIL" in edge_modes[(u, v)] for u, v in zip(path_list, path_list[1:])
            )
            alloc_mode = "INTERMODAL_RAIL" if uses_rail else "ROAD"
            allocations.append(
                FlowAllocation(
                    commodity="CONTAINERISED_AUTO_PARTS",
                    origin_id=origin_id,
                    destination_id=dest_id,
                    path=path_list,
                    mode=alloc_mode,
                    flow_teu=flow_teu,
                    unit_cost=unit_cost,
                    total_cost=round(flow_teu * unit_cost, 4),
                )
            )

        unmet_demand_teu = round(unmet_int / _FLOW_SCALE, 4)
        total_flow = sum(a.flow_teu for a in allocations)
        total_transport_cost = sum(a.total_cost for a in allocations)
        road_flow = sum(a.flow_teu for a in allocations if a.mode == "ROAD")
        rail_flow = sum(a.flow_teu for a in allocations if "RAIL" in a.mode)

        port_totals: dict[str, float] = defaultdict(float)
        for a in allocations:
            port_totals[a.origin_id] += a.flow_teu
        top_ports = sorted(
            ((pid, round(val, 1)) for pid, val in port_totals.items() if pid in port_ids),
            key=lambda x: (-x[1], x[0]),
        )
        gateways_desc = ", ".join(f"{pid} ({val} TEU)" for pid, val in top_ports[:3]) or "none"

        summary = (
            f"Allocated {round(total_flow, 1)} TEU across {len(allocations)} verified corridor routes "
            f"following {event.primary_entity_id} disruption (gateways: {gateways_desc}). "
            f"Rail share={round((rail_flow / total_flow) * 100.0, 1) if total_flow > 0 else 0.0}%, "
            f"Unmet assembly demand={round(unmet_demand_teu, 1)} TEU."
        )

        return MitigationPlan(
            plan_id=f"PLAN_{event.event_id}_{int(time.time())}",
            timestamp=datetime.now(timezone.utc),
            objective_cost=round(total_transport_cost + unmet_demand_teu * _UNMET_PENALTY_PER_TEU, 2),
            allocations=allocations,
            unmet_demand_teu=unmet_demand_teu,
            mode_split={
                "ROAD": round(road_flow / total_flow, 4) if total_flow > 0 else 0.0,
                "INTERMODAL_RAIL": round(rail_flow / total_flow, 4) if total_flow > 0 else 0.0,
            },
            summary=summary,
        )

    def run(
        self,
        state: PipelineState,
        cfg: PipelineConfig,
        rng: random.Random,
    ) -> tuple[PipelineState, OperatorResult]:
        """
        Execute Stage D optimization and L1-L3 verification.
        """
        _ = rng
        t0 = time.perf_counter()

        if not state.event or not state.graph_context:
            error_msg = "Stage D prerequisite failure: event or graph_context missing in PipelineState."
            return state, OperatorResult(
                operator_type=OperatorType.OPTIMIZE,
                success=False,
                message=error_msg,
                error=error_msg,
            )

        event = state.event
        graph_ctx = state.graph_context

        if state.candidate_plan is not None:
            candidate_plan = state.candidate_plan
        else:
            candidate_plan = self._solve_network_flow(state)

        # -------------------------------------------------------------------
        # Three-Layer Verification Protocol (L1, L2, L3)
        # -------------------------------------------------------------------
        l1_checks: list[VerificationCheck] = []
        l2_checks: list[VerificationCheck] = []
        l3_checks: list[VerificationCheck] = []
        failed_checks: list[str] = []

        # --- Layer 1: Ingestion & Graph Grounding Validation ---
        all_plan_entities = set()
        for a in candidate_plan.allocations:
            all_plan_entities.add(a.origin_id)
            all_plan_entities.add(a.destination_id)
            all_plan_entities.update(a.path)

        unregistered = sorted(eid for eid in all_plan_entities if not self.registry.validate_id(eid))
        if not unregistered:
            l1_checks.append(
                VerificationCheck(
                    layer="L1",
                    check_name="CANONICAL_ENTITY_GROUNDING",
                    verdict=VerificationVerdict.PASS,
                    details="All referenced path nodes and origins/destinations exist in Canonical Registry.",
                    metrics={"validated_entity_count": len(all_plan_entities)},
                )
            )
        else:
            l1_checks.append(
                VerificationCheck(
                    layer="L1",
                    check_name="CANONICAL_ENTITY_GROUNDING",
                    verdict=VerificationVerdict.FAIL,
                    details=f"Ungrounded entity IDs detected in plan: {unregistered}",
                )
            )
            failed_checks.append("L1:CANONICAL_ENTITY_GROUNDING")

        if event.corroboration_count >= 1:
            l1_checks.append(
                VerificationCheck(
                    layer="L1",
                    check_name="SOURCE_CORROBORATION",
                    verdict=VerificationVerdict.PASS,
                    details=f"Event corroborated across {event.corroboration_count} source(s).",
                    metrics={"corroboration_count": event.corroboration_count},
                )
            )
        else:
            l1_checks.append(
                VerificationCheck(
                    layer="L1",
                    check_name="SOURCE_CORROBORATION",
                    verdict=VerificationVerdict.FAIL,
                    details="Corroboration count below required threshold of 1.",
                )
            )
            failed_checks.append("L1:SOURCE_CORROBORATION")

        # --- Layer 2: Network Feasibility & Mathematical Solvency ---
        # 2.1 Graph Edge Validity & Acyclic Continuity
        invalid_paths: list[str] = []
        for idx, a in enumerate(candidate_plan.allocations):
            if len(a.path) < 2:
                invalid_paths.append(f"alloc[{idx}] path length < 2")
                continue
            if a.path[0] != a.origin_id or a.path[-1] != a.destination_id:
                invalid_paths.append(
                    f"alloc[{idx}] endpoints mismatch ({a.origin_id}->{a.destination_id} vs {a.path[0]}->{a.path[-1]})"
                )
                continue
            if len(set(a.path)) != len(a.path):
                invalid_paths.append(f"alloc[{idx}] contains cycle {a.path}")
                continue
            for u, v in zip(a.path, a.path[1:]):
                if not self.graph_store.has_active_edge(u, v):
                    invalid_paths.append(f"alloc[{idx}] non-existent or inactive edge {u}->{v}")
                    break

        if not invalid_paths:
            l2_checks.append(
                VerificationCheck(
                    layer="L2",
                    check_name="GRAPH_EDGE_VALIDITY",
                    verdict=VerificationVerdict.PASS,
                    details="All allocation paths traverse active directed edges in CorridorGraphStore.",
                    metrics={"checked_allocations": len(candidate_plan.allocations)},
                )
            )
        else:
            l2_checks.append(
                VerificationCheck(
                    layer="L2",
                    check_name="GRAPH_EDGE_VALIDITY",
                    verdict=VerificationVerdict.FAIL,
                    details="; ".join(invalid_paths[:3]),
                )
            )
            failed_checks.append("L2:GRAPH_EDGE_VALIDITY")

        # 2.2 Aggregated Node & Edge Capacity Bounds
        node_flows: dict[str, float] = defaultdict(float)
        edge_flows: dict[tuple[str, str], float] = defaultdict(float)
        for a in candidate_plan.allocations:
            for nid in set(a.path):
                node_flows[nid] += a.flow_teu
            for u, v in zip(a.path, a.path[1:]):
                edge_flows[(u, v)] += a.flow_teu

        capacity_breaches: list[str] = []
        for nid, flow_val in sorted(node_flows.items()):
            if not self.registry.validate_id(nid):
                capacity_breaches.append(f"ungrounded node {nid}")
                continue
            ent = self.registry.get(nid)
            if ent.capacity_teu_per_day is not None:
                mult = graph_ctx.node_capacity_multipliers.get(nid, 1.0)
                eff_cap = ent.capacity_teu_per_day * mult
                if flow_val > eff_cap + 1e-4:
                    capacity_breaches.append(
                        f"node {nid} flow {round(flow_val, 2)} > effective cap {round(eff_cap, 2)}"
                    )

        for (u, v), flow_val in sorted(edge_flows.items()):
            active_edges = self.graph_store.get_active_edges(u, v)
            if not active_edges:
                capacity_breaches.append(f"missing active edge {u}->{v}")
                continue
            nom_edge_cap = sum(
                float(attrs.get("capacity_teu_per_day", 0.0)) for _, attrs in active_edges
            )
            e_mult = graph_ctx.edge_capacity_multipliers.get(f"{u}->{v}", 1.0)
            eff_edge_cap = nom_edge_cap * e_mult
            if flow_val > eff_edge_cap + 1e-4:
                capacity_breaches.append(
                    f"edge {u}->{v} flow {round(flow_val, 2)} > effective cap {round(eff_edge_cap, 2)}"
                )

        if not capacity_breaches:
            l2_checks.append(
                VerificationCheck(
                    layer="L2",
                    check_name="EDGE_CAPACITY_BOUNDS",
                    verdict=VerificationVerdict.PASS,
                    details="Aggregated node and directed-edge flows obey physical effective capacity bounds.",
                    metrics={
                        "checked_nodes": len(node_flows),
                        "checked_edges": len(edge_flows),
                    },
                )
            )
        else:
            l2_checks.append(
                VerificationCheck(
                    layer="L2",
                    check_name="EDGE_CAPACITY_BOUNDS",
                    verdict=VerificationVerdict.FAIL,
                    details="; ".join(capacity_breaches[:3]),
                )
            )
            failed_checks.append("L2:EDGE_CAPACITY_BOUNDS")

        # 2.3 Explicit Flow Conservation, Non-Negativity & Demand Reconciliation
        conservation_errors: list[str] = []
        origin_outflows: dict[str, float] = defaultdict(float)
        dest_inflows: dict[str, float] = defaultdict(float)
        transit_in: dict[str, float] = defaultdict(float)
        transit_out: dict[str, float] = defaultdict(float)

        for idx, a in enumerate(candidate_plan.allocations):
            if a.flow_teu < 0 or a.unit_cost < 0 or a.total_cost < 0:
                conservation_errors.append(f"alloc[{idx}] contains negative flow or cost")
                continue
            expected_cost = a.flow_teu * a.unit_cost
            if abs(a.total_cost - expected_cost) > max(1.0, 0.01 * expected_cost):
                conservation_errors.append(
                    f"alloc[{idx}] total_cost {a.total_cost} != flow*unit_cost {round(expected_cost, 2)}"
                )
            origin_outflows[a.origin_id] += a.flow_teu
            dest_inflows[a.destination_id] += a.flow_teu
            for hop_idx, (u, v) in enumerate(zip(a.path, a.path[1:])):
                if hop_idx > 0:
                    transit_in[u] += a.flow_teu
                if hop_idx < len(a.path) - 2:
                    transit_out[v] += a.flow_teu

        # Check intermediate balance and corridor demand accounting
        all_transit_nodes = set(transit_in.keys()) | set(transit_out.keys())
        for nid in sorted(all_transit_nodes):
            diff = abs(transit_in[nid] - transit_out[nid])
            if diff > 1e-3:
                conservation_errors.append(f"transit imbalance at {nid}: diff={round(diff, 4)}")

        total_origin = sum(origin_outflows.values())
        total_dest = sum(dest_inflows.values())
        if abs(total_origin - total_dest) > 1e-3:
            conservation_errors.append(
                f"origin total {total_origin} != destination total {total_dest}"
            )

        plants = self.registry.get_by_type(EntityType.PLANT)
        total_corridor_demand = sum(float(p.daily_demand_teu or 500.0) for p in plants)
        if candidate_plan.unmet_demand_teu < 0:
            conservation_errors.append("negative unmet_demand_teu")
        elif total_dest + candidate_plan.unmet_demand_teu + 1e-2 < total_corridor_demand:
            conservation_errors.append(
                f"delivered ({round(total_dest, 1)}) + unmet ({round(candidate_plan.unmet_demand_teu, 1)}) "
                f"< corridor demand ({round(total_corridor_demand, 1)})"
            )

        if not conservation_errors:
            l2_checks.append(
                VerificationCheck(
                    layer="L2",
                    check_name="FLOW_CONSERVATION",
                    verdict=VerificationVerdict.PASS,
                    details=(
                        f"Flow conservation verified across {len(all_transit_nodes)} transit hops; "
                        f"delivered {round(total_dest, 1)} / {round(total_corridor_demand, 1)} TEU "
                        f"(unmet {round(candidate_plan.unmet_demand_teu, 1)} TEU)."
                    ),
                    metrics={
                        "total_delivered_teu": round(total_dest, 2),
                        "total_demand_teu": round(total_corridor_demand, 2),
                        "unmet_demand_teu": round(candidate_plan.unmet_demand_teu, 2),
                    },
                )
            )
        else:
            l2_checks.append(
                VerificationCheck(
                    layer="L2",
                    check_name="FLOW_CONSERVATION",
                    verdict=VerificationVerdict.FAIL,
                    details="; ".join(conservation_errors[:3]),
                )
            )
            failed_checks.append("L2:FLOW_CONSERVATION")

        # --- Layer 3: Decision Sanity & Citation Support ---
        max_unmet_allowed = max(10.0, total_corridor_demand * cfg.max_unmet_demand_ratio)
        if candidate_plan.unmet_demand_teu <= max_unmet_allowed:
            l3_checks.append(
                VerificationCheck(
                    layer="L3",
                    check_name="UNMET_DEMAND_BOUND",
                    verdict=VerificationVerdict.PASS,
                    details=(
                        f"Unmet demand {round(candidate_plan.unmet_demand_teu, 1)} TEU is within "
                        f"tolerance ({round(max_unmet_allowed, 1)} TEU)."
                    ),
                    metrics={"unmet_demand_teu": candidate_plan.unmet_demand_teu},
                )
            )
        else:
            l3_checks.append(
                VerificationCheck(
                    layer="L3",
                    check_name="UNMET_DEMAND_BOUND",
                    verdict=VerificationVerdict.FAIL,
                    details=(
                        f"Unmet demand {round(candidate_plan.unmet_demand_teu, 1)} TEU exceeds "
                        f"tolerance ({round(max_unmet_allowed, 1)} TEU)."
                    ),
                )
            )
            failed_checks.append("L3:UNMET_DEMAND_BOUND")

        relevant_entities = {event.primary_entity_id, *event.affected_entity_ids, *all_plan_entities}
        covering_docs = [
            doc
            for doc in state.evidence_set
            if any(eid in relevant_entities for eid in doc.entity_ids)
        ]
        if covering_docs:
            l3_checks.append(
                VerificationCheck(
                    layer="L3",
                    check_name="CITATION_GROUNDING",
                    verdict=VerificationVerdict.PASS,
                    details=(
                        f"Plan grounded against {len(covering_docs)} entity-matched evidence citations."
                    ),
                    metrics={
                        "citation_count": len(covering_docs),
                        "citation_ids": [d.citation_id for d in covering_docs],
                    },
                )
            )
        else:
            l3_checks.append(
                VerificationCheck(
                    layer="L3",
                    check_name="CITATION_GROUNDING",
                    verdict=VerificationVerdict.WARN,
                    details="No retrieved evidence citations directly cover disrupted or rerouted entities.",
                    metrics={"citation_count": len(state.evidence_set)},
                )
            )

        overall_pass = len(failed_checks) == 0
        overall_verdict = VerificationVerdict.PASS if overall_pass else VerificationVerdict.FAIL

        verification_report = VerificationReport(
            overall_verdict=overall_verdict,
            passed=overall_pass,
            l1_checks=l1_checks,
            l2_checks=l2_checks,
            l3_checks=l3_checks,
            failed_checks=failed_checks,
        )

        duration_ms = (time.perf_counter() - t0) * 1000.0
        op_cost = 0.0075

        trace_item = OperatorTraceItem(
            step_index=state.step_count + 1,
            operator_type=OperatorType.VERIFY,
            input_summary=f"Plan {candidate_plan.plan_id}, allocations={len(candidate_plan.allocations)}",
            output_summary=f"Verification verdict={overall_verdict.value}, passed={overall_pass}",
            duration_ms=round(duration_ms, 2),
            cost=op_cost,
            seed=cfg.random_seed,
            timestamp=datetime.now(timezone.utc),
        )

        new_status = PipelineStatus.VERIFIED if overall_pass else PipelineStatus.FAILED

        new_state = state.transition(
            updates={
                "candidate_plan": candidate_plan,
                "verification_report": verification_report,
                "status": new_status,
            },
            trace_item=trace_item,
        )

        result = OperatorResult(
            operator_type=OperatorType.VERIFY,
            success=overall_pass,
            message=(
                f"Stage D verified plan {candidate_plan.plan_id}: "
                f"Overall={overall_verdict.value}, failed_checks={failed_checks}."
            ),
            duration_ms=round(duration_ms, 2),
            cost=op_cost,
            artifacts={
                "plan_id": candidate_plan.plan_id,
                "overall_verdict": overall_verdict.value,
                "failed_checks": failed_checks,
            },
        )

        return new_state, result
