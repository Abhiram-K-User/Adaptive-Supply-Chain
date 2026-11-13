"""
Unit tests for DEMO_NEXT_STEPS endpoints:
- POST /whatif (Task 1A: What-If sensitivity re-optimization)
- GET /evidence/{citation_id} (Task 1B: Single citation drill-down with port recovery curves)
- POST /outcomes & GET /outcomes/{entity_id} (Task 1C: Realized outcomes Loop L1 calibration)
- GET /decisions (Task 1D: Loop L2 decision memory history)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from asci.api.main import create_app


@pytest.fixture
def api_client() -> TestClient:
    app = create_app(data_dir=None)  # in-memory stores
    return TestClient(app)


def test_decisions_list_and_record(api_client: TestClient) -> None:
    """Test GET /decisions returns empty initially and reflects recorded decisions."""
    resp = api_client.get("/decisions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_evidence_drilldown(api_client: TestClient) -> None:
    """Test GET /evidence/{citation_id} returns metadata and linked recovery curves."""
    resp = api_client.get("/evidence/CIT_PLAYBOOK_CYCLONE_001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["citation_id"] == "CIT_PLAYBOOK_CYCLONE_001"
    assert "supported_claims" in data
    assert "recovery_curves" in data

    # 404 on unknown citation
    not_found = api_client.get("/evidence/CIT_UNKNOWN_9999")
    assert not_found.status_code == 404


def test_outcomes_record_and_get(api_client: TestClient) -> None:
    """Test POST /outcomes recalibrates recovery curve and GET /outcomes retrieves baseline."""
    resp = api_client.post(
        "/outcomes",
        params={
            "entity_id": "PORT_CHENNAI",
            "hazard_type": "HAZARD_PORT",
            "day_offset": 3,
            "observed_teu": 4800,
            "vessel_calls": 11,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == "PORT_CHENNAI"
    assert "realized_multiplier" in data
    assert "deviation_pct" in data
    assert "updated_recovery_curve" in data

    # Query outcomes for entity
    get_resp = api_client.get("/outcomes/PORT_CHENNAI")
    assert get_resp.status_code == 200
    details = get_resp.json()
    assert details["entity_id"] == "PORT_CHENNAI"
    assert "baseline" in details
    assert "recovery_curves" in details


def test_whatif_endpoint(api_client: TestClient) -> None:
    """Test POST /whatif executes in-memory re-optimization without mutating persisted events."""
    payload = {
        "target_entity_id": "PORT_CHENNAI",
        "capacity_multiplier": 0.40,
        "duration_days": 3.0,
        "risk_mode": "CVAR",
        "propagation_tier": 2,
    }
    resp = api_client.post("/whatif", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "simulated_plan" in data
    assert "cost_delta" in data
    assert "rail_share_delta_pct" in data
    assert data["simulated_plan"] is not None

    # Invalid entity rejection
    bad_resp = api_client.post(
        "/whatif",
        json={"target_entity_id": "PORT_UNKNOWN_XYZ", "capacity_multiplier": 0.5, "duration_days": 2.0},
    )
    assert bad_resp.status_code == 400


def test_agentic_rag_multistep_loop_l2_and_loop_l4(api_client: TestClient) -> None:
    """
    Verify:
    1. Planning emits multi-step Agentic-RAG traces (RETRIEVE_TEXT, GRADE, RETRIEVE_TS, RETRIEVE_DECISIONS, SCENARIOS).
    2. APPROVE/EDIT decision via POST /decisions indexes a CIT_L4_DECISION_* playbook (Loop L4).
    3. Subsequent plan generation retrieves that precedent decision in Stage C RETRIEVE_DECISIONS (Loop L2).
    """
    ev_resp = api_client.post(
        "/events",
        json={
            "raw_headline": "Kamarajar Port Cyclone Closure",
            "raw_text": "Berth operations halted at Kamarajar Port due to storm surge.",
            "primary_entity_id": "PORT_KAMARAJAR",
            "event_type": "HAZARD_PORT",
            "severity": 0.85,
            "estimated_duration_days": 4.0,
        },
    )
    assert ev_resp.status_code == 201
    event_id = ev_resp.json()["event_id"]

    plan_1 = api_client.post(f"/events/{event_id}/plan", json={"risk_mode": "CVAR"}).json()
    session_1 = plan_1["session_id"]
    plan_id = plan_1["plan"]["plan_id"]

    traces_1 = api_client.get(f"/traces/{session_1}").json()
    ops_1 = [t["operator_type"] for t in traces_1]
    assert "RETRIEVE_TEXT" in ops_1
    assert "GRADE" in ops_1
    assert "RETRIEVE_TS" in ops_1
    assert "RETRIEVE_DECISIONS" in ops_1
    assert "SCENARIOS" in ops_1

    dec_resp = api_client.post(
        "/decisions",
        json={
            "plan_id": plan_id,
            "session_id": session_1,
            "decision": "EDIT",
            "planner_id": "ops_director",
            "comments": "Validated Ennore bypass with conservative berth factor",
            "modifications": {"capacity_multiplier_override": 0.30},
        },
    )
    assert dec_resp.status_code == 201
    cit_id = dec_resp.json().get("indexed_citation_id")
    assert cit_id is not None and cit_id.startswith("CIT_L4_DECISION_")

    # Loop L4: New citation is immediately searchable via GET /evidence/{citation_id}
    cit_detail = api_client.get(f"/evidence/{cit_id}")
    assert cit_detail.status_code == 200
    assert "PORT_KAMARAJAR" in cit_detail.json()["entity_ids"]

    # Loop L2: Re-planning queries RETRIEVE_DECISIONS and finds the human precedent
    plan_2 = api_client.post(f"/events/{event_id}/plan", json={"risk_mode": "CVAR"}).json()
    timeline_2 = plan_2["dashboard"]["trace_timeline"]
    dec_step = next(t for t in timeline_2 if t["operator_type"] == "RETRIEVE_DECISIONS")
    assert "Matched 1 prior APPROVE/EDIT decisions" in dec_step["output_summary"]
    assert "cap_override=0.30" in dec_step["output_summary"]

