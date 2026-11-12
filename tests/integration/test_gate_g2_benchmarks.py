"""
Gate G2 Benchmark Verification Suite (PRD Suite S1 Baseline).
Tests Stage B fixed-seed reproducibility, severity sensitivity, compound disruptions,
inactive edge avoidance, and zero L1/L2 constraint breaches across all 23 corridor entities.
"""

from __future__ import annotations

import copy
import random
from datetime import datetime, timezone

import pytest

from asci.core.contracts import PipelineConfig
from asci.core.registry import CanonicalEntityRegistry, EntityType
from asci.core.state import (
    DisruptionEvent,
    DisruptionEventType,
    EventStatus,
    PipelineState,
    PipelineStatus,
    RawSignal,
    TrustTier,
)
from asci.stages import (
    StageBCorridorRisk,
    StageDOptimiserAndVerifier,
    StageEDashboard,
    WalkingSkeletonPipeline,
)
from asci.uskl.graph_store import CorridorGraphStore

_SINGLE_POINT_BOTTLENECK_ENTITIES = {
    "ICD_WHITEFIELD",
    "PLANT_BIDADI",
    "ICD_IRUGUR",
    "PLANT_COIMBATORE",
    "PLANT_SRICITY",
    "PORT_KRISHNAPATNAM",
}


def _event_type_for_entity(entity_type: EntityType) -> DisruptionEventType:
    if entity_type == EntityType.PORT:
        return DisruptionEventType.HAZARD_PORT
    if entity_type == EntityType.PLANT:
        return DisruptionEventType.PLANT_OUTAGE
    if entity_type == EntityType.CORRIDOR_JUNCTION:
        return DisruptionEventType.HAZARD_ROAD
    return DisruptionEventType.RAIL_DISRUPTION


@pytest.mark.parametrize(
    "entity_id",
    [
        "PORT_CHENNAI",
        "PORT_KAMARAJAR",
        "PORT_KATTUPALLI",
        "PORT_KRISHNAPATNAM",
        "PORT_VOC",
        "PORT_COCHIN",
        "PORT_NEW_MANGALORE",
        "ICD_WHITEFIELD",
        "ICD_TONDIARPET",
        "ICD_IRUGUR",
        "CFS_CHENNAI_CENTRAL",
        "CFS_WHITEFIELD",
        "CFS_ENNORE_LOGISTICS",
        "JUNCTION_RANIPET",
        "JUNCTION_VELLORE",
        "JUNCTION_KRISHNAGIRI",
        "JUNCTION_CHITTOOR",
        "PLANT_SRICITY",
        "PLANT_SRIPERUMBUDUR",
        "PLANT_ORAGADAM",
        "PLANT_HOSUR",
        "PLANT_BIDADI",
        "PLANT_COIMBATORE",
    ],
)
def test_gate_g2_all_23_entities_reproducible_zero_l1_l2_breach(
    entity_id: str,
    registry: CanonicalEntityRegistry,
    pipeline_config: PipelineConfig,
):
    """
    Gate G2 Sweep (Suite S1): Every entity across all 23 corridor nodes runs Stage A->E
    reproducibly under fixed random seed with ZERO L1/L2 capacity or conservation breaches.
    """
    entity = registry.get(entity_id)
    evt = DisruptionEvent(
        event_id=f"EVT_G2_{entity_id}",
        event_type=_event_type_for_entity(entity.entity_type),
        status=EventStatus.NEW,
        primary_entity_id=entity_id,
        affected_entity_ids=[entity_id],
        severity=0.85,
        estimated_duration_days=3.0,
        source_feed="GATE_G2_SWEEP",
        raw_headline=f"Disruption affecting {entity.name}",
        raw_text=f"Operational bottleneck at {entity.name} ({entity_id}).",
        timestamp=datetime(2026, 11, 10, tzinfo=timezone.utc),
        corroboration_count=2,
        confidence=0.90,
    )
    s0 = PipelineState(session_id=f"SESS_G2_{entity_id}", status=PipelineStatus.PERCEIVED, event=evt)
    pipe = WalkingSkeletonPipeline()

    s1, _ = pipe.run(s0, pipeline_config, random.Random(pipeline_config.random_seed))
    s2, _ = pipe.run(s0, pipeline_config, random.Random(pipeline_config.random_seed))

    # Fixed-seed determinism across Stage B metrics & Stage D allocations
    assert s1.graph_context == s2.graph_context
    assert s1.candidate_plan is not None and s2.candidate_plan is not None
    assert s1.candidate_plan.plan_id == s2.candidate_plan.plan_id
    assert s1.candidate_plan.objective_cost == s2.candidate_plan.objective_cost
    assert s1.candidate_plan.allocations == s2.candidate_plan.allocations

    # Zero L1 or L2 constraint breaches across ALL 23 entities
    assert s1.verification_report is not None
    l1_l2_failures = [c for c in s1.verification_report.failed_checks if not c.startswith("L3:")]
    assert l1_l2_failures == []

    # Redundant entities must absorb disruption with zero unmet demand & full COMPLETED status
    if entity_id not in _SINGLE_POINT_BOTTLENECK_ENTITIES:
        assert s1.candidate_plan.unmet_demand_teu == 0.0
        assert s1.status == PipelineStatus.COMPLETED


def test_gate_g2_stage_b_severity_monotonicity_across_all_ports(
    registry: CanonicalEntityRegistry,
    graph_store: CorridorGraphStore,
    pipeline_config: PipelineConfig,
):
    """Gate G2: Verify higher severity produces strictly higher aggregate path risk across all 7 ports."""
    pipe = WalkingSkeletonPipeline()
    stage_b = pipe.stage_b

    for port in registry.get_by_type(EntityType.PORT):
        base_evt = DisruptionEvent(
            event_id=f"EVT_MONO_{port.id}",
            event_type=DisruptionEventType.HAZARD_PORT,
            status=EventStatus.NEW,
            primary_entity_id=port.id,
            affected_entity_ids=[port.id],
            severity=0.20,
            estimated_duration_days=2.0,
            source_feed="GATE_G2_MONO",
            raw_headline=f"Minor swell at {port.name}",
            raw_text=f"Mild weather at {port.name}",
            timestamp=datetime(2026, 11, 10, tzinfo=timezone.utc),
        )
        low_s, _ = stage_b.run(
            PipelineState(session_id="S_L", status=PipelineStatus.PERCEIVED, event=base_evt),
            pipeline_config,
            random.Random(42),
        )
        high_s, _ = stage_b.run(
            PipelineState(
                session_id="S_H",
                status=PipelineStatus.PERCEIVED,
                event=base_evt.model_copy(update={"severity": 0.92, "estimated_duration_days": 4.0}),
            ),
            pipeline_config,
            random.Random(42),
        )
        assert low_s.graph_context is not None and high_s.graph_context is not None
        low_risk = sum(m.path_risk for m in low_s.graph_context.path_metrics)
        high_risk = sum(m.path_risk for m in high_s.graph_context.path_metrics)
        assert high_risk > low_risk


def test_gate_g2_compound_chennai_cluster_outage_diverts_without_breach(
    registry: CanonicalEntityRegistry,
    pipeline_config: PipelineConfig,
):
    """Gate G2: Compound simultaneous outage across Kamarajar + Kattupalli + Chennai degrades cleanly."""
    evt = DisruptionEvent(
        event_id="EVT_COMPOUND_COASTAL",
        event_type=DisruptionEventType.HAZARD_PORT,
        status=EventStatus.NEW,
        primary_entity_id="PORT_KAMARAJAR",
        affected_entity_ids=["PORT_KAMARAJAR", "PORT_KATTUPALLI", "PORT_CHENNAI", "CFS_ENNORE_LOGISTICS"],
        severity=0.88,
        estimated_duration_days=4.0,
        source_feed="GATE_G2_COMPOUND",
        raw_headline="Bay Cyclone impacts Ennore, Kattupalli, and Chennai ports",
        raw_text="Simultaneous coastal storm warning along North Tamil Nadu ports.",
        timestamp=datetime(2026, 11, 10, tzinfo=timezone.utc),
        corroboration_count=3,
        confidence=0.95,
    )
    pipe = WalkingSkeletonPipeline()
    s0 = PipelineState(session_id="SESS_COMPOUND", status=PipelineStatus.PERCEIVED, event=evt)
    final_state, results = pipe.run(s0, pipeline_config, random.Random(42))

    assert all(r.success for r in results)
    assert final_state.status == PipelineStatus.COMPLETED
    assert final_state.verification_report is not None
    assert final_state.verification_report.passed is True
    assert final_state.candidate_plan is not None
    assert final_state.candidate_plan.unmet_demand_teu == 0.0

    # Flows must respect degraded port caps while shifting load to Krishnapatnam / Cochin / New Mangalore
    flows_by_port: dict[str, float] = {}
    for a in final_state.candidate_plan.allocations:
        flows_by_port[a.origin_id] = flows_by_port.get(a.origin_id, 0.0) + a.flow_teu

    assert flows_by_port.get("PORT_KAMARAJAR", 0.0) <= 4500.0 * 0.12 + 1e-4
    assert flows_by_port.get("PORT_CHENNAI", 0.0) <= 6000.0 * 0.47 + 1e-4


def test_gate_g2_inactive_graph_edge_carries_zero_flow(
    registry: CanonicalEntityRegistry,
    graph_store: CorridorGraphStore,
    pipeline_config: PipelineConfig,
):
    """Gate G2 / Sec 7.2: Explicitly deactivated graph links carry zero flow in solved plans."""
    g_copy = copy.deepcopy(graph_store.graph)
    g_copy["PORT_CHENNAI"]["ICD_WHITEFIELD"]["RAIL_DIRECT"]["active"] = False
    degraded_store = CorridorGraphStore(graph=g_copy, registry=registry)

    pipe = WalkingSkeletonPipeline(
        stage_b=StageBCorridorRisk(graph_store=degraded_store, registry=registry),
        stage_d=StageDOptimiserAndVerifier(graph_store=degraded_store, registry=registry),
        stage_e=StageEDashboard(graph_store=degraded_store, registry=registry),
    )

    evt = DisruptionEvent(
        event_id="EVT_INACTIVE_LINK",
        event_type=DisruptionEventType.RAIL_DISRUPTION,
        status=EventStatus.NEW,
        primary_entity_id="PORT_CHENNAI",
        affected_entity_ids=["PORT_CHENNAI"],
        severity=0.40,
        estimated_duration_days=2.0,
        source_feed="TEST",
        raw_headline="Chennai-Whitefield rail direct track suspended",
        raw_text="Direct rail block train corridor temporarily closed.",
        timestamp=datetime(2026, 11, 10, tzinfo=timezone.utc),
    )
    s_fin, _ = pipe.run(
        PipelineState(session_id="S_INACT", status=PipelineStatus.PERCEIVED, event=evt),
        pipeline_config,
        random.Random(42),
    )
    assert s_fin.verification_report is not None
    assert s_fin.verification_report.passed is True
    assert s_fin.candidate_plan is not None
    # Verify (PORT_CHENNAI, ICD_WHITEFIELD) edge is completely avoided
    for a in s_fin.candidate_plan.allocations:
        hops = list(zip(a.path, a.path[1:]))
        assert ("PORT_CHENNAI", "ICD_WHITEFIELD") not in hops


@pytest.mark.parametrize(
    ("headline", "body", "expected_type", "expected_entity"),
    [
        (
            "Severe cyclone forces berth closure at Kamarajar Port",
            "Storm surge halts container crane operations at Ennore for 72 hours.",
            DisruptionEventType.HAZARD_PORT,
            "PORT_KAMARAJAR",
        ),
        (
            "Heavy flood and waterlogging shut NH48 near Ranipet",
            "Bridge inundation strands inbound freight around Ranipet Bypass.",
            DisruptionEventType.HAZARD_ROAD,
            "JUNCTION_RANIPET",
        ),
        (
            "Stevedore strike and walkout hit Chennai Port berths",
            "Berth backlog delays Chennai Port Trust vessel unloading for 48 hours.",
            DisruptionEventType.PORT_CONGESTION_STRIKE,
            "PORT_CHENNAI",
        ),
        (
            "Track flooding triggers rail disruption at Tondiarpet ICD",
            "Signal failure leaves CONCOR Tondiarpet railway suspended for 2 days.",
            DisruptionEventType.RAIL_DISRUPTION,
            "ICD_TONDIARPET",
        ),
        (
            "Blank sailing causes vessel omission at Kattupalli Port",
            "Mainline carrier diversion skips Adani Kattupalli terminal this week.",
            DisruptionEventType.SHIPPING_SCHEDULE,
            "PORT_KATTUPALLI",
        ),
        (
            "Emergency import duty and tariff shift announced at Cochin Port",
            "Customs rule and export ban inspection slows Vallarpadam ICTT clearance.",
            DisruptionEventType.TRADE_POLICY,
            "PORT_COCHIN",
        ),
        (
            "Assembly stoppage and plant outage reported at Oragadam Cluster",
            "Line shutdown follows tier supplier breakdown at Oragadam Automotive Cluster.",
            DisruptionEventType.PLANT_OUTAGE,
            "PLANT_ORAGADAM",
        ),
    ],
)
def test_gate_g2_raw_signal_all_7_event_categories_end_to_end(
    headline: str,
    body: str,
    expected_type: DisruptionEventType,
    expected_entity: str,
    pipeline_config: PipelineConfig,
):
    """Gate G2 / Sec 5.1: All 7 PRD taxonomy categories classify and solve E2E from RawSignal."""
    sig = RawSignal(
        signal_id=f"SIG_TAX_{expected_type.value}",
        source_feed="GATE_G2_TAXONOMY",
        trust_tier=TrustTier.TIER_B,
        raw_headline=headline,
        raw_text=body,
        published_at=datetime(2026, 11, 10, tzinfo=timezone.utc),
    )
    pipe = WalkingSkeletonPipeline()
    s0 = PipelineState(
        session_id=f"SESS_TAX_{expected_type.value}",
        status=PipelineStatus.INITIALIZED,
        raw_signal=sig,
    )
    final_state, results = pipe.run(s0, pipeline_config, random.Random(42))

    assert len(results) == 5
    assert all(r.success for r in results)
    assert final_state.status == PipelineStatus.COMPLETED
    assert final_state.event is not None
    assert final_state.event.event_type == expected_type
    assert final_state.event.primary_entity_id == expected_entity
    assert final_state.verification_report is not None
    assert final_state.verification_report.passed is True
    assert final_state.candidate_plan is not None
    assert final_state.candidate_plan.unmet_demand_teu == 0.0

