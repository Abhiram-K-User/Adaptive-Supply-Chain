"""
Pipeline Stages for Adaptive Supply Chain Intelligence Platform.
Implements Gate G1 Walking Skeleton:
Stage A (Perception) -> Stage B (Graph Risk) -> Stage C (Controller) -> Stage D (Optimiser & Verifier) -> Stage E (Dashboard).
"""

from __future__ import annotations

import random

from asci.core.contracts import OperatorResult, PipelineConfig
from asci.core.registry import get_canonical_registry
from asci.core.state import PipelineState
from asci.stages.stage_a_events import StageAEventPerception
from asci.stages.stage_b_graph import StageBCorridorRisk
from asci.stages.stage_b_propagate import (
    Tier1PropagationSimulator,
    Tier2DynamicCongestionSimulator,
)
from asci.stages.stage_c_controller import StageCController
from asci.stages.stage_d_optimiser import StageDOptimiserAndVerifier
from asci.stages.stage_e_dashboard import StageEDashboard
from asci.uskl.graph_store import CorridorGraphStore
from asci.uskl.timeseries_store import TimeSeriesStore
from asci.uskl.vector_store import SemanticVectorStore


class WalkingSkeletonPipeline:
    """
    End-to-end Walking Skeleton Pipeline Runner (Gate G1 / Gate G2 modular propagate).
    Executes stages in order, passing immutable state between them.
    """

    def __init__(
        self,
        stage_a: StageAEventPerception | None = None,
        stage_b: StageBCorridorRisk | None = None,
        stage_c: StageCController | None = None,
        stage_d: StageDOptimiserAndVerifier | None = None,
        stage_e: StageEDashboard | None = None,
        propagate: Tier1PropagationSimulator | Tier2DynamicCongestionSimulator | None = None,
        enable_propagate_step: bool = False,
    ) -> None:
        self.stage_a = stage_a or StageAEventPerception()
        self.stage_b = stage_b or StageBCorridorRisk()
        self.propagate = propagate or Tier1PropagationSimulator()
        self.enable_propagate_step = enable_propagate_step
        self.stage_c = stage_c or StageCController()
        self.stage_d = stage_d or StageDOptimiserAndVerifier()
        self.stage_e = stage_e or StageEDashboard()

    @classmethod
    def from_config(
        cls,
        cfg: PipelineConfig,
        enable_propagate_step: bool = False,
    ) -> WalkingSkeletonPipeline:
        """Construct a pipeline cleanly bound to `cfg.network_scale` or custom seed paths."""
        registry = get_canonical_registry(
            seed_path=cfg.seed_registry_path,
            network_scale=cfg.network_scale,
        )
        graph_store = CorridorGraphStore.load_from_json(
            seed_path=cfg.seed_graph_path,
            registry=registry,
            network_scale=cfg.network_scale,
        )
        vector_store = SemanticVectorStore(registry=registry)
        ts_store = TimeSeriesStore(registry=registry)
        prop_op: Tier1PropagationSimulator | Tier2DynamicCongestionSimulator = (
            Tier2DynamicCongestionSimulator(graph_store=graph_store, registry=registry)
            if cfg.propagation_tier >= 2
            else Tier1PropagationSimulator(graph_store=graph_store, registry=registry)
        )
        return cls(
            stage_a=StageAEventPerception(registry=registry),
            stage_b=StageBCorridorRisk(graph_store=graph_store, registry=registry),
            stage_c=StageCController(
                vector_store=vector_store,
                timeseries_store=ts_store,
                registry=registry,
            ),
            stage_d=StageDOptimiserAndVerifier(registry=registry, graph_store=graph_store),
            stage_e=StageEDashboard(registry=registry, graph_store=graph_store),
            propagate=prop_op,
            enable_propagate_step=enable_propagate_step,
        )

    def run(
        self,
        state: PipelineState,
        cfg: PipelineConfig,
        rng: random.Random | None = None,
    ) -> tuple[PipelineState, list[OperatorResult]]:
        """
        Execute the full Stage A -> E pipeline sequentially and deterministically.
        """
        if rng is None:
            rng = random.Random(cfg.random_seed)

        results: list[OperatorResult] = []

        # Stage A: Perception
        state, res_a = self.stage_a.run(state, cfg, rng)
        results.append(res_a)
        if not res_a.success:
            return state, results

        # Stage B: Corridor Graph Analysis
        state, res_b = self.stage_b.run(state, cfg, rng)
        results.append(res_b)
        if not res_b.success:
            return state, results

        if self.enable_propagate_step:
            state, res_prop = self.propagate.run(state, cfg, rng)
            results.append(res_prop)
            if not res_prop.success:
                return state, results

        # Stage C: Controller & Scenarios
        state, res_c = self.stage_c.run(state, cfg, rng)
        results.append(res_c)
        if not res_c.success:
            return state, results

        # Stage D: Optimiser & L1-L3 Verifier
        state, res_d = self.stage_d.run(state, cfg, rng)
        results.append(res_d)
        if not res_d.success:
            return state, results

        # Stage E: Dashboard Payload Serializer
        state, res_e = self.stage_e.run(state, cfg, rng)
        results.append(res_e)

        return state, results


__all__ = [
    "StageAEventPerception",
    "StageBCorridorRisk",
    "Tier1PropagationSimulator",
    "Tier2DynamicCongestionSimulator",
    "StageCController",
    "StageDOptimiserAndVerifier",
    "StageEDashboard",
    "WalkingSkeletonPipeline",
]

