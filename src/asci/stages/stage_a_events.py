"""
Stage A: Live Event Intelligence & Entity Resolution.
Converts heterogeneous signals into structured disruption records grounded in canonical registry IDs.
"""

from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from typing import Any

from asci.core.contracts import OperatorResult, PipelineConfig
from asci.core.registry import CanonicalEntityRegistry, get_canonical_registry
from asci.core.state import (
    DisruptionEvent,
    DisruptionEventType,
    EventStatus,
    OperatorTraceItem,
    OperatorType,
    PipelineState,
    PipelineStatus,
)


class StageAEventPerception:
    """
    Stage A Operator: Disruption Signal Ingestion, Classification & Canonical Entity Resolution.
    """

    def __init__(self, registry: CanonicalEntityRegistry | None = None) -> None:
        self.registry = registry or get_canonical_registry()

    def run(
        self,
        state: PipelineState,
        cfg: PipelineConfig,
        rng: random.Random,
    ) -> tuple[PipelineState, OperatorResult]:
        """
        Execute Stage A perception.
        Enforces canonical entity grounding and immutable state transition.
        """
        t0 = time.perf_counter()

        # If an event is already present in state, validate grounding
        if state.event:
            event = state.event
            if not self.registry.validate_id(event.primary_entity_id):
                error_msg = f"Stage A validation error: entity '{event.primary_entity_id}' is not in Canonical Registry."
                result = OperatorResult(
                    operator_type=OperatorType.STAGE_A_PERCEPTION,
                    success=False,
                    message=error_msg,
                    error=error_msg,
                )
                return state, result
        else:
            # Create a default seed event if none provided (e.g. Cyclone Michaung at Kamarajar Port)
            primary_entity = self.registry.get("PORT_KAMARAJAR")
            event = DisruptionEvent(
                event_id="EVT_SEED_MICHAUNG_001",
                event_type=DisruptionEventType.HAZARD_PORT,
                status=EventStatus.NEW,
                primary_entity_id=primary_entity.id,
                affected_entity_ids=["PORT_KAMARAJAR", "CFS_ENNORE_LOGISTICS", "PORT_CHENNAI"],
                severity=0.85,
                estimated_duration_days=4.0,
                source_feed="IMD_GDACS_PORTWATCH",
                raw_headline="Severe Cyclonic Storm warning issued for North Tamil Nadu coast; Kamarajar Port halts container operations",
                raw_text=(
                    "Indian Meteorological Department (IMD) bulletin: Severe cyclonic storm approaching Chennai coast. "
                    "Kamarajar Port Limited (Ennore) container terminal has suspended all crane operations. "
                    "Feeder highways in Ennore logistics corridor inundated."
                ),
                timestamp=datetime.now(timezone.utc),
                corroboration_count=3,
                confidence=0.92,
            )

        duration_ms = (time.perf_counter() - t0) * 1000.0
        op_cost = 0.0015  # Nominal computation cost for Stage A extraction

        trace_item = OperatorTraceItem(
            step_index=state.step_count + 1,
            operator_type=OperatorType.STAGE_A_PERCEPTION,
            input_summary=f"Raw feed: {event.source_feed} ({event.event_id})",
            output_summary=f"Resolved primary={event.primary_entity_id}, type={event.event_type.value}, severity={event.severity}",
            duration_ms=round(duration_ms, 2),
            cost=op_cost,
            seed=cfg.random_seed,
            timestamp=datetime.now(timezone.utc),
        )

        new_state = state.transition(
            updates={
                "event": event,
                "status": PipelineStatus.PERCEIVED,
            },
            trace_item=trace_item,
        )

        result = OperatorResult(
            operator_type=OperatorType.STAGE_A_PERCEPTION,
            success=True,
            message=f"Event {event.event_id} successfully perceived and grounded into {event.primary_entity_id}.",
            duration_ms=round(duration_ms, 2),
            cost=op_cost,
            artifacts={"event_id": event.event_id, "primary_entity": event.primary_entity_id},
        )

        return new_state, result

