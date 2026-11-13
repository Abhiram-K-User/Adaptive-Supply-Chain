"""
Oracle Trajectory Generator & Dataset Builder (Phase 6 / Loop L3).

Simulates 1,000+ deterministic Stage C Agentic-RAG episodes across diverse corridor
disruption severities, signal confidences, evidence regimes, and budget penalties
lambda, labeling every valid state-action step with its optimal oracle operator and
expected Loop L3 regret:
    J(seq) = E[Regret(seq | episode)] + lambda * sum_t Cost(Operator_t).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime

from asci.core.contracts import PipelineConfig
from asci.core.state import (
    DisruptionEvent,
    DisruptionEventType,
    EvidenceItem,
    GraphContext,
    OperatorType,
    PipelineState,
    PipelineStatus,
    TrustTier,
)
from asci.policy.model import (
    ACTION_COST_MAP,
    ACTION_TO_IDX,
    ControllerHistory,
    compute_action_mask,
    extract_controller_features,
)

DEFAULT_ENTITY_POOL: tuple[str, ...] = (
    "PORT_KAMARAJAR",
    "PORT_CHENNAI",
    "CFS_ENNORE_LOGISTICS",
)

DEFAULT_EVENT_TYPES: tuple[DisruptionEventType, ...] = (
    DisruptionEventType.PORT_CONGESTION_STRIKE,
    DisruptionEventType.HAZARD_PORT,
    DisruptionEventType.RAIL_DISRUPTION,
    DisruptionEventType.HAZARD_ROAD,
    DisruptionEventType.SHIPPING_SCHEDULE,
)


@dataclass(frozen=True)
class OracleSample:
    """Single step supervision sample extracted along an oracle trajectory."""

    episode_id: int
    step_index: int
    lambda_cost_budget: float
    features: list[float]
    action_mask: list[bool]
    oracle_action: OperatorType
    oracle_action_idx: int
    episode_regret: float
    step_cost: float
    sample_weight: float


@dataclass(frozen=True)
class OracleEpisodeSummary:
    """Summary of one complete simulated oracle trajectory."""

    episode_id: int
    lambda_cost_budget: float
    severity: float
    confidence: float
    actions: tuple[OperatorType, ...]
    total_cost: float
    expected_regret: float
    total_objective: float


def _evaluate_candidate_objective(
    seq: tuple[OperatorType, ...],
    *,
    severity: float,
    confidence: float,
    duration_days: int,
    initial_quality: float,
    has_precedent_match: bool,
    lambda_cost_budget: float,
) -> tuple[float, float, float]:
    """
    Evaluate Loop L3 objective `J = regret + lambda * cost` for an operator plan.

    Returns `(expected_regret, total_cost, total_objective)`.
    """
    uncertainty = max(0.05, 1.0 - confidence)
    duration_factor = 1.0 + min(float(duration_days), 21.0) / 21.0
    base_risk = severity * uncertainty * duration_factor

    has_text = OperatorType.RETRIEVE_TEXT in seq
    has_grade = OperatorType.GRADE in seq
    has_rewrite = OperatorType.REWRITE_QUERY in seq
    second_text = seq.count(OperatorType.RETRIEVE_TEXT) >= 2
    has_ts = OperatorType.RETRIEVE_TS in seq
    has_decisions = OperatorType.RETRIEVE_DECISIONS in seq

    # Residual planning regret decays as targeted evidence operators resolve uncertainty.
    regret = 0.0085 * base_risk + 0.0020 * severity

    if has_text:
        quality_gain = initial_quality if initial_quality >= 0.6 else initial_quality * 0.65
        regret -= 0.0042 * base_risk * max(0.35, quality_gain)
    if has_grade and has_text:
        regret -= 0.0007 * base_risk
    if has_rewrite and initial_quality < 0.62:
        # Query rewrite strongly repairs weak/noisy initial retrieval.
        regret -= 0.0040 * max(severity, 0.35)
        if second_text:
            regret -= 0.0012 * max(severity, 0.35)
    elif has_rewrite:
        # Minimal benefit when initial evidence is already high quality.
        regret -= 0.0001 * base_risk

    if has_ts:
        regret -= 0.0022 * severity * (0.6 + 0.4 * min(duration_days / 14.0, 1.0))
    if has_decisions:
        precedent_bonus = 1.0 if has_precedent_match else 0.45
        regret -= 0.0016 * severity * precedent_bonus

    regret = max(0.0002, regret)
    total_cost = round(sum(ACTION_COST_MAP[op] for op in seq), 6)

    # Scale compute penalty weight smoothly relative to marginal regret units.
    scaled_compute_penalty = (lambda_cost_budget * 1.45) * total_cost
    total_objective = regret + scaled_compute_penalty
    return round(regret, 6), total_cost, round(total_objective, 6)


class OracleTrajectoryGenerator:
    """
    Deterministic simulator generating 1,000+ labeled Stage C oracle trajectories
    for training and auditing the Gate G4 MaskedMLPPolicy.
    """

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed

    def _build_initial_state(
        self,
        *,
        episode_id: int,
        severity: float,
        confidence: float,
        duration_days: int,
        impacted_node_count: int,
        entity_id: str,
        event_type: DisruptionEventType,
    ) -> PipelineState:
        now = datetime(2026, 4, 15, 10, 0, tzinfo=UTC)
        headline = f"Simulated {event_type.value} impacting {entity_id}"
        event = DisruptionEvent(
            event_id=f"EVT_ORC_{episode_id:05d}",
            event_type=event_type,
            primary_entity_id=entity_id,
            affected_entity_ids=[entity_id],
            severity=severity,
            confidence=confidence,
            estimated_duration_days=duration_days,
            source_feed="ORACLE_SIM",
            raw_headline=headline,
            raw_text=headline,
            timestamp=now,
        )
        node_ids = [entity_id] + [f"NODE_{i:02d}" for i in range(1, impacted_node_count)]
        graph_ctx = GraphContext(
            impacted_nodes=node_ids,
            impacted_edges=[],
            line_stop_metrics=[],
        )
        return PipelineState(
            session_id=f"SESS_ORC_{episode_id:05d}",
            status=PipelineStatus.ANALYZED,
            event=event,
            graph_context=graph_ctx,
            evidence_set=[],
            trace=[],
        )

    def _make_evidence_batch(
        self,
        *,
        episode_id: int,
        entity_id: str,
        quality: float,
        count: int,
        rewritten: bool,
    ) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []
        for i in range(count):
            tier = TrustTier.TIER_A if (rewritten or quality >= 0.72 or i == 0 and quality >= 0.58) else TrustTier.TIER_B
            score = min(0.97, max(0.30, quality + (0.22 if rewritten else 0.0) - 0.04 * i))
            items.append(
                EvidenceItem(
                    citation_id=f"CIT_ORC_{episode_id:05d}_{i}_{int(rewritten)}",
                    source="Port Trust Bulletin" if tier == TrustTier.TIER_A else "Trade Wire",
                    trust_tier=tier,
                    entity_ids=[entity_id],
                    snippet="Corridor operational status bulletin.",
                    publication_date="2026-04-15",
                    relevance_score=round(score, 4),
                )
            )
        return items

    def _select_oracle_sequence(
        self,
        *,
        cfg: PipelineConfig,
        severity: float,
        confidence: float,
        duration_days: int,
        initial_quality: float,
        has_precedent_match: bool,
    ) -> tuple[tuple[OperatorType, ...], float, float, float]:
        """Select optimal valid operator plan minimizing Loop L3 `J = regret + lambda * cost`."""
        grade_is_sufficient = initial_quality >= cfg.evidence_trust_threshold and (
            initial_quality >= 0.62
        )

        candidates: list[tuple[OperatorType, ...]] = [
            (OperatorType.SCENARIOS,),
            (
                OperatorType.RETRIEVE_TEXT,
                OperatorType.GRADE,
                OperatorType.SCENARIOS,
            ),
            (
                OperatorType.RETRIEVE_TEXT,
                OperatorType.GRADE,
                OperatorType.RETRIEVE_TS,
                OperatorType.SCENARIOS,
            ),
            (
                OperatorType.RETRIEVE_TEXT,
                OperatorType.GRADE,
                OperatorType.RETRIEVE_TS,
                OperatorType.RETRIEVE_DECISIONS,
                OperatorType.SCENARIOS,
            ),
        ]
        if not grade_is_sufficient:
            candidates.append(
                (
                    OperatorType.RETRIEVE_TEXT,
                    OperatorType.GRADE,
                    OperatorType.REWRITE_QUERY,
                    OperatorType.RETRIEVE_TS,
                    OperatorType.RETRIEVE_DECISIONS,
                    OperatorType.SCENARIOS,
                )
            )
            candidates.append(
                (
                    OperatorType.RETRIEVE_TEXT,
                    OperatorType.GRADE,
                    OperatorType.REWRITE_QUERY,
                    OperatorType.RETRIEVE_TEXT,
                    OperatorType.GRADE,
                    OperatorType.RETRIEVE_TS,
                    OperatorType.RETRIEVE_DECISIONS,
                    OperatorType.SCENARIOS,
                )
            )

        candidates = [seq for seq in candidates if len(seq) <= cfg.max_steps]
        if not candidates:
            return (OperatorType.ESCALATE,), 0.01, 0.0, 0.01

        best_seq = candidates[0]
        best_eval = (1e9, 0.0, 1e9)
        for seq in candidates:
            regret, total_cost, obj = _evaluate_candidate_objective(
                seq,
                severity=severity,
                confidence=confidence,
                duration_days=duration_days,
                initial_quality=initial_quality,
                has_precedent_match=has_precedent_match,
                lambda_cost_budget=cfg.lambda_cost_budget,
            )
            if obj < best_eval[2]:
                best_seq = seq
                best_eval = (regret, total_cost, obj)

        return best_seq, best_eval[0], best_eval[1], best_eval[2]

    def generate_dataset(
        self,
        num_episodes: int = 1050,
    ) -> tuple[list[OracleSample], list[OracleEpisodeSummary]]:
        """
        Generate `num_episodes` (>= 1000 default) complete Stage C oracle trajectories
        and return `(step_samples, episode_summaries)`.
        """
        rng = random.Random(self.seed)
        lambda_grid = (0.01, 0.03, 0.05, 0.10, 0.18, 0.30, 0.45)

        samples: list[OracleSample] = []
        summaries: list[OracleEpisodeSummary] = []

        for ep_id in range(num_episodes):
            lambda_val = lambda_grid[ep_id % len(lambda_grid)]
            severity = round(rng.uniform(0.18, 0.96), 4)
            confidence = round(rng.uniform(0.45, 0.96), 4)
            duration_days = rng.randint(1, 21)
            initial_quality = round(rng.uniform(0.35, 0.88), 4)
            has_precedent_match = rng.random() < 0.70
            impacted_node_count = rng.randint(3, 24)
            entity_id = DEFAULT_ENTITY_POOL[ep_id % len(DEFAULT_ENTITY_POOL)]
            event_type = DEFAULT_EVENT_TYPES[ep_id % len(DEFAULT_EVENT_TYPES)]

            cfg = PipelineConfig(
                lambda_cost_budget=lambda_val,
                random_seed=self.seed + ep_id,
                max_steps=8,
            )
            seq, ep_regret, total_cost, total_obj = self._select_oracle_sequence(
                cfg=cfg,
                severity=severity,
                confidence=confidence,
                duration_days=duration_days,
                initial_quality=initial_quality,
                has_precedent_match=has_precedent_match,
            )

            state = self._build_initial_state(
                episode_id=ep_id,
                severity=severity,
                confidence=confidence,
                duration_days=duration_days,
                impacted_node_count=impacted_node_count,
                entity_id=entity_id,
                event_type=event_type,
            )
            history = ControllerHistory()
            grade_is_sufficient = initial_quality >= 0.62

            for step_idx, op in enumerate(seq):
                features = extract_controller_features(state, cfg, history)
                mask = compute_action_mask(state, cfg, history)
                op_idx = ACTION_TO_IDX[op]
                if not mask[op_idx]:
                    raise RuntimeError(
                        f"Oracle sequence violation in episode {ep_id} step {step_idx}: "
                        f"operator {op.value} masked out by formal preconditions."
                    )

                step_cost = ACTION_COST_MAP[op]
                # Higher weight on steps with lower total Loop L3 regret
                sample_weight = max(0.5, 1.5 - min(ep_regret * 30.0, 0.8))
                samples.append(
                    OracleSample(
                        episode_id=ep_id,
                        step_index=step_idx,
                        lambda_cost_budget=lambda_val,
                        features=features,
                        action_mask=mask,
                        oracle_action=op,
                        oracle_action_idx=op_idx,
                        episode_regret=ep_regret,
                        step_cost=step_cost,
                        sample_weight=round(sample_weight, 4),
                    )
                )

                # Advance simulated state + history identically to StageCController
                history.steps_taken += 1
                history.cumulative_cost = round(history.cumulative_cost + step_cost, 6)
                if op == OperatorType.RETRIEVE_TEXT:
                    rewritten = history.last_rewritten
                    batch = self._make_evidence_batch(
                        episode_id=ep_id,
                        entity_id=entity_id,
                        quality=initial_quality,
                        count=3 if not rewritten else 4,
                        rewritten=rewritten,
                    )
                    state = state.transition(updates={"evidence_set": batch})
                    history.text_retrievals += 1
                    history.has_ungraded_evidence = True
                    history.last_rewritten = False
                elif op == OperatorType.GRADE:
                    history.grade_calls += 1
                    history.has_ungraded_evidence = False
                    mean_score = (
                        sum(d.relevance_score for d in state.evidence_set) / len(state.evidence_set)
                        if state.evidence_set
                        else 0.0
                    )
                    history.grade_sufficient = grade_is_sufficient or (mean_score >= 0.68)
                elif op == OperatorType.REWRITE_QUERY:
                    history.rewrite_count += 1
                    history.last_rewritten = True
                    # Rewrite elevates evidence pool unless second RETRIEVE_TEXT replaces it
                    if OperatorType.RETRIEVE_TEXT not in seq[step_idx + 1 :]:
                        upgraded = self._make_evidence_batch(
                            episode_id=ep_id,
                            entity_id=entity_id,
                            quality=initial_quality,
                            count=3,
                            rewritten=True,
                        )
                        state = state.transition(updates={"evidence_set": upgraded})
                elif op == OperatorType.RETRIEVE_TS:
                    history.ts_retrieved = True
                elif op == OperatorType.RETRIEVE_DECISIONS:
                    history.decisions_retrieved = True
                elif op == OperatorType.SCENARIOS:
                    history.scenarios_generated = True

            summaries.append(
                OracleEpisodeSummary(
                    episode_id=ep_id,
                    lambda_cost_budget=lambda_val,
                    severity=severity,
                    confidence=confidence,
                    actions=seq,
                    total_cost=total_cost,
                    expected_regret=ep_regret,
                    total_objective=total_obj,
                )
            )

        return samples, summaries
