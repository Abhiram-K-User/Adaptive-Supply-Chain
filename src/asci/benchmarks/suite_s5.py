"""Suite S5: replayable concurrent API episodes and the complete demo workflow."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from tempfile import TemporaryDirectory
from typing import Any

from fastapi.testclient import TestClient

from asci.api.main import create_app

SCENARIOS = (
    ("MICHAUNG", "PORT_KAMARAJAR", "HAZARD_PORT", "Severe cyclone at Kamarajar Port", 0.85),
    ("STRIKE", "PORT_KAMARAJAR", "PORT_CONGESTION_STRIKE", "Stevedore strike at Kamarajar Port", 0.65),
    ("RANIPET", "JUNCTION_RANIPET", "HAZARD_ROAD", "Ranipet highway flooding", 0.75),
)


def _checked(response):
    if not response.is_success:
        raise RuntimeError(f"{response.request.method} {response.request.url.path}: {response.status_code} {response.text}")
    return response.json()


def rehearse(client: TestClient, prefix: str = "S5") -> list[dict[str, Any]]:
    """Exercise the API operations backing all ten walkthrough steps and feedback loops."""
    ingested = []
    for name, entity, hazard, headline, severity in SCENARIOS:
        event = _checked(client.post("/events", json={
            "raw_headline": headline, "raw_text": headline + " for 4 days", "primary_entity_id": entity,
            "event_type": hazard, "severity": severity, "trust_tier": "TIER_A",
        }))
        ingested.append((name, event["event_id"]))

    def plan_episode(item):
        name, event_id = item
        return name, _checked(client.post(f"/events/{event_id}/plan", json={
            "risk_mode": "CVAR", "controller_mode": "rule_router", "enable_llm": False,
            "session_id": f"SESS_{prefix}_{name}_CONCURRENT",
        }))

    with ThreadPoolExecutor(max_workers=3) as executor:
        planned = list(executor.map(plan_episode, ingested))
    records = []
    for name, response in planned:
        if response["status"] != "COMPLETED" or not response["verification"]["passed"]:
            raise RuntimeError(f"{name} rehearsal failed: {response['verification']}")
        sid, event_id, plan_id = response["session_id"], response["event_id"], response["plan"]["plan_id"]
        trace = _checked(client.get(f"/traces/{sid}"))
        assert trace[-1]["operator_type"] == "STOP"
        assert len(trace) == len({t["step_index"] for t in trace})
        assert all(t["input_summary"] and t["output_summary"] for t in trace)
        assert _checked(client.get(f"/plans/{plan_id}"))["plan_id"] == plan_id
        for doc in response["dashboard"]["evidence_provenance"]:
            assert _checked(client.get(f"/evidence/{doc['citation_id']}"))["citation_id"] == doc["citation_id"]
        _checked(client.post("/decisions", json={"session_id": sid, "plan_id": plan_id,
                                                 "decision": "APPROVE", "planner_id": "rehearsal"}))
        _checked(client.post("/whatif", json={"event_id": event_id, "target_entity_id": "PORT_CHENNAI",
                                              "capacity_multiplier": 0.2, "duration_days": 5, "baseline_plan_id": plan_id}))
        _checked(client.post("/outcomes", params={"entity_id": "PORT_CHENNAI", "hazard_type": "HAZARD_PORT",
                                                "day_offset": 1, "observed_teu": 4500, "vessel_calls": 6}))
        _checked(client.post(f"/events/{event_id}/mitigate", json={"session_id": sid, "plan_id": plan_id}))
        assert _checked(client.get(f"/events/{event_id}"))["status"] == "MITIGATED"
        assert _checked(client.post(f"/events/{event_id}/reopen"))["status"] == "UPDATED"
        records.append({"scenario": name, "session_id": sid, "plan_id": plan_id,
                        "steps": len(trace), "passed": True})
    assert len(_checked(client.get("/decisions"))) >= 3
    return records


class SuiteS5Runner:
    def run_suite(self, network_scale: str = "v1_corridor") -> dict[str, Any]:
        with TemporaryDirectory(prefix="asci-s5-") as directory:
            with TestClient(create_app(data_dir=directory, network_scale=network_scale)) as client:
                records = rehearse(client)
            # Restart the API to prove trace persistence independent of the state cache.
            with TestClient(create_app(data_dir=directory, network_scale=network_scale)) as restarted:
                for row in records:
                    assert _checked(restarted.get(f"/traces/{row['session_id']}"))[-1]["operator_type"] == "STOP"
        return {"suite": "S5", "passed": True, "failures": [], "records": records}
