"""
GDACS Disaster Alert Ingestion Adapter.
Parses GeoJSON cyclone/flood alerts and spatial footprints with local fallback replay.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from asci.core.state import DisruptionEventType, RawSignal, TrustTier
from asci.ingestion.base import default_feeds_dir

GDACS_API_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"


class GDACSAdapter:
    """Adapter for GDACS cyclone and flood hazard alerts."""

    def __init__(
        self,
        fallback_path: str | Path | None = None,
        timeout_sec: float = 5.0,
    ) -> None:
        self.fallback_path = (
            Path(fallback_path) if fallback_path else default_feeds_dir() / "gdacs_alerts_sample.json"
        )
        self.timeout_sec = timeout_sec

    def fetch(self, use_fallback: bool = True) -> list[RawSignal]:
        """Fetch alerts from GDACS API or local replay JSON."""
        data: dict[str, Any] | None = None
        if not use_fallback:
            try:
                resp = httpx.get(
                    GDACS_API_URL,
                    params={"eventlist": "TC,FL", "country": "India"},
                    timeout=self.timeout_sec,
                )
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, ValueError):
                data = None

        if data is None:
            if not self.fallback_path.exists():
                return []
            with open(self.fallback_path, "r", encoding="utf-8") as f:
                data = json.load(f)

        return self.parse_feature_collection(data)

    @staticmethod
    def parse_feature_collection(payload: dict[str, Any]) -> list[RawSignal]:
        """Convert GeoJSON FeatureCollection into untrusted RawSignal containers."""
        signals: list[RawSignal] = []
        for feature in payload.get("features", []):
            props = feature.get("properties", {})
            geom = feature.get("geometry", {}) or {}
            geom_type = geom.get("type", "")
            coords = geom.get("coordinates")

            lat: float | None = None
            lon: float | None = None
            polygon: list[tuple[float, float]] = []

            if geom_type == "Point" and isinstance(coords, list) and len(coords) >= 2:
                lon, lat = float(coords[0]), float(coords[1])
            elif geom_type == "Polygon" and isinstance(coords, list) and coords:
                ring = coords[0]
                # GeoJSON ring points are [lon, lat] -> convert to (lat, lon)
                polygon = [(float(pt[1]), float(pt[0])) for pt in ring if len(pt) >= 2]
                if polygon:
                    lat = round(sum(p[0] for p in polygon) / len(polygon), 5)
                    lon = round(sum(p[1] for p in polygon) / len(polygon), 5)
            elif geom_type == "MultiPolygon" and isinstance(coords, list) and coords:
                first_poly = coords[0]
                if isinstance(first_poly, list) and first_poly:
                    ring = first_poly[0]
                    polygon = [(float(pt[1]), float(pt[0])) for pt in ring if len(pt) >= 2]
                    if polygon:
                        lat = round(sum(p[0] for p in polygon) / len(polygon), 5)
                        lon = round(sum(p[1] for p in polygon) / len(polygon), 5)

            event_id = str(props.get("eventid", "GDACS_UNKNOWN"))
            event_code = str(props.get("eventtype", "TC")).upper()
            alert_level = str(props.get("alertlevel", "Orange")).lower()

            sev_data = props.get("severitydata")
            raw_sev = sev_data.get("severity") if isinstance(sev_data, dict) else None
            if isinstance(raw_sev, (int, float)) and 0.0 <= float(raw_sev) <= 1.0:
                severity = float(raw_sev)
            else:
                severity = {"red": 0.88, "orange": 0.65, "green": 0.35}.get(alert_level, 0.6)

            from_str = props.get("fromdate")
            to_str = props.get("todate")
            published_at = _parse_iso(from_str) or datetime.now(timezone.utc)
            to_dt = _parse_iso(to_str)
            duration_days = 3.0
            if to_dt and to_dt > published_at:
                duration_days = max(1.0, round((to_dt - published_at).total_seconds() / 86400.0, 1))

            hint_type = (
                DisruptionEventType.HAZARD_PORT
                if event_code == "TC"
                else DisruptionEventType.HAZARD_ROAD
            )

            name = str(props.get("name", "GDACS Hazard Alert"))
            desc = str(props.get("description", name))
            headline = f"GDACS {alert_level.upper()} Alert: {name}"
            source_url = _extract_url(props.get("url"))

            signals.append(
                RawSignal(
                    signal_id=f"SIG_{event_id}",
                    source_feed="GDACS",
                    trust_tier=TrustTier.TIER_A,
                    raw_headline=headline,
                    raw_text=desc,
                    published_at=published_at,
                    latitude=lat,
                    longitude=lon,
                    polygon=polygon,
                    source_url=source_url,
                    hint_event_type=hint_type,
                    hint_severity=severity,
                    hint_duration_days=duration_days,
                    metadata={"alertlevel": alert_level, "gdacs_eventtype": event_code},
                )
            )
        return signals


def _extract_url(raw_url: Any) -> str | None:
    """Safely extract string URL from GDACS properties.url (which can be a str or dict)."""
    if isinstance(raw_url, str) and raw_url.strip():
        return raw_url.strip()
    if isinstance(raw_url, dict):
        for key in ("report", "details", "geometry"):
            val = raw_url.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        for val in raw_url.values():
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


def _parse_iso(val: Any) -> datetime | None:
    if not isinstance(val, str) or not val.strip():
        return None
    try:
        dt = datetime.fromisoformat(val.strip().replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None

