import random

import pytest

from asci.benchmarks.ablations.control import run_control_studies
from asci.benchmarks.ablations.dataset import AblationConfig, close_pipeline, holdouts
from asci.benchmarks.ablations.graph import run_graph_studies
from asci.benchmarks.ablations.retrieval import run_retrieval_studies
from asci.benchmarks.common import event_fixture
from asci.core.contracts import PipelineConfig
from asci.core.state import PipelineState
from asci.stages import WalkingSkeletonPipeline


@pytest.mark.parametrize("scale", ["v0_core", "v1_corridor"])
def test_graph_and_retrieval_studies_use_paired_cases(scale):
    config = AblationConfig(cases=2, bootstrap_samples=10, lambdas=(.1,))
    graph, propagation = run_graph_studies(config, scale)
    retrieval, grounding, gate = run_retrieval_studies(config, scale)
    assert all(r["completed"] for r in (graph, propagation, retrieval, grounding, gate))
    assert len(graph["records"]) == 4
    assert set(propagation["summary"]) == {"k_hop", "dynamic"}
    for row in propagation["records"]:
        truth, predicted = row["reference_node_delays_hrs"], row["predicted_node_delays_hrs"]
        error = sum(abs(predicted.get(node, 0)-truth.get(node, 0)) for node in set(truth) | set(predicted)) / row["scored_node_count"]
        assert row["delay_mae_hours"] == pytest.approx(error)
        assert row["ranking_domain"] == "propagated_node_delay_hours"
        if row["reference_top_10"]:
            assert row["recall_at_10"] == len(set(row["reference_top_10"]) & set(row["predicted_top_10"])) / len(row["reference_top_10"])
    assert len(retrieval["records"]) == 6
    assert grounding["summary"]["with_citation_checks"]["invalid_citations_retained"] == 0
    assert grounding["targets"]["claim_support"] is False  # real ID-only limitation
    assert all(r["gold_ids"] for r in retrieval["records"])


@pytest.mark.parametrize("scale", ["v0_core", "v1_corridor"])
def test_fixed_plan_score_matches_lp_scenario_objective(scale):
    cfg = PipelineConfig(network_scale=scale, risk_mode="EXPECTED_COST")
    pipe = WalkingSkeletonPipeline.from_config(cfg)
    try:
        event = event_fixture(severity=.9)
        state = PipelineState(session_id="EVALUATOR", event=event)
        state, _ = pipe.stage_b.run(state, cfg, random.Random(42))
        scenarios = holdouts(event, AblationConfig(cases=2))
        state = state.model_copy(update={"scenario_set": scenarios})
        instance = pipe.stage_d._build_lp_instance(state, cfg)
        result = pipe.stage_d._solve_with_ortools(instance)
        plan = pipe.stage_d._decompose_lp_to_plan(state, cfg, instance, result)
        scores = pipe.stage_d.evaluate_plan(state, cfg, plan, scenarios)
        evaluated = sum(s["cost"]*s["probability"] for s in scores)
        assert evaluated == pytest.approx(result.objective_value, rel=1e-5, abs=1)
        assert len(scores) == len(scenarios)
    finally:
        close_pipeline(pipe)


def test_control_rollouts_and_risk_holdout_integrate():
    config = AblationConfig(cases=2, bootstrap_samples=10, lambdas=(.1,), holdout_scenarios=3)
    retrieval, control, risk = run_control_studies(config, "v0_core", include_llm=False)
    assert retrieval["completed"] and risk["completed"]
    assert not control["completed"]  # missing LLM must never claim a complete comparison
    assert set(control["summary"]) == {"no_rag", "fixed_rag", "rule_router", "always_full", "learned_mlp"}
    assert len(control["records"]) == 10
    assert all("oracle_costs" in r and len(r["holdout_scenarios"]) == 3 for r in control["records"])
    assert set(risk["summary"]) == {"DETERMINISTIC", "CVAR"}
