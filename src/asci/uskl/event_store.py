"""
SQLite Event Lifecycle Manager.
Tracks disruption events across lifecycles (new, updated, retracted, expired)
and manages multi-source corroboration merging.
Validates all referenced entities against the Canonical Entity Registry.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from asci.core.registry import CanonicalEntityRegistry, get_canonical_registry
from asci.core.state import DisruptionEvent, DisruptionEventType, EventStatus


class SQLiteEventStore:
    """Relational event store for disruption lifecycle tracking."""

    def __init__(
        self,
        db_path: str | Path = ":memory:",
        registry: CanonicalEntityRegistry | None = None,
    ) -> None:
        self.db_path = str(db_path)
        self.registry = registry or get_canonical_registry()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return self._conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS disruption_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    primary_entity_id TEXT NOT NULL,
                    affected_entity_ids TEXT NOT NULL,
                    severity REAL NOT NULL,
                    estimated_duration_days REAL NOT NULL,
                    source_feed TEXT NOT NULL,
                    raw_headline TEXT NOT NULL,
                    raw_text TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    corroboration_count INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    spatial_footprint TEXT NOT NULL DEFAULT '[]',
                    source_urls TEXT NOT NULL DEFAULT '[]'
                )
                """
            )
            # Ensure legacy DB tables get migrated cleanly if needed
            cols = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(disruption_events)").fetchall()
            }
            if "spatial_footprint" not in cols:
                conn.execute(
                    "ALTER TABLE disruption_events ADD COLUMN spatial_footprint TEXT NOT NULL DEFAULT '[]'"
                )
            if "source_urls" not in cols:
                conn.execute(
                    "ALTER TABLE disruption_events ADD COLUMN source_urls TEXT NOT NULL DEFAULT '[]'"
                )
            conn.commit()

    def _validate_event_entities(self, event: DisruptionEvent) -> None:
        if not self.registry.validate_id(event.primary_entity_id):
            raise ValueError(
                f"Cannot save event: primary entity '{event.primary_entity_id}' is not in registry."
            )
        for entity_id in event.affected_entity_ids:
            if not self.registry.validate_id(entity_id):
                raise ValueError(
                    f"Cannot save event: affected entity '{entity_id}' is not in registry."
                )

    def save_event(self, event: DisruptionEvent) -> None:
        """Insert or replace a disruption event after validating entity grounding."""
        self._validate_event_entities(event)

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO disruption_events (
                    event_id, event_type, status, primary_entity_id, affected_entity_ids,
                    severity, estimated_duration_days, source_feed, raw_headline,
                    raw_text, timestamp, corroboration_count, confidence,
                    spatial_footprint, source_urls
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.event_type.value,
                    event.status.value,
                    event.primary_entity_id,
                    json.dumps(event.affected_entity_ids),
                    event.severity,
                    event.estimated_duration_days,
                    event.source_feed,
                    event.raw_headline,
                    event.raw_text,
                    event.timestamp.isoformat(),
                    event.corroboration_count,
                    event.confidence,
                    json.dumps([list(pt) for pt in event.spatial_footprint]),
                    json.dumps(event.source_urls),
                ),
            )
            conn.commit()

    def upsert_with_corroboration(self, event: DisruptionEvent) -> DisruptionEvent:
        """
        Insert a new event, or corroborate/update an active event sharing the same
        (primary_entity_id, event_type). Updates status from NEW -> UPDATED and merges evidence.
        """
        self._validate_event_entities(event)

        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM disruption_events
                WHERE primary_entity_id = ?
                  AND event_type = ?
                  AND status IN ('NEW', 'UPDATED')
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (event.primary_entity_id, event.event_type.value),
            ).fetchone()

        if not row:
            self.save_event(event)
            return event

        existing = self._row_to_event(row)
        merged_affected = list(dict.fromkeys(existing.affected_entity_ids + event.affected_entity_ids))
        merged_urls = list(dict.fromkeys(existing.source_urls + event.source_urls))
        merged_feeds = (
            existing.source_feed
            if event.source_feed in existing.source_feed
            else f"{existing.source_feed},{event.source_feed}"
        )
        merged_footprint = existing.spatial_footprint or event.spatial_footprint

        merged_event = existing.model_copy(
            update={
                "status": EventStatus.UPDATED,
                "affected_entity_ids": merged_affected,
                "severity": max(existing.severity, event.severity),
                "estimated_duration_days": max(
                    existing.estimated_duration_days, event.estimated_duration_days
                ),
                "source_feed": merged_feeds,
                "corroboration_count": existing.corroboration_count + event.corroboration_count,
                "confidence": min(0.99, round(max(existing.confidence, event.confidence) + 0.05, 4)),
                "timestamp": max(existing.timestamp, event.timestamp),
                "spatial_footprint": merged_footprint,
                "source_urls": merged_urls,
            }
        )
        self.save_event(merged_event)
        return merged_event

    def get_event(self, event_id: str) -> DisruptionEvent | None:
        """Fetch an event by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM disruption_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_event(row)

    def update_status(self, event_id: str, status: EventStatus) -> bool:
        """Update the lifecycle status of an event."""
        with self._get_connection() as conn:
            cur = conn.execute(
                "UPDATE disruption_events SET status = ? WHERE event_id = ?",
                (status.value, event_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def retract_event(self, event_id: str) -> bool:
        """Retract an active event (false alarm or withdrawn bulletin)."""
        return self.update_status(event_id, EventStatus.RETRACTED)

    def expire_stale_events(self, as_of: datetime | None = None) -> int:
        """Mark active events whose estimated duration has elapsed by as_of as EXPIRED."""
        ref_time = as_of or datetime.now(UTC)
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=UTC)

        active = [
            e
            for e in self.list_events()
            if e.status in (EventStatus.NEW, EventStatus.UPDATED)
        ]
        expired_count = 0
        for evt in active:
            evt_ts = evt.timestamp
            if evt_ts.tzinfo is None:
                evt_ts = evt_ts.replace(tzinfo=UTC)
            if evt_ts + timedelta(days=evt.estimated_duration_days) <= ref_time:
                if self.update_status(evt.event_id, EventStatus.EXPIRED):
                    expired_count += 1
        return expired_count

    def list_events(self, status: EventStatus | None = None) -> list[DisruptionEvent]:
        """List stored events, optionally filtered by status."""
        query = "SELECT * FROM disruption_events"
        params: tuple = ()
        if status:
            query += " WHERE status = ?"
            params = (status.value,)
        query += " ORDER BY timestamp DESC"

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_event(r) for r in rows]

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> DisruptionEvent:
        raw_fp = json.loads(row["spatial_footprint"]) if "spatial_footprint" in row.keys() else []
        raw_urls = json.loads(row["source_urls"]) if "source_urls" in row.keys() else []
        return DisruptionEvent(
            event_id=row["event_id"],
            event_type=DisruptionEventType(row["event_type"]),
            status=EventStatus(row["status"]),
            primary_entity_id=row["primary_entity_id"],
            affected_entity_ids=json.loads(row["affected_entity_ids"]),
            severity=float(row["severity"]),
            estimated_duration_days=float(row["estimated_duration_days"]),
            source_feed=row["source_feed"],
            raw_headline=row["raw_headline"],
            raw_text=row["raw_text"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            corroboration_count=int(row["corroboration_count"]),
            confidence=float(row["confidence"]),
            spatial_footprint=[(float(pt[0]), float(pt[1])) for pt in raw_fp],
            source_urls=list(raw_urls),
        )
