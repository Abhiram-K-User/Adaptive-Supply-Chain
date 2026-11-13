"""
Unit & Gate G4 Audit Tests for Phase 6 Agentic-RAG Policy Learning:
- OracleTrajectoryGenerator (>= 1,000 deterministic episodes across lambda regimes)
- Formal Stage C precondition masking (0% invalid/masked action probability)
- PyTorch MaskedMLPPolicy training, ECE/AUROC metrics, and checkpoint roundtrip
- End-to-end WalkingSkeletonPipeline execution under `controller_mode="learned_mlp"`
  and baselines (`always_full`, `fixed_rag`, `no_rag`)
- FastAPI `/events/{id}/plan` controller_mode routing
- Gate G4 citation provenance audit (>= 95% citation support)
"""

from __future__ import annotations

import random
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from asci.api.main import create_app
from asci.core.contracts import PipelineConfig
from asci.core.state import (
    DisruptionEvent,
    DisruptionEventType,
    GraphContext,
    OperatorType,
    PipelineState,
    PipelineStatus,
)
from asci.llm.explainer import verify_briefing_citations
from asci.policy import (
    ACTION_TO_IDX,
    CONTROLLER_ACTIONS,
    ControllerHistory,
    MaskedMLPPolicy,
    OracleTrajectoryGenerator,
    audit_gate_g4_citations,
    compute_action_mask,
    extract_controller_features,
    train_masked_mlp_controller,
)
from asci.stages import WalkingSkeletonPipeline


def _sample_event(
    *,
    event_id: str = "EVT_G4_TEST",
    entity_id: str = "PORT_KAMARAJAR",
    severity: float = 0.78,
    confidence: float = 0.85,
) -> DisruptionEvent:
    headline = f"{entity_id} strike disrupts container berths"
    return DisruptionEvent(
        event_id=event_id,
        event_type=DisruptionEventType.PORT_CONGESTION_STRIKE,
        primary_entity_id=entity_id,
        affected_entity_ids=[entity_id],
        severity=severity,
        confidence=confidence,
        estimated_duration_days=5.0,
        source_feed="GATE_G4_TEST",
        raw_headline=headline,
        raw_text=headline,
        timestamp=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
    )


def test_oracle_trajectory_generator_1000_plus_deterministic() -> None:
    gen_a = OracleTrajectoryGenerator(seed=42)
    gen_b = OracleTrajectoryGenerator(seed=42)

    samples_a, summaries_a = gen_a.generate_dataset(num_episodes=1050)
    samples_b, _ = gen_b.generate_dataset(num_episodes=1050)

    assert len(summaries_a) >= 1000
    assert len(samples_a) >= 3000
    assert samples_a[:25] == samples_b[:25]

    # Every oracle step must strictly respect the formal action mask
    assert all(s.action_mask[s.oracle_action_idx] for s in samples_a)

    # Higher compute penalty lambda must reduce mean Stage C episode compute cost
    low_lambda_costs = [ep.total_cost for ep in summaries_a if ep.lambda_cost_budget <= 0.05]
    high_lambda_costs = [ep.total_cost for ep in summaries_a if ep.lambda_cost_budget >= 0.30]
    assert low_lambda_costs and high_lambda_costs
    assert sum(high_lambda_costs) / len(high_lambda_costs) < sum(low_lambda_costs) / len(low_lambda_costs)


def test_action_masking_invariants_and_zero_probability_enforcement() -> None:
    event = _sample_event()
    cfg = PipelineConfig(lambda_cost_budget=0.05, max_steps=6)
    policy = MaskedMLPPolicy()

    # 1. Missing graph context -> only ESCALATE allowed
    no_graph_state = PipelineState(
        session_id="SESS_MASK_1",
        status=PipelineStatus.PERCEIVED,
        event=event,
        graph_context=None,
    )
    history = ControllerHistory()
    mask_no_graph = compute_action_mask(no_graph_state, cfg, history)
    assert mask_no_graph[ACTION_TO_IDX[OperatorType.ESCALATE]] is True
    assert sum(mask_no_graph) == 1

    op, probs = policy.predict_action(
        extract_controller_features(no_graph_state, cfg, history),
        mask_no_graph,
    )
    assert op == OperatorType.ESCALATE
    for i, allowed in enumerate(mask_no_graph):
        if not allowed:
            assert probs[i] == 0.0

    # 2. Step limit reached -> only ESCALATE allowed
    graph_state = no_graph_state.transition(
        updates={"graph_context": GraphContext(impacted_nodes=[event.primary_entity_id]), "status": PipelineStatus.ANALYZED}
    )
    exhausted_history = ControllerHistory(steps_taken=cfg.max_steps)
    mask_exhausted = compute_action_mask(graph_state, cfg, exhausted_history)
    assert mask_exhausted == [op_ == OperatorType.ESCALATE for op_ in CONTROLLER_ACTIONS]

    # 3. REWRITE_QUERY strictly masked prior to GRADE or after 2 rewrites
    mask_initial = compute_action_mask(graph_state, cfg, ControllerHistory())
    assert mask_initial[ACTION_TO_IDX[OperatorType.REWRITE_QUERY]] is False
    assert mask_initial[ACTION_TO_IDX[OperatorType.GRADE]] is False

    rewrite_cap_history = ControllerHistory(
        text_retrievals=2,
        grade_calls=2,
        grade_sufficient=False,
        rewrite_count=2,
    )
    mask_rw_capped = compute_action_mask(graph_state, cfg, rewrite_cap_history)
    assert mask_rw_capped[ACTION_TO_IDX[OperatorType.REWRITE_QUERY]] is False

    # Even untrained policy never emits non-zero probability on masked entries
    op2, probs2 = policy.predict_action(
        extract_controller_features(graph_state, cfg, rewrite_cap_history),
        mask_rw_capped,
    )
    assert mask_rw_capped[ACTION_TO_IDX[op2]] is True
    for i, allowed in enumerate(mask_rw_capped):
        if not allowed:
            assert probs2[i] == 0.0


def test_masked_mlp_training_metrics_and_checkpoint_roundtrip(tmp_path: Path) -> None:
    ckpt = tmp_path / "gate_g4_policy.pt"
    policy, report = train_masked_mlp_controller(
        num_episodes=1050,
        epochs=30,
        seed=42,
        checkpoint_path=ckpt,
    )

    assert ckpt.exists()
    assert report.num_episodes == 1050
    assert report.mask_violation_rate == 0.0
    assert report.val_accuracy >= 0.85
    assert report.ece <= 0.15
    assert report.auroc_rewrite >= 0.80
    assert report.mean_cost_savings_vs_always_full > 0.0

    reloaded, metadata = MaskedMLPPolicy.load_checkpoint(ckpt)
    assert metadata["num_episodes"] == 1050

    sample_features = [0.75, 0.80, 0.25, 0.10, 0.50, 0.72, 0.67, 0.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.40, 0.20]
    sample_mask = [False, False, False, True, True, True, False]
    op_a, probs_a = policy.predict_action(sample_features, sample_mask)
    op_b, probs_b = reloaded.predict_action(sample_features, sample_mask)
    assert op_a == op_b
    assert probs_a == probs_b


def test_pipeline_end_to_end_learned_mlp_and_baselines() -> None:
    pipeline = WalkingSkeletonPipeline()
    event = _sample_event()
    base_state = PipelineState(
        session_id="SESS_LEARNED_E2E",
        status=PipelineStatus.PERCEIVED,
        event=event,
    )

    # Deterministic repeated learned_mlp runs
    cfg_learned = PipelineConfig(lambda_cost_budget=0.05, random_seed=42, controller_mode="learned_mlp")
    out_a, res_a = pipeline.run(base_state, cfg_learned, random.Random(42))
    out_b, res_b = pipeline.run(base_state, cfg_learned, random.Random(42))

    assert out_a.status == PipelineStatus.COMPLETED
    assert out_a.verification_report is not None and out_a.verification_report.passed is True
    assert res_a[2].artifacts["controller_mode"] == "learned_mlp"
    assert res_a[2].artifacts["mask_violations"] == 0
    assert out_a.candidate_plan is not None and out_b.candidate_plan is not None
    assert out_a.candidate_plan.objective_cost == out_b.candidate_plan.objective_cost
    assert res_a[2].artifacts["operator_sequence"] == res_b[2].artifacts["operator_sequence"]

    # Baseline comparison: no_rag <= learned_mlp <= always_full Stage C compute cost
    cfg_no_rag = PipelineConfig(lambda_cost_budget=0.05, random_seed=42, controller_mode="no_rag")
    cfg_fixed = PipelineConfig(lambda_cost_budget=0.05, random_seed=42, controller_mode="fixed_rag")
    cfg_full = PipelineConfig(lambda_cost_budget=0.05, random_seed=42, controller_mode="always_full")

    _, res_no_rag = pipeline.run(base_state, cfg_no_rag, random.Random(42))
    _, res_fixed = pipeline.run(base_state, cfg_fixed, random.Random(42))
    _, res_full = pipeline.run(base_state, cfg_full, random.Random(42))

    assert res_no_rag[2].cost < res_fixed[2].cost < res_full[2].cost
    assert res_a[2].cost <= res_full[2].cost


def test_api_plan_endpoint_supports_learned_mlp_controller_mode(tmp_path: Path) -> None:
    app = create_app(network_scale="v0_core", data_dir=tmp_path)
    client = TestClient(app)

    ingest = client.post(
        "/events",
        json={
            "signal_id": "SIG_G4_API",
            "source_feed": "PORT_ALERT",
            "trust_tier": "TIER_A",
            "raw_headline": "Severe congestion reported at Kamarajar Container Terminal",
            "raw_text": "Berth queue exceeds 48 hours at Kamarajar Port.",
            "primary_entity_id": "PORT_KAMARAJAR",
            "event_type": "PORT_CONGESTION_STRIKE",
            "severity": 0.72,
            "estimated_duration_days": 4.0,
        },
    )
    assert ingest.status_code == 201
    event_id = ingest.json()["event_id"]

    plan_resp = client.post(
        f"/events/{event_id}/plan",
        json={"controller_mode": "learned_mlp", "lambda_cost_budget": 0.05},
    )
    assert plan_resp.status_code == 200
    body = plan_resp.json()
    assert body["status"] == "COMPLETED"
    assert body["verification"]["passed"] is True
    assert len(body["dashboard"]["evidence_provenance"]) >= 1


def test_gate_g4_citation_audit_exceeds_95_percent() -> None:
    audit = audit_gate_g4_citations(num_scenarios=10, seed=42, controller_mode="learned_mlp")
    assert audit["completed_runs"] == 10
    assert audit["mask_violations"] == 0
    assert audit["total_citations_checked"] > 0
    assert audit["citation_support_rate"] >= 0.95

    # Explicit negative control: injected fabricated citation must be rejected cleanly
    cleaned, verified, rejected = verify_briefing_citations(
        ["Berth congestion verified [CIT_REAL_01] with spurious claim [CIT_FAKE_999]."],
        {"CIT_REAL_01"},
    )
    assert verified == ["CIT_REAL_01"]
    assert rejected == ["CIT_FAKE_999"]
    assert "CIT_FAKE_999" not in cleaned[0]
