"""
Gate G3 Mutation Harness (PRD Suite S4 Systematic Fault Injection).
Verifies the L1-L3 verification layers catch all injected schema, graph, capacity,
conservation, supply-origin, sink-destination, per-plant over-delivery, and demand faults,
while Stage E preserves FAILED status.
"""

from __future__ import annotations

import copy
import random
from datetime import datetime, timezone

import pytest

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


def _base_analyzed_state(
    registry: CanonicalEntityRegistry,
    graph_store: CorridorGraphStore,
    cfg: PipelineConfig,
) -> PipelineState:
    evt = DisruptionEvent(
        event_id="EVT_MUT_BASE",
        event_type=DisruptionEventType.HAZARD_PORT,
        status=EventStatus.NEW,
        primary_entity_id="PORT_KAMARAJAR",
        affected_entity_ids=["PORT_KAMARAJAR"],
        severity=0.85,
        estimated_duration_days=3.0,
        source_feed="TEST_S4",
        raw_headline="Storm surge at Kamarajar Port",
        raw_text="Cyclonic alert at Ennore.",
        timestamp=datetime(2026, 11, 10, tzinfo=timezone.utc),
        corroboration_count=2,
        confidence=0.92,
    )
    ev = EvidenceItem(
        citation_id="CIT_S4_001",
        source="Official Notice",
        trust_tier=TrustTier.TIER_A,
        entity_ids=["PORT_KAMARAJAR", "PORT_CHENNAI", "PORT_COCHIN"],
        snippet="Port contingency active.",
        publication_date="2026-11-10",
    )
    s0 = PipelineState(
        session_id="SESS_MUT_BASE",
        status=PipelineStatus.PERCEIVED,
        event=evt,
        evidence_set=[ev],
    )
    s_b, _ = StageBCorridorRisk(graph_store=graph_store, registry=registry).run(
        s0, cfg, random.Random(42)
    )
    return s_b


def _assert_fault_caught(
    optimiser: StageDOptimiserAndVerifier,
    stage_e: StageEDashboard,
    state: PipelineState,
    cfg: PipelineConfig,
    expected_check: str,
) -> None:
    out_d, res_d = optimiser.run(state, cfg, random.Random(42))
    assert res_d.success is False
    assert out_d.status == PipelineStatus.FAILED
    assert out_d.verification_report is not None
    assert out_d.verification_report.passed is False
    assert expected_check in out_d.verification_report.failed_checks

    out_e, res_e = stage_e.run(out_d, cfg, random.Random(42))
    assert res_e.success is False
    assert out_e.status == PipelineStatus.FAILED


@pytest.mark.parametrize(
    ("fault_name", "allocations", "unmet_demand", "expected_check"),
    [
        (
            "unregistered_entity_id",
            [
                FlowAllocation(
                    origin_id="PORT_SINGAPORE",
                    destination_id="PLANT_ORAGADAM",
                    path=["PORT_SINGAPORE", "PLANT_ORAGADAM"],
                    mode="ROAD",
                    flow_teu=5300.0,
                    unit_cost=100.0,
                    total_cost=530000.0,
                )
            ],
            0.0,
            "L1:CANONICAL_ENTITY_GROUNDING",
        ),
        (
            "nonexistent_edge",
            [
                FlowAllocation(
                    origin_id="PORT_CHENNAI",
                    destination_id="PLANT_ORAGADAM",
                    path=["PORT_CHENNAI", "PLANT_ORAGADAM"],
                    mode="ROAD",
                    flow_teu=1200.0,
                    unit_cost=100.0,
                    total_cost=120000.0,
                )
            ],
            4100.0,
            "L2:GRAPH_EDGE_VALIDITY",
        ),
        (
            "wrong_direction_edge",
            [
                FlowAllocation(
                    origin_id="PORT_COCHIN",
                    destination_id="PLANT_COIMBATORE",
                    path=["PORT_COCHIN", "PLANT_COIMBATORE", "ICD_IRUGUR"],
                    mode="RAIL",
                    flow_teu=400.0,
                    unit_cost=200.0,
                    total_cost=80000.0,
                )
            ],
            4900.0,
            "L2:GRAPH_EDGE_VALIDITY",
        ),
        (
            "cyclic_route",
            [
                FlowAllocation(
                    origin_id="PORT_CHENNAI",
                    destination_id="PLANT_SRIPERUMBUDUR",
                    path=[
                        "PORT_CHENNAI",
                        "CFS_CHENNAI_CENTRAL",
                        "PLANT_SRIPERUMBUDUR",
                        "PLANT_ORAGADAM",
                        "PLANT_SRIPERUMBUDUR",
                    ],
                    mode="ROAD",
                    flow_teu=500.0,
                    unit_cost=280.0,
                    total_cost=140000.0,
                )
            ],
            4800.0,
            "L2:GRAPH_EDGE_VALIDITY",
        ),
        (
            "endpoint_mismatch",
            [
                FlowAllocation(
                    origin_id="PORT_CHENNAI",
                    destination_id="PLANT_HOSUR",
                    path=["PORT_CHENNAI", "CFS_CHENNAI_CENTRAL", "PLANT_ORAGADAM"],
                    mode="ROAD",
                    flow_teu=900.0,
                    unit_cost=160.0,
                    total_cost=144000.0,
                )
            ],
            4400.0,
            "L2:GRAPH_EDGE_VALIDITY",
        ),
        (
            "conjured_non_port_origin",
            [
                FlowAllocation(
                    origin_id="JUNCTION_KRISHNAGIRI",
                    destination_id="PLANT_HOSUR",
                    path=["JUNCTION_KRISHNAGIRI", "PLANT_HOSUR"],
                    mode="ROAD",
                    flow_teu=900.0,
                    unit_cost=85.0,
                    total_cost=76500.0,
                )
            ],
            4400.0,
            "L2:FLOW_CONSERVATION",
        ),
        (
            "fake_non_plant_destination",
            [
                FlowAllocation(
                    origin_id="PORT_CHENNAI",
                    destination_id="CFS_CHENNAI_CENTRAL",
                    path=["PORT_CHENNAI", "CFS_CHENNAI_CENTRAL"],
                    mode="ROAD",
                    flow_teu=1500.0,
                    unit_cost=55.0,
                    total_cost=82500.0,
                )
            ],
            3800.0,
            "L2:FLOW_CONSERVATION",
        ),
        (
            "per_plant_over_delivery_dumping",
            [
                FlowAllocation(
                    origin_id="PORT_CHENNAI",
                    destination_id="PLANT_ORAGADAM",
                    path=["PORT_CHENNAI", "CFS_CHENNAI_CENTRAL", "PLANT_ORAGADAM"],
                    mode="ROAD",
                    flow_teu=1450.0,  # Plant Oragadam demand is only 1200.0 TEU
                    unit_cost=160.0,
                    total_cost=232000.0,
                )
            ],
            3850.0,
            "L2:FLOW_CONSERVATION",
        ),
        (
            "cost_multiplication_fraud",
            [
                FlowAllocation(
                    origin_id="PORT_CHENNAI",
                    destination_id="PLANT_ORAGADAM",
                    path=["PORT_CHENNAI", "CFS_CHENNAI_CENTRAL", "PLANT_ORAGADAM"],
                    mode="ROAD",
                    flow_teu=1000.0,
                    unit_cost=160.0,
                    total_cost=1.0,
                )
            ],
            4300.0,
            "L2:FLOW_CONSERVATION",
        ),
        (
            "summed_node_capacity_breach",
            [
                FlowAllocation(
                    origin_id="PORT_CHENNAI",
                    destination_id="PLANT_ORAGADAM",
                    path=["PORT_CHENNAI", "CFS_CHENNAI_CENTRAL", "PLANT_ORAGADAM"],
                    mode="ROAD",
                    flow_teu=1100.0,
                    unit_cost=160.0,
                    total_cost=176000.0,
                ),
                FlowAllocation(
                    origin_id="PORT_CHENNAI",
                    destination_id="PLANT_SRIPERUMBUDUR",
                    path=["PORT_CHENNAI", "CFS_CHENNAI_CENTRAL", "PLANT_SRIPERUMBUDUR"],
                    mode="ROAD",
                    flow_teu=1100.0,  # 2200 > CFS_CHENNAI_CENTRAL cap 1500
                    unit_cost=150.0,
                    total_cost=165000.0,
                ),
            ],
            3100.0,
            "L2:EDGE_CAPACITY_BOUNDS",
        ),
    ],
)
def test_gate_g3_suite_s4_mutation_catalog(
    fault_name: str,
    allocations: list[FlowAllocation],
    unmet_demand: float,
    expected_check: str,
    registry: CanonicalEntityRegistry,
    graph_store: CorridorGraphStore,
    pipeline_config: PipelineConfig,
):
    """Gate G3 / Suite S4: Every injected plan mutation fails its targeted L1/L2 verification check."""
    s_b = _base_analyzed_state(registry, graph_store, pipeline_config)
    optimiser = StageDOptimiserAndVerifier(registry=registry, graph_store=graph_store)
    stage_e = StageEDashboard(registry=registry, graph_store=graph_store)

    mutated = MitigationPlan(
        plan_id=f"PLAN_MUT_{fault_name}",
        objective_cost=max(1.0, sum(a.total_cost for a in allocations)),
        allocations=allocations,
        unmet_demand_teu=unmet_demand,
        summary=f"Injected mutation: {fault_name}",
    )
    _assert_fault_caught(
        optimiser, stage_e, s_b.transition({"candidate_plan": mutated}), pipeline_config, expected_check
    )


def test_gate_g3_catches_closed_edge_and_closed_plant_passthrough(
    registry: CanonicalEntityRegistry,
    graph_store: CorridorGraphStore,
    pipeline_config: PipelineConfig,
):
    """Gate G3: Inactive edge traversal and flow through zero-multiplier closed nodes must fail L2."""
    s_b = _base_analyzed_state(registry, graph_store, pipeline_config)
    stage_e = StageEDashboard(registry=registry, graph_store=graph_store)

    # 1. Inactive graph link traversal even if flow_teu == 0.0
    g_copy = copy.deepcopy(graph_store.graph)
    g_copy["PORT_COCHIN"]["ICD_IRUGUR"]["RAIL_CONCOR"]["active"] = False
    inactive_store = CorridorGraphStore(graph=g_copy, registry=registry)
    opt_inact = StageDOptimiserAndVerifier(registry=registry, graph_store=inactive_store)

    inact_plan = MitigationPlan(
        plan_id="PLAN_INACTIVE_EDGE",
        objective_cost=86000.0,
        allocations=[
            FlowAllocation(
                origin_id="PORT_COCHIN",
                destination_id="PLANT_COIMBATORE",
                path=["PORT_COCHIN", "ICD_IRUGUR", "PLANT_COIMBATORE"],
                mode="INTERMODAL_RAIL",
                flow_teu=400.0,
                unit_cost=215.0,
                total_cost=86000.0,
            )
        ],
        unmet_demand_teu=4900.0,
        summary="Traverses deactivated link",
    )
    _assert_fault_caught(
        opt_inact, stage_e, s_b.transition({"candidate_plan": inact_plan}), pipeline_config, "L2:GRAPH_EDGE_VALIDITY"
    )

    # 2. Zero-multiplier closed plant node carrying passthrough freight
    assert s_b.graph_context is not None
    node_mults = dict(s_b.graph_context.node_capacity_multipliers)
    node_mults["PLANT_SRICITY"] = 0.0
    closed_plant_ctx = GraphContext(
        node_capacity_multipliers=node_mults,
        edge_capacity_multipliers=dict(s_b.graph_context.edge_capacity_multipliers),
    )
    opt_std = StageDOptimiserAndVerifier(registry=registry, graph_store=graph_store)
    passthrough_plan = MitigationPlan(
        plan_id="PLAN_CLOSED_PLANT",
        objective_cost=27500.0,
        allocations=[
            FlowAllocation(
                origin_id="PORT_KRISHNAPATNAM",
                destination_id="PLANT_SRIPERUMBUDUR",
                path=["PORT_KRISHNAPATNAM", "PLANT_SRICITY", "PLANT_SRIPERUMBUDUR"],
                mode="ROAD",
                flow_teu=100.0,
                unit_cost=275.0,
                total_cost=27500.0,
            )
        ],
        unmet_demand_teu=5200.0,
        summary="Routes through zero-capacity closed plant",
    )
    _assert_fault_caught(
        opt_std,
        stage_e,
        s_b.transition({"graph_context": closed_plant_ctx, "candidate_plan": passthrough_plan}),
        pipeline_config,
        "L2:EDGE_CAPACITY_BOUNDS",
    )


def test_gate_g3_l3_citation_grounding_warns_when_unmatched(
    registry: CanonicalEntityRegistry,
    graph_store: CorridorGraphStore,
    pipeline_config: PipelineConfig,
):
    """Gate G3: L3 CITATION_GROUNDING must downgrade to WARN if evidence touches zero plan/event entities."""
    evt = DisruptionEvent(
        event_id="EVT_NO_MATCH_CIT",
        event_type=DisruptionEventType.HAZARD_PORT,
        status=EventStatus.NEW,
        primary_entity_id="PORT_VOC",
        affected_entity_ids=["PORT_VOC"],
        severity=0.75,
        estimated_duration_days=2.0,
        source_feed="TEST",
        raw_headline="Strike at Tuticorin Port",
        raw_text="Berth slowdown at VOC Port",
        timestamp=datetime(2026, 11, 10, tzinfo=timezone.utc),
    )
    s0 = PipelineState(
        session_id="SESS_WARN_CIT",
        status=PipelineStatus.PERCEIVED,
        event=evt,
        evidence_set=[],  # Explicitly zero evidence items
    )
    s_b, _ = StageBCorridorRisk(graph_store=graph_store, registry=registry).run(
        s0, pipeline_config, random.Random(42)
    )
    out_d, _ = StageDOptimiserAndVerifier(registry=registry, graph_store=graph_store).run(
        s_b, pipeline_config, random.Random(42)
    )
    assert out_d.verification_report is not None
    cit_checks = [c for c in out_d.verification_report.l3_checks if c.check_name == "CITATION_GROUNDING"]
    assert len(cit_checks) == 1
    assert cit_checks[0].verdict == VerificationVerdict.WARN

