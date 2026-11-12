"""
Integration Gate G2 Statistical Verification (PRD Suite S1 across v0_core & v1_corridor).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from asci.api.main import create_app
from asci.benchmarks.suite_s1 import SuiteS1Runner


def test_suite_s1_gate_g2_v0_core_and_v1_corridor_statistical_summary() -> None:
    """
    Execute formal Suite S1 statistical benchmark over both v0_core and scaled v1_corridor,
    validating reproducibility, zero L1/L2 breaches, dual-solver parity, Tier-1/2 propagation,
    CVaR tail hedging, and elimination of all 3 v0 bottlenecks on v1_corridor.
    """
    runner = SuiteS1Runner()
    rep_v0 = runner.run_suite(network_scale="v0_core", verify_repro=True)
    rep_v1 = runner.run_suite(network_scale="v1_corridor", verify_repro=True)

    for rep in (rep_v0, rep_v1):
        assert rep.total_cases == 57
        assert rep.reproducibility_rate == 100.0
        assert rep.l1_l2_breach_count == 0
        assert rep.l1_l2_breach_rate == 0.0
        assert rep.max_dual_rel_diff_pct < 0.1
        assert (
            rep.tier_comparison["tier_2"]["mean_propagated_delay_hrs"]
            > rep.tier_comparison["tier_1"]["mean_propagated_delay_hrs"]
        )
        assert (
            rep.risk_mode_comparison["CVAR"]["mean_cvar_cost"]
            <= rep.risk_mode_comparison["EXPECTED_COST"]["mean_cvar_cost"] + 1e-2
        )

    # Scaled v1_corridor PRD structural & bottleneck elimination requirements
    assert 100 <= rep_v1.node_count <= 150
    assert 300 <= rep_v1.edge_count <= 500
    assert set(rep_v1.bottleneck_unmet_teu.keys()) == {
        "PORT_KRISHNAPATNAM",
        "ICD_WHITEFIELD",
        "ICD_IRUGUR",
    }
    assert all(unmet == 0.0 for unmet in rep_v1.bottleneck_unmet_teu.values())
    assert rep_v1.mean_unmet_demand_pct < rep_v0.mean_unmet_demand_pct
    assert rep_v1.p95_total_ms < 2000.0


def test_suite_s1_cli_and_api_v1_corridor_integration(tmp_path: Path) -> None:
    """Verify v1_corridor FastAPI boot, Tier-2 planning on former bottleneck, & CLI report JSON."""
    app = create_app(data_dir=tmp_path / "runtime", network_scale="v1_corridor")
    client = TestClient(app)

    net = client.get("/network").json()
    assert 100 <= net["node_count"] <= 150
    assert 300 <= net["edge_count"] <= 500

    reg_list = client.get("/registry").json()
    assert len(reg_list) == net["node_count"]

    ev_resp = client.post(
        "/events",
        json={
            "signal_id": "SIG_API_V1_WHITEFIELD",
            "source_feed": "TEST_API",
            "trust_tier": "TIER_A",
            "raw_headline": "Signal failure disrupts CONCOR Whitefield ICD",
            "raw_text": "Rail operations at ICD Whitefield reduced due to overhead gantry outage.",
            "hint_entity_id": "ICD_WHITEFIELD",
            "hint_severity": 0.85,
            "hint_duration_days": 3.0,
        },
    )
    assert ev_resp.status_code == 201
    event_id = ev_resp.json()["event_id"]

    plan_resp = client.post(
        f"/events/{event_id}/plan",
        json={
            "propagation_tier": 2,
            "risk_mode": "CVAR",
            "random_seed": 42,
        },
    )
    assert plan_resp.status_code == 200
    plan_payload = plan_resp.json()
    assert plan_payload["status"] == "COMPLETED"
    assert plan_payload["plan"]["solver_engine"] == "OR_TOOLS"
    assert plan_payload["plan"]["risk_mode"] == "CVAR"
    assert plan_payload["plan"]["unmet_demand_teu"] == 0.0

    # Verify CLI script writes clean JSON report
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import run_suite_s1

    out_file = tmp_path / "suite_s1_out.json"
    exit_code = run_suite_s1.run_cli(["--scale", "v1_corridor", "--output", str(out_file)])
    assert exit_code == 0
    assert out_file.exists()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["gate_g2_passed"] is True
    assert data["reports"]["v1_corridor"]["l1_l2_breach_count"] == 0

