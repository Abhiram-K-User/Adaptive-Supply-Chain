"""Suite S2: compound timelines, escalation, retraction, reopening and recovery.

Each active event is analysed independently. Joint disruptions conservatively take
the minimum residual capacity per node/edge; snapshots are rebuilt every day so
withdrawn bulletins cannot leave stale attenuation behind.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import random
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from asci.benchmarks.common import event_fixture, graph_snapshot, outcome
from asci.core.contracts import PipelineConfig
from asci.core.registry import CanonicalEntityRegistry, EntityType
from asci.core.state import (
    DisruptionEvent,
    DisruptionEventType,
    EventStatus,
    GraphContext,
    PipelineState,
    Scenario,
)
from asci.stages import WalkingSkeletonPipeline
from asci.uskl.event_store import SQLiteEventStore

DEFAULT_START = datetime(2026, 11, 1, tzinfo=UTC)
NetworkScale = Literal["v0_core", "v1_corridor"]


class SuiteS2Case(BaseModel):
    """Serializable evaluation inputs; revisions must worsen then improve weather."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    case_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    weather_entity_id: str
    road_entity_id: str
    weather_severity: float = Field(gt=0, lt=1)
    road_severity: float = Field(gt=0, le=1)
    escalated_severity: float = Field(gt=0, le=1)
    revised_severity: float = Field(ge=0, lt=1)
    confidence: float = Field(default=0.9, ge=0, le=1)
    initial_duration_days: float = Field(default=7, ge=4)

    @model_validator(mode="after")
    def validate_revisions(self) -> Self:
        if not self.revised_severity < self.weather_severity < self.escalated_severity:
            raise ValueError("Require revised_severity < weather_severity < escalated_severity")
        return self


def generate_cases(registry: CanonicalEntityRegistry, count: int, seed: int) -> list[SuiteS2Case]:
    """Seeded, varied cases grounded in the selected topology, not repeated episodes."""
    ports = sorted(e.id for e in registry.get_by_type(EntityType.PORT))
    junctions = sorted(e.id for e in registry.get_by_type(EntityType.CORRIDOR_JUNCTION))
    pairs = list(itertools.product(ports, junctions))
    if not pairs:
        raise ValueError("S2 requires at least one port and one corridor junction")
    rng = random.Random(seed)
    rng.shuffle(pairs)
    return [SuiteS2Case(
        case_id=f"S2_{index:03d}", weather_entity_id=pairs[index % len(pairs)][0],
        road_entity_id=pairs[index % len(pairs)][1],
        weather_severity=round(rng.uniform(0.4, 0.65), 3), road_severity=round(rng.uniform(0.4, 0.8), 3),
        escalated_severity=round(rng.uniform(0.8, 0.95), 3), revised_severity=round(rng.uniform(0.1, 0.3), 3),
        confidence=round(rng.uniform(0.6, 0.95), 3),
    ) for index in range(count)]


def combine_scenarios(groups: Sequence[Sequence[Scenario]], max_scenarios: int = 256) -> list[Scenario]:
    """Independent joint branches, preserving each event's normalized probability.

    Overlapping capacity restrictions take their minimum. Expansion is bounded;
    no scenario is silently dropped to meet the resource limit.
    """
    if max_scenarios < 1:
        raise ValueError("max_scenarios must be positive")
    if not groups:
        return []
    count = math.prod(len(group) for group in groups)
    if count == 0 or count > max_scenarios:
        raise ValueError(f"Joint scenario count {count} is outside 1..{max_scenarios}")
    normalized = [[(s, s.probability / sum(x.probability for x in group)) for s in group] for group in groups]
    joint = []
    for index, combination in enumerate(itertools.product(*normalized)):
        capacities: dict[str, float] = {}
        for scenario, _ in combination:
            for node, value in scenario.capacity_multipliers.items():
                if not math.isfinite(value) or not 0 <= value <= 1:
                    raise ValueError(f"Invalid scenario capacity for {node}: {value}")
                capacities[node] = min(capacities.get(node, 1.0), value)
        joint.append(Scenario(
            scenario_id=f"S2_JOINT_{index:03d}", name=" + ".join(s.name for s, _ in combination),
            probability=math.prod(p for _, p in combination), capacity_multipliers=capacities,
            duration_days=max(s.duration_days for s, _ in combination),
        ))
    return joint


def numerical_fingerprint(state: PipelineState) -> str:
    """Compare numerical results and decisions, excluding wall-clock audit fields."""
    data = state.model_dump(mode="json", exclude={"dashboard_payload", "raw_signal", "trace"})
    if data["candidate_plan"]:
        data["candidate_plan"].pop("timestamp")
    data["trace"] = [t.model_dump(mode="json", exclude={"timestamp", "duration_ms"}) for t in state.trace]
    return hashlib.sha256(json.dumps(data, sort_keys=True, allow_nan=False).encode()).hexdigest()


def run_compound(
    pipe: WalkingSkeletonPipeline, events: list[DisruptionEvent], cfg: PipelineConfig, session_id: str,
    *, as_of: datetime = DEFAULT_START, max_joint_scenarios: int = 256,
) -> PipelineState:
    """Evaluate simultaneous disruptions without mutating the canonical topology."""
    rng = random.Random(cfg.random_seed)
    if len({e.event_id for e in events}) != len(events):
        raise ValueError("Compound inputs contain duplicate event IDs")
    if any(e.status not in (EventStatus.NEW, EventStatus.UPDATED) for e in events):
        raise ValueError("Only active events may enter a compound snapshot")
    is_baseline = not events
    if is_baseline:
        ports = sorted(e.id for e in pipe.stage_b.registry.get_by_type(EntityType.PORT))
        if not ports:
            raise ValueError("A healthy reference requires a canonical port")
        # The optimizer requires an event, even for the healthy reference. This
        # zero-severity reference is excluded from all active-event metrics.
        events = [event_fixture(ports[0], severity=0.0, case_id=f"{session_id}_CLEAR", timestamp=as_of)]
        cfg = cfg.model_copy(update={"risk_mode": "DETERMINISTIC"})
    contexts = []
    states = []
    for evt in sorted(events, key=lambda e: e.event_id):
        state, res = pipe.stage_a.run(PipelineState(session_id=session_id, event=evt), cfg, rng)
        if not res.success:
            raise RuntimeError(res.message)
        state, res = pipe.stage_b.run(state, cfg, rng)
        if not res.success or state.graph_context is None:
            raise RuntimeError(res.message)
        states.append(state)
        contexts.append(state.graph_context)
    base = states[0]
    assert base.event is not None
    nodes: dict[str, float] = {}
    edges: dict[str, float] = {}
    for ctx in contexts:
        for key, value in ctx.node_capacity_multipliers.items():
            nodes[key] = min(nodes.get(key, 1.0), value)
        for key, value in ctx.edge_capacity_multipliers.items():
            edges[key] = min(edges.get(key, 1.0), value)
    metrics = {}
    paths = {}
    for ctx in contexts:
        for metric in ctx.line_stop_metrics:
            if metric.plant_id not in metrics or metric.time_to_line_stop_days < metrics[metric.plant_id].time_to_line_stop_days:
                metrics[metric.plant_id] = metric
        for metric in ctx.path_metrics:
            key = (metric.origin_id, metric.destination_id, tuple(metric.path), metric.mode)
            old = paths.get(key)
            if old is None or (metric.path_risk, metric.baseline_delay_hrs) > (old.path_risk, old.baseline_delay_hrs):
                paths[key] = metric

    def merge_max(field: str) -> dict[str, float]:
        return {key: max(getattr(c, field).get(key, 0.0) for c in contexts)
                for key in sorted({k for c in contexts for k in getattr(c, field)})}

    joint = GraphContext(
        impacted_nodes=sorted({n for c in contexts for n in c.impacted_nodes}),
        impacted_edges=sorted({e for c in contexts for e in c.impacted_edges}),
        node_capacity_multipliers=nodes, edge_capacity_multipliers=edges,
        line_stop_metrics=[metrics[k] for k in sorted(metrics)], path_metrics=[paths[k] for k in sorted(paths)],
        propagated_node_delays_hrs=merge_max("propagated_node_delays_hrs"),
        redistributed_edge_loads_teu=merge_max("redistributed_edge_loads_teu"),
        edge_congestion_ratios=merge_max("edge_congestion_ratios"),
        hop_decay_applied=any(c.hop_decay_applied for c in contexts),
        k_hops=cfg.k_hop_neighborhood, propagation_tier=cfg.propagation_tier,
    )
    all_affected = sorted({n for e in events for n in [e.primary_entity_id, *e.affected_entity_ids]})
    if is_baseline:
        joint = joint.model_copy(update={
            "impacted_nodes": [], "impacted_edges": [], "propagated_node_delays_hrs": {},
            "hop_decay_applied": False,
            "line_stop_metrics": [m.model_copy(update={
                "expected_delay_days": 0.0, "time_to_line_stop_days": m.days_of_cover,
                "line_stop_risk": 0.0, "line_stop_probability": 0.0,
            }) for m in joint.line_stop_metrics],
        })
    representative = max(events, key=lambda e: (e.severity, e.event_id))
    state = base.model_copy(update={
        "event": representative.model_copy(update={
            "affected_entity_ids": all_affected,
            "estimated_duration_days": max(e.estimated_duration_days for e in events),
            "confidence": min(e.confidence for e in events),
        }), "graph_context": joint,
    })
    # Each event keeps its own controller budget; aggregate every trace and cost.
    calibrated = []
    for item in states:
        if not is_baseline:
            item, res = pipe.stage_c.run(item, cfg, rng)
            if not res.success:
                raise RuntimeError(res.message)
        calibrated.append(item)
    traces = [t.model_copy(update={"step_index": index + 1})
              for index, t in enumerate(itertools.chain.from_iterable(s.trace for s in calibrated))]
    state = state.model_copy(update={
        "trace": traces, "step_count": len(traces),
        "compute_cost": round(sum(t.cost for t in traces), 6),
        "evidence_set": sorted({d.citation_id: d for s in calibrated for d in s.evidence_set}.values(), key=lambda d: d.citation_id),
    })
    scenarios = [] if is_baseline else combine_scenarios([s.scenario_set for s in calibrated], max_joint_scenarios)
    state = state.model_copy(update={"scenario_set": scenarios})
    state, result = pipe.stage_d.run(state, cfg, rng)
    if state.candidate_plan is None or state.verification_report is None:
        raise RuntimeError(result.message)
    state, _ = pipe.stage_e.run(state, cfg, rng)
    return state


class SuiteS2Runner:
    """Execute real lifecycle and optimization checks on isolated in-memory stores."""

    def run_suite(
        self, days: int = 7, cases: int = 10, network_scale: NetworkScale = "v1_corridor", *,
        seed: int = 42, start: datetime = DEFAULT_START, case_definitions: Sequence[SuiteS2Case] | None = None,
        pipeline_config: PipelineConfig | None = None, max_joint_scenarios: int = 256,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        if days < 7 or cases < 1:
            raise ValueError("S2 requires at least seven days and one case to exercise all transitions")
        if start.tzinfo is None or start.utcoffset() is None:
            raise ValueError("The timeline start must include a timezone")
        if max_joint_scenarios < 9:
            raise ValueError("S2's two three-branch events require at least nine joint scenarios")
        # Revalidate overrides instead of bypassing the existing configuration contract.
        cfg = PipelineConfig.model_validate({
            **(pipeline_config or PipelineConfig()).model_dump(), "network_scale": network_scale, "random_seed": seed,
        })
        if cfg.enable_llm:
            raise ValueError("S2 runs offline; enable_llm must be false")
        pipe = WalkingSkeletonPipeline.from_config(cfg)
        try:
            definitions = list(case_definitions) if case_definitions is not None else generate_cases(pipe.stage_b.registry, cases, seed)
            if len(definitions) != cases or len({c.case_id for c in definitions}) != cases:
                raise ValueError("Case definitions must match the requested count and have unique case IDs")
            for definition in definitions:
                for entity, expected in ((definition.weather_entity_id, EntityType.PORT),
                                         (definition.road_entity_id, EntityType.CORRIDOR_JUNCTION)):
                    if not pipe.stage_b.registry.validate_id(entity) or pipe.stage_b.registry.get(entity).entity_type != expected:
                        raise ValueError(f"{definition.case_id}: {entity} must be a canonical {expected}")
            return self._run_timelines(pipe, cfg, definitions, days, start, max_joint_scenarios, on_progress)
        finally:
            pipe.stage_c.timeseries_store._conn.close()
            if pipe.stage_c.decision_store is not None:
                pipe.stage_c.decision_store._conn.close()

    def _run_timelines(
        self, pipe: WalkingSkeletonPipeline, cfg: PipelineConfig, definitions: Sequence[SuiteS2Case],
        days: int, start: datetime, max_joint_scenarios: int,
        on_progress: Callable[[dict[str, Any]], None] | None,
    ) -> dict[str, Any]:
        snapshot = graph_snapshot(pipe)
        records = []
        failures = []
        for case, definition in enumerate(definitions):
            store = SQLiteEventStore(registry=pipe.stage_b.registry)
            weather = event_fixture(definition.weather_entity_id, case_id=f"{definition.case_id}_WEATHER",
                                    severity=definition.weather_severity, timestamp=start,
                                    confidence=definition.confidence, duration=definition.initial_duration_days)
            road = event_fixture(definition.road_entity_id, case_id=f"{definition.case_id}_ROAD",
                                 severity=definition.road_severity, timestamp=start + timedelta(days=1),
                                 confidence=definition.confidence, duration=definition.initial_duration_days,
                                 event_type=DisruptionEventType.HAZARD_ROAD)
            try:
                for day in range(days):
                    action = "expire_weather" if day == 6 else "observe_recovery"
                    if day == 0:
                        store.upsert_with_corroboration(weather)
                        action = "new_weather"
                    elif day == 1:
                        store.upsert_with_corroboration(road)
                        action = "compound_road"
                    elif day == 2:
                        weather = store.upsert_with_corroboration(weather.model_copy(update={
                            "severity": definition.escalated_severity, "timestamp": start + timedelta(days=day),
                        }), force_activate=True)
                        action = "escalate_weather"
                    elif day == 3:
                        store.retract_event(weather.event_id)
                        action = "retract_weather"
                    elif day == 4:
                        store.retract_event(road.event_id)
                        action = "reopen_route"
                    elif day == 5:
                        store.reopen_event(weather.event_id)
                        store.upsert_with_corroboration(weather.model_copy(update={
                            "severity": definition.revised_severity, "timestamp": start + timedelta(days=day),
                            "estimated_duration_days": 1.0,
                        }), force_activate=True)
                        action = "revised_weather"
                    as_of = start + timedelta(days=day)
                    expired = store.expire_stale_events(as_of)
                    stored = store.list_events()
                    active = [e for e in stored if e.status in (EventStatus.NEW, EventStatus.UPDATED)]
                    statuses = {e.event_id: e.status.value for e in stored}
                    expected_statuses = {
                        weather.event_id: ("NEW" if day < 2 else "UPDATED" if day in (2, 5)
                                           else "RETRACTED" if day < 5 else "EXPIRED"),
                        **({road.event_id: "NEW" if day < 4 else "RETRACTED"} if day >= 1 else {}),
                    }
                    checks = {"lifecycle": statuses == expected_statuses}
                    stored_weather = next(e for e in stored if e.event_id == weather.event_id)
                    expected_severity = (definition.weather_severity if day < 2 else
                                         definition.escalated_severity if day < 5 else definition.revised_severity)
                    checks["bulletin_revision"] = stored_weather.severity == expected_severity
                    # The store retains the original bulletin's timestamp and duration.
                    # Planning at a later snapshot uses the time still remaining, and
                    # retrieval can use evidence published up to that snapshot.
                    remaining = {e.event_id: (e.timestamp + timedelta(days=e.estimated_duration_days) - as_of).total_seconds() / 86400
                                 for e in active}
                    planning_events = [e.model_copy(update={"timestamp": as_of, "estimated_duration_days": remaining[e.event_id]})
                                       for e in active]
                    sid = f"{definition.case_id}_DAY_{day}"
                    record = {"case": case, "case_id": definition.case_id, "day": day, "action": action,
                              "as_of": as_of.isoformat(), "active_event_ids": sorted(e.event_id for e in active),
                              "event_statuses": statuses, "expired_events": expired,
                              "remaining_duration_days": remaining,
                              "active_events": [e.model_dump(mode="json") for e in sorted(active, key=lambda e: e.event_id)]}
                    try:
                        final = run_compound(pipe, planning_events, cfg, sid, as_of=as_of, max_joint_scenarios=max_joint_scenarios)
                        repeat = run_compound(pipe, planning_events, cfg, sid, as_of=as_of, max_joint_scenarios=max_joint_scenarios)
                        if final.graph_context is None:
                            raise RuntimeError("Graph context missing after compound execution")
                        fingerprint = numerical_fingerprint(final)
                        checks["reproducibility"] = fingerprint == numerical_fingerprint(repeat)
                        telemetry = outcome(final)
                        checks["l1_l2_safety"] = not telemetry["l1_l2_breaches"]
                        checks["l3_safety"] = all(c == "L3:UNMET_DEMAND_BOUND" for c in telemetry["failed_checks"])
                        checks["scenario_coverage"] = len(final.scenario_set) == (3 ** len(active) if active else 0)
                        checks["clear_capacity"] = bool(active) or (
                            all(v == 1.0 for v in final.graph_context.node_capacity_multipliers.values())
                            and all(v == 1.0 for v in final.graph_context.edge_capacity_multipliers.values())
                            and not final.scenario_set and not final.graph_context.impacted_nodes
                            and all(m.expected_delay_days == 0 for m in final.graph_context.line_stop_metrics)
                        )
                        checks["trace_accounting"] = (
                            [t.step_index for t in final.trace] == list(range(1, len(final.trace) + 1))
                            and final.step_count == len(final.trace)
                            and math.isclose(final.compute_cost, sum(t.cost for t in final.trace), abs_tol=1e-6)
                        )
                        record.update(telemetry, reproducible=checks["reproducibility"],
                                      numerical_fingerprint=fingerprint, scenario_count=len(final.scenario_set),
                                      restricted_nodes={n: m for n, m in final.graph_context.node_capacity_multipliers.items() if m < 1})
                    except (RuntimeError, ValueError) as exc:
                        checks["execution"] = False
                        record.update(error=str(exc), reproducible=False)
                    checks["canonical_graph_unchanged"] = graph_snapshot(pipe) == snapshot
                    record["checks"] = checks
                    record["passed"] = all(checks.values())
                    records.append(record)
                    failures.extend(f"{sid}: {name}" for name, passed in checks.items() if not passed)
                    if on_progress:
                        on_progress(record)
            finally:
                store._conn.close()
        if snapshot != graph_snapshot(pipe):
            failures.append("Canonical graph mutated")
        return {
            "suite": "S2", "passed": not failures, "failures": failures,
            "days": days, "cases": len(definitions), "network_scale": cfg.network_scale,
            "seed": cfg.random_seed, "start": start.isoformat(), "pipeline_config": cfg.model_dump(mode="json"),
            "case_definitions": [c.model_dump() for c in definitions],
            "summary": {"total_snapshots": len(records), "passed_snapshots": sum(r["passed"] for r in records),
                        "reproducibility_rate": sum(r["reproducible"] for r in records) / len(records),
                        "l1_l2_breach_snapshots": sum(bool(r.get("l1_l2_breaches")) for r in records),
                        "execution_errors": sum("error" in r for r in records),
                        "shortage_snapshots": sum("L3:UNMET_DEMAND_BOUND" in r.get("failed_checks", []) for r in records)},
            "methodology": {"scenario_dependence": "independent event branches",
                            "capacity_composition": "minimum residual node/edge capacity",
                            "controller_budget_scope": "per event; all traces and costs retained",
                            "limitations": ["Joint impacts compose per-event BPR and TTLS estimates; interacting queues are not simulated.",
                                            "Physical unmet demand is reported and rejected by L3; it is not itself a benchmark safety failure."]},
            "records": records,
        }
