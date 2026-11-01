"""
Stage B: Corridor Risk Graph & Path Impact Engine.
Extracts impacted k-hop subgraphs, path exposure, criticality, and plant line-stop KPIs.
"""

from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from typing import Any

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

    def run(
        self,
        state: PipelineState,
        cfg: PipelineConfig,
        rng: random.Random,
    ) -> tuple[PipelineState, OperatorResult]:
        """
        Execute Stage B graph analysis.
        Calculates k-hop impacted subgraph, path exposures, and plant Time-to-Line-Stop.
        """
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
                edge_multipliers[key] = mult
                impacted_edges.append((u, v))
            else:
                edge_multipliers[key] = 1.0

        # Extract k-hop subgraph
        k_hops = cfg.k_hop_neighborhood
        subgraph = self.graph_store.get_k_hop_subgraph(affected_nodes, k=k_hops)
        impacted_nodes = list(subgraph.nodes)

        # Enumerate critical paths from gateway ports to key assembly plants
        ports = [e.id for e in self.registry.get_by_type(EntityType.PORT)]
        plants = [e.id for e in self.registry.get_by_type(EntityType.PLANT)]

        path_metrics: list[PathRiskMetric] = []
        line_stop_metrics: list[LineStopMetric] = []

        total_corridor_capacity = 30000.0

        for plant_id in plants:
            plant_entity = self.registry.get(plant_id)
            days_of_cover = plant_entity.days_of_cover or 4.0

            # Calculate path risks from affected ports to this plant
            max_inbound_delay_hrs = 0.0

            for port_id in ports:
                paths = self.graph_store.find_candidate_paths(port_id, plant_id, cutoff=4)
                for path in paths[:2]:
                    # Determine whether this path traverses impacted nodes
                    traverses_impact = any(node in affected_nodes for node in path)
                    base_delay = 48.0 if traverses_impact else 4.0
                    if traverses_impact and base_delay > max_inbound_delay_hrs:
                        max_inbound_delay_hrs = base_delay

                    exposure = round(1200.0 / total_corridor_capacity, 3)
                    criticality = 0.85 if traverses_impact else 0.25
                    risk_val = round(exposure * criticality * event.severity, 3)

                    path_metrics.append(
                        PathRiskMetric(
                            origin_id=port_id,
                            destination_id=plant_id,
                            path=path,
                            mode="ROAD" if "RAIL" not in str(path) else "INTERMODAL",
                            exposure=exposure,
                            criticality=criticality,
                            path_risk=risk_val,
                            baseline_delay_hrs=base_delay,
                        )
                    )

            # Plant line-stop calculation: Days-of-Cover - Expected Inbound Delay (days)
            expected_delay_days = round(max_inbound_delay_hrs / 24.0, 2)
            time_to_line_stop = round(days_of_cover - expected_delay_days, 2)
            risk_score = 0.0
            if days_of_cover > 0:
                risk_score = min(1.0, max(0.0, round(expected_delay_days / days_of_cover, 2)))

            line_stop_metrics.append(
                LineStopMetric(
                    plant_id=plant_id,
                    days_of_cover=days_of_cover,
                    expected_delay_days=expected_delay_days,
                    time_to_line_stop_days=time_to_line_stop,
                    line_stop_risk=risk_score,
                )
            )

        graph_context = GraphContext(
            impacted_nodes=impacted_nodes,
            impacted_edges=impacted_edges,
            node_capacity_multipliers=node_multipliers,
            edge_capacity_multipliers=edge_multipliers,
            k_hops=k_hops,
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
            timestamp=datetime.now(timezone.utc),
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

