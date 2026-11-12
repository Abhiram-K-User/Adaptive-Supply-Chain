"""
Unit tests for generalized Stage D flow solver and genuine L1-L3 verification checks.
"""

import random
from datetime import UTC, datetime

from asci.core.contracts import PipelineConfig
from asci.core.registry import CanonicalEntityRegistry
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
    TrustTier,
    VerificationVerdict,
)
from asci.stages.stage_b_graph import StageBCorridorRisk
from asci.stages.stage_d_optimiser import StageDOptimiserAndVerifier
from asci.stages.stage_e_dashboard import StageEDashboard
from asci.uskl.graph_store import CorridorGraphStore


def _prepare_analyzed_state(
    entity_id: str,
    event_type: DisruptionEventType,
    severity: float,
    registry: CanonicalEntityRegistry,
    graph_store: CorridorGraphStore,
    cfg: PipelineConfig,
) -> PipelineState:
    evt = DisruptionEvent(
        event_id=f"EVT_{entity_id}",
        event_type=event_type,
        status=EventStatus.NEW,
        primary_entity_id=entity_id,
        affected_entity_ids=[entity_id],
        severity=severity,
        estimated_duration_days=3.0,
        source_feed="TEST_FEED",
        raw_headline=f"Disruption at {entity_id}",
        raw_text=f"Operational stoppage affecting {entity_id}.",
        timestamp=datetime(2026, 11, 10, tzinfo=UTC),
    )
    ev_doc = EvidenceItem(
        citation_id=f"CIT_{entity_id}",
        source="Official Port Notice",
        trust_tier=TrustTier.TIER_A,
        entity_ids=[entity_id, "PORT_COCHIN", "ICD_IRUGUR", "PORT_KRISHNAPATNAM"],
        snippet=f"Operational notice for {entity_id}.",
        publication_date="2026-11-10",
    )
    s0 = PipelineState(
        session_id=f"SESS_{entity_id}",
        status=PipelineStatus.PERCEIVED,
        event=evt,
        evidence_set=[ev_doc],
    )
    stage_b = StageBCorridorRisk(graph_store=graph_store, registry=registry)
    s_b, _ = stage_b.run(s0, cfg, random.Random(42))
    return s_b


def test_stage_d_solves_chennai_and_voc_without_hardcoding(
    registry: CanonicalEntityRegistry,
    graph_store: CorridorGraphStore,
    pipeline_config: PipelineConfig,
):
    """Verify Stage D reroutes cleanly for PORT_CHENNAI and PORT_VOC disruptions."""
    optimiser = StageDOptimiserAndVerifier(registry=registry, graph_store=graph_store)

    # 1. Severe Chennai Port disruption (0.92 -> residual cap ~480 TEU/day)
    s_chennai = _prepare_analyzed_state(
        "PORT_CHENNAI", DisruptionEventType.HAZARD_PORT, 0.92, registry, graph_store, pipeline_config
    )
    out_ch, res_ch = optimiser.run(s_chennai, pipeline_config, random.Random(42))
    assert res_ch.success is True
    assert out_ch.status == PipelineStatus.VERIFIED
    assert out_ch.candidate_plan is not None
    assert out_ch.candidate_plan.unmet_demand_teu == 0.0
    chennai_out = sum(
        a.flow_teu for a in out_ch.candidate_plan.allocations if a.origin_id == "PORT_CHENNAI"
    )
    assert chennai_out <= 6000.0 * 0.08 + 1e-4
    assert "PORT_CHENNAI" in out_ch.candidate_plan.summary

    # 2. V.O. Chidambaranar (Tuticorin) Port strike
    s_voc = _prepare_analyzed_state(
        "PORT_VOC",
        DisruptionEventType.PORT_CONGESTION_STRIKE,
        0.85,
        registry,
        graph_store,
        pipeline_config,
    )
    out_voc, res_voc = optimiser.run(s_voc, pipeline_config, random.Random(42))
    assert res_voc.success is True
    assert out_voc.status == PipelineStatus.VERIFIED
    assert out_voc.candidate_plan is not None
    assert out_voc.candidate_plan.unmet_demand_teu == 0.0
    assert "PORT_VOC" in out_voc.candidate_plan.summary
    assert any(a.destination_id == "PLANT_COIMBATORE" for a in out_voc.candidate_plan.allocations)


def test_l2_catches_nonexistent_graph_edge_and_aggregate_capacity_breach(
    registry: CanonicalEntityRegistry,
    graph_store: CorridorGraphStore,
    pipeline_config: PipelineConfig,
):
    """Verify L2 catches broken edges (PORT_CHENNAI -> PLANT_ORAGADAM) and summed CFS capacity overruns."""
    optimiser = StageDOptimiserAndVerifier(registry=registry, graph_store=graph_store)
    s_b = _prepare_analyzed_state(
        "PORT_KAMARAJAR", DisruptionEventType.HAZARD_PORT, 0.85, registry, graph_store, pipeline_config
    )

    # Fault A: Direct nonexistent edge + flow imbalance
    broken_edge_plan = MitigationPlan(
        plan_id="PLAN_BAD_EDGE",
        objective_cost=100000.0,
        allocations=[
            FlowAllocation(
                origin_id="PORT_CHENNAI",
                destination_id="PLANT_ORAGADAM",
                path=["PORT_CHENNAI", "PLANT_ORAGADAM"],  # Missing direct edge!
                mode="ROAD",
                flow_teu=5300.0,
                unit_cost=100.0,
                total_cost=530000.0,
            )
        ],
        unmet_demand_teu=0.0,
        summary="Broken edge test",
    )
    out_a, res_a = optimiser.run(
        s_b.transition({"candidate_plan": broken_edge_plan}), pipeline_config, random.Random(42)
    )
    assert res_a.success is False
    assert out_a.verification_report is not None
    assert "L2:GRAPH_EDGE_VALIDITY" in out_a.verification_report.failed_checks

    # Fault B: Two valid paths summing over CFS_CHENNAI_CENTRAL capacity (1500 TEU/day)
    cap_breach_plan = MitigationPlan(
        plan_id="PLAN_SUM_CAP_BREACH",
        objective_cost=500000.0,
        allocations=[
            FlowAllocation(
                origin_id="PORT_CHENNAI",
                destination_id="PLANT_ORAGADAM",
                path=["PORT_CHENNAI", "CFS_CHENNAI_CENTRAL", "PLANT_ORAGADAM"],
                mode="ROAD",
                flow_teu=1200.0,  # Under 1500 individually
                unit_cost=160.0,
                total_cost=192000.0,
            ),
            FlowAllocation(
                origin_id="PORT_CHENNAI",
                destination_id="PLANT_SRIPERUMBUDUR",
                path=["PORT_CHENNAI", "CFS_CHENNAI_CENTRAL", "PLANT_SRIPERUMBUDUR"],
                mode="ROAD",
                flow_teu=1500.0,  # Total through CFS_CHENNAI_CENTRAL = 2700 > 1500!
                unit_cost=150.0,
                total_cost=225000.0,
            ),
        ],
        unmet_demand_teu=2600.0,
        summary="Summed node cap breach test",
    )
    out_b, res_b = optimiser.run(
        s_b.transition({"candidate_plan": cap_breach_plan}), pipeline_config, random.Random(42)
    )
    assert res_b.success is False
    assert out_b.verification_report is not None
    assert "L2:EDGE_CAPACITY_BOUNDS" in out_b.verification_report.failed_checks


def test_l2_catches_demand_conservation_fraud_and_stage_e_preserves_failed_status(
    registry: CanonicalEntityRegistry,
    graph_store: CorridorGraphStore,
    pipeline_config: PipelineConfig,
):
    """Verify L2 catches underreported demand / cost fraud and Stage E preserves FAILED status."""
    optimiser = StageDOptimiserAndVerifier(registry=registry, graph_store=graph_store)
    stage_e = StageEDashboard(registry=registry, graph_store=graph_store)
    s_b = _prepare_analyzed_state(
        "PORT_KAMARAJAR", DisruptionEventType.HAZARD_PORT, 0.85, registry, graph_store, pipeline_config
    )

    fraud_plan = MitigationPlan(
        plan_id="PLAN_DEMAND_FRAUD",
        objective_cost=1000.0,
        allocations=[
            FlowAllocation(
                origin_id="PORT_CHENNAI",
                destination_id="PLANT_ORAGADAM",
                path=["PORT_CHENNAI", "CFS_CHENNAI_CENTRAL", "PLANT_ORAGADAM"],
                mode="ROAD",
                flow_teu=100.0,
                unit_cost=160.0,
                total_cost=99999.0,  # Mismatched cost
            )
        ],
        unmet_demand_teu=0.0,  # Dishonest: total corridor demand is 5300 TEU!
        summary="Fraudulent under-reported unmet demand",
    )
    out_f, res_f = optimiser.run(
        s_b.transition({"candidate_plan": fraud_plan}), pipeline_config, random.Random(42)
    )
    assert res_f.success is False
    assert out_f.status == PipelineStatus.FAILED
    assert out_f.verification_report is not None
    assert out_f.verification_report.overall_verdict == VerificationVerdict.FAIL
    assert "L2:FLOW_CONSERVATION" in out_f.verification_report.failed_checks

    # Stage E must preserve FAILED rather than flipping status to COMPLETED
    out_e, res_e = stage_e.run(out_f, pipeline_config, random.Random(42))
    assert out_e.status == PipelineStatus.FAILED
    assert res_e.success is False

    # Extreme multi-port closure should yield real unmet demand and fail L3
    zero_ports_ctx = GraphContext(
        node_capacity_multipliers={
            pid.id: 0.0 for pid in registry.get_by_type(registry.get("PORT_CHENNAI").entity_type)
        },
        edge_capacity_multipliers=s_b.graph_context.edge_capacity_multipliers if s_b.graph_context else {},
    )
    catastrophic_state = s_b.transition({"graph_context": zero_ports_ctx})
    out_cat, res_cat = optimiser.run(catastrophic_state, pipeline_config, random.Random(42))
    assert res_cat.success is False
    assert out_cat.candidate_plan is not None
    assert out_cat.candidate_plan.unmet_demand_teu >= 5000.0
    assert out_cat.verification_report is not None
    assert "L3:UNMET_DEMAND_BOUND" in out_cat.verification_report.failed_checks

