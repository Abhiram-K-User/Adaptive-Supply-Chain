import pytest

from asci.benchmarks.suite_s2 import SuiteS2Runner


@pytest.mark.parametrize("scale", ["v0_core", "v1_corridor"])
def test_compound_timeline_retracts_and_recovers(scale):
    report = SuiteS2Runner().run_suite(days=8, cases=1, network_scale=scale)
    assert report["passed"], report["failures"]
    records = report["records"]
    assert [len(r["active_event_ids"]) for r in records] == [1, 2, 2, 1, 0, 1, 0, 0]
    assert [r["scenario_count"] for r in records] == [3, 9, 9, 3, 0, 3, 0, 0]
    weather_id = records[0]["active_event_ids"][0]
    assert records[3]["event_statuses"][weather_id] == "RETRACTED"
    assert records[5]["event_statuses"][weather_id] == "UPDATED"
    assert records[6]["event_statuses"][weather_id] == "EXPIRED"
    assert records[6]["expired_events"] == 1
    assert all(not records[day]["restricted_nodes"] for day in (4, 6, 7))
    assert records[6]["objective_cost"] == records[7]["objective_cost"]
    spec = report["case_definitions"][0]
    assert records[1]["remaining_duration_days"][weather_id] == spec["initial_duration_days"] - 1
    assert records[2]["remaining_duration_days"][weather_id] == spec["initial_duration_days"]
    assert records[5]["remaining_duration_days"][weather_id] == 1
    assert next(e["severity"] for e in records[2]["active_events"] if e["event_id"] == weather_id) == spec["escalated_severity"]
    assert records[5]["active_events"][0]["severity"] == spec["revised_severity"]
    # Both events' analyses remain represented in compound telemetry.
    assert records[1]["operators"].count("GRAPH_ANALYZE") == 2
    assert records[1]["compute_cost"] > records[0]["compute_cost"]
    assert all(r["reproducible"] for r in records)
    assert report["summary"]["execution_errors"] == 0
    assert all(all(r["checks"].values()) for r in records)
