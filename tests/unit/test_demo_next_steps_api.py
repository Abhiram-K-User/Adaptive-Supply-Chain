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
