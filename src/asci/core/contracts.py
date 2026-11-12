"""
Operator protocol, execution contracts, and configuration schemas.
Enforces the immutable boundary:
run(state: PipelineState, cfg: PipelineConfig, rng: random.Random) -> tuple[PipelineState, OperatorResult]
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from asci.core.state import OperatorType, PipelineState


class PipelineConfig(BaseModel):
    """Execution parameters and computational budget configuration."""

    model_config = ConfigDict(frozen=True)

    lambda_cost_budget: float = Field(
        default=0.05,
        ge=0.0,
        description="Cost penalty lambda balancing search cost against regret",
    )
    max_steps: int = Field(default=12, ge=1, le=50, description="Hard step limit per Section 6.3")
    random_seed: int = Field(default=42, description="Deterministic seed for reproducibility")
    solver_type: str = Field(default="OR_TOOLS", description="Primary solver engine")
    risk_mode: Literal["DETERMINISTIC", "EXPECTED_COST", "CVAR"] = Field(
        default="EXPECTED_COST",
        description="Optimization risk mode across scenario_set",
    )
    cvar_alpha: float = Field(
        default=0.90,
        ge=0.5,
        lt=1.0,
        description="Tail confidence quantile alpha for CVaR risk-aware planning",
    )
    cvar_weight: float = Field(
        default=0.50,
        ge=0.0,
        le=1.0,
        description="Convex combination weight on CVaR tail risk vs expected cost",
    )
    enable_multi_commodity: bool = Field(
        default=True,
        description="Disaggregate automotive cargo across component sub-commodities",
    )
    enable_propagation: bool = Field(
        default=True,
        description="Enable cascading spillover propagation in Stage B",
    )
    propagation_tier: Literal[1, 2] = Field(
        default=2,
        description="Propagation model tier: 1=BFS hop-decay, 2=dynamic BPR load redistribution",
    )
    network_scale: Literal["v0_core", "v1_corridor"] = Field(
        default="v0_core",
        description="Corridor seed topology scale: 23-node Gate G0/G1 core or 100-150 node Gate G2 graph",
    )
    line_stop_penalty_per_day: float = Field(
        default=25000.0,
        ge=0.0,
        description="Daily penalty weight for plant assembly delay exceeding days-of-cover",
    )
    evidence_trust_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    k_hop_neighborhood: int = Field(default=2, ge=1, le=5)
    max_unmet_demand_ratio: float = Field(default=0.05, ge=0.0, le=1.0)
    seed_registry_path: Path | None = None
    seed_graph_path: Path | None = None


class OperatorResult(BaseModel):
    """Standardized output structure for every pipeline operator."""

    model_config = ConfigDict(frozen=True)

    operator_type: OperatorType
    success: bool
    message: str
    duration_ms: float = Field(default=0.0, ge=0.0)
    cost: float = Field(default=0.0, ge=0.0)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class Operator(Protocol):
    """
    Formal operator protocol governing all stage operators and tools.
    Every operator must follow this signature without modifying state in-place.
    """

    def run(
        self,
        state: PipelineState,
        cfg: PipelineConfig,
        rng: random.Random,
    ) -> tuple[PipelineState, OperatorResult]:
        """
        Execute operator deterministically.
        Returns a new immutable PipelineState instance and an OperatorResult.
        """
        ...

