"""
Unit tests for Gate G2 Part 1 Mathematical Core:
- Google OR-Tools primary LP solver & SciPy HiGHS independent dual verification
- Multi-commodity containerised freight conservation & transmutation rejection
- Two-stage Scenario Expected-Cost & CVaR risk-aware routing sensitivity
- Legacy NetworkX single-commodity deterministic equivalence
"""

from __future__ import annotations

import random
from datetime import UTC, datetime

import pytest

from asci.core.contracts import PipelineConfig
from asci.core.registry import CanonicalEntityRegistry, EntityType
from asci.core.state import (
    DisruptionEvent,
    DisruptionEventType,
    EventStatus,
    EvidenceItem,
    FlowAllocation,
    GraphContext,
    MitigationPlan,
    PipelineState,
    PipelineStatus,
    Scenario,
    TrustTier,
    VerificationVerdict,
)
from asci.stages.stage_b_graph import StageBCorridorRisk
from asci.stages.stage_d_optimiser import StageDOptimiserAndVerifier
from asci.uskl.graph_store import CorridorGraphStore


def _make_analyzed_state(
    primary_entity_id: str,
    severity: float,
    registry: CanonicalEntityRegistry,
    graph_store: CorridorGraphStore,
    cfg: PipelineConfig,
    scenarios: list[Scenario] | None = None,
    duration_days: float = 3.0,
) -> PipelineState:
    evt = DisruptionEvent(
        event_id=f"EVT_LP_{primary_entity_id}",
        event_type=DisruptionEventType.HAZARD_PORT,
        status=EventStatus.NEW,
        primary_entity_id=primary_entity_id,
        affected_entity_ids=[primary_entity_id],
        severity=severity,
        estimated_duration_days=duration_days,
        source_feed="GATE_G2_PART1",
        raw_headline=f"Disruption at {primary_entity_id}",
        raw_text=f"Operational bottleneck at {primary_entity_id}.",
        timestamp=datetime(2026, 11, 10, tzinfo=UTC),
        corroboration_count=2,
        confidence=0.90,
    )
    ev = EvidenceItem(
        citation_id=f"CIT_LP_{primary_entity_id}",
        source="Port Trust Advisory",
        trust_tier=TrustTier.TIER_A,
        entity_ids=[primary_entity_id, "PORT_CHENNAI", "PORT_KAMARAJAR", "PORT_COCHIN"],
        snippet="Contingency berth allocation bulletin.",
        publication_date="2026-11-10",
    )
    s0 = PipelineState(
        session_id=f"SESS_LP_{primary_entity_id}",
        status=PipelineStatus.PERCEIVED,
        event=evt,
        evidence_set=[ev],
        scenario_set=scenarios or [],
    )
    s_b, _ = StageBCorridorRisk(graph_store=graph_store, registry=registry).run(
        s0, cfg, random.Random(42)
    )
    return s_b


@pytest.mark.parametrize("entity_id", ["PORT_CHENNAI", "PORT_KAMARAJAR", "PORT_VOC"])
def test_gate_g2_part1_ortools_and_highs_dual_agreement(
    entity_id: str,
    registry: CanonicalEntityRegistry,
    graph_store: CorridorGraphStore,
):
    """Primary OR-Tools LP and independent SciPy HiGHS dual solver must agree strictly within 0.1%."""
    cfg = PipelineConfig(solver_type="OR_TOOLS", risk_mode="DETERMINISTIC", random_seed=42)
    s_b = _make_analyzed_state(entity_id, 0.85, registry, graph_store, cfg)
    out_d, res_d = StageDOptimiserAndVerifier(registry=registry, graph_store=graph_store).run(
        s_b, cfg, random.Random(42)
    )

    assert res_d.success is True
    assert out_d.candidate_plan is not None
    assert out_d.candidate_plan.solver_engine == "OR_TOOLS"
    assert out_d.verification_report is not None
    assert out_d.verification_report.passed is True

    dual_checks = [
        c for c in out_d.verification_report.l2_checks if c.check_name == "DUAL_SOLVER_AGREEMENT"
    ]
    assert len(dual_checks) == 1
    assert dual_checks[0].verdict == VerificationVerdict.PASS
    assert dual_checks[0].metrics["rel_diff_pct"] < 0.1
    assert dual_checks[0].metrics["ortools_objective"] == pytest.approx(
        dual_checks[0].metrics["highs_objective"], rel=1e-3, abs=5.0
    )


def test_gate_g2_part1_multi_commodity_conservation_and_transmutation_catch(
    registry: CanonicalEntityRegistry,
    graph_store: CorridorGraphStore,
):
    """Stage D models multi-commodity flows explicitly and L2 rejects mid-path commodity transmutation."""
    cfg = PipelineConfig(solver_type="OR_TOOLS", enable_multi_commodity=True, risk_mode="DETERMINISTIC")
    s_b = _make_analyzed_state("PORT_CHENNAI", 0.80, registry, graph_store, cfg)
    optimiser = StageDOptimiserAndVerifier(registry=registry, graph_store=graph_store)

    out_d, res_d = optimiser.run(s_b, cfg, random.Random(42))
    assert res_d.success is True
    assert out_d.candidate_plan is not None

    commodities_used = {a.commodity for a in out_d.candidate_plan.allocations}
    assert commodities_used == {"POWERTRAIN_CKD", "EV_BATTERY_PACKS", "BODY_CHASSIS_PARTS"}

    delivered_total = sum(a.flow_teu for a in out_d.candidate_plan.allocations)
    assert delivered_total == pytest.approx(5300.0, abs=0.1)

    # Inject multi-commodity wrong-mix over-delivery over strictly valid edges & capacities
    # PLANT_SRIPERUMBUDUR total demand=1500, EV_BATTERY_PACKS share=25% (375 TEU); sending 700 TEU fails L2!
    bad_plan = MitigationPlan(
        plan_id="PLAN_COMM_OVERMIX",
        objective_cost=800000.0,
        allocations=[
            FlowAllocation(
                commodity="POWERTRAIN_CKD",
                origin_id="PORT_CHENNAI",
                destination_id="PLANT_ORAGADAM",
                path=["PORT_CHENNAI", "CFS_CHENNAI_CENTRAL", "PLANT_ORAGADAM"],
                mode="ROAD",
                flow_teu=400.0,
                unit_cost=160.0,
                total_cost=64000.0,
            ),
            FlowAllocation(
                commodity="EV_BATTERY_PACKS",
                origin_id="PORT_CHENNAI",
                destination_id="PLANT_SRIPERUMBUDUR",
                path=["PORT_CHENNAI", "CFS_CHENNAI_CENTRAL", "PLANT_SRIPERUMBUDUR"],
                mode="ROAD",
                flow_teu=700.0,  # Exceeds Sriperumbudur EV_BATTERY_PACKS 375 TEU limit while < 1500 total!
                unit_cost=150.0,
                total_cost=105000.0,
            ),
        ],
        unmet_demand_teu=4200.0,
        summary="Faulty commodity mix check",
    )
    bad_out, bad_res = optimiser.run(s_b.transition({"candidate_plan": bad_plan}), cfg, random.Random(42))
    assert bad_res.success is False
    assert bad_out.verification_report is not None
    assert "L2:FLOW_CONSERVATION" in bad_out.verification_report.failed_checks


def test_gate_g2_part1_cvar_diversifies_fragile_port_tail_risk(
    registry: CanonicalEntityRegistry,
    graph_store: CorridorGraphStore,
):
    """
    Under mild baseline Chennai disruption paired with a severe tail scenario choking Chennai Port,
    CVaR optimization proactively shifts TEUs away from fragile PORT_CHENNAI vs deterministic routing.
    """
    scenarios = [
        Scenario(
            scenario_id="SCENARIO_EXPECTED",
            name="Moderate swell",
            probability=0.55,
            capacity_multipliers={"PORT_CHENNAI": 0.45},
            duration_days=3.0,
        ),
        Scenario(
            scenario_id="SCENARIO_SEVERE",
            name="Severe cyclone tail collapse at Chennai",
            probability=0.30,
            capacity_multipliers={"PORT_CHENNAI": 0.05},  # Collapses Chennai to 300 TEU/day!
            duration_days=5.5,
        ),
        Scenario(
            scenario_id="SCENARIO_RAPID",
            name="Quick recovery",
            probability=0.15,
            capacity_multipliers={"PORT_CHENNAI": 0.80},
            duration_days=1.5,
        ),
    ]

    cfg_det = PipelineConfig(solver_type="OR_TOOLS", risk_mode="DETERMINISTIC", random_seed=42)
    cfg_cvar = PipelineConfig(
        solver_type="OR_TOOLS",
        risk_mode="CVAR",
        cvar_alpha=0.90,
        cvar_weight=0.80,
        random_seed=42,
    )

    s_b = _make_analyzed_state("PORT_CHENNAI", 0.25, registry, graph_store, cfg_det, scenarios=scenarios)
    optimiser = StageDOptimiserAndVerifier(registry=registry, graph_store=graph_store)

    out_det, res_det = optimiser.run(s_b, cfg_det, random.Random(42))
    out_cvar, res_cvar = optimiser.run(s_b, cfg_cvar, random.Random(42))

    assert res_det.success is True and res_cvar.success is True
    assert out_det.candidate_plan is not None and out_cvar.candidate_plan is not None
    assert out_det.candidate_plan.risk_mode == "DETERMINISTIC"
    assert out_cvar.candidate_plan.risk_mode == "CVAR"
    assert out_cvar.candidate_plan.cvar_cost is not None and out_cvar.candidate_plan.cvar_cost > 0.0

    det_chennai_flow = sum(
        a.flow_teu for a in out_det.candidate_plan.allocations if a.origin_id == "PORT_CHENNAI"
    )
    cvar_chennai_flow = sum(
        a.flow_teu for a in out_cvar.candidate_plan.allocations if a.origin_id == "PORT_CHENNAI"
    )
    # Deterministic exploits Chennai heavily (3000+ TEU), whereas CVaR hedges Chennai below or near 300 TEU tail cap!
    assert det_chennai_flow > 1000.0
    assert cvar_chennai_flow < det_chennai_flow
    assert out_cvar.verification_report is not None
    assert out_cvar.verification_report.passed is True


def test_gate_g2_part1_dual_solver_catches_fraudulent_sub_lower_bound_cost(
    registry: CanonicalEntityRegistry,
    graph_store: CorridorGraphStore,
):
    """Dual solver check catches valid-topology plans that underreport total cost below HiGHS lower bound."""
    cfg = PipelineConfig(solver_type="OR_TOOLS", risk_mode="DETERMINISTIC")
    s_b = _make_analyzed_state("PORT_KAMARAJAR", 0.70, registry, graph_store, cfg)
    optimiser = StageDOptimiserAndVerifier(registry=registry, graph_store=graph_store)

    out_valid, _ = optimiser.run(s_b, cfg, random.Random(42))
    assert out_valid.candidate_plan is not None

    underpriced = out_valid.candidate_plan.model_copy(update={"objective_cost": 1.0})
    out_bad, res_bad = optimiser.run(s_b.transition({"candidate_plan": underpriced}), cfg, random.Random(42))

    assert res_bad.success is False
    assert out_bad.verification_report is not None
    assert "L2:DUAL_SOLVER_AGREEMENT" in out_bad.verification_report.failed_checks


def test_gate_g2_part1_networkx_comparator_matches_ortools_deterministic(
    registry: CanonicalEntityRegistry,
    graph_store: CorridorGraphStore,
):
    """OR-Tools single-commodity deterministic LP objective must match NetworkX min-cost flow identically."""
    cfg_nx = PipelineConfig(
        solver_type="NETWORKX",
        enable_multi_commodity=False,
        risk_mode="DETERMINISTIC",
        line_stop_penalty_per_day=0.0,
    )
    cfg_or = PipelineConfig(
        solver_type="OR_TOOLS",
        enable_multi_commodity=False,
        risk_mode="DETERMINISTIC",
        line_stop_penalty_per_day=0.0,
    )
    s_b = _make_analyzed_state("PORT_CHENNAI", 0.85, registry, graph_store, cfg_or)
    optimiser = StageDOptimiserAndVerifier(registry=registry, graph_store=graph_store)

    out_nx, res_nx = optimiser.run(s_b, cfg_nx, random.Random(42))
    out_or, res_or = optimiser.run(s_b, cfg_or, random.Random(42))

    assert res_nx.success is True and res_or.success is True
    assert out_nx.candidate_plan is not None and out_or.candidate_plan is not None
    assert out_nx.candidate_plan.objective_cost == pytest.approx(
        out_or.candidate_plan.objective_cost, rel=1e-4, abs=5.0
    )
    assert out_nx.candidate_plan.unmet_demand_teu == pytest.approx(
        out_or.candidate_plan.unmet_demand_teu, abs=0.5
    )


def test_gate_g2_part1_linestop_penalty_protects_lowest_cover_jit_plant(
    registry: CanonicalEntityRegistry,
    graph_store: CorridorGraphStore,
):
    """Under scarce capacity, line-stop penalty prioritizes low days-of-cover JIT plants first."""
    cfg = PipelineConfig(
        solver_type="OR_TOOLS",
        risk_mode="DETERMINISTIC",
        enable_multi_commodity=False,
        line_stop_penalty_per_day=25000.0,
    )
    # Give single Chennai-cluster ports tiny supply totaling 2000 TEU over 6-day disruption
    # Both PLANT_SRIPERUMBUDUR (cover=3.5d, dem=1500) & PLANT_SRICITY (cover=6.0d, dem=500) compete for scarce port flow
    mults = {e.id: 0.0 for e in registry.get_by_type(EntityType.PORT)}
    mults["PORT_CHENNAI"] = 0.25  # 1500 TEU available -> strictly < 5300 total demand!
    ctx = GraphContext(
        node_capacity_multipliers=mults,
        edge_capacity_multipliers={},
    )
    evt = DisruptionEvent(
        event_id="EVT_JIT_SCARCE",
        event_type=DisruptionEventType.HAZARD_PORT,
        status=EventStatus.NEW,
        primary_entity_id="PORT_CHENNAI",
        affected_entity_ids=["PORT_CHENNAI"],
        severity=0.75,
        estimated_duration_days=6.0,
        source_feed="TEST",
        raw_headline="Regional port closure",
        raw_text="Severe disruption limiting ports to Chennai residual.",
        timestamp=datetime(2026, 11, 10, tzinfo=UTC),
    )
    state = PipelineState(
        session_id="SESS_JIT",
        status=PipelineStatus.ANALYZED,
        event=evt,
        graph_context=ctx,
    )
    out_d, _ = StageDOptimiserAndVerifier(registry=registry, graph_store=graph_store).run(
        state, cfg, random.Random(42)
    )
    assert out_d.candidate_plan is not None
    deliv_by_plant = {
        pid: sum(a.flow_teu for a in out_d.candidate_plan.allocations if a.destination_id == pid)
        for pid in ("PLANT_SRIPERUMBUDUR", "PLANT_SRICITY")
    }
    # Lowest-cover Sriperumbudur (3.5d < 6.0d duration -> triggers line-stop excess) must receive priority
    assert deliv_by_plant["PLANT_SRIPERUMBUDUR"] >= deliv_by_plant["PLANT_SRICITY"]
