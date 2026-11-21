import hashlib
import json

import pytest

from asci.benchmarks.suite_s6 import HISTORICAL_PATH, SuiteS6Config, SuiteS6Runner, load_history


@pytest.mark.parametrize("scale", ["v0_core", "v1_corridor"])
def test_real_history_is_replayed_without_future_observation_leakage(scale):
    report = SuiteS6Runner().run_suite(scale)
    assert report["passed"], report["failures"]
    assert len(report["records"]) == 26
    assert {p["entity_id"] for p in report["ports"]} == {"PORT_CHENNAI", "PORT_KAMARAJAR"}
    assert all(p["observations"] == 13 and -1 <= p["spearman_rho"] <= 1 for p in report["ports"])
    assert report["source_url"].startswith("https://services9.arcgis.com/")
    assert all(not r["l1_l2_breaches"] for r in report["records"])


def test_history_rejects_tampering_duplicates_and_nonfinite_calls(tmp_path):
    data = load_history()
    target = tmp_path / "history.json"
    data["features"][0]["attributes"]["portcalls"] += 1
    target.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        load_history(target)
    data["features"].append(data["features"][0])
    data["observations_sha256"] = hashlib.sha256(json.dumps(data["features"], sort_keys=True).encode()).hexdigest()
    target.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="observation"):
        load_history(target)
    data = load_history()
    data["features"][0]["attributes"]["portcalls"] = float("nan")
    data["observations_sha256"] = hashlib.sha256(json.dumps(data["features"], sort_keys=True).encode()).hexdigest()
    target.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="observation"):
        load_history(target)


def test_forecast_uses_baseline_only_and_configured_assumptions(tmp_path):
    config = SuiteS6Config(forecast_end="2023-12-03", initial_capacity_ratio=0.25)
    first = SuiteS6Runner().run_suite("v0_core", config=config)
    data = json.loads(HISTORICAL_PATH.read_text(encoding="utf-8"))
    for feature in data["features"]:
        if feature["attributes"]["date"][:10] >= "2023-12-03":
            feature["attributes"]["portcalls"] = 100
    data["observations_sha256"] = hashlib.sha256(json.dumps(data["features"], sort_keys=True).encode()).hexdigest()
    path = tmp_path / "altered.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    second = SuiteS6Runner().run_suite("v0_core", path, config)
    assert [r["predicted_capacity_ratio"] for r in first["records"]] == [0.25, 0.25]
    assert [r["predicted_capacity_ratio"] for r in second["records"]] == [0.25, 0.25]
    assert first["mean_absolute_error"] != second["mean_absolute_error"]
    assert [r["baseline_calls"] for r in first["records"]] == [r["baseline_calls"] for r in second["records"]]
