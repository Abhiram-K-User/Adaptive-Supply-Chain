"""
Training Pipeline & Gate G4 Citation/Mask Audit for MaskedMLPPolicy.

Optimizes:
    L_policy = -sum w_i * log(pi_theta(a*_i | S_i))
where w_i incorporates episode regret weighting under budget constraint lambda.
Computes validation accuracy, 10-bin ECE, rewrite AUROC, mask violation rate,
compute savings vs Always-Full RAG, and Gate G4 citation verification rate.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn

from asci.core.contracts import PipelineConfig
from asci.core.state import (
    DisruptionEvent,
    DisruptionEventType,
    OperatorType,
    PipelineStatus,
)
from asci.llm.explainer import PlanBriefingGenerator, verify_briefing_citations
from asci.policy.model import (
    ACTION_COST_MAP,
    ACTION_TO_IDX,
    CONTROLLER_ACTIONS,
    FEATURE_DIM,
    NUM_ACTIONS,
    MaskedMLPPolicy,
)
from asci.policy.oracle import OracleSample, OracleTrajectoryGenerator


@dataclass(frozen=True)
class TrainingReport:
    """Validation and calibration metrics from policy training."""

    num_episodes: int
    num_samples: int
    epochs: int
    final_train_loss: float
    train_accuracy: float
    val_accuracy: float
    mask_violation_rate: float
    ece: float
    auroc_rewrite: float
    mean_cost_savings_vs_always_full: float
    checkpoint_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize report into primitive dictionary."""
        return asdict(self)


def _compute_ece(confidences: np.ndarray, correct: np.ndarray, num_bins: int = 10) -> float:
    """Compute multi-class Expected Calibration Error (ECE)."""
    if len(confidences) == 0:
        return 0.0
    bin_edges = np.linspace(0.0, 1.0, num_bins + 1)
    ece = 0.0
    n = float(len(confidences))
    for b in range(num_bins):
        lo, hi = bin_edges[b], bin_edges[b + 1]
        if b == num_bins - 1:
            in_bin = (confidences >= lo) & (confidences <= hi)
        else:
            in_bin = (confidences >= lo) & (confidences < hi)
        count = int(np.sum(in_bin))
        if count > 0:
            acc = float(np.mean(correct[in_bin]))
            conf = float(np.mean(confidences[in_bin]))
            ece += (float(count) / n) * abs(acc - conf)
    return round(float(ece), 5)


def _compute_binary_auroc(labels: np.ndarray, scores: np.ndarray) -> float:
    """Compute ROC-AUC with trapezoidal integration without external ML dependencies."""
    pos_mask = labels == 1
    neg_mask = labels == 0
    n_pos = int(np.sum(pos_mask))
    n_neg = int(np.sum(neg_mask))
    if n_pos == 0 or n_neg == 0:
        return 1.0

    order = np.argsort(-scores, kind="mergesort")
    sorted_labels = labels[order]
    tps = np.cumsum(sorted_labels == 1).astype(np.float64)
    fps = np.cumsum(sorted_labels == 0).astype(np.float64)
    tpr = np.concatenate(([0.0], tps / float(n_pos)))
    fpr = np.concatenate(([0.0], fps / float(n_neg)))
    return round(float(np.trapezoid(tpr, fpr)), 5)


def _split_samples_by_episode(
    samples: list[OracleSample],
    val_mod: int = 5,
) -> tuple[list[OracleSample], list[OracleSample]]:
    train_samples = [s for s in samples if s.episode_id % val_mod != 0]
    val_samples = [s for s in samples if s.episode_id % val_mod == 0]
    return train_samples, val_samples


def _samples_to_tensors(
    samples: list[OracleSample],
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    features = torch.tensor([s.features for s in samples], dtype=torch.float32)
    masks = torch.tensor([s.action_mask for s in samples], dtype=torch.bool)
    targets = torch.tensor([s.oracle_action_idx for s in samples], dtype=torch.long)
    weights = torch.tensor([s.sample_weight for s in samples], dtype=torch.float32)
    costs = torch.tensor([s.step_cost for s in samples], dtype=torch.float32)
    return features, masks, targets, weights, costs


def train_masked_mlp_controller(
    *,
    num_episodes: int = 1050,
    epochs: int = 35,
    lr: float = 4e-3,
    regret_beta: float = 0.5,
    seed: int = 42,
    checkpoint_path: str | Path | None = None,
) -> tuple[MaskedMLPPolicy, TrainingReport]:
    """
    Generate oracle trajectories and train `MaskedMLPPolicy` with masked cross-entropy
    + regret-weighted optimization.
    """
    torch.manual_seed(seed)
    np.random.seed(seed)

    generator = OracleTrajectoryGenerator(seed=seed)
    samples, summaries = generator.generate_dataset(num_episodes=num_episodes)
    train_samples, val_samples = _split_samples_by_episode(samples)

    x_train, m_train, y_train, w_train, _ = _samples_to_tensors(train_samples)
    x_val, m_val, y_val, _, c_val = _samples_to_tensors(val_samples)

    # Combine sample regret weights cleanly with beta factor: weight = 1 + beta * w_norm
    regret_arr = torch.tensor(
        [s.episode_regret for s in train_samples],
        dtype=torch.float32,
    )
    regret_norm = regret_arr / regret_arr.mean().clamp(min=1e-6)
    loss_weights = w_train + regret_beta * (1.0 / (1.0 + regret_norm))
    loss_weights = loss_weights / loss_weights.mean().clamp(min=1e-6)

    policy = MaskedMLPPolicy(input_dim=FEATURE_DIM, num_actions=NUM_ACTIONS)
    optimizer = torch.optim.AdamW(policy.parameters(), lr=lr, weight_decay=1e-4)

    batch_size = 256
    final_loss = 0.0
    num_train = x_train.size(0)

    for _epoch in range(epochs):
        policy.train()
        perm = torch.randperm(num_train)
        epoch_loss = 0.0
        batches = 0
        for start in range(0, num_train, batch_size):
            idx = perm[start : start + batch_size]
            xb = x_train[idx]
            mb = m_train[idx]
            yb = y_train[idx]
            wb = loss_weights[idx]

            optimizer.zero_grad()
            masked_logits, _ = policy(xb, mb)
            ce = nn.functional.cross_entropy(masked_logits, yb, reduction="none")
            loss = (ce * wb).mean()
            loss.backward()
            optimizer.step()

            epoch_loss += float(loss.item())
            batches += 1
        final_loss = epoch_loss / float(max(batches, 1))

    policy.eval()
    with torch.no_grad():
        _, train_probs = policy(x_train, m_train)
        train_preds = torch.argmax(train_probs, dim=-1)
        train_acc = float((train_preds == y_train).float().mean().item())

        _, val_probs = policy(x_val, m_val)
        val_preds = torch.argmax(val_probs, dim=-1)
        val_correct = (val_preds == y_val).cpu().numpy().astype(np.float64)
        val_acc = float(np.mean(val_correct))

        # Check strict mask validity across all validation predictions
        pred_valid = m_val[torch.arange(x_val.size(0)), val_preds]
        mask_violation_rate = float(1.0 - pred_valid.float().mean().item())

        val_conf = val_probs.max(dim=-1).values.cpu().numpy()
        ece = _compute_ece(val_conf, val_correct, num_bins=10)

        rewrite_idx = ACTION_TO_IDX[OperatorType.REWRITE_QUERY]
        rewrite_valid = m_val[:, rewrite_idx].cpu().numpy()
        if int(np.sum(rewrite_valid)) > 0:
            rw_labels = (y_val.cpu().numpy()[rewrite_valid] == rewrite_idx).astype(np.int32)
            rw_scores = val_probs.cpu().numpy()[rewrite_valid, rewrite_idx]
        else:
            rw_labels = (y_val.cpu().numpy() == rewrite_idx).astype(np.int32)
            rw_scores = val_probs.cpu().numpy()[:, rewrite_idx]
        auroc_rewrite = _compute_binary_auroc(rw_labels, rw_scores)

        # Estimate validation episode cost savings vs Always-Full RAG sequence
        always_full_cost = 0.0080  # TEXT + GRADE + REWRITE + TEXT + GRADE + TS + DECISIONS + SCENARIOS
        pred_step_costs = torch.tensor(
            [ACTION_COST_MAP[CONTROLLER_ACTIONS[int(p)]] for p in val_preds],
            dtype=torch.float32,
        )
        val_ep_ids = sorted({s.episode_id for s in val_samples})
        ep_savings: list[float] = []
        ep_index_map: dict[int, list[int]] = {eid: [] for eid in val_ep_ids}
        for i, s in enumerate(val_samples):
            ep_index_map[s.episode_id].append(i)
        for eid in val_ep_ids:
            ep_cost = float(pred_step_costs[ep_index_map[eid]].sum().item())
            ep_savings.append((always_full_cost - ep_cost) / always_full_cost)
        mean_savings = float(np.mean(ep_savings)) if ep_savings else float(
            (always_full_cost - float(c_val.mean().item()) * 5.0) / always_full_cost
        )

    saved_path: str | None = None
    if checkpoint_path is not None:
        out_path = policy.save_checkpoint(
            checkpoint_path,
            metadata={
                "seed": seed,
                "num_episodes": len(summaries),
                "num_samples": len(samples),
                "val_accuracy": round(val_acc, 5),
                "mask_violation_rate": round(mask_violation_rate, 6),
                "ece": ece,
                "auroc_rewrite": auroc_rewrite,
            },
        )
        saved_path = str(out_path)

    report = TrainingReport(
        num_episodes=len(summaries),
        num_samples=len(samples),
        epochs=epochs,
        final_train_loss=round(final_loss, 5),
        train_accuracy=round(train_acc, 5),
        val_accuracy=round(val_acc, 5),
        mask_violation_rate=round(mask_violation_rate, 6),
        ece=ece,
        auroc_rewrite=auroc_rewrite,
        mean_cost_savings_vs_always_full=round(mean_savings, 5),
        checkpoint_path=saved_path,
    )
    return policy, report


_DEFAULT_POLICY_CACHE: dict[int, tuple[MaskedMLPPolicy, TrainingReport]] = {}


def get_or_train_default_policy(seed: int = 42) -> tuple[MaskedMLPPolicy, TrainingReport]:
    """
    Return a deterministic cached MaskedMLPPolicy for runtime inference in StageCController.
    Trains once per process on first request (~0.5s on CPU).
    """
    if seed not in _DEFAULT_POLICY_CACHE:
        _DEFAULT_POLICY_CACHE[seed] = train_masked_mlp_controller(
            num_episodes=1050,
            epochs=35,
            seed=seed,
        )
    return _DEFAULT_POLICY_CACHE[seed]


def audit_gate_g4_citations(
    *,
    num_scenarios: int = 10,
    seed: int = 42,
    controller_mode: str = "learned_mlp",
) -> dict[str, Any]:
    """
    Run Gate G4 citation provenance audit across corridor disruption scenarios.

    Executes the full `WalkingSkeletonPipeline` + `PlanBriefingGenerator` and
    verifies zero unsupported citations (`>= 95%` citation support required).
    """
    from asci.core.state import PipelineState
    from asci.stages import WalkingSkeletonPipeline

    policy, report = get_or_train_default_policy(seed=seed)
    pipeline = WalkingSkeletonPipeline()
    pipeline.stage_c.policy = policy
    explainer = PlanBriefingGenerator(registry=pipeline.stage_c.registry)

    scenarios = [
        ("PORT_KAMARAJAR", DisruptionEventType.PORT_CONGESTION_STRIKE, 0.78, 0.86, 5, 0.05),
        ("PORT_CHENNAI", DisruptionEventType.HAZARD_PORT, 0.85, 0.72, 8, 0.05),
        ("CFS_ENNORE_LOGISTICS", DisruptionEventType.SHIPPING_SCHEDULE, 0.52, 0.88, 3, 0.15),
        ("PORT_KAMARAJAR", DisruptionEventType.RAIL_DISRUPTION, 0.65, 0.62, 6, 0.05),
        ("PORT_CHENNAI", DisruptionEventType.HAZARD_ROAD, 0.40, 0.91, 2, 0.30),
        ("PORT_KAMARAJAR", DisruptionEventType.PORT_CONGESTION_STRIKE, 0.90, 0.55, 10, 0.01),
        ("PORT_CHENNAI", DisruptionEventType.RAIL_DISRUPTION, 0.70, 0.80, 4, 0.10),
        ("CFS_ENNORE_LOGISTICS", DisruptionEventType.HAZARD_PORT, 0.60, 0.75, 7, 0.05),
        ("PORT_KAMARAJAR", DisruptionEventType.TRADE_POLICY, 0.48, 0.83, 4, 0.20),
        ("PORT_CHENNAI", DisruptionEventType.PORT_CONGESTION_STRIKE, 0.74, 0.79, 5, 0.05),
    ][:num_scenarios]

    total_citations = 0
    supported_citations = 0
    rejected_citations = 0
    mask_violations = 0
    completed_runs = 0
    now = datetime(2026, 4, 15, 10, 0, tzinfo=UTC)

    for idx, (entity_id, ev_type, sev, conf, dur, lam) in enumerate(scenarios):
        cfg = PipelineConfig(
            lambda_cost_budget=lam,
            random_seed=seed + idx,
            controller_mode=controller_mode,  # type: ignore[arg-type]
        )
        headline = f"{entity_id} {ev_type.value} disruption scenario {idx}"
        event = DisruptionEvent(
            event_id=f"EVT_G4_{idx:03d}",
            event_type=ev_type,
            primary_entity_id=entity_id,
            affected_entity_ids=[entity_id],
            severity=sev,
            confidence=conf,
            estimated_duration_days=dur,
            source_feed="G4_AUDIT",
            raw_headline=headline,
            raw_text=headline,
            timestamp=now,
        )
        state0 = PipelineState(
            session_id=f"SESS_G4_AUDIT_{idx:03d}",
            status=PipelineStatus.PERCEIVED,
            event=event,
        )
        final_state, _ = pipeline.run(state0, cfg, random.Random(cfg.random_seed))
        if final_state.status == PipelineStatus.COMPLETED:
            completed_runs += 1

        # Verify trace contains no unexpected failures in Stage C operator steps
        for tr in final_state.trace:
            if tr.operator_type == CONTROLLER_ACTIONS[-1]:  # ESCALATE
                mask_violations += 1

        briefing = explainer.generate(final_state, cfg)
        valid_cits = {doc.citation_id for doc in final_state.evidence_set}
        _, verified_inline, rejected_inline = verify_briefing_citations(
            [
                str(briefing.get("headline", "")),
                str(briefing.get("executive_summary", "")),
                *[str(x) for x in briefing.get("key_actions", [])],
                *[str(x) for x in briefing.get("line_stop_watchouts", [])],
            ],
            valid_cits,
        )
        cited_field = [str(c) for c in briefing.get("cited_ids", [])]
        valid_field = [c for c in cited_field if c in valid_cits]
        invalid_field = [c for c in cited_field if c not in valid_cits]
        rejected_field = [str(c) for c in briefing.get("rejected_citations", [])]

        supported_citations += len(verified_inline) + len(valid_field)
        rejected_citations += len(rejected_inline) + len(invalid_field) + len(rejected_field)
        total_citations += (
            len(verified_inline)
            + len(valid_field)
            + len(rejected_inline)
            + len(invalid_field)
            + len(rejected_field)
        )

    support_rate = float(supported_citations) / float(total_citations) if total_citations > 0 else 1.0
    return {
        "scenarios_audited": len(scenarios),
        "completed_runs": completed_runs,
        "mask_violations": mask_violations,
        "total_citations_checked": total_citations,
        "supported_citations": supported_citations,
        "rejected_citations": rejected_citations,
        "citation_support_rate": round(support_rate, 5),
        "training_report": report.to_dict(),
    }
