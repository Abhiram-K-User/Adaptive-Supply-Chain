"""
Decision and Execution Trace Store.
Maintains append-only traces (JSONL) and records human planner feedback (SQLite).
Implements Architectural Feedback Loop L2 (Planner Actions -> Decision Memory).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from asci.core.state import OperatorTraceItem


class DecisionTraceStore:
    """Store for pipeline execution traces and human-in-the-loop decisions."""

    def __init__(
        self,
        db_path: str | Path = ":memory:",
        jsonl_trace_path: str | Path | None = None,
    ) -> None:
        self.db_path = str(db_path)
        self.jsonl_trace_path = Path(jsonl_trace_path) if jsonl_trace_path else None
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return self._conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS human_decisions (
                    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    decision TEXT NOT NULL, -- 'APPROVE', 'EDIT', 'REJECT'
                    planner_id TEXT NOT NULL,
                    comments TEXT,
                    modifications_json TEXT,
                    timestamp TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS operator_traces (
                    trace_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    operator_type TEXT NOT NULL,
                    duration_ms REAL NOT NULL,
                    cost REAL NOT NULL,
                    seed INTEGER NOT NULL,
                    timestamp TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def record_trace(self, session_id: str, trace_items: list[OperatorTraceItem]) -> None:
        """Persist execution trace items to SQLite and optional JSONL file."""
        with self._get_connection() as conn:
            for item in trace_items:
                conn.execute(
                    """
                    INSERT INTO operator_traces (
                        session_id, step_index, operator_type, duration_ms, cost, seed, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        item.step_index,
                        item.operator_type.value,
                        item.duration_ms,
                        item.cost,
                        item.seed,
                        item.timestamp.isoformat(),
                    ),
                )
            conn.commit()

        if self.jsonl_trace_path:
            self.jsonl_trace_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.jsonl_trace_path, "a", encoding="utf-8") as f:
                for item in trace_items:
                    record = {
                        "session_id": session_id,
                        **item.model_dump(mode="json"),
                    }
                    f.write(json.dumps(record) + "\n")

    def record_human_decision(
        self,
        plan_id: str,
        session_id: str,
        decision: str,
        planner_id: str,
        comments: str = "",
        modifications: dict[str, Any] | None = None,
    ) -> int:
        """Log human planner approval, edit, or rejection."""
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO human_decisions (
                    plan_id, session_id, decision, planner_id, comments, modifications_json, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan_id,
                    session_id,
                    decision.upper(),
                    planner_id,
                    comments,
                    json.dumps(modifications or {}),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid or 0)

    def get_traces_for_session(self, session_id: str) -> list[dict[str, Any]]:
        """Retrieve chronological execution trace for a session."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM operator_traces WHERE session_id = ? ORDER BY step_index ASC",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]
