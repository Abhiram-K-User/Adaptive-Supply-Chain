"""
Comprehensive verification test for backend-to-frontend connection in ASCI.
Verifies that:
1. backend.app.main:app serves the built React frontend dist at GET /
2. Static assets are served correctly from /assets
3. REST API endpoints function end-to-end with USKL and Google OR-Tools / HiGHS
4. Decision loop L2 records operator approval
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Ensure root directory and src directory are in path
root_dir = Path(__file__).resolve().parent.parent
src_dir = root_dir / "src"
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from starlette.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402


def run_checks():
    client = TestClient(app)
    print("=" * 60)
    print("ASCI BACKEND-TO-FRONTEND CONNECTION VERIFICATION")
    print("=" * 60)

    # 1. Test frontend root serving
    res_root = client.get("/")
    assert res_root.status_code == 200, f"Expected 200 on /, got {res_root.status_code}"
    assert '<div id="root"></div>' in res_root.text or '<div id="root"' in res_root.text, "index.html missing root element"
    print(f"[OK] GET / -> 200 OK (Served React index.html, {len(res_root.text)} bytes)")

    # 2. Extract asset references and verify static serving
    asset_matches = re.findall(r'/assets/[a-zA-Z0-9_\-\.]+', res_root.text)
    assert len(asset_matches) >= 2, f"Expected at least CSS and JS assets, found: {asset_matches}"
    for asset_path in asset_matches:
        res_asset = client.get(asset_path)
        assert res_asset.status_code == 200, f"Failed to fetch asset {asset_path}: {res_asset.status_code}"
        print(f"[OK] GET {asset_path} -> 200 OK ({len(res_asset.content)} bytes)")

    # 3. Test API /health
    res_health = client.get("/health")
    assert res_health.status_code == 200, f"Health check failed: {res_health.status_code}"
    health_data = res_health.json()
    assert health_data["status"] == "healthy", f"Unhealthy status: {health_data}"
    print(f"[OK] GET /health -> 200 OK (Scale: {health_data['network_scale']}, Status: {health_data['status']})")

    # 4. Test API /registry
    res_reg = client.get("/registry")
    assert res_reg.status_code == 200
    reg_data = res_reg.json()
    assert len(reg_data) >= 20, f"Expected entities, got {len(reg_data)}"
    print(f"[OK] GET /registry -> 200 OK ({len(reg_data)} canonical entities registered)")

    # 5. Test API /network
    res_net = client.get("/network")
    assert res_net.status_code == 200
    net_data = res_net.json()
    assert len(net_data["edges"]) >= 40, f"Expected edges, got {len(net_data['edges'])}"
    print(f"[OK] GET /network -> 200 OK ({net_data['node_count']} nodes, {net_data['edge_count']} links)")

    # 6. Test Event Ingestion
    payload = {
        "raw_headline": "Severe Cyclone Michaung Near Ennore Maritime Hub",
        "raw_text": "High storm surge warning has halted ship movements at Kamarajar Port for 48 hours.",
        "source_feed": "VERIFICATION_TEST",
        "trust_tier": "TIER_A",
        "enable_llm": False,
    }
    res_event = client.post("/events", json=payload)
    assert res_event.status_code == 201, f"Event creation failed: {res_event.status_code} {res_event.text}"
    event_data = res_event.json()
    event_id = event_data["event_id"]
    print(f"[OK] POST /events -> 201 Created (ID: {event_id}, Primary Entity: {event_data['primary_entity_id']})")

    # 7. Test 5-Stage Optimization Planning
    res_plan = client.post(f"/events/{event_id}/plan", json={"risk_mode": "CVAR", "strict_citation_gate": False})
    assert res_plan.status_code == 200, f"Plan failed: {res_plan.status_code} {res_plan.text}"
    plan_data = res_plan.json()
    plan_id = plan_data["plan"]["plan_id"]
    verification = plan_data["verification"]
    session_id = plan_data["session_id"]
    print(f"[OK] POST /events/{event_id}/plan -> 200 OK")
    print(f"     Status: {plan_data['status']}, Dual-Solver Verification: {verification['overall_verdict']} (Passed: {verification['passed']})")
    print(f"     Allocated Flows: {len(plan_data['plan']['allocations'])}, Steps: {plan_data['step_count']}, Solver: {plan_data['plan']['solver_engine']}")

    # 8. Test Human Operator Decision Recording (Loop L2)
    res_decision = client.post(
        "/decisions",
        json={
            "plan_id": plan_id,
            "session_id": session_id,
            "decision": "APPROVE",
            "planner_id": "TEST_OPERATOR_SUITE",
            "comments": "Automated verification test sign-off.",
        },
    )
    assert res_decision.status_code == 201
    print("[OK] POST /decisions -> 201 Created (Recorded operator APPROVE into Decision Memory)")

    # 9. Test Operator Traces
    res_traces = client.get(f"/traces/{session_id}")
    assert res_traces.status_code == 200
    trace_data = res_traces.json()
    print(f"[OK] GET /traces/{session_id} -> 200 OK ({len(trace_data)} trace steps retrieved)")

    print("=" * 60)
    print("ALL 9 BACKEND-TO-FRONTEND CHECKS PASSED WITH 100% SUCCESS!")
    print("=" * 60)

if __name__ == "__main__":
    run_checks()
