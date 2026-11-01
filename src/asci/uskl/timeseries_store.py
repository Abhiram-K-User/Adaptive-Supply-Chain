"""
Time-Series Store for Port Baselines, AIS Vessel Calls, and Recovery Curves.
Backed by SQLite (with DuckDB compatibility) and calibrated to IMF PortWatch data.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from asci.core.registry import CanonicalEntityRegistry, get_canonical_registry


class TimeSeriesStore:
    """
    Time-Series Store storing operational baselines, daily throughput,
    and empirical post-event recovery trajectories.
    """

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
        self._seed_baselines()

    def _get_connection(self) -> sqlite3.Connection:
        return self._conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS port_baselines (
                    entity_id TEXT PRIMARY KEY,
                    daily_vessel_calls REAL NOT NULL,
                    daily_teu_capacity REAL NOT NULL,
                    avg_dwell_time_days REAL NOT NULL,
                    anomaly_std_threshold REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS recovery_curves (
                    entity_id TEXT NOT NULL,
                    hazard_type TEXT NOT NULL,
                    day_offset INTEGER NOT NULL,
                    capacity_multiplier REAL NOT NULL,
                    PRIMARY KEY (entity_id, hazard_type, day_offset)
                )
                """
            )
            conn.commit()

    def _seed_baselines(self) -> None:
        """Seed empirical baselines calibrated to PortWatch and port authority publications."""
        baselines = [
            ("PORT_CHENNAI", 8.5, 6000.0, 1.8, 1.5),
            ("PORT_KAMARAJAR", 5.2, 4500.0, 2.1, 1.2),
            ("PORT_KATTUPALLI", 4.0, 3500.0, 1.9, 1.0),
            ("PORT_KRISHNAPATNAM", 4.8, 4000.0, 2.2, 1.1),
            ("PORT_VOC", 4.2, 3000.0, 2.4, 1.0),
            ("PORT_COCHIN", 4.5, 3500.0, 1.7, 1.2),
            ("PORT_NEW_MANGALORE", 3.2, 2500.0, 2.0, 0.9),
        ]
        with self._get_connection() as conn:
            for entity_id, calls, teu, dwell, std in baselines:
                if self.registry.validate_id(entity_id):
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO port_baselines (
                            entity_id, daily_vessel_calls, daily_teu_capacity,
                            avg_dwell_time_days, anomaly_std_threshold
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (entity_id, calls, teu, dwell, std),
                    )

            # Seed empirical recovery curves for cyclone hazard
            # Day 1: 0.1, Day 2: 0.3, Day 3: 0.6, Day 4: 0.85, Day 5: 1.0
            recovery = [
                ("PORT_KAMARAJAR", "HAZARD_PORT", 1, 0.1),
                ("PORT_KAMARAJAR", "HAZARD_PORT", 2, 0.3),
                ("PORT_KAMARAJAR", "HAZARD_PORT", 3, 0.65),
                ("PORT_KAMARAJAR", "HAZARD_PORT", 4, 0.85),
                ("PORT_KAMARAJAR", "HAZARD_PORT", 5, 1.0),
                ("PORT_CHENNAI", "HAZARD_PORT", 1, 0.2),
                ("PORT_CHENNAI", "HAZARD_PORT", 2, 0.5),
                ("PORT_CHENNAI", "HAZARD_PORT", 3, 0.8),
                ("PORT_CHENNAI", "HAZARD_PORT", 4, 1.0),
            ]
            for entity_id, hazard, day, mult in recovery:
                if self.registry.validate_id(entity_id):
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO recovery_curves (
                            entity_id, hazard_type, day_offset, capacity_multiplier
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (entity_id, hazard, day, mult),
                    )
            conn.commit()

    def get_baseline_throughput(self, entity_id: str) -> float:
        """Return expected daily TEU throughput."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT daily_teu_capacity FROM port_baselines WHERE entity_id = ?",
                (entity_id,),
            ).fetchone()
            if row:
                return float(row["daily_teu_capacity"])
            return 3000.0

    def get_recovery_curve(self, entity_id: str, hazard_type: str) -> list[float]:
        """Return empirical capacity multiplier recovery trajectory across days."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT capacity_multiplier FROM recovery_curves
                WHERE entity_id = ? AND hazard_type = ?
                ORDER BY day_offset ASC
                """,
                (entity_id, hazard_type),
            ).fetchall()
            if rows:
                return [float(r["capacity_multiplier"]) for r in rows]
            # Default linear recovery fallback
            return [0.2, 0.5, 0.75, 0.9, 1.0]
