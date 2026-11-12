"""
Unit tests for Event Store lifecycle transitions and multi-feed corroboration merging.
"""

from datetime import UTC, datetime, timedelta

from asci.core.state import DisruptionEvent, DisruptionEventType, EventStatus
from asci.uskl.event_store import SQLiteEventStore


def test_event_corroboration_merges_and_updates_status(event_store: SQLiteEventStore):
    """Verify corroborating an active event transitions status NEW -> UPDATED and boosts confidence."""
    t0 = datetime(2026, 11, 10, 6, 0, tzinfo=UTC)
    evt_gdacs = DisruptionEvent(
        event_id="EVT_GDACS_01",
        event_type=DisruptionEventType.HAZARD_PORT,
        status=EventStatus.NEW,
        primary_entity_id="PORT_KAMARAJAR",
        affected_entity_ids=["PORT_KAMARAJAR"],
        severity=0.80,
        estimated_duration_days=3.0,
        source_feed="GDACS",
        raw_headline="GDACS Cyclone alert near Ennore",
        raw_text="Storm surge warning",
        timestamp=t0,
        corroboration_count=1,
        confidence=0.88,
        source_urls=["https://gdacs.example/1"],
    )
    saved1 = event_store.upsert_with_corroboration(evt_gdacs)
    assert saved1.status == EventStatus.NEW
    assert saved1.corroboration_count == 1

    evt_portwatch = DisruptionEvent(
        event_id="EVT_PW_02",
        event_type=DisruptionEventType.HAZARD_PORT,
        status=EventStatus.NEW,
        primary_entity_id="PORT_KAMARAJAR",
        affected_entity_ids=["PORT_KAMARAJAR", "CFS_ENNORE_LOGISTICS"],
        severity=0.86,
        estimated_duration_days=4.0,
        source_feed="IMF_PORTWATCH",
        raw_headline="PortWatch drop at Kamarajar",
        raw_text="Vessel calls dropped 84%",
        timestamp=t0 + timedelta(hours=2),
        corroboration_count=1,
        confidence=0.90,
        source_urls=["https://portwatch.example/2"],
    )
    merged = event_store.upsert_with_corroboration(evt_portwatch)

    assert merged.event_id == "EVT_GDACS_01"
    assert merged.status == EventStatus.UPDATED
    assert merged.corroboration_count == 2
    assert merged.severity == 0.86
    assert merged.estimated_duration_days == 4.0
    assert merged.confidence > 0.90
    assert "CFS_ENNORE_LOGISTICS" in merged.affected_entity_ids
    assert len(merged.source_urls) == 2


def test_event_retraction_and_expiry(event_store: SQLiteEventStore):
    """Verify retract_event and expire_stale_events update lifecycle states correctly."""
    t0 = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
    evt1 = DisruptionEvent(
        event_id="EVT_EXPIRE_01",
        event_type=DisruptionEventType.HAZARD_ROAD,
        status=EventStatus.NEW,
        primary_entity_id="JUNCTION_RANIPET",
        severity=0.60,
        estimated_duration_days=2.0,
        source_feed="IMD",
        raw_headline="Rain alert Ranipet",
        raw_text="Waterlogging on NH48",
        timestamp=t0,
    )
    evt2 = DisruptionEvent(
        event_id="EVT_RETRACT_02",
        event_type=DisruptionEventType.PORT_CONGESTION_STRIKE,
        status=EventStatus.NEW,
        primary_entity_id="PORT_VOC",
        severity=0.70,
        estimated_duration_days=5.0,
        source_feed="RSS",
        raw_headline="Unconfirmed strike",
        raw_text="Union strike rumor",
        timestamp=t0 + timedelta(days=5),
    )
    event_store.save_event(evt1)
    event_store.save_event(evt2)

    assert event_store.retract_event("EVT_RETRACT_02") is True
    assert event_store.get_event("EVT_RETRACT_02").status == EventStatus.RETRACTED

    expired_count = event_store.expire_stale_events(as_of=t0 + timedelta(days=3))
    assert expired_count == 1
    assert event_store.get_event("EVT_EXPIRE_01").status == EventStatus.EXPIRED

