"""Shared, deterministic fixtures and measured outcomes for the evaluation suites."""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime
from typing import Any

from asci.core.contracts import PipelineConfig
from asci.core.io import write_json as write_report  # noqa: F401 - shared public compatibility
from asci.core.state import DisruptionEvent, DisruptionEventType, PipelineState
from asci.stages import WalkingSkeletonPipeline


def event_fixture(
    entity_id: str = "PORT_CHENNAI", *, case_id: str = "BENCH", severity: float = 0.75,
    timestamp: datetime | None = None, event_type: DisruptionEventType = DisruptionEventType.HAZARD_PORT,
    confidence: float = 0.9, duration: float = 4.0,
) -> DisruptionEvent:
    return DisruptionEvent(
        event_id=f"EVT_{case_id}", event_type=event_type, primary_entity_id=entity_id,
        affected_entity_ids=[entity_id], severity=severity, confidence=confidence,
        estimated_duration_days=duration, source_feed="BENCHMARK_REPLAY",
        raw_headline=f"Operational disruption at {entity_id}", raw_text="Controlled evaluation fixture.",
        timestamp=timestamp or datetime(2026, 11, 10, tzinfo=UTC), corroboration_count=2,
    )


def run_event(
    pipe: WalkingSkeletonPipeline, event: DisruptionEvent, cfg: PipelineConfig,
    *, session_id: str | None = None,
) -> PipelineState:
    state, _ = pipe.run(
        PipelineState(session_id=session_id or f"SESS_{event.event_id}", event=event),
        cfg, random.Random(cfg.random_seed),
    )
    if state.candidate_plan is None or state.verification_report is None:
        raise RuntimeError(f"Incomplete benchmark episode {event.event_id}: {state.status}")
    return state


def outcome(state: PipelineState) -> dict[str, Any]:
    plan = state.candidate_plan
    report = state.verification_report
    if plan is None or report is None:
        raise ValueError("An evaluated state must contain a plan and verification report")
    return {
        "session_id": state.session_id, "status": state.status.value, "plan_id": plan.plan_id,
        "objective_cost": plan.objective_cost, "unmet_demand_teu": plan.unmet_demand_teu,
        "compute_cost": state.compute_cost, "steps": state.step_count,
        "failed_checks": report.failed_checks,
        "l1_l2_breaches": [x for x in report.failed_checks if not x.startswith("L3:")],
        "operators": [t.operator_type.value for t in state.trace],
    }


def graph_snapshot(pipe: WalkingSkeletonPipeline) -> str:
    """Serialize the authoritative graph, including attributes, to detect mutation."""
    graph = pipe.stage_b.graph_store._graph
    return json.dumps({"nodes": sorted(graph.nodes(data=True)),
                       "edges": sorted(graph.edges(keys=True, data=True))}, sort_keys=True)
