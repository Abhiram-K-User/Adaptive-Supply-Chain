from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from asci.benchmarks.common import event_fixture, write_report
from asci.benchmarks.suite_s2 import (
    SuiteS2Case,
    SuiteS2Runner,
    combine_scenarios,
    generate_cases,
    numerical_fingerprint,
    run_compound,
)
from asci.core.contracts import PipelineConfig
from asci.core.registry import get_canonical_registry
from asci.core.state import EventStatus, Scenario
from asci.stages import WalkingSkeletonPipeline


@pytest.fixture(scope="module")
def cli():
    path = Path(__file__).resolve().parents[2] / "scripts/run_suite_s2.py"
    spec = importlib.util.spec_from_file_location("run_suite_s2", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run_cli


@pytest.fixture(scope="module")
def pipe():
    instance = WalkingSkeletonPipeline.from_config(PipelineConfig())
    yield instance
    instance.stage_c.timeseries_store._conn.close()
    instance.stage_c.decision_store._conn.close()


def test_case_generation_is_varied_grounded_and_seeded():
    registry = get_canonical_registry(network_scale="v1_corridor")
    cases = generate_cases(registry, 10, seed=42)
    assert cases == generate_cases(registry, 10, seed=42)
    assert cases != generate_cases(registry, 10, seed=43)
    assert len({(c.weather_entity_id, c.road_entity_id) for c in cases}) == 10
    assert len({c.weather_severity for c in cases}) > 1
    for case in cases:
        assert registry.validate_id(case.weather_entity_id)
        assert registry.validate_id(case.road_entity_id)


def test_joint_scenarios_preserve_independent_probabilities_and_overlaps():
    def branch(name, probability, capacities, duration):
        return Scenario(scenario_id=name, name=name, probability=probability,
                        capacity_multipliers=capacities, duration_days=duration)

    groups = [
        [branch("A", 0.2, {"PORT_CHENNAI": 0.8}, 2), branch("B", 0.8, {"PORT_CHENNAI": 0.3}, 4)],
        [branch("C", 0.6, {"PORT_CHENNAI": 0.5, "JUNCTION_RANIPET": 0.7}, 3),
         branch("D", 0.4, {"JUNCTION_RANIPET": 0.2}, 1)],
    ]
    combined = combine_scenarios(groups)
    assert [s.probability for s in combined] == pytest.approx([0.12, 0.08, 0.48, 0.32])
    assert sum(s.probability for s in combined) == pytest.approx(1)
    assert combined[0].capacity_multipliers == {"PORT_CHENNAI": 0.5, "JUNCTION_RANIPET": 0.7}
    assert combined[0].duration_days == 3
    assert combined[-1].duration_days == 4
    with pytest.raises(ValueError, match="scenario count"):
        combine_scenarios(groups, max_scenarios=3)
    with pytest.raises(ValueError, match="scenario count"):
        combine_scenarios([[]])
    with pytest.raises(ValueError, match="Invalid scenario capacity"):
        combine_scenarios([[branch("BAD", 1, {"PORT_CHENNAI": float("nan")}, 1)]])


def test_compound_is_order_independent_and_fingerprint_detects_numerical_change(pipe):
    events = [event_fixture("PORT_CHENNAI", case_id="WEATHER"),
              event_fixture("JUNCTION_RANIPET", case_id="ROAD", severity=0.6)]
    first = run_compound(pipe, events, PipelineConfig(), "S2_ORDER")
    second = run_compound(pipe, list(reversed(events)), PipelineConfig(), "S2_ORDER")
    assert numerical_fingerprint(first) == numerical_fingerprint(second)
    changed = first.model_copy(update={"candidate_plan": first.candidate_plan.model_copy(update={
        "objective_cost": first.candidate_plan.objective_cost + 1,
    })})
    assert changed.candidate_plan.plan_id == first.candidate_plan.plan_id
    assert numerical_fingerprint(changed) != numerical_fingerprint(first)
    audit_only = first.model_copy(update={"candidate_plan": first.candidate_plan.model_copy(update={
        "timestamp": first.candidate_plan.timestamp + timedelta(seconds=1),
    })})
    assert numerical_fingerprint(audit_only) == numerical_fingerprint(first)


def test_compound_rejects_inactive_or_duplicate_events(pipe):
    event = event_fixture()
    with pytest.raises(ValueError, match="duplicate"):
        run_compound(pipe, [event, event], PipelineConfig(), "S2_DUPLICATE")
    with pytest.raises(ValueError, match="active"):
        run_compound(pipe, [event.model_copy(update={"status": EventStatus.RETRACTED})], PipelineConfig(), "S2_STALE")


@pytest.mark.parametrize("kwargs", [
    {"days": 6}, {"cases": 0}, {"start": datetime(2026, 11, 1)}, {"max_joint_scenarios": 8},
    {"network_scale": "invalid"}, {"pipeline_config": PipelineConfig(enable_llm=True)},
])
def test_invalid_run_parameters_fail_before_execution(kwargs):
    with pytest.raises(ValueError):
        SuiteS2Runner().run_suite(**kwargs)


def test_cli_exports_custom_case_and_returns_failure_for_controller_exhaustion(cli, tmp_path):
    case = generate_cases(get_canonical_registry(), 1, seed=42)[0]
    case_file = tmp_path / "cases.json"
    case_file.write_text(json.dumps([case.model_dump()]), encoding="utf-8")
    output = tmp_path / "result.json"
    args = ["--scale", "v0_core", "--case-file", str(case_file), "--output", str(output)]
    assert cli(args) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["passed"]
    assert report["reports"]["v0_core"]["case_definitions"] == [case.model_dump()]
    assert report["reports"]["v0_core"]["summary"]["total_snapshots"] == 7
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"max_steps": 1}), encoding="utf-8")
    assert cli([*args, "--pipeline-config", str(config_file)]) == 1
    failed = json.loads(output.read_text(encoding="utf-8"))
    assert not failed["passed"]
    assert failed["reports"]["v0_core"]["summary"]["execution_errors"] > 0
    assert failed["failures"]


def test_cli_rejects_bad_configuration_and_case_ids(cli, tmp_path):
    output = tmp_path / "result.json"
    assert cli(["--days", "6", "--output", str(output)]) == 2
    assert not output.exists()
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"unknown_setting": 42}', encoding="utf-8")
    assert cli(["--pipeline-config", str(invalid)]) == 2
    case = generate_cases(get_canonical_registry(), 1, seed=42)[0]
    invalid.write_text(json.dumps([{**case.model_dump(), "road_entity_id": "PORT_FAKE"}]), encoding="utf-8")
    assert cli(["--case-file", str(invalid), "--scale", "v0_core"]) == 2
    with pytest.raises(ValueError, match="revised_severity"):
        SuiteS2Case.model_validate({**case.model_dump(), "revised_severity": 1})


def test_report_serialization_preserves_previous_file_on_failure(tmp_path):
    output = tmp_path / "report.json"
    write_report(output, {"passed": True})
    with pytest.raises(ValueError):
        write_report(output, {"result": float("nan")})
    assert json.loads(output.read_text(encoding="utf-8")) == {"passed": True}
    assert not list(tmp_path.glob("*.tmp"))
