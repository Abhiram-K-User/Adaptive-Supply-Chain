"""Learned Agentic-RAG controller policy, oracle generator, and training utilities (Gate G4)."""

from asci.policy.model import (
    ACTION_COST_MAP,
    ACTION_TO_IDX,
    CONTROLLER_ACTIONS,
    FEATURE_DIM,
    ControllerHistory,
    MaskedMLPPolicy,
    compute_action_mask,
    extract_controller_features,
)
from asci.policy.oracle import OracleSample, OracleTrajectoryGenerator
from asci.policy.train_mlp_controller import (
    TrainingReport,
    audit_gate_g4_citations,
    get_or_train_default_policy,
    train_masked_mlp_controller,
)

__all__ = [
    "ACTION_COST_MAP",
    "ACTION_TO_IDX",
    "CONTROLLER_ACTIONS",
    "ControllerHistory",
    "FEATURE_DIM",
    "MaskedMLPPolicy",
    "OracleSample",
    "OracleTrajectoryGenerator",
    "TrainingReport",
    "audit_gate_g4_citations",
    "compute_action_mask",
    "extract_controller_features",
    "get_or_train_default_policy",
    "train_masked_mlp_controller",
]

