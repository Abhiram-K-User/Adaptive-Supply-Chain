"""
Unit tests for Corridor Graph topology repairs and Stage B risk/mode calculations.
"""

import random
from datetime import UTC, datetime

from asci.core.contracts import PipelineConfig
from asci.core.registry import CanonicalEntityRegistry, EntityType, get_canonical_registry
from asci.core.state import (
    DisruptionEvent,
    DisruptionEventType,
    EventStatus,
    OperatorType,
    PipelineState,
    PipelineStatus,
)
from asci.stages import WalkingSkeletonPipeline
from asci.stages.stage_b_graph import StageBCorridorRisk
from asci.stages.stage_b_propagate import (
    Tier1PropagationSimulator,
    Tier2DynamicCongestionSimulator,
)
from asci.uskl import osmnx_builder as osmnx_mod
from asci.uskl.graph_store import CorridorGraphStore
from asci.uskl.osmnx_builder import CorridorOSMnxBuilder


def test_corridor_graph_connectivity_repaired(
    graph_store: CorridorGraphStore,
    registry: CanonicalEntityRegistry,
):
    """Verify repaired topology has no disconnected orphan or dead-end ICDs."""
    g = graph_store.graph
    for nid in registry.all_entities():
        assert g.in_degree(nid) + g.out_degree(nid) > 0, f"Isolated node: {nid}"

    # Previously broken terminals & junctions must have both inbound and outbound links
    assert g.out_degree("ICD_TONDIARPET") >= 2
    assert g.in_degree("JUNCTION_CHITTOOR") >= 1
    assert g.out_degree("JUNCTION_CHITTOOR") >= 1

    # Inbound Whitefield CONCOR -> Hosur last-mile route must exist in forward direction
    assert graph_store.has_active_edge("ICD_WHITEFIELD", "CFS_WHITEFIELD")
    assert graph_store.has_active_edge("CFS_WHITEFIELD", "PLANT_HOSUR")


def test_stage_b_rail_mode_and_non_constant_exposure(
    graph_store: CorridorGraphStore,
    registry: CanonicalEntityRegistry,
    pipeline_config: PipelineConfig,
):
    """Verify Stage B derives mode from edge attributes and computes varied exposures."""
    stage_b = StageBCorridorRisk(graph_store=graph_store, registry=registry)
    evt = DisruptionEvent(
        event_id="EVT_STAGEB_CHENNAI",
        event_type=DisruptionEventType.HAZARD_PORT,
        status=EventStatus.NEW,
        primary_entity_id="PORT_CHENNAI",
        affected_entity_ids=["PORT_CHENNAI", "CFS_CHENNAI_CENTRAL"],
        severity=0.80,
        estimated_duration_days=3.0,
        source_feed="TEST",
        raw_headline="Chennai cyclone alert",
        raw_text="Storm warning at Chennai Port",
        timestamp=datetime(2026, 11, 10, tzinfo=UTC),
    )
    state = PipelineState(session_id="SESS_B", status=PipelineStatus.PERCEIVED, event=evt)
    next_state, res = stage_b.run(state, pipeline_config, random.Random(42))

    assert res.success is True
    assert next_state.graph_context is not None
    metrics = next_state.graph_context.path_metrics

    # Exposure must not be collapsed to a single hardcoded constant like 0.04
    exposures = {m.exposure for m in metrics}
    assert len(exposures) > 2

    # Intermodal paths traversing CONCOR rail links must report INTERMODAL, never ROAD
    rail_paths = [
        m
        for m in metrics
        if m.path[:2] in (["PORT_CHENNAI", "ICD_WHITEFIELD"], ["PORT_VOC", "ICD_IRUGUR"], ["PORT_COCHIN", "ICD_IRUGUR"])
    ]
    assert len(rail_paths) >= 2
    assert all(m.mode == "INTERMODAL" for m in rail_paths)

    # Plant Coimbatore (fed via Cochin/VOC) should not suffer Ennore/Chennai delay when unimpacted
    line_stops = {ls.plant_id: ls for ls in next_state.graph_context.line_stop_metrics}
    assert line_stops["PLANT_COIMBATORE"].expected_delay_days == 0.0
    assert line_stops["PLANT_ORAGADAM"].expected_delay_days >= 0.0


def test_stage_b_vulnerability_factors_and_propagate_determinism(
    graph_store: CorridorGraphStore,
    registry: CanonicalEntityRegistry,
):
    """Verify PRD Sec. 5.2 Utilisation/Uncertainty/Concentration, LineStop prob, and Tier-1 PROPAGATE."""
    stage_b = StageBCorridorRisk(graph_store=graph_store, registry=registry)
    cfg = PipelineConfig(enable_propagation=True, k_hop_neighborhood=2, random_seed=42)

    high_conf_evt = DisruptionEvent(
        event_id="EVT_CONF_HIGH",
        event_type=DisruptionEventType.HAZARD_PORT,
        status=EventStatus.NEW,
        primary_entity_id="PORT_CHENNAI",
        affected_entity_ids=["PORT_CHENNAI"],
        severity=0.85,
        estimated_duration_days=4.5,
        source_feed="IMD",
        raw_headline="Bay storm at Chennai",
        raw_text="Severe storm surge at Chennai Port.",
        timestamp=datetime(2026, 11, 10, tzinfo=UTC),
        corroboration_count=3,
        confidence=0.95,
    )
    low_conf_evt = high_conf_evt.model_copy(
        update={"event_id": "EVT_CONF_LOW", "corroboration_count": 1, "confidence": 0.40}
    )

    s_high, _ = stage_b.run(
        PipelineState(session_id="S_HIGH", status=PipelineStatus.PERCEIVED, event=high_conf_evt),
        cfg,
        random.Random(42),
    )
    s_low, _ = stage_b.run(
        PipelineState(session_id="S_LOW", status=PipelineStatus.PERCEIVED, event=low_conf_evt),
        cfg,
        random.Random(42),
    )

    assert s_high.graph_context is not None and s_low.graph_context is not None
    assert s_high.graph_context.hop_decay_applied is True
    assert s_high.graph_context.propagated_node_delays_hrs["PORT_CHENNAI"] > 0.0
    assert (
        s_high.graph_context.propagated_node_delays_hrs["PORT_CHENNAI"]
        > s_high.graph_context.propagated_node_delays_hrs.get("CFS_CHENNAI_CENTRAL", 0.0)
    )

    # Low-confidence single-source alerts must increase uncertainty_factor & aggregate path risk
    uf_high = s_high.graph_context.path_metrics[0].uncertainty_factor
    uf_low = s_low.graph_context.path_metrics[0].uncertainty_factor
    assert uf_low > uf_high >= 1.0
    assert sum(m.path_risk for m in s_low.graph_context.path_metrics) > sum(
        m.path_risk for m in s_high.graph_context.path_metrics
    )

    # Concentration must be higher for single-corridor Coimbatore than multi-port Sriperumbudur
    conc_by_plant = {m.destination_id: m.concentration for m in s_high.graph_context.path_metrics}
    assert conc_by_plant["PLANT_COIMBATORE"] > conc_by_plant["PLANT_SRIPERUMBUDUR"]
    assert all(0.0 < m.utilisation <= 1.0 for m in s_high.graph_context.path_metrics)

    # Standalone PROPAGATE step preserves pipeline execution and increments trace cleanly
    prop_pipe = WalkingSkeletonPipeline(enable_propagate_step=True)
    cfg_no_inline_prop = PipelineConfig(enable_propagation=False, random_seed=42)
    s_prop, results_prop = prop_pipe.run(
        PipelineState(session_id="S_PROP", status=PipelineStatus.PERCEIVED, event=high_conf_evt),
        cfg_no_inline_prop,
        random.Random(42),
    )
    assert len(results_prop) == 6  # A (passthrough), B, PROPAGATE, C, D, E
    assert any(r.operator_type == OperatorType.PROPAGATE and r.success for r in results_prop)
    assert s_prop.graph_context is not None and s_prop.graph_context.hop_decay_applied is True

    # Calling Tier1PropagationSimulator directly again should be idempotent on multipliers
    sim = Tier1PropagationSimulator(graph_store=graph_store, registry=registry)
    s_idem, res_idem = sim.run(s_prop, cfg_no_inline_prop, random.Random(42))
    assert res_idem.success is True
    assert s_idem.graph_context == s_prop.graph_context


def test_tier2_dynamic_congestion_redistribution_and_idempotency(
    graph_store: CorridorGraphStore,
    registry: CanonicalEntityRegistry,
):
    """Verify Tier-2 PROPAGATE shifts displaced corridor flow, adds BPR dwell, and is idempotent."""
    evt = DisruptionEvent(
        event_id="EVT_TIER2_CONGESTION",
        event_type=DisruptionEventType.HAZARD_PORT,
        status=EventStatus.NEW,
        primary_entity_id="PORT_CHENNAI",
        affected_entity_ids=["PORT_CHENNAI", "PORT_KAMARAJAR"],
        severity=0.85,
        estimated_duration_days=4.0,
        source_feed="IMD",
        raw_headline="Compound Bay storm disrupts Chennai & Kamarajar ports",
        raw_text="Severe cyclonic storm diverts inland TEU freight toward southern corridors.",
        timestamp=datetime(2026, 11, 10, tzinfo=UTC),
    )
    stage_b = StageBCorridorRisk(graph_store=graph_store, registry=registry)
    s0 = PipelineState(session_id="S_T2_CMP", status=PipelineStatus.PERCEIVED, event=evt)

    cfg_t1 = PipelineConfig(enable_propagation=True, propagation_tier=1, random_seed=42)
    cfg_t2 = PipelineConfig(enable_propagation=True, propagation_tier=2, random_seed=42)

    s_t1, _ = stage_b.run(s0, cfg_t1, random.Random(42))
    s_t2, _ = stage_b.run(s0, cfg_t2, random.Random(42))

    assert s_t1.graph_context is not None and s_t2.graph_context is not None
    assert s_t1.graph_context.propagation_tier == 1
    assert s_t2.graph_context.propagation_tier == 2
    assert len(s_t2.graph_context.redistributed_edge_loads_teu) > 0
    assert len(s_t2.graph_context.edge_congestion_ratios) > 0
    # Tier-2 BPR dynamic dwell adds congestion spillover monotonically over Tier-1 baseline
    assert sum(s_t2.graph_context.propagated_node_delays_hrs.values()) >= sum(
        s_t1.graph_context.propagated_node_delays_hrs.values()
    )

    # Standalone Tier2DynamicCongestionSimulator step & idempotency
    pipe_t2 = WalkingSkeletonPipeline(enable_propagate_step=True)
    pipe_t2.propagate = Tier2DynamicCongestionSimulator(graph_store=graph_store, registry=registry)
    cfg_no_inline = PipelineConfig(enable_propagation=False, propagation_tier=2, random_seed=42)
    s_standalone, results = pipe_t2.run(s0, cfg_no_inline, random.Random(42))
    assert any(r.operator_type == OperatorType.PROPAGATE and r.success for r in results)
    assert s_standalone.graph_context is not None
    assert s_standalone.graph_context.propagation_tier == 2
    assert s_standalone.graph_context.hop_decay_applied is True
    assert len(s_standalone.graph_context.redistributed_edge_loads_teu) > 0

    s_idem, res_idem = pipe_t2.propagate.run(s_standalone, cfg_no_inline, random.Random(42))
    assert res_idem.success is True
    assert s_idem.graph_context == s_standalone.graph_context


def test_osmnx_builder_v1_corridor_topology_and_mock_calibration(monkeypatch):
    """Verify v1_corridor fulfills PRD 100-150 node / 300-500 edge scaling & OSMnx mock hook."""
    v0_reg = get_canonical_registry(network_scale="v0_core")
    v1_reg = get_canonical_registry(network_scale="v1_corridor")
    v1_gs = CorridorGraphStore.load_from_json(registry=v1_reg, network_scale="v1_corridor")

    assert len(v0_reg) == 23
    assert 100 <= len(v1_reg) <= 150
    assert 300 <= len(v1_gs.get_all_edges()) <= 500
    for eid in v0_reg.all_entities():
        assert v1_reg.validate_id(eid)

    outbound_nodes = [
        e for e in v1_reg.all_entities().values() if e.metadata.get("role") == "outbound_gateway"
    ]
    assert len(outbound_nodes) == 10

    for plant in v1_reg.get_by_type(EntityType.PLANT):
        assert v1_gs.graph.in_degree(plant.id) >= 2

    # Mock offline OSMnx fallback vs live OSMnx snapping
    _, links_payload = CorridorOSMnxBuilder.build_v1_payloads(use_osmnx=False)
    sample_links = links_payload["links"][:5]
    entities_map = {e.id: e.model_dump() for e in v1_reg.all_entities().values()}

    monkeypatch.setattr(osmnx_mod, "ox", None)
    uncal, used_live = CorridorOSMnxBuilder.calibrate_edges_with_osmnx(entities_map, sample_links)
    assert used_live is False
    assert uncal[0]["distance_km"] == sample_links[0]["distance_km"]

    class _FakeDist:
        @staticmethod
        def nearest_nodes(_g, lon, lat):
            return int(round((lat + lon) * 100))

    class _FakeOX:
        distance = _FakeDist()

        @staticmethod
        def graph_from_place(_place, network_type="drive"):
            return object()

        @staticmethod
        def shortest_path_length(_g, _n1, _n2, weight="length"):
            return 42500.0  # 42.5 km highway segment

    monkeypatch.setattr(osmnx_mod, "ox", _FakeOX())
    cal_links, used_live = CorridorOSMnxBuilder.calibrate_edges_with_osmnx(
        entities_map,
        [{"source": "PORT_CHENNAI", "target": "CFS_MANALI", "mode": "ROAD", "distance_km": 10.0, "transit_time_hrs": 1.0}],
    )
    assert used_live is True
    assert cal_links[0]["distance_km"] == 42.5
    assert cal_links[0]["transit_time_hrs"] == round(42.5 / 52.0, 2)

    # All 3 former v0 bottlenecks must clear with zero unmet demand on v1_corridor
    cfg_v1 = PipelineConfig(network_scale="v1_corridor", propagation_tier=2, random_seed=42)
    pipe_v1 = WalkingSkeletonPipeline.from_config(cfg_v1)
    for bottleneck_id in ("PORT_KRISHNAPATNAM", "ICD_WHITEFIELD", "ICD_IRUGUR"):
        evt = DisruptionEvent(
            event_id=f"EVT_V1_{bottleneck_id}",
            event_type=DisruptionEventType.HAZARD_PORT,
            status=EventStatus.NEW,
            primary_entity_id=bottleneck_id,
            affected_entity_ids=[bottleneck_id],
            severity=0.85,
            estimated_duration_days=3.0,
            source_feed="V1_BOTTLENECK_CHECK",
            raw_headline=f"Major outage at {bottleneck_id}",
            raw_text=f"Heavy congestion at {bottleneck_id}.",
            timestamp=datetime(2026, 11, 10, tzinfo=UTC),
        )
        s_fin, results = pipe_v1.run(
            PipelineState(session_id=f"S_V1_{bottleneck_id}", status=PipelineStatus.PERCEIVED, event=evt),
            cfg_v1,
            random.Random(42),
        )
        assert all(r.success for r in results)
        assert s_fin.status == PipelineStatus.COMPLETED
        assert s_fin.candidate_plan is not None
        assert s_fin.candidate_plan.unmet_demand_teu == 0.0
        assert s_fin.verification_report is not None and s_fin.verification_report.passed is True



