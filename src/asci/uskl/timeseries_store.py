"""
Time-Series Store for Port Baselines, AIS Vessel Calls, and Recovery Curves.
Backed by SQLite (with DuckDB compatibility) and calibrated to IMF PortWatch data.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from asci.core.registry import CanonicalEntityRegistry, get_canonical_registry


@dataclass(frozen=True)
class PortObservation:
    """Single daily observation from AIS / IMF PortWatch."""

    entity_id: str
    obs_date: str
    vessel_calls: float
    teu_volume: float
    source: str = "IMF_PORTWATCH"


@dataclass(frozen=True)
class PortAnomaly:
    """Detected port arrival drop below baseline."""

    entity_id: str
    obs_date: str
    observed_calls: float
    baseline_calls: float
    observed_teu: float
    baseline_teu: float
    z_score: float
    drop_ratio: float


class TimeSeriesStore:
    """
    Time-Series Store storing operational baselines, daily throughput observations,
    anomaly detection metrics, and empirical post-event recovery trajectories.
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_port_observations (
                    entity_id TEXT NOT NULL,
                    obs_date TEXT NOT NULL,
                    vessel_calls REAL NOT NULL,
                    teu_volume REAL NOT NULL,
                    source TEXT NOT NULL,
                    PRIMARY KEY (entity_id, obs_date)
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

    def get_baseline_record(self, entity_id: str) -> dict[str, Any] | None:
        """Return baseline calls, TEU capacity, dwell time, and std threshold for an entity."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM port_baselines WHERE entity_id = ?",
                (entity_id,),
            ).fetchone()
            return dict(row) if row else None

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
            return [0.2, 0.5, 0.75, 0.9, 1.0]

    def ingest_observations(self, observations: list[PortObservation]) -> int:
        """Persist daily AIS/PortWatch observations after validating canonical entity IDs."""
        for obs in observations:
            if not self.registry.validate_id(obs.entity_id):
                raise ValueError(
                    f"Port observation references ungrounded entity ID '{obs.entity_id}'."
                )

        with self._get_connection() as conn:
            for obs in observations:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO daily_port_observations (
                        entity_id, obs_date, vessel_calls, teu_volume, source
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (obs.entity_id, obs.obs_date, obs.vessel_calls, obs.teu_volume, obs.source),
                )
            conn.commit()
        return len(observations)

    def query_recent_series(self, entity_id: str, window_days: int = 14) -> list[PortObservation]:
        """Retrieve recent daily port observations sorted chronologically ascending."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT entity_id, obs_date, vessel_calls, teu_volume, source
                FROM daily_port_observations
                WHERE entity_id = ?
                ORDER BY obs_date DESC
                LIMIT ?
                """,
                (entity_id, window_days),
            ).fetchall()
        obs_list = [
            PortObservation(
                entity_id=r["entity_id"],
                obs_date=r["obs_date"],
                vessel_calls=float(r["vessel_calls"]),
                teu_volume=float(r["teu_volume"]),
                source=r["source"],
            )
            for r in rows
        ]
        obs_list.reverse()
        return obs_list

    def detect_anomalies(
        self,
        z_threshold: float = -2.0,
        min_drop_ratio: float = 0.35,
    ) -> list[PortAnomaly]:
        """
        Scan latest daily observations per port against rolling/baseline vessel call norms.
        Flags drops where z_score <= z_threshold and drop_ratio >= min_drop_ratio.
        """
        with self._get_connection() as conn:
            entity_rows = conn.execute(
                "SELECT DISTINCT entity_id FROM daily_port_observations ORDER BY entity_id ASC"
            ).fetchall()

        anomalies: list[PortAnomaly] = []
        for erow in entity_rows:
            entity_id = erow["entity_id"]
            series = self.query_recent_series(entity_id, window_days=30)
            if not series:
                continue

            latest = series[-1]
            baseline = self.get_baseline_record(entity_id)

            # Use historical window before latest if >= 3 points exist, else fall back to calibrated baseline
            prior = series[:-1]
            if len(prior) >= 3:
                mean_calls = sum(p.vessel_calls for p in prior) / len(prior)
                mean_teu = sum(p.teu_volume for p in prior) / len(prior)
                variance = sum((p.vessel_calls - mean_calls) ** 2 for p in prior) / len(prior)
                std_calls = max(0.35, math.sqrt(variance))
            elif baseline:
                mean_calls = float(baseline["daily_vessel_calls"])
                mean_teu = float(baseline["daily_teu_capacity"])
                std_calls = max(0.35, float(baseline["anomaly_std_threshold"]))
            else:
                continue

            if mean_calls <= 0.0:
                continue

            z_score = round((latest.vessel_calls - mean_calls) / std_calls, 3)
            drop_ratio = round(max(0.0, 1.0 - (latest.vessel_calls / mean_calls)), 3)

            if z_score <= z_threshold and drop_ratio >= min_drop_ratio:
                anomalies.append(
                    PortAnomaly(
                        entity_id=entity_id,
                        obs_date=latest.obs_date,
                        observed_calls=latest.vessel_calls,
                        baseline_calls=round(mean_calls, 2),
                        observed_teu=latest.teu_volume,
                        baseline_teu=round(mean_teu, 2),
                        z_score=z_score,
                        drop_ratio=drop_ratio,
                    )
                )

        anomalies.sort(key=lambda a: a.z_score)
        return anomalies
