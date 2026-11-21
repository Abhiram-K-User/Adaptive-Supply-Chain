"""Real controller rollouts, held-out fixed-plan regret and CVaR comparison."""
from __future__ import annotations

import hashlib
import random
import time
from statistics import mean

import numpy as np

from asci.benchmarks.ablations.dataset import cases, close_pipeline, holdouts
from asci.benchmarks.metrics import auroc, ece, mean_ci, pareto_frontier, reduction, weighted_cvar
from asci.core.contracts import PipelineConfig
from asci.core.state import OperatorType, PipelineState
from asci.policy.model import (
    ACTION_TO_IDX,
    ControllerHistory,
    compute_action_mask,
    extract_controller_features,
)
from asci.stages import WalkingSkeletonPipeline

MODES = ("no_rag", "fixed_rag", "rule_router", "always_full", "learned_mlp", "llm_planner")


def _summarize(rows, variants, config):
    keys = ("regret", "compute_cost", "runtime_ms", "unmet_demand_teu", "line_stop_days", "scenario_spill_teu")
    # Lambda repeats are clustered within an event, not independent samples.
    return {variant: {key: mean_ci([mean(r[key] for r in rows if r["variant"] == variant and r["case"] == case)
                                    for case in sorted({r["case"] for r in rows if r["variant"] == variant})],
                                   seed=config.seed, samples=config.bootstrap_samples)
                      for key in keys} for variant in variants}


def run_control_studies(config, scale, *, include_llm=True):
    cfg = PipelineConfig(network_scale=scale, llm_planner_cache_dir=config.planner_cache_dir,
                         llm_planner_allow_live=config.record_llm)
    pipe = WalkingSkeletonPipeline.from_config(cfg)
    rows, risk_rows = [], []
    modes = MODES if include_llm else MODES[:-1]
    try:
        initialized = time.perf_counter()
        policy = pipe.stage_c._resolve_policy(cfg)
        policy_initialization_ms = (time.perf_counter()-initialized)*1000
        weights = hashlib.sha256()
        for name, tensor in sorted(policy.state_dict().items()):
            weights.update(name.encode())
            weights.update(tensor.detach().cpu().numpy().tobytes())
        policy_sha256 = weights.hexdigest()
        for event in cases(config, scale):
            state = PipelineState(session_id=event.event_id, event=event)
            state, result = pipe.stage_a.run(state, cfg, random.Random(config.seed))
            if not result.success:
                raise RuntimeError(result.message)
            state, result = pipe.stage_b.run(state, cfg, random.Random(config.seed))
            if not result.success:
                raise RuntimeError(result.message)
            heldout = holdouts(event, config)
            oracle_costs = []
            for realization in heldout:
                hindsight = state.model_copy(update={"scenario_set": [realization]})
                instance = pipe.stage_d._build_lp_instance(hindsight, cfg)
                oracle = pipe.stage_d._solve_with_ortools(instance)
                dual = pipe.stage_d._solve_with_highs_dual(instance)
                if not oracle.feasible or not dual.feasible or abs(oracle.objective_value-dual.objective_value)/max(1, oracle.objective_value) > .01:
                    raise RuntimeError("Hindsight oracle failed independent dual-solver verification")
                oracle_costs.append(oracle.objective_value)
            for budget in config.lambdas:
                if not 0 <= budget <= .5:
                    raise ValueError("Ablation lambda must be in [0,.5]")
                for mode in modes:
                    settings = cfg.model_copy(update={"controller_mode": mode, "lambda_cost_budget": budget})
                    start = time.perf_counter()
                    controlled, controller_result = pipe.stage_c.run(state, settings, random.Random(config.seed))
                    if not controller_result.success:
                        raise RuntimeError(f"{mode} failed: {controller_result.message}")
                    final, result = pipe.stage_d.run(controlled, settings, random.Random(config.seed))
                    if final.candidate_plan is None or final.verification_report is None:
                        raise RuntimeError(f"{mode} produced no verifiable plan: {result.message}")
                    breaches = [check for check in final.verification_report.failed_checks if not check.startswith("L3:")]
                    if breaches:
                        raise RuntimeError(f"{mode} mathematical breaches: {breaches}")
                    scores = pipe.stage_d.evaluate_plan(state, settings, final.candidate_plan, heldout)
                    regrets = [max(0., score["cost"]-oracle) for score, oracle in zip(scores, oracle_costs, strict=True)]
                    if any(score["cost"] < oracle - max(.1, abs(oracle)*1e-5) for score, oracle in zip(scores, oracle_costs, strict=True)):
                        raise RuntimeError("Fixed-plan scoring is below the hindsight optimal value")
                    probability = 1. if mode in ("rule_router", "always_full", "fixed_rag") else 0.
                    if mode == "learned_mlp":
                        history = ControllerHistory()
                        _, probs = pipe.stage_c._resolve_policy(settings).predict_action(
                            extract_controller_features(state, settings, history), compute_action_mask(state, settings, history))
                        probability = 1-float(probs[ACTION_TO_IDX[OperatorType.SCENARIOS]])
                    planner_records = controller_result.artifacts.get("planner_records", [])
                    if mode == "llm_planner":
                        probability = planner_records[0]["probability_deeper_needed"]
                    row = {"case": event.event_id, "variant": mode, "lambda": budget,
                           "regret": mean(regrets), "regret_samples": regrets,
                           "p95_regret": float(np.quantile(regrets, .95)),
                           "heldout_mean_cost": mean(s["cost"] for s in scores),
                           "compute_cost": controller_result.cost,
                           "runtime_ms": (time.perf_counter()-start)*1000,
                           "steps": len(controller_result.artifacts["operator_sequence"]),
                           "operators": controller_result.artifacts["operator_sequence"],
                           "unmet_demand_teu": mean(s["unmet_demand_teu"] for s in scores),
                           "line_stop_days": mean(s["line_stop_days"] for s in scores),
                           "scenario_spill_teu": mean(s["scenario_spill_teu"] for s in scores),
                           "probability_deeper_needed": probability, "planner_records": planner_records,
                           "verification_failures": final.verification_report.failed_checks,
                           "holdout_scenarios": [s.model_dump(mode="json") for s in heldout],
                           "oracle_costs": oracle_costs}
                    rows.append(row)
                    # Reuse the exact same controller-generated training scenarios;
                    # each risk mode is scored on unseen realization scenarios.
                    if mode == "always_full" and budget == config.lambdas[0]:
                        for risk_mode in ("DETERMINISTIC", "CVAR"):
                            risk_cfg = settings.model_copy(update={"risk_mode": risk_mode, "cvar_alpha": config.cvar_alpha})
                            risk_state, risk_result = pipe.stage_d.run(controlled, risk_cfg, random.Random(config.seed))
                            if risk_state.candidate_plan is None or risk_state.verification_report is None:
                                raise RuntimeError(risk_result.message)
                            if any(not x.startswith("L3:") for x in risk_state.verification_report.failed_checks):
                                raise RuntimeError("Risk comparison mathematical breach")
                            realized = pipe.stage_d.evaluate_plan(state, settings, risk_state.candidate_plan, heldout)
                            regret = [max(0., s["cost"]-oracle) for s, oracle in zip(realized, oracle_costs, strict=True)]
                            risk_rows.append({"case": event.event_id, "variant": risk_mode, "regret": mean(regret),
                                "regret_samples": regret, "cost_samples": [s["cost"] for s in realized],
                                "heldout_mean_cost": mean(s["cost"] for s in realized),
                                "tail_regret_cvar": weighted_cvar(regret, [s.probability for s in heldout], config.cvar_alpha),
                                "unmet_demand_teu": mean(s["unmet_demand_teu"] for s in realized),
                                "scenario_spill_teu": mean(s["scenario_spill_teu"] for s in realized),
                                "line_stop_days": mean(s["line_stop_days"] for s in realized),
                                "line_stop_plants": mean(s["line_stop_plants"] for s in realized),
                                "compute_cost": controller_result.cost, "runtime_ms": risk_result.duration_ms})
    finally:
        close_pipeline(pipe)
    # The need label is measured full-vs-no-retrieval reduction in held-out model
    # regret, not the oracle policy's own action label or test-time teacher forcing.
    lookup = {(r["case"], r["lambda"], r["variant"]): r for r in rows}
    for row in rows:
        full = lookup[row["case"], row["lambda"], "always_full"]
        base = lookup[row["case"], row["lambda"], "no_rag"]
        improvement = (base["regret"]-full["regret"])/max(1., base["heldout_mean_cost"])
        row["deeper_needed"] = int(improvement > config.deeper_value_threshold)
    frontiers = {}
    for mode in ("no_rag", "fixed_rag", "rule_router"):
        points = [{"lambda": budget, "cost": mean(r["compute_cost"] for r in rows if r["variant"] == mode and r["lambda"] == budget),
                   "regret": mean(r["regret"] for r in rows if r["variant"] == mode and r["lambda"] == budget)} for budget in config.lambdas]
        frontiers[mode] = pareto_frontier(points)
    base = [r for r in rows if r["variant"] == "no_rag"]
    agentic = [r for r in rows if r["variant"] == "rule_router"]
    ratio = mean(r["compute_cost"] for r in agentic)/max(1e-12, mean(r["compute_cost"] for r in base))
    full_mean = mean(r["compute_cost"] for r in rows if r["variant"] == "always_full")
    equal_cost = [{"cost_allowance": allowance,
                   "variants": {mode: min((point for point in points if point["cost"] <= allowance), key=lambda p: p["regret"], default=None)
                                for mode, points in frontiers.items()}}
                  for allowance in sorted({point["cost"] for points in frontiers.values() for point in points})]
    equal_regret = [{"regret_allowance": allowance,
                     "variants": {mode: min((point for point in points if point["regret"] <= allowance), key=lambda p: p["cost"], default=None)
                                  for mode, points in frontiers.items()}}
                    for allowance in sorted({point["regret"] for points in frontiers.values() for point in points})]
    adaptive = {}
    for mode in modes:
        group = [r for r in rows if r["variant"] == mode]
        savings = reduction(full_mean, mean(r["compute_cost"] for r in group))
        labels, scores = [r["deeper_needed"] for r in group], [r["probability_deeper_needed"] for r in group]
        auc, calibration = auroc(labels, scores), ece(labels, scores)
        extra_regret = mean(r["regret"]-lookup[r["case"], r["lambda"], "always_full"]["regret"] for r in group)
        full_regret = mean(lookup[r["case"], r["lambda"], "always_full"]["regret"] for r in group)
        comparable = extra_regret <= max(1e-6, config.comparable_regret_increase_limit * full_regret)
        paired_regret = [mean(r["regret"]-lookup[r["case"], r["lambda"], "always_full"]["regret"] for r in group if r["case"] == case)
                         for case in sorted({r["case"] for r in group})]
        adaptive[mode] = {"compute_savings": savings, "auroc": auc, "ece": calibration,
                          "deeper_positive_cases": sum(labels), "samples": len(group), "extra_regret_vs_full": extra_regret,
                          "paired_extra_regret_ci": mean_ci(paired_regret, seed=config.seed, samples=config.bootstrap_samples),
                          "comparable_regret": comparable,
                          "planner_calls": sum(len(r["planner_records"]) for r in group),
                          "planner_original_latency_ms": sum(p["latency_ms"] for r in group for p in r["planner_records"]),
                          "targets": {"savings_at_comparable_regret": savings is not None and savings >= config.compute_savings_target and comparable,
                                      "auroc": auc is not None and auc >= config.auroc_target, "ece": calibration <= config.ece_target}}
    risk_summary = _summarize(risk_rows, ("DETERMINISTIC", "CVAR"), config)
    tails = {}
    for mode in ("DETERMINISTIC", "CVAR"):
        group = [r for r in risk_rows if r["variant"] == mode]
        tails[mode] = float(np.quantile([v for r in group for v in r["regret_samples"]], .95))
        risk_summary[mode]["p95_regret"] = tails[mode]
    tail_reduction = reduction(tails["DETERMINISTIC"], tails["CVAR"])
    deterministic_cost = mean(r["heldout_mean_cost"] for r in risk_rows if r["variant"] == "DETERMINISTIC")
    cvar_cost = mean(r["heldout_mean_cost"] for r in risk_rows if r["variant"] == "CVAR")
    mean_increase = (cvar_cost-deterministic_cost)/deterministic_cost
    limitations = ["Seeded synthetic disruption cases and independent synthetic holdouts; regret uses the deployed LP, not observed economic outcomes.",
                   "Scenario spill is the optimizer's soft capacity penalty; no physical queue, failed dispatch or recourse routing is simulated.",
                   "Compute units are the Stage C operator cost schedule and exclude planner inference overhead; savings are not total compute or API dollars. Original planner latency and call counts are separate.",
                   "Confidence intervals resample event-level means across lambda repeats; the case is the sampling unit.",
                   "LLM replay retains actual provider/model/prompt hashes and latency; replay wall time excludes the original network wait."]
    return ({"study": 2, "completed": True, "records": [r for r in rows if r["variant"] in frontiers],
             "summary": _summarize(rows, tuple(frontiers), config), "frontiers": frontiers,
             "regret_at_equal_cost_allowance": equal_cost, "cost_at_equal_regret_allowance": equal_regret,
             "agentic_cost_ratio_to_no_rag": ratio,
             "targets": {"lower_regret_within_cost_ratio": mean(r["regret"] for r in agentic) < mean(r["regret"] for r in base) and ratio <= config.retrieval_cost_ratio_target},
             "limitations": limitations + ["No interpolation or invented equal-cost matches: frontiers retain measured nondominated points. An empty matched comparison is explicitly unavailable."]},
            {"study": 6, "completed": include_llm, "records": rows, "summary": _summarize(rows, modes, config),
             "learned_policy_sha256": policy_sha256, "policy_initialization_ms": policy_initialization_ms,
             "adaptive_metrics": adaptive, "limitations": limitations + ["Policy loading/training is measured separately before timed inference rollouts.",
             "AUROC is undefined when held-out benefit labels contain only one class; it is reported as null, never 1.0."]},
            {"study": 8, "completed": True, "records": risk_rows, "summary": risk_summary,
             "tail_regret_reduction": tail_reduction, "mean_cost_increase": mean_increase,
             "targets": {"tail_reduction": tail_reduction is not None and tail_reduction >= config.tail_regret_reduction_target,
                         "mean_cost_limit": mean_increase <= config.mean_cost_increase_limit}, "limitations": limitations})
