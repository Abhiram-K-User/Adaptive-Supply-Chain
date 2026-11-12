"""
Workstream 3: Hypothesis Property-Based Fuzzing Suite for Gate G2.
Verifies fixed-seed determinism, Stage B probability/factor bounds, and 0.0%
L1/L2 + dual-solver invariant breach rates under randomized disruptions across
both v0_core (23 nodes) and v1_corridor (118 nodes).
"""

from __future__ import annotations

import random
from datetime import datetime, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from asci.core.contracts import PipelineConfig
from asci.core.registry import get_canonical_registry
from asci.core.state import (
    DisruptionEvent,
    DisruptionEventType,
    EventStatus,
    PipelineState,
    PipelineStatus,
)
from asci.stages import WalkingSkeletonPipeline

_V0_IDS = tuple(sorted(get_canonical_registry(network_scale="v0_core").all_entities().keys()))
_V1_IDS = tuple(sorted(get_canonical_registry(network_scale="v1_corridor").all_entities().keys()))

_PIPE_CACHE: dict[tuple[str, int], WalkingSkeletonPipeline] = {}


def _get_cached_pipeline(network_scale: str, propagation_tier: int) -> WalkingSkeletonPipeline:
    key = (network_scale, propagation_tier)
    pipe = _PIPE_CACHE.get(key)
    if pipe is None:
        cfg = PipelineConfig(
            network_scale=network_scale,  # type: ignore[arg-type]
            propagation_tier=propagation_tier,  # type: ignore[arg-type]
        )
        pipe = WalkingSkeletonPipeline.from_config(cfg)
        _PIPE_CACHE[key] = pipe
    return pipe


@st.composite
def _fuzz_event_cases(draw: st.DrawFn) -> tuple[str, DisruptionEvent, PipelineConfig]:
    scale = draw(st.sampled_from(["v0_core", "v1_corridor"]))
    pool = _V0_IDS if scale == "v0_core" else _V1_IDS
    primary_id = draw(st.sampled_from(pool))
    extra_count = draw(st.integers(min_value=0, max_value=3))
    extra_ids = [
        draw(st.sampled_from(pool))
        for _ in range(extra_count)
    ]
    affected = list(dict.fromkeys([primary_id, *extra_ids]))

    severity = round(draw(st.floats(min_value=0.05, max_value=0.99, allow_nan=False, allow_infinity=False)), 4)
    duration_days = round(draw(st.floats(min_value=0.5, max_value=10.0, allow_nan=False, allow_infinity=False)), 2)
    confidence = round(draw(st.floats(min_value=0.25, max_value=1.0, allow_nan=False, allow_infinity=False)), 3)
    corroboration = draw(st.integers(min_value=1, max_value=5))
    event_type = draw(st.sampled_from(list(DisruptionEventType)))
    prop_tier = draw(st.sampled_from([1, 2]))
    risk_mode = draw(st.sampled_from(["DETERMINISTIC", "EXPECTED_COST", "CVAR"]))
    seed = draw(st.integers(min_value=1, max_value=10000))

    evt = DisruptionEvent(
        event_id=f"EVT_FUZZ_{scale}_{primary_id}_{seed}",
        event_type=event_type,
        status=EventStatus.NEW,
        primary_entity_id=primary_id,
        affected_entity_ids=affected,
        severity=severity,
        estimated_duration_days=duration_days,
        source_feed="HYPOTHESIS_FUZZ",
        raw_headline=f"Fuzz disruption on {primary_id}",
        raw_text=f"Simulated randomized disruption impacting {', '.join(affected)}.",
        timestamp=datetime(2026, 11, 10, tzinfo=timezone.utc),
        corroboration_count=corroboration,
        confidence=confidence,
    )
    cfg = PipelineConfig(
        network_scale=scale,  # type: ignore[arg-type]
        propagation_tier=prop_tier,  # type: ignore[arg-type]
        risk_mode=risk_mode,  # type: ignore[arg-type]
        random_seed=seed,
    )
    return scale, evt, cfg


@settings(max_examples=20, deadline=None)
@given(case=_fuzz_event_cases())
def test_gate_g2_property_fixed_seed_determinism(
    case: tuple[str, DisruptionEvent, PipelineConfig],
) -> None:
    """Property 1: Identical (event, cfg, seed) must yield bit-identical plans & graph metrics."""
    scale, evt, cfg = case
    pipe = _get_cached_pipeline(scale, cfg.propagation_tier)
    s0 = PipelineState(session_id=f"SESS_DET_{evt.event_id}", status=PipelineStatus.PERCEIVED, event=evt)

    s1, _ = pipe.run(s0, cfg, random.Random(cfg.random_seed))
    s2, _ = pipe.run(s0, cfg, random.Random(cfg.random_seed))

    assert s1.graph_context == s2.graph_context
    assert s1.candidate_plan is not None and s2.candidate_plan is not None
    assert s1.candidate_plan.plan_id == s2.candidate_plan.plan_id
    assert s1.candidate_plan.objective_cost == s2.candidate_plan.objective_cost
    assert s1.candidate_plan.allocations == s2.candidate_plan.allocations
    assert s1.verification_report == s2.verification_report


@settings(max_examples=20, deadline=None)
@given(
    case=_fuzz_event_cases(),
    k_hops=st.integers(min_value=1, max_value=3),
)
def test_gate_g2_property_stage_b_factor_and_probability_bounds(
    case: tuple[str, DisruptionEvent, PipelineConfig],
    k_hops: int,
) -> None:
    """Property 2: All Stage B vulnerability factors & line-stop probabilities stay bounded."""
    scale, evt, base_cfg = case
    cfg = base_cfg.model_copy(update={"k_hop_neighborhood": k_hops})
    pipe = _get_cached_pipeline(scale, cfg.propagation_tier)
    s0 = PipelineState(session_id=f"SESS_B_{evt.event_id}", status=PipelineStatus.PERCEIVED, event=evt)

    s_b, res_b = pipe.stage_b.run(s0, cfg, random.Random(cfg.random_seed))
    assert res_b.success is True
    assert s_b.graph_context is not None

    ctx = s_b.graph_context
    assert ctx.propagation_tier == cfg.propagation_tier
    assert ctx.hop_decay_applied is True

    for m in ctx.path_metrics:
        assert 0.0 <= m.exposure <= 1.0
        assert 0.0 <= m.criticality <= 1.0
        assert 0.0 <= m.utilisation <= 1.0
        assert 1.0 <= m.uncertainty_factor <= 2.0
        assert 0.0 <= m.concentration <= 2.0
        assert m.path_risk >= 0.0
        assert m.baseline_delay_hrs >= 0.0
        assert m.mode in {"ROAD", "INTERMODAL"}

    for ls in ctx.line_stop_metrics:
        assert 0.0 <= ls.line_stop_risk <= 1.0
        assert 0.0 <= ls.line_stop_probability <= 1.0
        assert ls.expected_delay_days >= 0.0

    if cfg.propagation_tier >= 2:
        for ratio in ctx.edge_congestion_ratios.values():
            assert 0.0 < ratio <= 2.5
        for load in ctx.redistributed_edge_loads_teu.values():
            assert load > 0.0


@settings(max_examples=20, deadline=None)
@given(case=_fuzz_event_cases())
def test_gate_g2_property_zero_l1_l2_and_dual_solver_breaches(
    case: tuple[str, DisruptionEvent, PipelineConfig],
) -> None:
    """Property 3: Zero L1/L2 or OR-Tools/HiGHS dual-solver breaches under random single/compound faults."""
    scale, evt, cfg = case
    pipe = _get_cached_pipeline(scale, cfg.propagation_tier)
    s0 = PipelineState(session_id=f"SESS_L2_{evt.event_id}", status=PipelineStatus.PERCEIVED, event=evt)

    final_state, results = pipe.run(s0, cfg, random.Random(cfg.random_seed))

    assert len(results) >= 4  # Stages A, B, C, D always execute (E runs when L3 passes)
    assert final_state.candidate_plan is not None
    assert final_state.verification_report is not None

    l1_l2_failures = [
        check
        for check in final_state.verification_report.failed_checks
        if not check.startswith("L3:")
    ]
    assert l1_l2_failures == [], f"Unexpected L1/L2 breach: {l1_l2_failures}"

    dual_checks = [
        chk
        for chk in final_state.verification_report.l2_checks
        if chk.check_name == "DUAL_SOLVER_AGREEMENT"
    ]
    assert len(dual_checks) == 1
    assert dual_checks[0].metrics.get("rel_diff_pct", 100.0) < 0.1

