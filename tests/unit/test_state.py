"""
Unit tests for PipelineState and Pydantic v2 immutable contracts.
Verifies immutability, copy-on-write state transitions, and schema validation.
"""

import pytest
from pydantic import ValidationError

from asci.core.state import (
    DisruptionEvent,
    DisruptionEventType,
    EventStatus,
    OperatorTraceItem,
    OperatorType,
    PipelineState,
    PipelineStatus,
)


def test_pipeline_state_immutability(initial_state: PipelineState):
    """Verify that attempting to mutate PipelineState directly raises a ValidationError."""
    with pytest.raises(ValidationError):
        initial_state.status = PipelineStatus.COMPLETED  # type: ignore

    with pytest.raises(ValidationError):
        initial_state.step_count = 5  # type: ignore


def test_deterministic_state_transition(initial_state: PipelineState):
    """Verify state.transition() produces a valid, updated immutable state without mutating the original."""
    trace_item = OperatorTraceItem(
        step_index=1,
        operator_type=OperatorType.STAGE_A_PERCEPTION,
        input_summary="Test perception",
        output_summary="Grounded to PORT_KAMARAJAR",
        duration_ms=12.5,
        cost=0.002,
        seed=42,
    )

    new_state = initial_state.transition(
        updates={"status": PipelineStatus.ANALYZED},
        trace_item=trace_item,
    )

    # Original state remains unchanged
    assert initial_state.status == PipelineStatus.PERCEIVED
    assert initial_state.step_count == 0
    assert initial_state.compute_cost == 0.0
    assert len(initial_state.trace) == 0

    # New state has updated values
    assert new_state.status == PipelineStatus.ANALYZED
    assert new_state.step_count == 1
    assert new_state.compute_cost == 0.002
    assert len(new_state.trace) == 1
    assert new_state.trace[0].operator_type == OperatorType.STAGE_A_PERCEPTION
    assert new_state.session_id == initial_state.session_id


def test_cumulative_cost_accumulation(initial_state: PipelineState):
    """Verify multiple transitions accumulate step count and compute cost accurately."""
    item1 = OperatorTraceItem(
        step_index=1,
        operator_type=OperatorType.GRAPH_ANALYZE,
        input_summary="Op 1",
        output_summary="Res 1",
        duration_ms=10.0,
        cost=0.005,
        seed=42,
    )
    item2 = OperatorTraceItem(
        step_index=2,
        operator_type=OperatorType.OPTIMIZE,
        input_summary="Op 2",
        output_summary="Res 2",
        duration_ms=15.0,
        cost=0.0075,
        seed=42,
    )

    s1 = initial_state.transition({}, trace_item=item1)
    s2 = s1.transition({}, trace_item=item2)

    assert s2.step_count == 2
    assert s2.compute_cost == pytest.approx(0.0125, rel=1e-4)
    assert len(s2.trace) == 2


def test_disruption_event_validation():
    """Verify Pydantic v2 field constraints on DisruptionEvent."""
    # Invalid severity > 1.0
    with pytest.raises(ValidationError):
        DisruptionEvent(
            event_id="EVT_BAD",
            event_type=DisruptionEventType.HAZARD_PORT,
            status=EventStatus.NEW,
            primary_entity_id="PORT_KAMARAJAR",
            severity=1.5,  # Exceeds max 1.0
            estimated_duration_days=2.0,
            source_feed="TEST",
            raw_headline="Test",
            raw_text="Test",
        )

    # Invalid corroboration count < 1
    with pytest.raises(ValidationError):
        DisruptionEvent(
            event_id="EVT_BAD",
            event_type=DisruptionEventType.HAZARD_PORT,
            status=EventStatus.NEW,
            primary_entity_id="PORT_KAMARAJAR",
            severity=0.5,
            estimated_duration_days=2.0,
            source_feed="TEST",
            raw_headline="Test",
            raw_text="Test",
            corroboration_count=0,  # Below min 1
        )


def test_json_serialization(initial_state: PipelineState):
    """Verify round-trip JSON serialization with Pydantic v2."""
    json_str = initial_state.model_dump_json()
    assert isinstance(json_str, str)
    deserialized = PipelineState.model_validate_json(json_str)
    assert deserialized.session_id == initial_state.session_id
    assert deserialized.status == initial_state.status
    assert deserialized.event.event_id == initial_state.event.event_id

