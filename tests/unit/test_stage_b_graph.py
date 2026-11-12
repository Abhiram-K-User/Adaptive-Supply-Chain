"""
Unit tests for Corridor Graph topology repairs and Stage B risk/mode calculations.
"""

import random
from datetime import datetime, timezone

from asci.core.contracts import PipelineConfig
from asci.core.registry import CanonicalEntityRegistry
from asci.core.state import (
    DisruptionEvent,
    DisruptionEventType,
    EventStatus,
    PipelineState,
    PipelineStatus,
)
from asci.stages.stage_b_graph import StageBCorridorRisk
from asci.uskl.graph_store import CorridorGraphStore


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
        timestamp=datetime(2026, 11, 10, tzinfo=timezone.utc),
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

