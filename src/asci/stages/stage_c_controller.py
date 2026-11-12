"""
Stage C: Controller & Scenario Parameterization Core.
Rule-router controller executing masked retrieval, time-series recovery querying,
and scenario generation under step and cost budgets.
"""

from __future__ import annotations

import math
import random
import time
from datetime import datetime, timezone

from asci.core.contracts import OperatorResult, PipelineConfig
from asci.core.registry import CanonicalEntityRegistry, get_canonical_registry
from asci.core.state import (
    OperatorTraceItem,
    OperatorType,
    PipelineState,
    PipelineStatus,
    Scenario,
    TrustTier,
)
from asci.uskl.timeseries_store import TimeSeriesStore
from asci.uskl.vector_store import SemanticVectorStore


class StageCController:
    """
    Stage C Operator: Budget-Aware Rule-Router Controller.
    Executes entity-tagged retrieval (with fallback query broadening when evidence is sparse),
    multi-day time-series recovery parameterization, and scenario formulation under masking rules.
    """

    def __init__(
        self,
        vector_store: SemanticVectorStore | None = None,
        timeseries_store: TimeSeriesStore | None = None,
        registry: CanonicalEntityRegistry | None = None,
    ) -> None:
        self.registry = registry or get_canonical_registry()
        self.vector_store = vector_store or SemanticVectorStore(registry=self.registry)
        self.timeseries_store = timeseries_store or TimeSeriesStore(registry=self.registry)

    def run(
        self,
        state: PipelineState,
        cfg: PipelineConfig,
        rng: random.Random,
    ) -> tuple[PipelineState, OperatorResult]:
        """
        Execute Stage C controller step while preserving Gate G1 1-trace-per-stage cadence.
        Applies masking rules:
        - Enforces step limit (T <= max_steps)
        - SCENARIOS is masked until event & graph_context exist
        - Uses deterministic event date for vector expiry filtering
        """
        _ = rng
        t0 = time.perf_counter()

        # Masking Rule 1: Step budget exhaustion check
        if state.step_count >= cfg.max_steps:
            trace_item = OperatorTraceItem(
                step_index=state.step_count + 1,
                operator_type=OperatorType.ESCALATE,
                input_summary=f"Step count {state.step_count} >= max {cfg.max_steps}",
                output_summary="Forced escalation due to computational step budget exhaustion",
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
        primary_ent = self.registry.get(event.primary_entity_id)
        as_of_date = event.timestamp.strftime("%Y-%m-%d")

        query_text = (
            f"{event.event_type.value} {primary_ent.name} {event.primary_entity_id} "
            f"{event.raw_headline}"
        )

        # 1. RETRIEVE_TEXT operator execution (deterministic event timestamp & entity filter)
        entity_filter = [event.primary_entity_id] + [
            eid for eid in event.affected_entity_ids if eid != event.primary_entity_id
        ]
        retrieved_docs = self.vector_store.query(
            query_text=query_text,
            entity_ids=entity_filter,
            min_trust_tier=TrustTier.TIER_B,
            as_of_date=as_of_date,
            limit=3,
        )

        # Evidence grading & budget-aware query rewrite if direct Tier A/B evidence is insufficient
        query_rewritten = False
        best_rel = max((d.relevance_score for d in retrieved_docs), default=0.0)
        rewrite_cost = 0.0020
        can_afford_rewrite = (cfg.lambda_cost_budget <= 0.15) or (len(retrieved_docs) == 0)
        if (len(retrieved_docs) == 0 or best_rel < 0.12) and can_afford_rewrite:
            query_rewritten = True
            broadened_query = (
                f"{primary_ent.region} {event.event_type.value} corridor diversion playbook"
            )
            broadened = self.vector_store.query(
                query_text=broadened_query,
                region=primary_ent.region,
                min_trust_tier=TrustTier.TIER_B,
                as_of_date=as_of_date,
                limit=3,
            )
            if not broadened and not retrieved_docs:
                broadened = self.vector_store.query(
                    query_text=broadened_query,
                    region=primary_ent.region,
                    as_of_date=as_of_date,
                    limit=3,
                )
            seen_cits = {d.citation_id for d in retrieved_docs}
            for doc in broadened:
                if doc.citation_id not in seen_cits:
                    retrieved_docs.append(doc)
                    seen_cits.add(doc.citation_id)
            retrieved_docs = retrieved_docs[:3]

        # 2. RETRIEVE_TS operator execution (aggregate over event duration window)
        recovery_trajectory = self.timeseries_store.get_recovery_curve(
            event.primary_entity_id,
            event.event_type.value,
        )
        window = min(len(recovery_trajectory), max(1, math.ceil(event.estimated_duration_days)))
        ts_mean_mult = (
            sum(recovery_trajectory[:window]) / window if recovery_trajectory else 0.35
        )
        severity_residual = max(0.05, 1.0 - event.severity)
        expected_mult = round(max(0.05, min(0.95, 0.5 * ts_mean_mult + 0.5 * severity_residual)), 2)
        severe_mult = round(max(0.05, expected_mult * 0.45), 2)
        rapid_mult = round(min(0.90, max(expected_mult + 0.25, 0.55)), 2)

        # Adjust scenario weights using corroboration confidence & evidence sufficiency
        evidence_conf = min(1.0, (event.confidence + best_rel) / 1.5)
        p_expected = round(0.55 + 0.10 * evidence_conf, 2)
        p_severe = round(max(0.15, 0.35 - 0.10 * evidence_conf), 2)
        p_rapid = round(max(0.05, 1.0 - p_expected - p_severe), 2)

        # 3. SCENARIOS operator execution: Probability-weighted discrete scenarios
        scenarios = [
            Scenario(
                scenario_id="SCENARIO_EXPECTED",
                name="Most Likely (Calibrated Recovery)",
                probability=p_expected,
                capacity_multipliers={event.primary_entity_id: expected_mult},
                duration_days=event.estimated_duration_days,
            ),
            Scenario(
                scenario_id="SCENARIO_SEVERE",
                name="Severe Cascade (Extended Disruption)",
                probability=p_severe,
                capacity_multipliers={event.primary_entity_id: severe_mult},
                duration_days=min(14.0, round(event.estimated_duration_days * 1.75, 2)),
            ),
            Scenario(
                scenario_id="SCENARIO_RAPID",
                name="Rapid Clearance (Minor Event)",
                probability=p_rapid,
                capacity_multipliers={event.primary_entity_id: rapid_mult},
                duration_days=max(1.0, round(event.estimated_duration_days * 0.5, 2)),
            ),
        ]

        duration_ms = (time.perf_counter() - t0) * 1000.0
        op_cost = 0.0050 + (rewrite_cost if query_rewritten else 0.0)

        trace_item = OperatorTraceItem(
            step_index=state.step_count + 1,
            operator_type=OperatorType.SCENARIOS,
            input_summary=f"Event {event.event_id}, retrieved docs={len(retrieved_docs)}, rewrite={query_rewritten}",
            output_summary=f"Formulated {len(scenarios)} calibrated disruption scenarios",
            duration_ms=round(duration_ms, 2),
            cost=round(op_cost, 6),
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
                f"(query_rewritten={query_rewritten}) and parameterized {len(scenarios)} scenarios."
            ),
            duration_ms=round(duration_ms, 2),
            cost=round(op_cost, 6),
            artifacts={
                "evidence_count": len(retrieved_docs),
                "scenario_count": len(scenarios),
                "query_rewritten": query_rewritten,
                "as_of_date": as_of_date,
                "encoder_backend": self.vector_store.encoder_backend,
            },
        )

        return new_state, result
