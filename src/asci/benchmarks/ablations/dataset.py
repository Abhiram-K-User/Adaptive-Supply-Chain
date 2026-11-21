"""Validated seeded study design and case fixtures shared across comparisons."""
from __future__ import annotations

import random
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from asci.benchmarks.common import event_fixture
from asci.core.registry import EntityType, get_canonical_registry
from asci.core.state import DisruptionEventType, Scenario


class AblationConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    seed: int = 42
    cases: int = Field(default=12, ge=2, le=1000)
    bootstrap_samples: int = Field(default=1000, ge=10, le=100000)
    lambdas: tuple[float, ...] = (0.0, 0.1, 0.4)
    holdout_scenarios: int = Field(default=7, ge=3, le=100)
    retrieval_k: int = Field(default=5, ge=1, le=20)
    gate_threshold: float = Field(default=.7, ge=0, le=1)
    fixed_retrievals: int = Field(default=2, ge=1, le=2)
    deeper_value_threshold: float = Field(default=.001, ge=0)
    compute_savings_target: float = Field(default=.4, ge=0, le=1)
    auroc_target: float = Field(default=.8, ge=0, le=1)
    ece_target: float = Field(default=.08, ge=0, le=1)
    citation_support_target: float = Field(default=.95, ge=0, le=1)
    retrieval_recall_target: float = Field(default=.8, ge=0, le=1)
    propagation_recall_gain_target: float = Field(default=.1, ge=0, le=1)
    comparable_regret_increase_limit: float = Field(default=.01, ge=0)
    retrieval_cost_ratio_target: float = Field(default=1.5, ge=1)
    tail_regret_reduction_target: float = Field(default=.15, ge=0, le=1)
    mean_cost_increase_limit: float = Field(default=.05, ge=0)
    cvar_alpha: float = Field(default=.95, ge=.5, lt=1)
    planner_cache_dir: Path = Path("local_data/llm_planner_cache")
    record_llm: bool = False

    @field_validator("lambdas")
    @classmethod
    def validate_lambdas(cls, values):
        if not values or len(set(values)) != len(values) or any(not 0 <= x <= .5 for x in values):
            raise ValueError("Provide distinct lambdas in [0,.5]")
        return values


def cases(config: AblationConfig, scale: str):
    registry = get_canonical_registry(network_scale=scale)
    # Core anchors occur in both topologies, preserving paired scale comparisons.
    anchors = get_canonical_registry(network_scale="v0_core")
    ports = sorted(e.id for e in anchors.get_by_type(EntityType.PORT))
    inland = sorted(e.id for e in anchors.all_entities().values() if e.entity_type not in (EntityType.PORT, EntityType.PLANT))
    rng = random.Random(config.seed)
    entities = ports + inland
    rng.shuffle(entities)
    for i in range(config.cases):
        entity = entities[i % len(entities)]
        if not registry.validate_id(entity):
            raise ValueError(f"Missing paired anchor {entity}")
        event_type = DisruptionEventType.HAZARD_PORT if entity in ports else DisruptionEventType.HAZARD_ROAD
        yield event_fixture(entity, case_id=f"ABL_{i:04d}", severity=rng.uniform(.1, .95),
                            confidence=rng.uniform(.5, .99), duration=rng.uniform(1, 10),
                            timestamp=datetime(2026, 11, 10, tzinfo=UTC), event_type=event_type)


def holdouts(event, config: AblationConfig):
    # Separate seed stream; these scenarios never reach the retrieval/controller.
    rng = random.Random(f"holdout:{config.seed}:{event.event_id}")
    return [Scenario(scenario_id=f"HOLDOUT_{i}", name="Held-out operational realization",
                     probability=1/config.holdout_scenarios,
                     capacity_multipliers={event.primary_entity_id: rng.uniform(.05, 1)},
                     duration_days=event.estimated_duration_days * rng.uniform(.5, 2))
            for i in range(config.holdout_scenarios)]


def close_pipeline(pipe):
    pipe.stage_c.timeseries_store._conn.close()
    if pipe.stage_c.decision_store:
        pipe.stage_c.decision_store._conn.close()
