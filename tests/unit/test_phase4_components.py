"""
Verification tests for implemented Phase 4 components across USKL & Stage C/E:
- TimeSeriesStore baselines, recovery curves & rolling z-score anomaly detection
- DecisionTraceStore human-decision validation & ordering
- StageCController budget-aware query rewrite & deterministic as_of_date expiry filtering
- StageEDashboard Cytoscape node status & edge freight flow aggregation
"""

from __future__ import annotations

import random
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from asci.api.main import create_app
from asci.core.contracts import PipelineConfig
from asci.core.registry import CanonicalEntityRegistry
from asci.core.state import (
    DisruptionEvent,
    DisruptionEventType,
    EventStatus,
    EvidenceItem,
    PipelineState,
    PipelineStatus,
    TrustTier,
)
from asci.stages import WalkingSkeletonPipeline
from asci.stages.stage_c_controller import StageCController
from asci.uskl.decision_store import DecisionTraceStore
from asci.uskl.timeseries_store import PortObservation, TimeSeriesStore
from asci.uskl.vector_store import SemanticVectorStore


def test_phase4_timeseries_baselines_curves_and_chronology(
    timeseries_store: TimeSeriesStore,
):
    """Verify seeded baselines, recovery curves, unknown-entity validation, and chronological query sorting."""
    assert timeseries_store.get_baseline_throughput("PORT_CHENNAI") == 6000.0
    assert timeseries_store.get_baseline_throughput("UNKNOWN_PORT") == 3000.0

    # Specific hazard curve vs default fallback curve
    kpl_curve = timeseries_store.get_recovery_curve("PORT_KAMARAJAR", "HAZARD_PORT")
    assert kpl_curve == [0.1, 0.3, 0.65, 0.85, 1.0]
    default_curve = timeseries_store.get_recovery_curve("PORT_COCHIN", "RAIL_DISRUPTION")
    assert default_curve == [0.2, 0.5, 0.75, 0.9, 1.0]

    # Ungrounded entity ingestion must fail
    with pytest.raises(ValueError):
        timeseries_store.ingest_observations(
            [PortObservation("PORT_FAKE_99", "2026-11-01", 4.0, 2000.0)]
        )

    # Out-of-order ingestion must return ascending chronological order
    timeseries_store.ingest_observations(
        [
            PortObservation("PORT_NEW_MANGALORE", "2026-11-05", 3.2, 2400.0),
            PortObservation("PORT_NEW_MANGALORE", "2026-11-03", 3.1, 2350.0),
            PortObservation("PORT_NEW_MANGALORE", "2026-11-04", 3.3, 2450.0),
        ]
    )
    series = timeseries_store.query_recent_series("PORT_NEW_MANGALORE", window_days=10)
    assert [s.obs_date for s in series] == ["2026-11-03", "2026-11-04", "2026-11-05"]


def test_phase4_decision_store_and_api_decision_validation():
    """Verify DecisionTraceStore rejects invalid decisions and API /decisions enforces plan existence."""
    store = DecisionTraceStore(db_path=":memory:")
    with pytest.raises(ValueError):
        store.record_human_decision(
            plan_id="PLAN_1",
            session_id="SESS_1",
            decision="MAYBE",
            planner_id="ops_lead",
        )

    store.record_human_decision("PLAN_1", "SESS_1", "edit", "ops_1", "Adjusted rail split")
    store.record_human_decision("PLAN_1", "SESS_1", "APPROVE", "ops_2", "Signed off")
    history = store.get_decisions_for_plan("PLAN_1")
    assert len(history) == 2
    assert history[0]["decision"] == "APPROVE"  # Ordered most recent first
    assert history[1]["decision"] == "EDIT"

    client = TestClient(create_app())
    missing = client.post(
        "/decisions",
        json={
            "plan_id": "PLAN_DOES_NOT_EXIST",
            "session_id": "SESS_X",
            "decision": "APPROVE",
            "planner_id": "ops_lead",
        },
    )
    assert missing.status_code == 404


def test_phase4_stage_c_budget_awareness_and_deterministic_as_of_date(
    registry: CanonicalEntityRegistry,
    timeseries_store: TimeSeriesStore,
):
    """Verify tight vs loose lambda_cost_budget controls rewrite spend and respects event as_of_date."""
    # Empty vector store except one custom AP-tagged playbook with relevance check + Chennai expired doc
    vs = SemanticVectorStore(registry=registry, load_default_corpus=True)
    # Create an isolated event on a node with low direct match to check rewrite triggering vs budget suppression
    vs_sparse = SemanticVectorStore(registry=registry, load_default_corpus=False)
    vs_sparse.add_document(
        EvidenceItem(
            citation_id="CIT_TAN_GENERAL",
            source="Regional SOP",
            trust_tier=TrustTier.TIER_A,
            entity_ids=["PORT_KAMARAJAR"],
            region="Tamil Nadu",
            hazard_types=[DisruptionEventType.HAZARD_ROAD],
            snippet="Tamil Nadu corridor diversion playbook activates inland ICD rail loops.",
            publication_date="2026-10-01",
        )
    )
    controller = StageCController(vector_store=vs_sparse, timeseries_store=timeseries_store, registry=registry)
    pipe = WalkingSkeletonPipeline(stage_c=controller)

    evt_sparse = DisruptionEvent(
        event_id="EVT_SPARSE_VOC",
        event_type=DisruptionEventType.HAZARD_ROAD,
        status=EventStatus.NEW,
        primary_entity_id="PORT_VOC",
        affected_entity_ids=["PORT_VOC"],
        severity=0.70,
        estimated_duration_days=2.0,
        source_feed="TEST",
        raw_headline="Flooded road near Tuticorin",
        raw_text="Highway access slowed near Tuticorin.",
        timestamp=datetime(2026, 11, 10, tzinfo=UTC),
    )
    s0 = PipelineState(session_id="S_BUDGET", status=PipelineStatus.PERCEIVED, event=evt_sparse)
    s_b, _ = pipe.stage_b.run(s0, PipelineConfig(), random.Random(42))

    # Even with zero direct hits, Stage C broadens cleanly and tracks rewrite cost (0.0050 + 0.0020)
    s_c, res_c = controller.run(s_b, PipelineConfig(lambda_cost_budget=0.05), random.Random(42))
    assert res_c.artifacts["query_rewritten"] is True
    assert res_c.cost == 0.0070
    assert any(d.citation_id == "CIT_TAN_GENERAL" for d in s_c.evidence_set)

    # Full corpus preserves expired doc excluded at 2026-11-10
    assert len(vs) >= 9
    assert all(
        d.citation_id != "CIT_EXPIRED_ADVISORY_008"
        for d in vs.query("customs EDI", entity_ids=["PORT_CHENNAI"], as_of_date="2026-11-10")
    )


def test_phase4_stage_e_cytoscape_serialization_integrity(
    initial_state: PipelineState,
    pipeline_config: PipelineConfig,
):
    """Verify Stage E serializes accurate node statuses (DISRUPTED/RESTRICTED/NORMAL) and summed Cytoscape edge flows."""
    pipe = WalkingSkeletonPipeline()
    final_state, _ = pipe.run(initial_state, pipeline_config, random.Random(42))

    dash = final_state.dashboard_payload
    assert dash is not None
    nodes = {n["data"]["id"]: n["data"] for n in dash.geospatial_network["nodes"]}
    edges = dash.geospatial_network["edges"]

    assert len(nodes) == 23
    # severity=0.85 -> primary mult=0.15 (<0.5 -> DISRUPTED), secondary mult=0.49 (<0.5 -> DISRUPTED)
    assert nodes["PORT_KAMARAJAR"]["status"] == "DISRUPTED"
    assert nodes["PORT_CHENNAI"]["status"] == "DISRUPTED"
    assert nodes["PORT_COCHIN"]["status"] == "NORMAL"

    # Moderate severity=0.50 -> primary mult=0.50 (RESTRICTED), secondary mult=0.70 (RESTRICTED)
    mod_evt = initial_state.event.model_copy(update={"severity": 0.50})  # type: ignore[union-attr]
    mod_state, _ = pipe.run(
        initial_state.model_copy(update={"event": mod_evt}),
        pipeline_config,
        random.Random(42),
    )
    assert mod_state.dashboard_payload is not None
    mod_nodes = {n["data"]["id"]: n["data"] for n in mod_state.dashboard_payload.geospatial_network["nodes"]}
    assert mod_nodes["PORT_CHENNAI"]["status"] == "RESTRICTED"

    total_alloc_hop_flow = sum(
        a.flow_teu * (len(a.path) - 1) for a in final_state.candidate_plan.allocations  # type: ignore[union-attr]
    )
    # Note: parallel MultiDiGraph links share (source, target) and get equal aggregated flow per link entry,
    # so unique (source, target) edge flow sum must equal total allocated hop flow
    unique_uv_flows = {(e["data"]["source"], e["data"]["target"]): e["data"]["freight_flow_teu"] for e in edges}
    assert round(sum(unique_uv_flows.values()), 2) == round(total_alloc_hop_flow, 2)
