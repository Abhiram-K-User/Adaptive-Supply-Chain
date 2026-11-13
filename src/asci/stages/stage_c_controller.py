"""
Stage C Operator: Multi-Step Budget-Aware Agentic-RAG Controller (Gate G1 & Gate G4).
Supports explicit state-conditioned transitions across:
    RETRIEVE_TEXT, GRADE, REWRITE_QUERY, RETRIEVE_TS, RETRIEVE_DECISIONS, SCENARIOS, ESCALATE
under formal precondition masking and compute penalty lambda.

Controller modes (`cfg.controller_mode`):
- "rule_router": Gate G1 deterministic heuristic router (default).
- "learned_mlp": Gate G4 PyTorch MaskedMLPPolicy conditioned on PipelineState + lambda.
- "always_full": Baseline executing the full retrieval + rewrite operator chain.
- "fixed_rag": Baseline executing static single-pass retrieval without grading/rewrite.
- "no_rag": Baseline skipping external retrieval and moving directly to SCENARIOS.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from asci.core.contracts import OperatorResult, PipelineConfig
from asci.core.registry import CanonicalEntityRegistry, get_canonical_registry
from asci.core.state import (
    DisruptionEvent,
    EvidenceItem,
    OperatorTraceItem,
    OperatorType,
    PipelineState,
    PipelineStatus,
    Scenario,
    TrustTier,
)
from asci.policy.model import (
    ACTION_COST_MAP,
    ACTION_TO_IDX,
    ControllerHistory,
    MaskedMLPPolicy,
    compute_action_mask,
    extract_controller_features,
)
from asci.policy.train_mlp_controller import get_or_train_default_policy
from asci.uskl.decision_store import DecisionTraceStore
from asci.uskl.timeseries_store import TimeSeriesStore
from asci.uskl.vector_store import SemanticVectorStore


@dataclass
class _StageCEpisodeContext:
    """Mutable working accumulator inside a single Stage C controller execution."""

    event: DisruptionEvent
    primary_entity_name: str
    primary_entity_region: str
    as_of_date: str
    retrieved_docs: list[EvidenceItem] = field(default_factory=list)
    sufficiency: float = 0.0
    best_rel: float = 0.0
    query_rewritten: bool = False
    active_query: str = ""
    ts_mean_mult: float = 0.35
    precedents: list[dict[str, Any]] = field(default_factory=list)
    capacity_override: float | None = None
    scenarios: list[Scenario] = field(default_factory=list)
    operator_sequence: list[str] = field(default_factory=list)
    total_cost: float = 0.0
    mask_violations: int = 0


class StageCController:
    """
    Stage C Operator: Multi-Step Budget-Aware Agentic-RAG Controller.
    Executes explicit masked transitions across:
    RETRIEVE_TEXT -> GRADE -> [REWRITE_QUERY] -> RETRIEVE_TS -> RETRIEVE_DECISIONS -> SCENARIOS.
    """

    def __init__(
        self,
        vector_store: SemanticVectorStore | None = None,
        timeseries_store: TimeSeriesStore | None = None,
        registry: CanonicalEntityRegistry | None = None,
        decision_store: DecisionTraceStore | None = None,
        policy: MaskedMLPPolicy | None = None,
    ) -> None:
        self.registry = registry or get_canonical_registry()
        self.vector_store = vector_store or SemanticVectorStore(registry=self.registry)
        self.timeseries_store = timeseries_store or TimeSeriesStore(registry=self.registry)
        self.decision_store = decision_store
        self.policy = policy

    def _grade_evidence(
        self,
        docs: list[EvidenceItem],
        event: DisruptionEvent,
    ) -> tuple[float, float]:
        """Compute sufficiency score [0..1] and max relevance from entity/claim/trust coverage."""
        if not docs:
            return 0.0, 0.0
        best_rel = max(d.relevance_score for d in docs)
        target_entities = {event.primary_entity_id, *event.affected_entity_ids}
        entity_hits = sum(
            1 for d in docs if any(eid in target_entities for eid in d.entity_ids)
        )
        tier_a_hits = sum(1 for d in docs if d.trust_tier == TrustTier.TIER_A)
        sufficiency = min(
            1.0,
            0.45 * best_rel
            + 0.30 * min(1.0, entity_hits / max(1, len(docs)))
            + 0.25 * min(1.0, (len(docs) + tier_a_hits) / 4.0),
        )
        return round(sufficiency, 3), round(best_rel, 3)

    def _resolve_policy(self, cfg: PipelineConfig) -> MaskedMLPPolicy:
        """Return injected policy, load configured checkpoint, or train default cached policy."""
        if self.policy is not None:
            return self.policy
        if cfg.policy_checkpoint_path is not None:
            loaded, _ = MaskedMLPPolicy.load_checkpoint(cfg.policy_checkpoint_path)
            self.policy = loaded
            return loaded
        trained, _ = get_or_train_default_policy(seed=42)
        self.policy = trained
        return trained

    def _op_escalate(
        self,
        state: PipelineState,
        cfg: PipelineConfig,
        reason: str,
        error_code: str,
    ) -> tuple[PipelineState, OperatorResult]:
        trace_item = OperatorTraceItem(
            step_index=state.step_count + 1,
            operator_type=OperatorType.ESCALATE,
            input_summary=f"Step count {state.step_count} / max {cfg.max_steps}",
            output_summary=reason,
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
            message=reason,
            error=error_code,
        )

    def _step_retrieve_text(
        self,
        state: PipelineState,
        cfg: PipelineConfig,
        ctx: _StageCEpisodeContext,
        history: ControllerHistory,
    ) -> PipelineState:
        t_step = time.perf_counter()
        event = ctx.event
        if not ctx.active_query:
            ctx.active_query = (
                f"{event.event_type.value} {ctx.primary_entity_name} {event.primary_entity_id} "
                f"{event.raw_headline}"
            )
        entity_filter = [event.primary_entity_id] + [
            eid for eid in event.affected_entity_ids if eid != event.primary_entity_id
        ]
        fetched = self.vector_store.query(
            query_text=ctx.active_query,
            entity_ids=entity_filter,
            min_trust_tier=TrustTier.TIER_B,
            as_of_date=ctx.as_of_date,
            limit=3,
        )
        if history.last_rewritten and ctx.retrieved_docs:
            seen_cits = {d.citation_id for d in ctx.retrieved_docs}
            for doc in fetched:
                if doc.citation_id not in seen_cits:
                    ctx.retrieved_docs.append(doc)
                    seen_cits.add(doc.citation_id)
            ctx.retrieved_docs = ctx.retrieved_docs[:3]
        else:
            ctx.retrieved_docs = fetched

        cost = ACTION_COST_MAP[OperatorType.RETRIEVE_TEXT]
        ctx.total_cost = round(ctx.total_cost + cost, 6)
        ctx.operator_sequence.append(OperatorType.RETRIEVE_TEXT.value)
        history.steps_taken += 1
        history.text_retrievals += 1
        history.has_ungraded_evidence = True
        history.last_rewritten = False
        history.cumulative_cost = ctx.total_cost

        return state.transition(
            updates={"evidence_set": list(ctx.retrieved_docs)},
            trace_item=OperatorTraceItem(
                step_index=state.step_count + 1,
                operator_type=OperatorType.RETRIEVE_TEXT,
                input_summary=(
                    f"Query vector store for {event.primary_entity_id} "
                    f"({event.event_type.value}, as_of={ctx.as_of_date})"
                ),
                output_summary=f"Retrieved {len(ctx.retrieved_docs)} direct Tier-A/B evidence chunks",
                duration_ms=round((time.perf_counter() - t_step) * 1000.0, 2),
                cost=cost,
                seed=cfg.random_seed,
                timestamp=datetime.now(UTC),
            ),
        )

    def _step_grade(
        self,
        state: PipelineState,
        cfg: PipelineConfig,
        ctx: _StageCEpisodeContext,
        history: ControllerHistory,
    ) -> tuple[PipelineState, bool]:
        t_step = time.perf_counter()
        sufficiency, best_rel = self._grade_evidence(ctx.retrieved_docs, ctx.event)
        ctx.sufficiency = sufficiency
        ctx.best_rel = best_rel

        needs_rewrite = len(ctx.retrieved_docs) == 0 or best_rel < 0.12 or sufficiency < 0.35
        can_afford_rewrite = (cfg.lambda_cost_budget <= 0.15) or (len(ctx.retrieved_docs) == 0)
        will_rewrite = needs_rewrite and can_afford_rewrite

        cost = ACTION_COST_MAP[OperatorType.GRADE]
        ctx.total_cost = round(ctx.total_cost + cost, 6)
        ctx.operator_sequence.append(OperatorType.GRADE.value)
        history.steps_taken += 1
        history.grade_calls += 1
        history.has_ungraded_evidence = False
        history.grade_sufficient = not needs_rewrite
        history.cumulative_cost = ctx.total_cost

        new_state = state.transition(
            updates={},
            trace_item=OperatorTraceItem(
                step_index=state.step_count + 1,
                operator_type=OperatorType.GRADE,
                input_summary=f"Grade {len(ctx.retrieved_docs)} passages (best_rel={best_rel:.3f})",
                output_summary=(
                    f"Sufficiency={sufficiency:.3f}; trigger_rewrite={will_rewrite} "
                    f"(lambda={cfg.lambda_cost_budget})"
                ),
                duration_ms=round((time.perf_counter() - t_step) * 1000.0, 2),
                cost=cost,
                seed=cfg.random_seed,
                timestamp=datetime.now(UTC),
            ),
        )
        return new_state, will_rewrite

    def _step_rewrite_query(
        self,
        state: PipelineState,
        cfg: PipelineConfig,
        ctx: _StageCEpisodeContext,
        history: ControllerHistory,
    ) -> PipelineState:
        t_step = time.perf_counter()
        event = ctx.event
        ctx.query_rewritten = True
        broadened_query = (
            f"{ctx.primary_entity_region} {event.event_type.value} corridor diversion playbook"
        )
        ctx.active_query = broadened_query

        broadened = self.vector_store.query(
            query_text=broadened_query,
            region=ctx.primary_entity_region,
            min_trust_tier=TrustTier.TIER_B,
            as_of_date=ctx.as_of_date,
            limit=3,
        )
        if not broadened and not ctx.retrieved_docs:
            broadened = self.vector_store.query(
                query_text=broadened_query,
                region=ctx.primary_entity_region,
                as_of_date=ctx.as_of_date,
                limit=3,
            )
        if not broadened and not ctx.retrieved_docs:
            broadened = self.vector_store.query(
                query_text=f"{event.event_type.value} port rail corridor diversion",
                as_of_date=ctx.as_of_date,
                limit=3,
            )
        seen_cits = {d.citation_id for d in ctx.retrieved_docs}
        for doc in broadened:
            if doc.citation_id not in seen_cits:
                ctx.retrieved_docs.append(doc)
                seen_cits.add(doc.citation_id)
        ctx.retrieved_docs = ctx.retrieved_docs[:3]
        ctx.sufficiency, ctx.best_rel = self._grade_evidence(ctx.retrieved_docs, event)

        cost = ACTION_COST_MAP[OperatorType.REWRITE_QUERY]
        ctx.total_cost = round(ctx.total_cost + cost, 6)
        ctx.operator_sequence.append(OperatorType.REWRITE_QUERY.value)
        history.steps_taken += 1
        history.rewrite_count += 1
        history.last_rewritten = True
        history.cumulative_cost = ctx.total_cost

        return state.transition(
            updates={"evidence_set": list(ctx.retrieved_docs)},
            trace_item=OperatorTraceItem(
                step_index=state.step_count + 1,
                operator_type=OperatorType.REWRITE_QUERY,
                input_summary=f"Rewrite sparse query -> '{broadened_query}'",
                output_summary=(
                    f"Expanded evidence set to {len(ctx.retrieved_docs)} chunks "
                    f"(sufficiency={ctx.sufficiency:.3f})"
                ),
                duration_ms=round((time.perf_counter() - t_step) * 1000.0, 2),
                cost=cost,
                seed=cfg.random_seed,
                timestamp=datetime.now(UTC),
            ),
        )

    def _step_retrieve_ts(
        self,
        state: PipelineState,
        cfg: PipelineConfig,
        ctx: _StageCEpisodeContext,
        history: ControllerHistory,
    ) -> PipelineState:
        t_step = time.perf_counter()
        recovery_trajectory = self.timeseries_store.get_recovery_curve(
            ctx.event.primary_entity_id,
            ctx.event.event_type.value,
        )
        window = min(len(recovery_trajectory), max(1, math.ceil(ctx.event.estimated_duration_days)))
        ctx.ts_mean_mult = (
            sum(recovery_trajectory[:window]) / window if recovery_trajectory else 0.35
        )
        cost = ACTION_COST_MAP[OperatorType.RETRIEVE_TS]
        ctx.total_cost = round(ctx.total_cost + cost, 6)
        ctx.operator_sequence.append(OperatorType.RETRIEVE_TS.value)
        history.steps_taken += 1
        history.ts_retrieved = True
        history.cumulative_cost = ctx.total_cost

        return state.transition(
            updates={},
            trace_item=OperatorTraceItem(
                step_index=state.step_count + 1,
                operator_type=OperatorType.RETRIEVE_TS,
                input_summary=(
                    f"Query recovery trajectory for {ctx.event.primary_entity_id} (window={window}d)"
                ),
                output_summary=(
                    f"Mean recovery multiplier={ctx.ts_mean_mult:.2f} over "
                    f"{len(recovery_trajectory)}d curve"
                ),
                duration_ms=round((time.perf_counter() - t_step) * 1000.0, 2),
                cost=cost,
                seed=cfg.random_seed,
                timestamp=datetime.now(UTC),
            ),
        )

    def _step_retrieve_decisions(
        self,
        state: PipelineState,
        cfg: PipelineConfig,
        ctx: _StageCEpisodeContext,
        history: ControllerHistory,
    ) -> PipelineState:
        t_step = time.perf_counter()
        precedents = (
            self.decision_store.query_precedent_decisions(
                event_id=ctx.event.event_id,
                entity_id=ctx.event.primary_entity_id,
                limit=5,
            )
            if self.decision_store is not None
            else []
        )
        ctx.precedents = precedents
        for prec in precedents:
            mods = prec.get("modifications") or {}
            if isinstance(mods, dict) and "capacity_multiplier_override" in mods:
                try:
                    val = float(mods["capacity_multiplier_override"])
                    ctx.capacity_override = max(0.05, min(0.95, val))
                    break
                except (TypeError, ValueError):
                    pass

        cost = ACTION_COST_MAP[OperatorType.RETRIEVE_DECISIONS]
        ctx.total_cost = round(ctx.total_cost + cost, 6)
        ctx.operator_sequence.append(OperatorType.RETRIEVE_DECISIONS.value)
        history.steps_taken += 1
        history.decisions_retrieved = True
        history.cumulative_cost = ctx.total_cost

        return state.transition(
            updates={},
            trace_item=OperatorTraceItem(
                step_index=state.step_count + 1,
                operator_type=OperatorType.RETRIEVE_DECISIONS,
                input_summary=(
                    f"Lookup Loop L2 human planner precedents for "
                    f"{ctx.event.primary_entity_id}/{ctx.event.event_id}"
                ),
                output_summary=(
                    f"Matched {len(precedents)} prior APPROVE/EDIT decisions"
                    + (
                        f"; cap_override={ctx.capacity_override:.2f}"
                        if ctx.capacity_override is not None
                        else ""
                    )
                ),
                duration_ms=round((time.perf_counter() - t_step) * 1000.0, 2),
                cost=cost,
                seed=cfg.random_seed,
                timestamp=datetime.now(UTC),
            ),
        )

    def _step_scenarios(
        self,
        state: PipelineState,
        cfg: PipelineConfig,
        ctx: _StageCEpisodeContext,
        history: ControllerHistory,
    ) -> PipelineState:
        t_step = time.perf_counter()
        event = ctx.event
        severity_residual = max(0.05, 1.0 - event.severity)
        expected_mult = round(
            ctx.capacity_override
            if ctx.capacity_override is not None
            else max(0.05, min(0.95, 0.5 * ctx.ts_mean_mult + 0.5 * severity_residual)),
            2,
        )
        severe_mult = round(max(0.05, expected_mult * 0.45), 2)
        rapid_mult = round(min(0.90, max(expected_mult + 0.25, 0.55)), 2)

        precedent_boost = min(0.15, 0.05 * len(ctx.precedents))
        evidence_conf = min(1.0, (event.confidence + ctx.best_rel) / 1.5 + precedent_boost)
        p_expected = round(0.55 + 0.10 * evidence_conf, 2)
        p_severe = round(max(0.15, 0.35 - 0.10 * evidence_conf), 2)
        p_rapid = round(max(0.05, 1.0 - p_expected - p_severe), 2)

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
        ctx.scenarios = scenarios
        cost = ACTION_COST_MAP[OperatorType.SCENARIOS]
        ctx.total_cost = round(ctx.total_cost + cost, 6)
        ctx.operator_sequence.append(OperatorType.SCENARIOS.value)
        history.steps_taken += 1
        history.scenarios_generated = True
        history.cumulative_cost = ctx.total_cost

        return state.transition(
            updates={
                "evidence_set": list(ctx.retrieved_docs),
                "scenario_set": scenarios,
                "status": PipelineStatus.ANALYZED,
            },
            trace_item=OperatorTraceItem(
                step_index=state.step_count + 1,
                operator_type=OperatorType.SCENARIOS,
                input_summary=(
                    f"Event {event.event_id}, docs={len(ctx.retrieved_docs)}, "
                    f"precedents={len(ctx.precedents)}, rewrite={ctx.query_rewritten}"
                ),
                output_summary=f"Formulated {len(scenarios)} calibrated disruption scenarios",
                duration_ms=round((time.perf_counter() - t_step) * 1000.0, 2),
                cost=cost,
                seed=cfg.random_seed,
                timestamp=datetime.now(UTC),
            ),
        )

    def _execute_operator(
        self,
        op: OperatorType,
        state: PipelineState,
        cfg: PipelineConfig,
        ctx: _StageCEpisodeContext,
        history: ControllerHistory,
    ) -> tuple[PipelineState, bool]:
        """Dispatch single validated Stage C operator and return `(updated_state, will_rewrite)`."""
        if op == OperatorType.RETRIEVE_TEXT:
            return self._step_retrieve_text(state, cfg, ctx, history), False
        if op == OperatorType.GRADE:
            return self._step_grade(state, cfg, ctx, history)
        if op == OperatorType.REWRITE_QUERY:
            return self._step_rewrite_query(state, cfg, ctx, history), False
        if op == OperatorType.RETRIEVE_TS:
            return self._step_retrieve_ts(state, cfg, ctx, history), False
        if op == OperatorType.RETRIEVE_DECISIONS:
            return self._step_retrieve_decisions(state, cfg, ctx, history), False
        if op == OperatorType.SCENARIOS:
            return self._step_scenarios(state, cfg, ctx, history), False
        raise ValueError(f"Unsupported Stage C operator dispatch: {op.value}")

    def run(
        self,
        state: PipelineState,
        cfg: PipelineConfig,
        rng: random.Random,
    ) -> tuple[PipelineState, OperatorResult]:
        """
        Execute multi-step Stage C controller loop with immutable state transitions.
        Enforces action-masking preconditions across rule_router, learned_mlp, and baselines.
        """
        _ = rng
        stage_t0 = time.perf_counter()

        # Masking Rule 1: Step budget exhaustion check
        if state.step_count >= cfg.max_steps:
            return self._op_escalate(
                state,
                cfg,
                f"Computational step budget {cfg.max_steps} exhausted; escalated to human planner.",
                "STEP_BUDGET_EXHAUSTED",
            )

        # Masking Rule 2: SCENARIOS is masked until graph context exists
        if not state.graph_context or not state.event:
            error_msg = (
                "Stage C masking violation: graph context or event missing before controller execution."
            )
            return state, OperatorResult(
                operator_type=OperatorType.SCENARIOS,
                success=False,
                message=error_msg,
                error=error_msg,
            )

        event = state.event
        primary_ent = self.registry.get(event.primary_entity_id)
        as_of_date = event.timestamp.strftime("%Y-%m-%d")

        ctx = _StageCEpisodeContext(
            event=event,
            primary_entity_name=primary_ent.name,
            primary_entity_region=primary_ent.region,
            as_of_date=as_of_date,
        )
        history = ControllerHistory()

        if cfg.controller_mode == "learned_mlp":
            policy = self._resolve_policy(cfg)
            while True:
                features = extract_controller_features(state, cfg, history)
                mask = compute_action_mask(state, cfg, history)
                chosen_op, action_probs = policy.predict_action(features, mask, deterministic=True)

                chosen_idx = ACTION_TO_IDX[chosen_op]
                if not mask[chosen_idx]:
                    ctx.mask_violations += 1
                    chosen_op = OperatorType.ESCALATE
                for i, allowed in enumerate(mask):
                    if not allowed and action_probs[i] > 0.0:
                        ctx.mask_violations += 1

                if chosen_op == OperatorType.ESCALATE:
                    return self._op_escalate(
                        state,
                        cfg,
                        "Learned controller reached step ceiling and escalated.",
                        "CONTROLLER_ESCALATED",
                    )

                state, _ = self._execute_operator(chosen_op, state, cfg, ctx, history)
                if chosen_op == OperatorType.SCENARIOS:
                    break

        elif cfg.controller_mode == "no_rag":
            state = self._step_scenarios(state, cfg, ctx, history)

        elif cfg.controller_mode == "fixed_rag":
            for op in (
                OperatorType.RETRIEVE_TEXT,
                OperatorType.RETRIEVE_TS,
                OperatorType.RETRIEVE_DECISIONS,
                OperatorType.SCENARIOS,
            ):
                state, _ = self._execute_operator(op, state, cfg, ctx, history)

        elif cfg.controller_mode == "always_full":
            full_plan = (
                OperatorType.RETRIEVE_TEXT,
                OperatorType.GRADE,
                OperatorType.REWRITE_QUERY,
                OperatorType.RETRIEVE_TEXT,
                OperatorType.GRADE,
                OperatorType.RETRIEVE_TS,
                OperatorType.RETRIEVE_DECISIONS,
                OperatorType.SCENARIOS,
            )
            for op in full_plan:
                if history.steps_taken >= cfg.max_steps:
                    break
                state, _ = self._execute_operator(op, state, cfg, ctx, history)
            if not history.scenarios_generated:
                state = self._step_scenarios(state, cfg, ctx, history)

        else:
            # Default Gate G1 rule_router behavior (strictly preserves Gate G1 invariants & cost)
            state = self._step_retrieve_text(state, cfg, ctx, history)
            state, will_rewrite = self._step_grade(state, cfg, ctx, history)
            if will_rewrite:
                state = self._step_rewrite_query(state, cfg, ctx, history)
            state = self._step_retrieve_ts(state, cfg, ctx, history)
            state = self._step_retrieve_decisions(state, cfg, ctx, history)
            state = self._step_scenarios(state, cfg, ctx, history)

        total_duration_ms = (time.perf_counter() - stage_t0) * 1000.0
        result = OperatorResult(
            operator_type=OperatorType.SCENARIOS,
            success=True,
            message=(
                f"Stage C Agentic-RAG ({cfg.controller_mode}) retrieved {len(ctx.retrieved_docs)} "
                f"evidence items (sufficiency={ctx.sufficiency:.2f}, query_rewritten={ctx.query_rewritten}, "
                f"precedents={len(ctx.precedents)}) and parameterized {len(ctx.scenarios)} scenarios."
            ),
            duration_ms=round(total_duration_ms, 2),
            cost=ctx.total_cost,
            artifacts={
                "controller_mode": cfg.controller_mode,
                "operator_sequence": ctx.operator_sequence,
                "mask_violations": ctx.mask_violations,
                "evidence_count": len(ctx.retrieved_docs),
                "scenario_count": len(ctx.scenarios),
                "query_rewritten": ctx.query_rewritten,
                "evidence_sufficiency": ctx.sufficiency,
                "decision_precedents_count": len(ctx.precedents),
                "as_of_date": as_of_date,
                "encoder_backend": self.vector_store.encoder_backend,
            },
        )
        return state, result
