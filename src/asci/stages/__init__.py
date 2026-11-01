"""
Pipeline Stages for Adaptive Supply Chain Intelligence Platform.
Implements Gate G1 Walking Skeleton:
Stage A (Perception) -> Stage B (Graph Risk) -> Stage C (Controller) -> Stage D (Optimiser & Verifier) -> Stage E (Dashboard).
"""

from __future__ import annotations

import random

from asci.core.contracts import OperatorResult, PipelineConfig
from asci.core.state import PipelineState
from asci.stages.stage_a_events import StageAEventPerception
from asci.stages.stage_b_graph import StageBCorridorRisk
from asci.stages.stage_c_controller import StageCController
from asci.stages.stage_d_optimiser import StageDOptimiserAndVerifier
from asci.stages.stage_e_dashboard import StageEDashboard


class WalkingSkeletonPipeline:
    """
    End-to-end Walking Skeleton Pipeline Runner (Gate G1).
    Executes all 5 stages in order, passing immutable state between them.
    """

    def __init__(
        self,
        stage_a: StageAEventPerception | None = None,
        stage_b: StageBCorridorRisk | None = None,
        stage_c: StageCController | None = None,
        stage_d: StageDOptimiserAndVerifier | None = None,
        stage_e: StageEDashboard | None = None,
    ) -> None:
        self.stage_a = stage_a or StageAEventPerception()
        self.stage_b = stage_b or StageBCorridorRisk()
        self.stage_c = stage_c or StageCController()
        self.stage_d = stage_d or StageDOptimiserAndVerifier()
        self.stage_e = stage_e or StageEDashboard()

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
    "StageCController",
    "StageDOptimiserAndVerifier",
    "StageEDashboard",
    "WalkingSkeletonPipeline",
]

