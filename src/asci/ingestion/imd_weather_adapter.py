"""
IMD Weather Bulletin Ingestion Adapter.
Provides regional severity priors from rainfall and wind velocity warnings.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from asci.core.state import DisruptionEventType, RawSignal, TrustTier
from asci.ingestion.base import default_feeds_dir


class IMDWeatherAdapter:
    """Adapter for Indian Meteorological Department (IMD) coastal and inland bulletins."""

    ALERT_SEVERITY_MAP = {
        "RED": 0.85,
        "ORANGE": 0.62,
        "YELLOW": 0.38,
        "GREEN": 0.15,
    }

    def __init__(self, fallback_path: str | Path | None = None) -> None:
        self.fallback_path = (
            Path(fallback_path) if fallback_path else default_feeds_dir() / "imd_bulletins_sample.json"
        )

    def fetch(self, use_fallback: bool = True) -> list[RawSignal]:
        """Load IMD bulletins from fallback sample archive (offline-first)."""
        _ = use_fallback
        if not self.fallback_path.exists():
            return []
        with open(self.fallback_path, encoding="utf-8") as f:
            payload = json.load(f)
        return self.parse_bulletins(payload.get("bulletins", []))

    def parse_bulletins(self, bulletins: list[dict[str, Any]]) -> list[RawSignal]:
        """Parse IMD bulletin dicts into RawSignals with weather severity priors."""
        signals: list[RawSignal] = []
        for idx, b in enumerate(bulletins):
            color = str(b.get("alert_color", "ORANGE")).upper()
            base_sev = self.ALERT_SEVERITY_MAP.get(color, 0.5)
            wind = float(b.get("wind_speed_kmph", 0.0))
            rain = float(b.get("rainfall_24h_mm", 0.0))

            # Adjust severity smoothly with observed physical wind/rainfall intensity
            wind_boost = 0.05 if wind >= 90.0 else 0.0
            rain_boost = 0.05 if rain >= 200.0 else 0.0
            severity = min(0.98, round(base_sev + wind_boost + rain_boost, 2))

            hazard_cat = str(b.get("hazard_category", "")).upper()
            hint_type = (
                DisruptionEventType.HAZARD_PORT
                if "CYCLONE" in hazard_cat or "SURGE" in hazard_cat
                else DisruptionEventType.HAZARD_ROAD
            )

            issued_str = b.get("issued_at")
            try:
                issued_dt = (
                    datetime.fromisoformat(issued_str.replace("Z", "+00:00"))
                    if issued_str
                    else datetime.now(UTC)
                )
            except ValueError:
                issued_dt = datetime.now(UTC)

            bulletin_id = str(b.get("bulletin_id", f"IMD_{idx}"))
            signals.append(
                RawSignal(
                    signal_id=f"SIG_{bulletin_id}",
                    source_feed="IMD_WEATHER",
                    trust_tier=TrustTier.TIER_A,
                    raw_headline=str(b.get("headline", f"IMD {color} Weather Warning")),
                    raw_text=str(b.get("text", "")),
                    published_at=issued_dt,
                    latitude=float(b["latitude"]) if b.get("latitude") is not None else None,
                    longitude=float(b["longitude"]) if b.get("longitude") is not None else None,
                    hint_event_type=hint_type,
                    hint_severity=severity,
                    hint_duration_days=float(b.get("estimated_duration_days", 3.0)),
                    metadata={
                        "alert_color": color,
                        "wind_speed_kmph": wind,
                        "rainfall_24h_mm": rain,
                        "region": b.get("region"),
                    },
                )
            )
        return signals

