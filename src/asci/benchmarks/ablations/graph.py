"""Graph and propagation studies against a declared expanded simulator reference."""
from __future__ import annotations

import math
import random
import time
from statistics import mean

from asci.benchmarks.ablations.dataset import cases, close_pipeline
from asci.benchmarks.metrics import mean_ci
from asci.core.contracts import PipelineConfig
from asci.core.state import PipelineState
from asci.stages import WalkingSkeletonPipeline


def _loss(pipe, path, context):
    """Independent bottleneck arithmetic; no Stage B scoring functions reused."""
    nominal, residual = [], []
    for node in path:
        cap = pipe.stage_b.registry.get(node).capacity_teu_per_day
        if cap is not None:
            nominal.append(cap)
            residual.append(cap * context.node_capacity_multipliers.get(node, 1))
    for u, v in zip(path, path[1:], strict=False):
        cap = sum(float(a["capacity_teu_per_day"]) for _, a in pipe.stage_b.graph_store.get_active_edges(u, v))
        nominal.append(cap)
        residual.append(cap * context.edge_capacity_multipliers.get(f"{u}->{v}", 1))
    return max(0., 1 - min(residual)/max(min(nominal), 1e-9))


def run_graph_studies(config, scale):
    cfg = PipelineConfig(network_scale=scale)
    pipe = WalkingSkeletonPipeline.from_config(cfg)
    graph_rows, propagation_rows = [], []
    try:
        for event in cases(config, scale):
            initial = PipelineState(session_id=event.event_id, event=event)
            reference, result = pipe.stage_b.run(initial, cfg.model_copy(update={"k_hop_neighborhood": 5}), random.Random(config.seed))
            if not result.success:
                raise RuntimeError(result.message)
            truth = reference.graph_context
            assert truth is not None
            contexts = {}
            for label, tier in (("k_hop", 1), ("dynamic", 2)):
                start = time.perf_counter()
                state, result = pipe.stage_b.run(initial, cfg.model_copy(update={"propagation_tier": tier}), random.Random(config.seed))
                if not result.success:
                    raise RuntimeError(result.message)
                contexts[label] = (state.graph_context, (time.perf_counter()-start)*1000)
            true_losses = [_loss(pipe, path.path, truth) for path in truth.path_metrics]
            for variant in ("no_graph", "k_hop"):
                predicted = ([0.] * len(true_losses) if variant == "no_graph" else
                             [_loss(pipe, path.path, contexts["k_hop"][0]) for path in truth.path_metrics])
                affected = [i for i, loss in enumerate(true_losses) if loss > 1e-6]
                graph_rows.append({"case": event.event_id, "variant": variant, "paths": len(true_losses),
                                   "affected_paths": len(affected),
                                   "affected_path_recall": sum(predicted[i] > 1e-6 for i in affected)/len(affected) if affected else None,
                                   "exposure_mae": mean(abs(p.exposure * (a-b)) for p, a, b in zip(truth.path_metrics, predicted, true_losses, strict=True))})
            truth_edges = truth.edge_capacity_multipliers
            truth_delays = truth.propagated_node_delays_hrs
            ranked = sorted((node for node, delay in truth_delays.items() if delay > 1e-6),
                            key=lambda node: (-truth_delays[node], node))[:10]
            for variant, (context, runtime) in contexts.items():
                predicted_delays = context.propagated_node_delays_hrs
                predicted_top = sorted((node for node, delay in predicted_delays.items() if delay > 1e-6),
                                       key=lambda node: (-predicted_delays[node], node))[:10]
                propagation_rows.append({"case": event.event_id, "variant": variant, "runtime_ms": runtime,
                                         "ranking_domain": "propagated_node_delay_hours", "reference_top_10": ranked,
                                         "predicted_top_10": predicted_top,
                                         "reference_node_delays_hrs": truth_delays, "predicted_node_delays_hrs": predicted_delays,
                                         "scored_node_count": len(pipe.stage_b.registry),
                                         "recall_at_10": len(set(predicted_top) & set(ranked))/len(ranked) if ranked else None,
                                         "delay_mae_hours": mean(abs(predicted_delays.get(node, 0)-truth_delays.get(node, 0))
                                                                 for node in pipe.stage_b.registry.all_entities()),
                                         "capacity_multiplier_mae": mean(abs(context.edge_capacity_multipliers.get(key, 1)-v) for key, v in truth_edges.items())})
    finally:
        close_pipeline(pipe)
    def summarize(rows, keys):
        return {variant: {key: mean_ci([r[key] for r in rows if r["variant"] == variant and r[key] is not None],
                                      seed=config.seed, samples=config.bootstrap_samples)
                          for key in keys if any(r[key] is not None for r in rows if r["variant"] == variant)}
                for variant in sorted({r["variant"] for r in rows})}
    limitations = ["Synthetic paired events; reference is the existing dynamic BPR model with five-hop propagation, not observed traffic.",
                   "Exposure error is path exposure weighted by independently computed bottleneck capacity loss.",
                   "Propagation Recall@10 ranks the most delayed nodes; delay MAE measures congestion behaviour. Both engines share capacity attenuation, reported only as a secondary metric.",
                   "Runtime includes Stage B path analysis and centrality; no GNN exists, so its optional comparison is omitted."]
    recall_gain = mean(r["recall_at_10"] for r in propagation_rows if r["variant"] == "dynamic" and r["recall_at_10"] is not None) - mean(r["recall_at_10"] for r in propagation_rows if r["variant"] == "k_hop" and r["recall_at_10"] is not None)
    return ({"study": 1, "completed": True, "records": graph_rows, "summary": summarize(graph_rows, ["affected_path_recall", "exposure_mae"]), "limitations": limitations},
            {"study": 7, "completed": True, "records": propagation_rows, "summary": summarize(propagation_rows, ["recall_at_10", "delay_mae_hours", "capacity_multiplier_mae", "runtime_ms"]),
             "recall_gain": recall_gain, "targets": {"recall_gain": recall_gain >= config.propagation_recall_gain_target
             or math.isclose(recall_gain, config.propagation_recall_gain_target, rel_tol=0, abs_tol=1e-12)}, "limitations": limitations})
