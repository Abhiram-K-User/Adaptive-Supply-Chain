"""
Stage E: Operational Dashboard & State-to-UI Payload Serializer.
Prepares structured payloads for the Cytoscape.js geospatial map and planner review panels.
"""

from __future__ import annotations

import random
import time
from datetime import UTC, datetime
from typing import Any

from asci.core.contracts import OperatorResult, PipelineConfig
from asci.core.registry import CanonicalEntityRegistry, get_canonical_registry
from asci.core.state import (
    DashboardPayload,
    OperatorTraceItem,
    OperatorType,
    PipelineState,
    PipelineStatus,
)
from asci.llm.explainer import PlanBriefingGenerator
from asci.uskl.graph_store import CorridorGraphStore


class StageEDashboard:
    """
    Stage E Operator: State-to-UI Serializer.
    Transforms internal immutable state into rich, typed frontend models.
    """

    def __init__(
        self,
        registry: CanonicalEntityRegistry | None = None,
        graph_store: CorridorGraphStore | None = None,
        briefing_generator: PlanBriefingGenerator | None = None,
    ) -> None:
        self.registry = registry or get_canonical_registry()
        self.graph_store = graph_store or CorridorGraphStore.load_from_json(registry=self.registry)
        self.briefing_generator = briefing_generator or PlanBriefingGenerator(
            registry=self.registry
        )

    def run(
        self,
        state: PipelineState,
        cfg: PipelineConfig,
        rng: random.Random,
    ) -> tuple[PipelineState, OperatorResult]:
        """
        Execute Stage E serialization.
        """
        t0 = time.perf_counter()

        event = state.event
        plan = state.candidate_plan
        graph_ctx = state.graph_context
        verif = state.verification_report

        # 1. Geospatial Network Serializer (Cytoscape.js compatible)
        nodes_payload: list[dict[str, Any]] = []
        for entity_id, entity in self.registry.all_entities().items():
            mult = graph_ctx.node_capacity_multipliers.get(entity_id, 1.0) if graph_ctx else 1.0
            status = "NORMAL"
            if mult < 0.5:
                status = "DISRUPTED"
            elif mult < 0.9:
                status = "RESTRICTED"

            nodes_payload.append(
                {
                    "data": {
                        "id": entity.id,
                        "label": entity.name,
                        "entity_type": entity.entity_type.value,
                        "lat": entity.latitude,
                        "lon": entity.longitude,
                        "region": entity.region,
                        "capacity_multiplier": mult,
                        "status": status,
                    }
                }
            )

        edges_payload: list[dict[str, Any]] = []
        for u, v, attrs in self.graph_store.get_all_edges():
            edge_key = f"{u}->{v}"
            mult = graph_ctx.edge_capacity_multipliers.get(edge_key, 1.0) if graph_ctx else 1.0
            flow = 0.0
            if plan:
                for alloc in plan.allocations:
                    for i in range(len(alloc.path) - 1):
                        if alloc.path[i] == u and alloc.path[i + 1] == v:
                            flow += alloc.flow_teu

            edges_payload.append(
                {
                    "data": {
                        "id": f"{u}_{v}_{attrs.get('key', 'default')}",
                        "source": u,
                        "target": v,
                        "mode": attrs.get("mode", "ROAD"),
                        "distance_km": attrs.get("distance_km", 0.0),
                        "capacity_multiplier": mult,
                        "freight_flow_teu": flow,
                    }
                }
            )

        # 2. Event Summary
        event_summary: dict[str, Any] = {}
        if event:
            event_summary = {
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "primary_entity_id": event.primary_entity_id,
                "severity": event.severity,
                "confidence": event.confidence,
                "headline": event.raw_headline,
                "source_feed": event.source_feed,
                "duration_days": event.estimated_duration_days,
            }

        # 3. Line-Stop Forecast
        line_stop_forecast: list[dict[str, Any]] = []
        if graph_ctx:
            for ls in graph_ctx.line_stop_metrics:
                line_stop_forecast.append(
                    {
                        "plant_id": ls.plant_id,
                        "plant_name": self.registry.get(ls.plant_id).name,
                        "days_of_cover": ls.days_of_cover,
                        "expected_delay_days": ls.expected_delay_days,
                        "time_to_line_stop_days": ls.time_to_line_stop_days,
                        "line_stop_risk": ls.line_stop_risk,
                        "critical": ls.time_to_line_stop_days < 1.0,
                    }
                )

        # 4. Evidence Provenance
        evidence_provenance: list[dict[str, Any]] = []
        for doc in state.evidence_set:
            evidence_provenance.append(
                {
                    "citation_id": doc.citation_id,
                    "source": doc.source,
                    "trust_tier": doc.trust_tier.value,
                    "entity_ids": doc.entity_ids,
                    "snippet": doc.snippet,
                    "supported_claims": doc.supported_claims,
                }
            )

        # 5. Mitigation Summary
        mitigation_summary: dict[str, Any] = {}
        if plan:
            mitigation_summary = {
                "plan_id": plan.plan_id,
                "objective_cost": plan.objective_cost,
                "unmet_demand_teu": plan.unmet_demand_teu,
                "mode_split": plan.mode_split,
                "summary": plan.summary,
                "verification_passed": verif.passed if verif else False,
                "allocations": [a.model_dump(mode="json") for a in plan.allocations],
            }

        # 6. Trace Timeline & Citation-Verified RAG/LLM Briefing
        trace_timeline = [t.model_dump(mode="json") for t in state.trace]
        executive_briefing = self.briefing_generator.generate(state, cfg)

        dashboard_payload = DashboardPayload(
            event_summary=event_summary,
            geospatial_network={"nodes": nodes_payload, "edges": edges_payload},
            line_stop_forecast=line_stop_forecast,
            evidence_provenance=evidence_provenance,
            mitigation_summary=mitigation_summary,
            trace_timeline=trace_timeline,
            executive_briefing=executive_briefing,
        )

        duration_ms = (time.perf_counter() - t0) * 1000.0
        op_cost = 0.0010

        trace_item = OperatorTraceItem(
            step_index=state.step_count + 1,
            operator_type=OperatorType.STOP,
            input_summary=f"Finalizing session {state.session_id}",
            output_summary="Serialized DashboardPayload for React/Cytoscape.js",
            duration_ms=round(duration_ms, 2),
            cost=op_cost,
            seed=cfg.random_seed,
            timestamp=datetime.now(UTC),
        )

        new_status = (
            PipelineStatus.FAILED
            if state.status == PipelineStatus.FAILED or (verif is not None and not verif.passed)
            else (
                PipelineStatus.ESCALATED
                if state.status == PipelineStatus.ESCALATED
                else PipelineStatus.COMPLETED
            )
        )

        new_state = state.transition(
            updates={
                "dashboard_payload": dashboard_payload,
                "status": new_status,
            },
            trace_item=trace_item,
        )

        result = OperatorResult(
            operator_type=OperatorType.STOP,
            success=new_status == PipelineStatus.COMPLETED,
            message=f"Stage E generated dashboard payload for session {state.session_id} (status={new_status.value}).",
            duration_ms=round(duration_ms, 2),
            cost=op_cost,
            artifacts={"nodes": len(nodes_payload), "edges": len(edges_payload)},
        )

        return new_state, result

