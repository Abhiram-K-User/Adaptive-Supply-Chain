"""
Verification suites for Gate G0 (Data Readiness & Adapter Fallbacks)
and Gate G1 (Operator Contracts, Trace Integrity, Determinism & API Error Paths).
"""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from asci.api.main import create_app
from asci.core.contracts import PipelineConfig
from asci.core.registry import CanonicalEntityRegistry, EntityType
from asci.core.state import (
    DisruptionEventType,
    OperatorType,
    PipelineState,
    PipelineStatus,
    RawSignal,
    TrustTier,
)
from asci.ingestion import (
    GDACSAdapter,
    GDELTRSSAdapter,
    IMDWeatherAdapter,
    PortWatchAnomalyDetector,
)
from asci.stages import WalkingSkeletonPipeline
from asci.stages.stage_a_events import StageAEventPerception
from asci.stages.stage_c_controller import StageCController
from asci.uskl.graph_store import CorridorGraphStore
from asci.uskl.timeseries_store import TimeSeriesStore


def test_gate_g0_canonical_seeds_and_graph_integrity(
    registry: CanonicalEntityRegistry,
    graph_store: CorridorGraphStore,
):
    """Gate G0: Verify exact corridor seed dimensions and edge attribute sanity."""
    ports = registry.get_by_type(EntityType.PORT)
    plants = registry.get_by_type(EntityType.PLANT)
    icds = registry.get_by_type(EntityType.ICD)
    cfss = registry.get_by_type(EntityType.CFS)
    junctions = registry.get_by_type(EntityType.CORRIDOR_JUNCTION)

    assert len(registry) == 23
    assert len(ports) == 7
    assert len(plants) == 6
    assert len(icds) == 3
    assert len(cfss) == 3
    assert len(junctions) == 4

    assert sum(p.capacity_teu_per_day or 0.0 for p in ports) == 27000.0
    assert sum(p.daily_demand_teu or 0.0 for p in plants) == 5300.0

    for u, v, attrs in graph_store.get_all_edges():
        assert registry.validate_id(u)
        assert registry.validate_id(v)
        assert float(attrs["capacity_teu_per_day"]) > 0.0
        assert float(attrs["base_cost_per_teu"]) > 0.0
        assert float(attrs["transit_time_hrs"]) > 0.0
        assert attrs["mode"] in ("ROAD", "RAIL")


def test_gate_g0_live_adapter_http_errors_fall_back_gracefully(monkeypatch, registry: CanonicalEntityRegistry):
    """Gate G0: HTTP timeouts/errors in GDACS & GDELT live mode must seamlessly trigger replay fallback."""

    def _fail_get(*args, **kwargs):
        raise httpx.ConnectError("Simulated offline environment")

    monkeypatch.setattr(httpx, "get", _fail_get)

    gdacs_sigs = GDACSAdapter().fetch(use_fallback=False)
    gdelt_sigs = GDELTRSSAdapter(registry=registry).fetch(use_fallback=False)
    imd_sigs = IMDWeatherAdapter().fetch(use_fallback=False)
    pw_sigs = PortWatchAnomalyDetector(
        timeseries_store=TimeSeriesStore(db_path=":memory:", registry=registry),
        registry=registry,
    ).fetch(use_fallback=False)

    assert len(gdacs_sigs) >= 1
    assert len(gdelt_sigs) >= 1
    assert len(imd_sigs) >= 1
    assert len(pw_sigs) >= 1


def test_gate_g1_stage_a_unresolvable_signal_fails_cleanly(
    registry: CanonicalEntityRegistry,
    pipeline_config: PipelineConfig,
):
    """Gate G1: Signal referencing zero corridor entities fails Stage A cleanly without crashing pipeline."""
    sig = RawSignal(
        signal_id="SIG_NOWHERE",
        source_feed="TEST",
        trust_tier=TrustTier.TIER_C,
        raw_headline="Port strike in Rotterdam freezes North Sea freight",
        raw_text="Unrelated European disruption far from South India.",
    )
    s0 = PipelineState(session_id="SESS_NOWHERE", status=PipelineStatus.INITIALIZED, raw_signal=sig)
    pipe = WalkingSkeletonPipeline(stage_a=StageAEventPerception(registry=registry))

    final_state, results = pipe.run(s0, pipeline_config, random.Random(42))
    assert len(results) == 1
    assert results[0].operator_type == OperatorType.STAGE_A_PERCEPTION
    assert results[0].success is False
    assert "grounding failure" in (results[0].error or "").lower()
    assert final_state.event is None


def test_gate_g1_step_budget_exhaustion_triggers_escalate_status(
    initial_state: PipelineState,
    pipeline_config: PipelineConfig,
    registry: CanonicalEntityRegistry,
):
    """Gate G1 / Sec 6.3: Reaching max_steps triggers ESCALATE and preserves ESCALATED status in Stage E."""
    pipe = WalkingSkeletonPipeline()
    s_b, _ = pipe.stage_b.run(initial_state, pipeline_config, random.Random(42))
    budget_hit = s_b.model_copy(update={"step_count": pipeline_config.max_steps})

    esc_state, res_c = StageCController(registry=registry).run(
        budget_hit, pipeline_config, random.Random(42)
    )
    assert res_c.success is False
    assert res_c.operator_type == OperatorType.ESCALATE
    assert res_c.error == "STEP_BUDGET_EXHAUSTED"
    assert esc_state.status == PipelineStatus.ESCALATED

    out_e, res_e = pipe.stage_e.run(esc_state, pipeline_config, random.Random(42))
    assert out_e.status == PipelineStatus.ESCALATED
    assert res_e.success is False


def test_gate_g1_api_validation_dual_plan_noncollision_and_jsonl_traces(tmp_path: Path):
    """
    Gate G1: Verify HTTP 400/422 validation, distinct plan_ids on back-to-back calls within 1s,
    and append-only traces.jsonl integrity under ASCI_DATA_DIR.
    """
    client = TestClient(create_app(data_dir=tmp_path))

    # Bad hint entity -> 400
    bad_hint = client.post(
        "/events",
        json={
            "raw_headline": "Storm alert",
            "raw_text": "Weather alert",
            "primary_entity_id": "PORT_NOT_REAL",
        },
    )
    assert bad_hint.status_code == 400

    # Unresolvable body without hint -> 422
    unresolvable = client.post(
        "/events",
        json={
            "raw_headline": "Snowstorm in Oslo",
            "raw_text": "No Indian corridor entities mentioned.",
        },
    )
    assert unresolvable.status_code == 422

    evt = client.post(
        "/events",
        json={
            "raw_headline": "Cyclone hits Kamarajar Port",
            "raw_text": "Ennore berth operations halted due to gale winds.",
            "primary_entity_id": "PORT_KAMARAJAR",
            "event_type": DisruptionEventType.HAZARD_PORT.value,
            "severity": 0.85,
            "published_at": datetime(2026, 11, 10, tzinfo=UTC).isoformat(),
        },
    ).json()

    # Back-to-back planning within same second must keep both plans distinct in SQLite
    p1 = client.post(f"/events/{evt['event_id']}/plan", json={"lambda_cost_budget": 0.02}).json()
    p2 = client.post(f"/events/{evt['event_id']}/plan", json={"lambda_cost_budget": 0.50}).json()

    assert p1["plan"]["plan_id"] != p2["plan"]["plan_id"]
    assert client.get(f"/plans/{p1['plan']['plan_id']}").status_code == 200
    assert client.get(f"/plans/{p2['plan']['plan_id']}").status_code == 200

    trace_file = tmp_path / "traces.jsonl"
    assert trace_file.exists()
    lines = [json.loads(line) for line in trace_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == p1["step_count"] + p2["step_count"]
    assert len(lines) >= 18  # >= 9 multi-step Agentic-RAG steps x 2 sessions
    assert {row["session_id"] for row in lines} == {p1["session_id"], p2["session_id"]}

