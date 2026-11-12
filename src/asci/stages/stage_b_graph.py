"""
Stage B: Corridor Risk Graph & Path Impact Engine.
Extracts impacted k-hop subgraphs, path exposure, criticality, and plant line-stop KPIs.
"""

from __future__ import annotations

import math
import random
import time
from datetime import UTC, datetime

from asci.core.contracts import OperatorResult, PipelineConfig
from asci.core.registry import CanonicalEntityRegistry, EntityType, get_canonical_registry
from asci.core.state import (
    GraphContext,
    LineStopMetric,
    OperatorTraceItem,
    OperatorType,
    PathRiskMetric,
    PipelineState,
    PipelineStatus,
)
from asci.stages.stage_b_propagate import (
    propagate_graph_context,
    propagate_graph_context_tier2,
)
from asci.uskl.graph_store import CorridorGraphStore


class StageBCorridorRisk:
    """
    Stage B Operator: Computes corridor graph vulnerability and plant line-stop timelines.
    """

    def __init__(
        self,
        graph_store: CorridorGraphStore | None = None,
        registry: CanonicalEntityRegistry | None = None,
    ) -> None:
        self.registry = registry or get_canonical_registry()
        self.graph_store = graph_store or CorridorGraphStore.load_from_json(registry=self.registry)

    def _compute_path_nominal_and_residual(
        self,
        path: list[str],
        node_multipliers: dict[str, float],
        edge_multipliers: dict[str, float],
    ) -> tuple[float, float, float, float]:
        """Return (nominal_cap, residual_cap, nominal_transit_hrs, min_multiplier) for a path."""
        nominal_caps: list[float] = []
        residual_caps: list[float] = []
        multipliers: list[float] = []

        for nid in path:
            ent = self.registry.get(nid)
            n_mult = node_multipliers.get(nid, 1.0)
            multipliers.append(n_mult)
            if ent.capacity_teu_per_day is not None:
                nominal_caps.append(float(ent.capacity_teu_per_day))
                residual_caps.append(float(ent.capacity_teu_per_day) * n_mult)

        transit_hrs = 0.0
        for u, v in zip(path, path[1:], strict=False):
            edges = self.graph_store.get_active_edges(u, v)
            if not edges:
                return 0.0, 0.0, float("inf"), 0.0
            e_mult = edge_multipliers.get(f"{u}->{v}", 1.0)
            multipliers.append(e_mult)
            hop_nom_cap = sum(float(attrs.get("capacity_teu_per_day", 1000.0)) for _, attrs in edges)
            nominal_caps.append(hop_nom_cap)
            residual_caps.append(hop_nom_cap * e_mult)
            transit_hrs += min(float(attrs.get("transit_time_hrs", 2.0)) for _, attrs in edges)

        nom_cap = min(nominal_caps) if nominal_caps else 0.0
        res_cap = min(residual_caps) if residual_caps else 0.0
        min_mult = min(multipliers) if multipliers else 1.0
        return nom_cap, res_cap, transit_hrs, min_mult

    def run(
        self,
        state: PipelineState,
        cfg: PipelineConfig,
        rng: random.Random,
    ) -> tuple[PipelineState, OperatorResult]:
        """
        Execute Stage B graph analysis.
        Calculates k-hop impacted subgraph, topology-grounded path exposures, and plant Time-to-Line-Stop.
        """
        _ = rng
        t0 = time.perf_counter()

        if not state.event:
            error_msg = "Stage B failure: PipelineState does not contain an ingested DisruptionEvent."
            return state, OperatorResult(
                operator_type=OperatorType.GRAPH_ANALYZE,
                success=False,
                message=error_msg,
                error=error_msg,
            )

        event = state.event
        primary_node = event.primary_entity_id
        affected_nodes = [primary_node] + [
            nid for nid in event.affected_entity_ids if nid != primary_node
        ]

        # Compute capacity multipliers based on event severity
        node_multipliers: dict[str, float] = {}
        for nid in self.graph_store.get_all_nodes():
            if nid == primary_node:
                node_multipliers[nid] = max(0.05, round(1.0 - event.severity, 2))
            elif nid in event.affected_entity_ids:
                node_multipliers[nid] = max(0.20, round(1.0 - (event.severity * 0.6), 2))
            else:
                node_multipliers[nid] = 1.0

        # Edge capacity multipliers
        edge_multipliers: dict[str, float] = {}
        impacted_edges: list[tuple[str, str]] = []
        for u, v, _ in self.graph_store.get_all_edges():
            key = f"{u}->{v}"
            if u in affected_nodes or v in affected_nodes:
                mult = min(node_multipliers.get(u, 1.0), node_multipliers.get(v, 1.0))
                edge_multipliers[key] = min(edge_multipliers.get(key, 1.0), mult)
                if (u, v) not in impacted_edges:
                    impacted_edges.append((u, v))
            else:
                edge_multipliers.setdefault(key, 1.0)

        # Build simple active DiGraph view once per run for fast k-shortest path queries & centrality
        simple_graph = self.graph_store.build_simple_active_digraph()

        # Extract k-hop subgraph and optionally run Tier-1/Tier-2 propagation
        k_hops = cfg.k_hop_neighborhood
        propagated_delays: dict[str, float] = {}
        hop_decay_applied = False
        prop_tier = 1
        redistributed_loads: dict[str, float] = {}
        edge_congestion_ratios: dict[str, float] = {}
        if cfg.enable_propagation:
            if cfg.propagation_tier >= 2:
                (
                    node_multipliers,
                    edge_multipliers,
                    propagated_delays,
                    impacted_nodes,
                    redistributed_loads,
                    edge_congestion_ratios,
                ) = propagate_graph_context_tier2(
                    graph_store=self.graph_store,
                    registry=self.registry,
                    affected_nodes=affected_nodes,
                    severity=event.severity,
                    k_hops=k_hops,
                    base_node_multipliers=node_multipliers,
                    base_edge_multipliers=edge_multipliers,
                    simple_graph=simple_graph,
                )
                prop_tier = 2
            else:
                node_multipliers, edge_multipliers, propagated_delays, impacted_nodes = (
                    propagate_graph_context(
                        graph_store=self.graph_store,
                        registry=self.registry,
                        affected_nodes=affected_nodes,
                        severity=event.severity,
                        k_hops=k_hops,
                        base_node_multipliers=node_multipliers,
                        base_edge_multipliers=edge_multipliers,
                    )
                )
                prop_tier = 1
            hop_decay_applied = True
        else:
            subgraph = self.graph_store.get_k_hop_subgraph(affected_nodes, k=k_hops)
            impacted_nodes = list(subgraph.nodes)

        betweenness, edge_betweenness = self.graph_store.get_centrality_metrics(
            simple_graph=simple_graph
        )

        uncertainty_factor = round(
            min(
                2.0,
                1.0
                + (1.0 - event.confidence) * 0.65
                + (0.35 / math.sqrt(max(1, event.corroboration_count))),
            ),
            4,
        )

        ports = self.registry.get_by_type(EntityType.PORT)
        plants = self.registry.get_by_type(EntityType.PLANT)
        port_ids = [e.id for e in ports]
        plant_ids = [e.id for e in plants]

        total_corridor_capacity = sum(
            float(e.capacity_teu_per_day or 0.0) for e in ports
        ) or 1.0
        total_plant_demand = sum(float(e.daily_demand_teu or 500.0) for e in plants) or 1.0

        path_metrics: list[PathRiskMetric] = []
        line_stop_metrics: list[LineStopMetric] = []

        path_cutoff = 6 if len(self.registry) <= 40 else 8

        for plant_id in plant_ids:
            plant_entity = self.registry.get(plant_id)
            days_of_cover = plant_entity.days_of_cover or 4.0
            demand_dep = (plant_entity.daily_demand_teu or 500.0) / total_plant_demand
            plant_demand = float(plant_entity.daily_demand_teu or 500.0)

            candidate_plant_paths: list[
                tuple[str, list[str], float, float, float, float]
            ] = []
            distinct_origin_ports: set[str] = set()
            healthy_origin_ports: set[str] = set()

            for port_id in port_ids:
                paths = self.graph_store.find_ranked_paths(
                    port_id,
                    plant_id,
                    max_paths=2,
                    cutoff=path_cutoff,
                    simple_graph=simple_graph,
                )
                for path in paths:
                    nom_cap, res_cap, nominal_hrs, min_mult = (
                        self._compute_path_nominal_and_residual(
                            path, node_multipliers, edge_multipliers
                        )
                    )
                    if math.isinf(nominal_hrs):
                        continue
                    distinct_origin_ports.add(port_id)
                    traverses_impact = any(node in affected_nodes for node in path)
                    if not traverses_impact and min_mult >= 0.70:
                        healthy_origin_ports.add(port_id)
                    candidate_plant_paths.append(
                        (port_id, path, nom_cap, res_cap, nominal_hrs, min_mult)
                    )

            total_origin_ports = max(1, len(distinct_origin_ports))
            healthy_port_ratio = len(healthy_origin_ports) / total_origin_ports
            plant_concentration = round(
                min(2.0, (1.0 / total_origin_ports) + 0.50 * (1.0 - healthy_port_ratio)),
                4,
            )

            best_nominal_hrs = float("inf")
            best_healthy_hrs = float("inf")
            healthy_residual_cap = 0.0
            impacted_path_delays: list[float] = []

            for port_id, path, nom_cap, res_cap, nominal_hrs, min_mult in candidate_plant_paths:
                best_nominal_hrs = min(best_nominal_hrs, nominal_hrs)
                traverses_impact = any(node in affected_nodes for node in path)
                spillover_hrs = sum(
                    propagated_delays.get(nid, 0.0)
                    for nid in path
                    if nid not in affected_nodes
                )
                if traverses_impact:
                    added_delay = (
                        (1.0 - min_mult)
                        * min(event.estimated_duration_days, 4.0)
                        * 24.0
                        * 0.55
                    )
                    path_delay_hrs = round(nominal_hrs + added_delay + 0.5 * spillover_hrs, 2)
                    impacted_path_delays.append(path_delay_hrs)
                else:
                    path_delay_hrs = round(nominal_hrs + 0.35 * spillover_hrs, 2)
                    best_healthy_hrs = min(best_healthy_hrs, path_delay_hrs)
                    healthy_residual_cap += res_cap

                exposure = round(
                    min(1.0, nom_cap / total_corridor_capacity),
                    4,
                )
                link_congestion = max(
                    (
                        edge_congestion_ratios.get(f"{u}->{v}", 0.0)
                        for u, v in zip(path, path[1:], strict=False)
                    ),
                    default=0.0,
                )
                utilisation = round(
                    min(1.0, max(0.05, max(plant_demand / max(1.0, res_cap), link_congestion))),
                    4,
                )
                path_node_betw = max(betweenness.get(nid, 0.0) for nid in path)
                path_edge_betw = max(
                    (
                        edge_betweenness.get((u, v), 0.0)
                        for u, v in zip(path, path[1:], strict=False)
                    ),
                    default=0.0,
                )
                betweenness_factor = min(1.0, max(0.10, max(path_node_betw, path_edge_betw) * 3.0))
                demand_factor = min(1.0, max(0.10, demand_dep * 3.5))
                impact_factor = (1.0 - min_mult) if traverses_impact else 0.15
                impact_scale = 0.35 + 0.65 * impact_factor

                criticality = round(
                    min(
                        1.0,
                        max(
                            0.05,
                            (betweenness_factor * utilisation * demand_factor * 4.0 * impact_scale)
                            + (0.10 * impact_scale),
                        ),
                    ),
                    4,
                )
                risk_val = round(
                    exposure * criticality * event.severity * uncertainty_factor * plant_concentration,
                    4,
                )
                mode = self.graph_store.get_path_mode(path)

                path_metrics.append(
                    PathRiskMetric(
                        origin_id=port_id,
                        destination_id=plant_id,
                        path=path,
                        mode=mode,
                        exposure=exposure,
                        criticality=criticality,
                        utilisation=utilisation,
                        uncertainty_factor=uncertainty_factor,
                        concentration=plant_concentration,
                        path_risk=risk_val,
                        baseline_delay_hrs=path_delay_hrs,
                    )
                )

            # Plant expected inbound delay (hours above free-flow baseline)
            if not impacted_path_delays:
                expected_delay_hrs = 0.0
            elif not math.isinf(best_healthy_hrs) and healthy_residual_cap >= plant_demand:
                reroute_delta = max(4.0, best_healthy_hrs - best_nominal_hrs)
                expected_delay_hrs = min(reroute_delta, min(impacted_path_delays))
            else:
                expected_delay_hrs = min(impacted_path_delays) - (
                    best_nominal_hrs if not math.isinf(best_nominal_hrs) else 0.0
                )
                expected_delay_hrs = max(expected_delay_hrs, 0.0)

            expected_delay_days = round(expected_delay_hrs / 24.0, 2)
            time_to_line_stop = round(days_of_cover - expected_delay_days, 2)
            risk_score = 0.0
            if days_of_cover > 0:
                risk_score = min(1.0, max(0.0, round(expected_delay_days / days_of_cover, 2)))

            # Scenario-aware probability of inbound delay exhausting plant buffer days-of-cover
            delay_branches = [
                (0.55, expected_delay_days),
                (0.30, expected_delay_days * (1.25 + 0.50 * (1.0 - event.confidence))),
                (0.15, expected_delay_days * 0.60),
            ]
            if state.scenario_set:
                total_p = sum(s.probability for s in state.scenario_set) or 1.0
                delay_branches = [
                    (
                        s.probability / total_p,
                        expected_delay_days * max(0.5, s.duration_days / max(0.5, event.estimated_duration_days)),
                    )
                    for s in state.scenario_set
                ]
            prob_accum = 0.0
            for prob_s, delay_s in delay_branches:
                if delay_s <= 0.0 or days_of_cover <= 0.0:
                    continue
                ratio = delay_s / days_of_cover
                if ratio >= 1.0:
                    prob_accum += prob_s
                elif ratio > 0.50:
                    prob_accum += prob_s * ((ratio - 0.50) / 0.50) * 0.75
            line_stop_prob = round(min(1.0, max(0.0, prob_accum)), 4)

            line_stop_metrics.append(
                LineStopMetric(
                    plant_id=plant_id,
                    days_of_cover=days_of_cover,
                    expected_delay_days=expected_delay_days,
                    time_to_line_stop_days=time_to_line_stop,
                    line_stop_risk=risk_score,
                    line_stop_probability=line_stop_prob,
                )
            )

        graph_context = GraphContext(
            impacted_nodes=impacted_nodes,
            impacted_edges=impacted_edges,
            node_capacity_multipliers=node_multipliers,
            edge_capacity_multipliers=edge_multipliers,
            k_hops=k_hops,
            propagated_node_delays_hrs=propagated_delays,
            hop_decay_applied=hop_decay_applied,
            propagation_tier=prop_tier,
            redistributed_edge_loads_teu=redistributed_loads,
            edge_congestion_ratios=edge_congestion_ratios,
            path_metrics=path_metrics,
            line_stop_metrics=line_stop_metrics,
        )

        duration_ms = (time.perf_counter() - t0) * 1000.0
        op_cost = 0.0035

        trace_item = OperatorTraceItem(
            step_index=state.step_count + 1,
            operator_type=OperatorType.GRAPH_ANALYZE,
            input_summary=f"Event {event.event_id} at {primary_node}, k={k_hops}",
            output_summary=(
                f"Impacted nodes={len(impacted_nodes)}, paths={len(path_metrics)}, "
                f"critical plants={sum(1 for ls in line_stop_metrics if ls.time_to_line_stop_days < 1.5)}"
            ),
            duration_ms=round(duration_ms, 2),
            cost=op_cost,
            seed=cfg.random_seed,
            timestamp=datetime.now(UTC),
        )

        new_state = state.transition(
            updates={
                "graph_context": graph_context,
                "status": PipelineStatus.ANALYZED,
            },
            trace_item=trace_item,
        )

        result = OperatorResult(
            operator_type=OperatorType.GRAPH_ANALYZE,
            success=True,
            message=(
                f"Stage B analyzed corridor graph: {len(impacted_nodes)} nodes impacted, "
                f"{len(line_stop_metrics)} plant line-stop metrics evaluated."
            ),
            duration_ms=round(duration_ms, 2),
            cost=op_cost,
            artifacts={
                "impacted_node_count": len(impacted_nodes),
                "path_count": len(path_metrics),
            },
        )

        return new_state, result

