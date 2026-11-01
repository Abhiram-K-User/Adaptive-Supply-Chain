"""
Stage C: Agentic RAG Controller & Computation Core.
Rule-Router Baseline executing masked operator sequencing under a computational budget.
"""

from __future__ import annotations

import random
import time
from datetime import datetime, timezone

from asci.core.contracts import OperatorResult, PipelineConfig
from asci.core.state import (
    EvidenceItem,
    OperatorTraceItem,
    OperatorType,
    PipelineState,
    PipelineStatus,
    Scenario,
)
from asci.uskl.timeseries_store import TimeSeriesStore
from asci.uskl.vector_store import SemanticVectorStore


class StageCController:
    """
    Stage C Operator: Rule-Router Controller Core.
    Executes text retrieval, time-series querying, and scenario generation under strict masking rules.
    """

    def __init__(
        self,
        vector_store: SemanticVectorStore | None = None,
        timeseries_store: TimeSeriesStore | None = None,
    ) -> None:
        self.vector_store = vector_store or SemanticVectorStore()
        self.timeseries_store = timeseries_store or TimeSeriesStore()

    def run(
        self,
        state: PipelineState,
        cfg: PipelineConfig,
        rng: random.Random,
    ) -> tuple[PipelineState, OperatorResult]:
        """
        Execute Stage C controller loop.
        Applies masking rules:
        - Must have graph context before scenario generation
        - Retrieves evidence and parameterizes discrete scenarios
        - Enforces step limit (T <= 12)
        """
        t0 = time.perf_counter()

        # Masking Rule 1: Step budget exhaustion check
        if state.step_count >= cfg.max_steps:
            trace_item = OperatorTraceItem(
                step_index=state.step_count + 1,
                operator_type=OperatorType.ESCALATE,
                input_summary=f"Step count {state.step_count} >= max {cfg.max_steps}",
                output_summary="Forced escalation due to computational budget exhaustion",
                duration_ms=1.0,
                cost=0.0,
                seed=cfg.random_seed,
            )
            escalated_state = state.transition(
                updates={"status": PipelineStatus.ESCALATED},
                trace_item=trace_item,
            )
            return escalated_state, OperatorResult(
                operator_type=OperatorType.ESCALATE,
                success=False,
                message=f"Computational step budget {cfg.max_steps} exhausted; escalated to human planner.",
                error="STEP_BUDGET_EXHAUSTED",
            )

        # Masking Rule 2: SCENARIOS is masked until graph context exists
        if not state.graph_context or not state.event:
            error_msg = "Stage C masking violation: graph context or event missing before controller execution."
            return state, OperatorResult(
                operator_type=OperatorType.SCENARIOS,
                success=False,
                message=error_msg,
                error=error_msg,
            )

        event = state.event
        query_text = f"{event.event_type.value} disruption at {event.primary_entity_id} {event.raw_headline}"

        # 1. RETRIEVE_TEXT operator execution
        retrieved_docs = self.vector_store.query(
            query_text=query_text,
            entity_ids=[event.primary_entity_id] + event.affected_entity_ids,
            limit=3,
        )

        # 2. RETRIEVE_TS operator execution
        recovery_trajectory = self.timeseries_store.get_recovery_curve(
            event.primary_entity_id,
            event.event_type.value,
        )

        # 3. SCENARIOS operator execution: Generate probability-weighted discrete scenarios
        scenarios = [
            Scenario(
                scenario_id="SCENARIO_EXPECTED",
                name="Most Likely (Baseline Recovery)",
                probability=0.60,
                capacity_multipliers={
                    event.primary_entity_id: recovery_trajectory[0] if recovery_trajectory else 0.2,
                },
                duration_days=event.estimated_duration_days,
            ),
            Scenario(
                scenario_id="SCENARIO_SEVERE",
                name="Severe Cascade (Extended Disruption)",
                probability=0.30,
                capacity_multipliers={
                    event.primary_entity_id: 0.05,
                },
                duration_days=min(14.0, event.estimated_duration_days * 1.75),
            ),
            Scenario(
                scenario_id="SCENARIO_RAPID",
                name="Rapid Clearance (Minor Event)",
                probability=0.10,
                capacity_multipliers={
                    event.primary_entity_id: 0.60,
                },
                duration_days=max(1.0, event.estimated_duration_days * 0.5),
            ),
        ]

        duration_ms = (time.perf_counter() - t0) * 1000.0
        op_cost = 0.0050

        trace_item = OperatorTraceItem(
            step_index=state.step_count + 1,
            operator_type=OperatorType.SCENARIOS,
            input_summary=f"Event {event.event_id}, retrieved docs={len(retrieved_docs)}",
            output_summary=f"Formulated {len(scenarios)} discrete disruption scenarios",
            duration_ms=round(duration_ms, 2),
            cost=op_cost,
            seed=cfg.random_seed,
            timestamp=datetime.now(timezone.utc),
        )

        new_state = state.transition(
            updates={
                "evidence_set": retrieved_docs,
                "scenario_set": scenarios,
                "status": PipelineStatus.ANALYZED,
            },
            trace_item=trace_item,
        )

        result = OperatorResult(
            operator_type=OperatorType.SCENARIOS,
            success=True,
            message=(
                f"Stage C controller retrieved {len(retrieved_docs)} evidence items "
                f"and parameterized {len(scenarios)} discrete scenarios."
            ),
            duration_ms=round(duration_ms, 2),
            cost=op_cost,
            artifacts={
                "evidence_count": len(retrieved_docs),
                "scenario_count": len(scenarios),
            },
        )

        return new_state, result

