"""
PyTorch Masked MLP Controller Policy (Stage C, Gate G4).

Implements formal precondition masking and Markov state feature extraction for
budget-aware Agentic-RAG operator selection:
    pi_theta(a | S_t) with invalid action logits masked to -inf.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn

from asci.core.contracts import PipelineConfig
from asci.core.state import OperatorType, PipelineState, TrustTier

FEATURE_DIM = 15

CONTROLLER_ACTIONS: tuple[OperatorType, ...] = (
    OperatorType.RETRIEVE_TEXT,
    OperatorType.GRADE,
    OperatorType.REWRITE_QUERY,
    OperatorType.RETRIEVE_TS,
    OperatorType.RETRIEVE_DECISIONS,
    OperatorType.SCENARIOS,
    OperatorType.ESCALATE,
)

NUM_ACTIONS = len(CONTROLLER_ACTIONS)
ACTION_TO_IDX: dict[OperatorType, int] = {op: idx for idx, op in enumerate(CONTROLLER_ACTIONS)}

ACTION_COST_MAP: dict[OperatorType, float] = {
    OperatorType.RETRIEVE_TEXT: 0.0015,
    OperatorType.GRADE: 0.0010,
    OperatorType.REWRITE_QUERY: 0.0020,
    OperatorType.RETRIEVE_TS: 0.0010,
    OperatorType.RETRIEVE_DECISIONS: 0.0005,
    OperatorType.SCENARIOS: 0.0010,
    OperatorType.ESCALATE: 0.0000,
}

FEATURE_NAMES: tuple[str, ...] = (
    "event_severity",
    "event_confidence",
    "duration_norm",
    "lambda_budget_norm",
    "evidence_count_norm",
    "mean_evidence_score",
    "tier_a_ratio",
    "rewrite_count_norm",
    "text_retrieved_flag",
    "graded_flag",
    "grade_sufficient_flag",
    "ts_retrieved_flag",
    "decisions_retrieved_flag",
    "graph_nodes_norm",
    "steps_ratio",
)


@dataclass
class ControllerHistory:
    """Mutable episode execution tracker used inside Stage C rollout."""

    steps_taken: int = 0
    text_retrievals: int = 0
    grade_calls: int = 0
    rewrite_count: int = 0
    grade_sufficient: bool = False
    last_rewritten: bool = False
    ts_retrieved: bool = False
    decisions_retrieved: bool = False
    scenarios_generated: bool = False
    has_ungraded_evidence: bool = False
    cumulative_cost: float = 0.0


def extract_controller_features(
    state: PipelineState,
    cfg: PipelineConfig,
    history: ControllerHistory,
) -> list[float]:
    """
    Project the frozen PipelineState + execution history into a normalized 15-D feature vector.
    All components lie in [0.0, 1.0].
    """
    event = state.event
    severity = float(event.severity) if event is not None else 0.0
    confidence = float(event.confidence) if event is not None else 0.0
    duration_norm = min(float(event.estimated_duration_days) / 30.0, 1.0) if event is not None else 0.0

    lambda_norm = min(float(cfg.lambda_cost_budget) / 0.50, 1.0)

    ev_count = len(state.evidence_set)
    ev_count_norm = min(float(ev_count) / 6.0, 1.0)
    if ev_count > 0:
        mean_score = sum(float(d.relevance_score) for d in state.evidence_set) / float(ev_count)
        tier_a_ratio = sum(1 for d in state.evidence_set if d.trust_tier == TrustTier.TIER_A) / float(ev_count)
    else:
        mean_score = 0.0
        tier_a_ratio = 0.0

    rewrite_norm = min(float(history.rewrite_count) / 2.0, 1.0)
    text_flag = 1.0 if history.text_retrievals > 0 else 0.0
    graded_flag = 1.0 if history.grade_calls > 0 else 0.0
    sufficient_flag = 1.0 if history.grade_sufficient else 0.0
    ts_flag = 1.0 if history.ts_retrieved else 0.0
    dec_flag = 1.0 if history.decisions_retrieved else 0.0

    graph_nodes_norm = (
        min(float(len(state.graph_context.impacted_nodes)) / 25.0, 1.0)
        if state.graph_context is not None
        else 0.0
    )
    steps_ratio = min(float(history.steps_taken) / float(max(cfg.max_steps, 1)), 1.0)

    return [
        severity,
        confidence,
        duration_norm,
        lambda_norm,
        ev_count_norm,
        mean_score,
        tier_a_ratio,
        rewrite_norm,
        text_flag,
        graded_flag,
        sufficient_flag,
        ts_flag,
        dec_flag,
        graph_nodes_norm,
        steps_ratio,
    ]


def compute_action_mask(
    state: PipelineState,
    cfg: PipelineConfig,
    history: ControllerHistory,
) -> list[bool]:
    """
    Compute the formal Stage C precondition boolean mask aligned with `CONTROLLER_ACTIONS`.

    Masking guarantees:
    - Beyond `cfg.max_steps` or when event/graph context is missing: only `ESCALATE` is valid.
    - `RETRIEVE_TEXT` requires zero prior text calls or an unconsumed query rewrite (max 2 calls).
    - `GRADE` is valid only when ungraded text retrieval output is present.
    - `REWRITE_QUERY` requires prior grading failure, `rewrite_count < 2`, and no pending rewrite.
    - `RETRIEVE_TS` and `RETRIEVE_DECISIONS` run at most once per episode.
    - `SCENARIOS` requires valid `event` and `graph_context`, and cannot execute twice.
    """
    if (
        state.event is None
        or state.graph_context is None
        or history.steps_taken >= cfg.max_steps
        or state.step_count >= cfg.max_steps
    ):
        return [op == OperatorType.ESCALATE for op in CONTROLLER_ACTIONS]

    can_retrieve_text = (history.text_retrievals == 0) or (
        history.last_rewritten and history.text_retrievals < 2
    )
    can_grade = history.has_ungraded_evidence
    can_rewrite = (
        history.grade_calls > 0
        and not history.grade_sufficient
        and not history.last_rewritten
        and history.rewrite_count < 2
    )
    can_retrieve_ts = not history.ts_retrieved
    can_retrieve_decisions = not history.decisions_retrieved
    can_scenarios = not history.scenarios_generated

    mask_by_op = {
        OperatorType.RETRIEVE_TEXT: can_retrieve_text,
        OperatorType.GRADE: can_grade,
        OperatorType.REWRITE_QUERY: can_rewrite,
        OperatorType.RETRIEVE_TS: can_retrieve_ts,
        OperatorType.RETRIEVE_DECISIONS: can_retrieve_decisions,
        OperatorType.SCENARIOS: can_scenarios,
        OperatorType.ESCALATE: False,
    }
    mask = [mask_by_op[op] for op in CONTROLLER_ACTIONS]

    # Safety fallback if no forward transition remains
    if not any(mask):
        mask[ACTION_TO_IDX[OperatorType.ESCALATE]] = True
    return mask


class MaskedMLPPolicy(nn.Module):
    """
    Masked 2-hidden-layer MLP policy network for Agentic-RAG Stage C control.

    Architecture: 15 -> 64 (ReLU) -> 32 (ReLU) -> 7 (Masked Softmax).
    """

    def __init__(
        self,
        input_dim: int = FEATURE_DIM,
        hidden_dim_1: int = 64,
        hidden_dim_2: int = 32,
        num_actions: int = NUM_ACTIONS,
    ) -> None:
        super().__init__()
        self.input_dim = input_dim
        self.hidden_dim_1 = hidden_dim_1
        self.hidden_dim_2 = hidden_dim_2
        self.num_actions = num_actions
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim_1),
            nn.ReLU(),
            nn.Linear(hidden_dim_1, hidden_dim_2),
            nn.ReLU(),
            nn.Linear(hidden_dim_2, num_actions),
        )

    def forward(
        self,
        features: torch.Tensor,
        action_mask: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Compute masked logits and exact zero-probability masked action probabilities.

        Returns `(masked_logits, probs)`.
        """
        raw_logits = self.net(features)
        bool_mask = action_mask.bool()
        masked_logits = raw_logits.masked_fill(~bool_mask, -1e9)
        probs = torch.softmax(masked_logits, dim=-1)
        probs = probs * bool_mask.to(probs.dtype)
        denom = probs.sum(dim=-1, keepdim=True).clamp(min=1e-12)
        probs = probs / denom
        return masked_logits, probs

    def predict_action(
        self,
        features: list[float],
        action_mask: list[bool],
        deterministic: bool = True,
        generator: torch.Generator | None = None,
    ) -> tuple[OperatorType, list[float]]:
        """
        Infer the next valid `OperatorType` and calibrated probability distribution.
        Invalid actions strictly receive 0.0 probability.
        """
        if not any(action_mask):
            raise ValueError("Action mask must permit at least one valid operator.")

        self.eval()
        with torch.no_grad():
            feat_t = torch.tensor([features], dtype=torch.float32)
            mask_t = torch.tensor([action_mask], dtype=torch.bool)
            _, probs_t = self.forward(feat_t, mask_t)
            probs_row = probs_t[0]
            if deterministic:
                idx = int(torch.argmax(probs_row).item())
            else:
                idx = int(torch.multinomial(probs_row, num_samples=1, generator=generator).item())

        probs_list = [
            float(probs_row[i].item()) if action_mask[i] else 0.0
            for i in range(self.num_actions)
        ]
        return CONTROLLER_ACTIONS[idx], probs_list

    def save_checkpoint(self, path: str | Path, metadata: dict[str, Any] | None = None) -> Path:
        """Persist weights and metadata safely to disk."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "input_dim": self.input_dim,
            "hidden_dim_1": self.hidden_dim_1,
            "hidden_dim_2": self.hidden_dim_2,
            "num_actions": self.num_actions,
            "state_dict": self.state_dict(),
            "metadata": metadata or {},
        }
        torch.save(payload, target)
        return target

    @classmethod
    def load_checkpoint(
        cls,
        path: str | Path,
        map_location: str = "cpu",
    ) -> tuple[MaskedMLPPolicy, dict[str, Any]]:
        """Load a saved policy checkpoint on CPU/target device."""
        payload = torch.load(Path(path), map_location=map_location, weights_only=True)
        policy = cls(
            input_dim=int(payload["input_dim"]),
            hidden_dim_1=int(payload["hidden_dim_1"]),
            hidden_dim_2=int(payload["hidden_dim_2"]),
            num_actions=int(payload["num_actions"]),
        )
        policy.load_state_dict(payload["state_dict"])
        policy.eval()
        metadata = dict(payload.get("metadata") or {})
        return policy, metadata
