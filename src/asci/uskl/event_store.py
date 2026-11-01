"""
SQLite Event Lifecycle Manager.
Tracks disruption events across lifecycles (new, updated, retracted, expired).
Validates all referenced entities against the Canonical Entity Registry.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
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
                    confidence REAL NOT NULL
                )
                """
            )
            conn.commit()

    def save_event(self, event: DisruptionEvent) -> None:
        """Insert or replace a disruption event after validating entity grounding."""
        if not self.registry.validate_id(event.primary_entity_id):
            raise ValueError(
                f"Cannot save event: primary entity '{event.primary_entity_id}' is not in registry."
            )
        for entity_id in event.affected_entity_ids:
            if not self.registry.validate_id(entity_id):
                raise ValueError(
                    f"Cannot save event: affected entity '{entity_id}' is not in registry."
                )

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO disruption_events (
                    event_id, event_type, status, primary_entity_id, affected_entity_ids,
                    severity, estimated_duration_days, source_feed, raw_headline,
                    raw_text, timestamp, corroboration_count, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )
            conn.commit()

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

    def list_events(self, status: EventStatus | None = None) -> list[DisruptionEvent]:
        """List stored events, optionally filtered by status."""
        query = "SELECT * FROM disruption_events"
        params: tuple = ()
        if status:
            query += " WHERE status = ?"
            params = (status.value,)

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_event(r) for r in rows]

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> DisruptionEvent:
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
        )
