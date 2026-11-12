"""
Formal Suite S1 Statistical Benchmark Runner (PRD Sec. 11.1 & Gate G2).
Evaluates determinism/reproducibility, L1/L2 & dual-solver invariant breach rates,
Tier-1 vs Tier-2 PROPAGATE deltas, Expected-Cost vs CVaR tail hedging, latency
quantiles (mean & P95), and v1_corridor bottleneck elimination across v0_core & v1_corridor.
"""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from asci.core.contracts import PipelineConfig
from asci.core.registry import CanonicalEntityRegistry, EntityType
from asci.core.state import (
    DisruptionEvent,
    DisruptionEventType,
    EventStatus,
    OperatorType,
    PipelineState,
    PipelineStatus,
)
from asci.stages import WalkingSkeletonPipeline

DEFAULT_ANCHOR_ENTITIES: tuple[str, ...] = (
    "PORT_CHENNAI",
    "PORT_KAMARAJAR",
    "PORT_KRISHNAPATNAM",
    "PORT_COCHIN",
    "ICD_WHITEFIELD",
    "ICD_IRUGUR",
    "JUNCTION_RANIPET",
    "PLANT_SRIPERUMBUDUR",
)

V0_BOTTLENECK_ENTITIES: tuple[str, ...] = (
    "PORT_KRISHNAPATNAM",
    "ICD_WHITEFIELD",
    "ICD_IRUGUR",
)


class SuiteS1CaseResult(BaseModel):
    """Frozen telemetry record for a single Suite S1 benchmark case."""

    model_config = ConfigDict(frozen=True)

    case_id: str
    network_scale: str
    entity_id: str
    entity_type: str
    severity: float
    confidence: float
    propagation_tier: int
    risk_mode: str
    reproducible: bool
    status: str
    objective_cost: float
    cvar_cost: float | None = None
    unmet_demand_teu: float
    unmet_demand_pct: float
    primary_port_flow_teu: float = 0.0
    propagated_delay_hrs: float = 0.0
    tier2_links_redistributed: int = 0
    l1_l2_breach: bool
    dual_rel_diff_pct: float
    stage_b_ms: float
    stage_d_ms: float
    total_ms: float


class SuiteS1Report(BaseModel):
    """Aggregated Suite S1 statistical benchmark summary report (Gate G2)."""

    model_config = ConfigDict(frozen=True)

    network_scale: str
    node_count: int
    edge_count: int
    total_cases: int
    reproducibility_rate: float
    l1_l2_breach_count: int
    l1_l2_breach_rate: float
    max_dual_rel_diff_pct: float
    mean_objective_cost: float
    p95_objective_cost: float
    mean_unmet_demand_pct: float
    bottleneck_unmet_teu: dict[str, float] = Field(default_factory=dict)
    tier_comparison: dict[str, dict[str, float]] = Field(default_factory=dict)
    risk_mode_comparison: dict[str, dict[str, float]] = Field(default_factory=dict)
    mean_stage_b_ms: float
    p95_stage_b_ms: float
    mean_stage_d_ms: float
    p95_stage_d_ms: float
    mean_total_ms: float
    p95_total_ms: float
    cases: list[SuiteS1CaseResult] = Field(default_factory=list)


def _event_type_for_entity(entity_type: EntityType) -> DisruptionEventType:
    if entity_type == EntityType.PORT:
        return DisruptionEventType.HAZARD_PORT
    if entity_type == EntityType.PLANT:
        return DisruptionEventType.PLANT_OUTAGE
    if entity_type == EntityType.CORRIDOR_JUNCTION:
        return DisruptionEventType.HAZARD_ROAD
    return DisruptionEventType.RAIL_DISRUPTION


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, math.ceil(0.95 * len(ordered)) - 1))
    return round(ordered[idx], 4)


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


class SuiteS1Runner:
    """
    Executes structured statistical Suite S1 sweeps across v0_core and/or v1_corridor,
    reusing initialized pipeline stores per (network_scale, propagation_tier) pair.
    """

    def __init__(self) -> None:
        self._pipelines: dict[tuple[str, int], WalkingSkeletonPipeline] = {}
        self._registries: dict[str, CanonicalEntityRegistry] = {}

    def _get_pipeline(
        self,
        network_scale: Literal["v0_core", "v1_corridor"],
        propagation_tier: Literal[1, 2],
    ) -> WalkingSkeletonPipeline:
        key = (network_scale, int(propagation_tier))
        pipe = self._pipelines.get(key)
        if pipe is None:
            cfg = PipelineConfig(network_scale=network_scale, propagation_tier=propagation_tier)
            pipe = WalkingSkeletonPipeline.from_config(cfg)
            self._pipelines[key] = pipe
            self._registries[network_scale] = pipe.stage_b.registry
        return pipe

    def _run_case(
        self,
        case_id: str,
        network_scale: Literal["v0_core", "v1_corridor"],
        entity_id: str,
        severity: float,
        confidence: float,
        propagation_tier: Literal[1, 2],
        risk_mode: Literal["DETERMINISTIC", "EXPECTED_COST", "CVAR"],
        seed: int = 42,
        verify_repro: bool = True,
    ) -> SuiteS1CaseResult:
        pipe = self._get_pipeline(network_scale, propagation_tier)
        reg = pipe.stage_b.registry
        entity = reg.get(entity_id)
        total_demand = sum(
            float(p.daily_demand_teu or 500.0) for p in reg.get_by_type(EntityType.PLANT)
        ) or 1.0

        evt = DisruptionEvent(
            event_id=f"EVT_{case_id}",
            event_type=_event_type_for_entity(entity.entity_type),
            status=EventStatus.NEW,
            primary_entity_id=entity_id,
            affected_entity_ids=[entity_id],
            severity=severity,
            estimated_duration_days=3.0 if severity < 0.80 else 4.0,
            source_feed="SUITE_S1",
            raw_headline=f"Suite S1 disruption affecting {entity.name}",
            raw_text=f"Operational disruption at {entity.name} ({entity_id}) severity={severity}.",
            timestamp=datetime(2026, 11, 10, tzinfo=UTC),
            corroboration_count=3 if confidence >= 0.80 else 1,
            confidence=confidence,
        )
        cfg = PipelineConfig(
            network_scale=network_scale,
            propagation_tier=propagation_tier,
            risk_mode=risk_mode,
            random_seed=seed,
        )
        s0 = PipelineState(
            session_id=f"SESS_{case_id}",
            status=PipelineStatus.PERCEIVED,
            event=evt,
        )

        s1, res1 = pipe.run(s0, cfg, random.Random(seed))
        reproducible = True
        if verify_repro:
            s2, _ = pipe.run(s0, cfg, random.Random(seed))
            reproducible = (
                s1.candidate_plan is not None
                and s2.candidate_plan is not None
                and s1.candidate_plan.plan_id == s2.candidate_plan.plan_id
                and s1.candidate_plan.objective_cost == s2.candidate_plan.objective_cost
                and s1.candidate_plan.allocations == s2.candidate_plan.allocations
                and s1.graph_context == s2.graph_context
            )

        stage_b_ms = 0.0
        stage_d_ms = 0.0
        total_ms = 0.0
        for op in res1:
            total_ms += op.duration_ms
            if op.operator_type == OperatorType.GRAPH_ANALYZE:
                stage_b_ms = op.duration_ms
            elif op.operator_type == OperatorType.VERIFY:
                stage_d_ms = op.duration_ms

        assert s1.candidate_plan is not None
        assert s1.verification_report is not None
        assert s1.graph_context is not None

        l1_l2_failures = [
            chk
            for chk in s1.verification_report.failed_checks
            if not chk.startswith("L3:")
        ]
        dual_rel_diff = max(
            (
                float(c.metrics.get("rel_diff_pct", 0.0))
                for c in s1.verification_report.l2_checks
                if c.check_name == "DUAL_SOLVER_AGREEMENT"
            ),
            default=0.0,
        )
        unmet = float(s1.candidate_plan.unmet_demand_teu)
        primary_flow = sum(
            a.flow_teu for a in s1.candidate_plan.allocations if a.origin_id == entity_id
        )

        return SuiteS1CaseResult(
            case_id=case_id,
            network_scale=network_scale,
            entity_id=entity_id,
            entity_type=entity.entity_type.value,
            severity=severity,
            confidence=confidence,
            propagation_tier=int(propagation_tier),
            risk_mode=risk_mode,
            reproducible=reproducible,
            status=s1.status.value,
            objective_cost=round(float(s1.candidate_plan.objective_cost), 2),
            cvar_cost=s1.candidate_plan.cvar_cost,
            unmet_demand_teu=round(unmet, 2),
            unmet_demand_pct=round((unmet / total_demand) * 100.0, 4),
            primary_port_flow_teu=round(primary_flow, 2),
            propagated_delay_hrs=round(
                sum(s1.graph_context.propagated_node_delays_hrs.values()), 2
            ),
            tier2_links_redistributed=len(s1.graph_context.redistributed_edge_loads_teu),
            l1_l2_breach=len(l1_l2_failures) > 0,
            dual_rel_diff_pct=round(dual_rel_diff, 6),
            stage_b_ms=round(stage_b_ms, 2),
            stage_d_ms=round(stage_d_ms, 2),
            total_ms=round(total_ms, 2),
        )

    def run_suite(
        self,
        network_scale: Literal["v0_core", "v1_corridor"] = "v1_corridor",
        full_sweep: bool = False,
        verify_repro: bool = True,
    ) -> SuiteS1Report:
        """
        Execute the Gate G2 statistical Suite S1 benchmark on the selected network scale.
        Covers:
        1) Severity buckets (0.35, 0.65, 0.90) x Confidence tiers (0.45, 0.90) across corridor anchors
        2) Tier-1 vs Tier-2 dynamic congestion PROPAGATE comparison at high severity (0.85)
        3) Risk mode comparison (DETERMINISTIC, EXPECTED_COST, CVAR) under scenario uncertainty
        4) Full all-entity single-event sweep when `full_sweep=True`
        """
        pipe_default = self._get_pipeline(network_scale, 2)
        reg = pipe_default.stage_b.registry
        gs = pipe_default.stage_b.graph_store

        cases: list[SuiteS1CaseResult] = []
        anchors = [eid for eid in DEFAULT_ANCHOR_ENTITIES if reg.validate_id(eid)]

        # 1. Core Severity x Confidence Sweep (Tier-2, EXPECTED_COST)
        for eid in anchors[:6]:
            for sev in (0.35, 0.65, 0.90):
                for conf in (0.45, 0.90):
                    cid = f"S1_{network_scale}_{eid}_S{int(sev*100)}_C{int(conf*100)}_T2_EC"
                    cases.append(
                        self._run_case(
                            case_id=cid,
                            network_scale=network_scale,
                            entity_id=eid,
                            severity=sev,
                            confidence=conf,
                            propagation_tier=2,
                            risk_mode="EXPECTED_COST",
                            verify_repro=verify_repro,
                        )
                    )

        # 2. Tier-1 vs Tier-2 Dynamic PROPAGATE Comparison at 0.85 severity
        for eid in anchors[:6]:
            for tier in (1, 2):
                cid = f"S1_{network_scale}_{eid}_TIER{tier}_S85"
                cases.append(
                    self._run_case(
                        case_id=cid,
                        network_scale=network_scale,
                        entity_id=eid,
                        severity=0.85,
                        confidence=0.90,
                        propagation_tier=tier,  # type: ignore[arg-type]
                        risk_mode="EXPECTED_COST",
                        verify_repro=verify_repro,
                    )
                )

        # 3. Risk Mode Tail-Risk Comparison (DETERMINISTIC vs EXPECTED_COST vs CVAR)
        for eid in ("PORT_CHENNAI", "PORT_KAMARAJAR", "PORT_COCHIN"):
            for rmode in ("DETERMINISTIC", "EXPECTED_COST", "CVAR"):
                cid = f"S1_{network_scale}_{eid}_RMODE_{rmode}"
                cases.append(
                    self._run_case(
                        case_id=cid,
                        network_scale=network_scale,
                        entity_id=eid,
                        severity=0.65,
                        confidence=0.45,
                        propagation_tier=2,
                        risk_mode=rmode,  # type: ignore[arg-type]
                        verify_repro=verify_repro,
                    )
                )

        # 4. Optional exhaustive node sweep at 0.85 severity
        if full_sweep:
            for eid in sorted(reg.all_entities().keys()):
                cid = f"S1_{network_scale}_FULL_{eid}_S85"
                cases.append(
                    self._run_case(
                        case_id=cid,
                        network_scale=network_scale,
                        entity_id=eid,
                        severity=0.85,
                        confidence=0.90,
                        propagation_tier=2,
                        risk_mode="EXPECTED_COST",
                        verify_repro=verify_repro,
                    )
                )

        total_cases = len(cases)
        repro_count = sum(1 for c in cases if c.reproducible)
        breach_count = sum(1 for c in cases if c.l1_l2_breach)
        max_dual_gap = max((c.dual_rel_diff_pct for c in cases), default=0.0)

        tier1_cases = [c for c in cases if c.case_id.endswith("_S85") and c.propagation_tier == 1]
        tier2_cases = [c for c in cases if c.case_id.endswith("_S85") and c.propagation_tier == 2]
        tier_comparison = {
            "tier_1": {
                "case_count": float(len(tier1_cases)),
                "mean_propagated_delay_hrs": _mean([c.propagated_delay_hrs for c in tier1_cases]),
                "mean_objective_cost": _mean([c.objective_cost for c in tier1_cases]),
                "mean_unmet_demand_pct": _mean([c.unmet_demand_pct for c in tier1_cases]),
            },
            "tier_2": {
                "case_count": float(len(tier2_cases)),
                "mean_propagated_delay_hrs": _mean([c.propagated_delay_hrs for c in tier2_cases]),
                "mean_objective_cost": _mean([c.objective_cost for c in tier2_cases]),
                "mean_unmet_demand_pct": _mean([c.unmet_demand_pct for c in tier2_cases]),
            },
        }

        risk_mode_comparison: dict[str, dict[str, float]] = {}
        for rmode in ("DETERMINISTIC", "EXPECTED_COST", "CVAR"):
            rcases = [c for c in cases if "_RMODE_" in c.case_id and c.risk_mode == rmode]
            cvar_vals = [float(c.cvar_cost) for c in rcases if c.cvar_cost is not None]
            risk_mode_comparison[rmode] = {
                "case_count": float(len(rcases)),
                "mean_objective_cost": _mean([c.objective_cost for c in rcases]),
                "mean_cvar_cost": _mean(cvar_vals),
                "mean_primary_port_flow_teu": _mean([c.primary_port_flow_teu for c in rcases]),
                "mean_unmet_demand_pct": _mean([c.unmet_demand_pct for c in rcases]),
            }

        bottleneck_unmet: dict[str, float] = {}
        for b_id in V0_BOTTLENECK_ENTITIES:
            matched = [
                c
                for c in cases
                if c.entity_id == b_id and c.propagation_tier == 2 and abs(c.severity - 0.85) < 1e-6
            ]
            if matched:
                bottleneck_unmet[b_id] = matched[0].unmet_demand_teu

        return SuiteS1Report(
            network_scale=network_scale,
            node_count=len(gs.get_all_nodes()),
            edge_count=len(gs.get_all_edges()),
            total_cases=total_cases,
            reproducibility_rate=round((repro_count / max(1, total_cases)) * 100.0, 2),
            l1_l2_breach_count=breach_count,
            l1_l2_breach_rate=round((breach_count / max(1, total_cases)) * 100.0, 4),
            max_dual_rel_diff_pct=round(max_dual_gap, 6),
            mean_objective_cost=_mean([c.objective_cost for c in cases]),
            p95_objective_cost=_p95([c.objective_cost for c in cases]),
            mean_unmet_demand_pct=_mean([c.unmet_demand_pct for c in cases]),
            bottleneck_unmet_teu=bottleneck_unmet,
            tier_comparison=tier_comparison,
            risk_mode_comparison=risk_mode_comparison,
            mean_stage_b_ms=_mean([c.stage_b_ms for c in cases]),
            p95_stage_b_ms=_p95([c.stage_b_ms for c in cases]),
            mean_stage_d_ms=_mean([c.stage_d_ms for c in cases]),
            p95_stage_d_ms=_p95([c.stage_d_ms for c in cases]),
            mean_total_ms=_mean([c.total_ms for c in cases]),
            p95_total_ms=_p95([c.total_ms for c in cases]),
            cases=cases,
        )
