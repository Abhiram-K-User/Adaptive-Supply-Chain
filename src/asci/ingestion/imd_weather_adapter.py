"""
IMD Weather Bulletin Ingestion Adapter.
Provides regional severity priors from rainfall and wind velocity warnings.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from asci.core.state import DisruptionEventType, RawSignal, TrustTier
from asci.ingestion.base import default_feeds_dir

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

DEFAULT_WEATHER_HUBS: tuple[dict[str, Any], ...] = (
    {"entity_id": "PORT_CHENNAI", "name": "Chennai Port Trust", "region": "Tamil Nadu", "lat": 13.0837, "lon": 80.2826, "is_port": True},
    {"entity_id": "PORT_KAMARAJAR", "name": "Kamarajar Port (Ennore)", "region": "Tamil Nadu", "lat": 13.2611, "lon": 80.3314, "is_port": True},
    {"entity_id": "PORT_KRISHNAPATNAM", "name": "Krishnapatnam Port", "region": "Andhra Pradesh", "lat": 14.2500, "lon": 80.1200, "is_port": True},
    {"entity_id": "PORT_VOC", "name": "VOC Port Tuticorin", "region": "Tamil Nadu", "lat": 8.7547, "lon": 78.1887, "is_port": True},
    {"entity_id": "PORT_COCHIN", "name": "Cochin Port ICTT", "region": "Kerala", "lat": 9.9673, "lon": 76.2673, "is_port": True},
    {"entity_id": "JUNCTION_RANIPET", "name": "Ranipet NH48 Junction", "region": "Tamil Nadu", "lat": 12.9333, "lon": 79.3333, "is_port": False},
)


class IMDWeatherAdapter:
    """Adapter for IMD bulletins and live South India Open-Meteo corridor telemetry."""

    ALERT_SEVERITY_MAP = {
        "RED": 0.85,
        "ORANGE": 0.62,
        "YELLOW": 0.38,
        "GREEN": 0.15,
    }

    def __init__(
        self,
        fallback_path: str | Path | None = None,
        timeout_sec: float | None = None,
    ) -> None:
        self.fallback_path = (
            Path(fallback_path) if fallback_path else default_feeds_dir() / "imd_bulletins_sample.json"
        )
        env_timeout = os.environ.get("ASCI_FEED_TIMEOUT_SECONDS")
        self.timeout_sec = (
            timeout_sec
            if timeout_sec is not None
            else (float(env_timeout) if env_timeout else 6.0)
        )
        self.weather_url = os.environ.get("ASCI_WEATHER_API_URL") or OPEN_METEO_FORECAST_URL
        self.last_fetch_mode: str = "uninitialized"
        self.last_error: str | None = None
        self.last_fetched_at: str | None = None
        self.last_telemetry: list[dict[str, Any]] = []

    def fetch(self, use_fallback: bool = True) -> list[RawSignal]:
        """Fetch live South India corridor weather (Open-Meteo) or load fallback IMD sample archive."""
        self.last_error = None
        if not use_fallback:
            try:
                live_bulletins, telemetry = self._fetch_live_open_meteo()
                self.last_telemetry = telemetry
                self.last_fetch_mode = "live"
                self.last_fetched_at = datetime.now(UTC).isoformat()
                return self.parse_bulletins(live_bulletins)
            except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"

        self.last_fetch_mode = "fallback"
        if not self.fallback_path.exists():
            return []
        with open(self.fallback_path, encoding="utf-8") as f:
            payload = json.load(f)
        self.last_fetched_at = datetime.now(UTC).isoformat()
        return self.parse_bulletins(payload.get("bulletins", []))

    def _fetch_live_open_meteo(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Query live weather forecasts across key South India ports & junctions."""
        lats = ",".join(str(hub["lat"]) for hub in DEFAULT_WEATHER_HUBS)
        lons = ",".join(str(hub["lon"]) for hub in DEFAULT_WEATHER_HUBS)
        resp = httpx.get(
            self.weather_url,
            params={
                "latitude": lats,
                "longitude": lons,
                "daily": "precipitation_sum,wind_speed_10m_max,weather_code",
                "timezone": "Asia/Kolkata",
                "forecast_days": "2",
            },
            headers={"User-Agent": "ASCI-Control-Tower/2.0"},
            timeout=self.timeout_sec,
        )
        resp.raise_for_status()
        raw = resp.json()
        rows = raw if isinstance(raw, list) else [raw]

        telemetry: list[dict[str, Any]] = []
        bulletins: list[dict[str, Any]] = []
        now_iso = datetime.now(UTC).isoformat()

        for hub, item in zip(DEFAULT_WEATHER_HUBS, rows, strict=False):
            daily = item.get("daily", {}) if isinstance(item, dict) else {}
            rain_list = daily.get("precipitation_sum") or [0.0]
            wind_list = daily.get("wind_speed_10m_max") or [0.0]
            code_list = daily.get("weather_code") or [0]
            dates = daily.get("time") or [datetime.now(UTC).strftime("%Y-%m-%d")]

            rain_mm = float(rain_list[0] or 0.0)
            wind_kmh = float(wind_list[0] or 0.0)
            wmo_code = int(code_list[0] or 0)
            obs_date = str(dates[0])

            # Classify IMD-equivalent color level from live meteorological measurements
            if wind_kmh >= 85.0 or rain_mm >= 180.0:
                color = "RED"
            elif wind_kmh >= 60.0 or rain_mm >= 90.0:
                color = "ORANGE"
            elif wind_kmh >= 40.0 or rain_mm >= 35.0 or wmo_code in (65, 82, 95, 96, 99):
                color = "YELLOW"
            else:
                color = "GREEN"

            telemetry.append(
                {
                    "entity_id": hub["entity_id"],
                    "name": hub["name"],
                    "region": hub["region"],
                    "obs_date": obs_date,
                    "rain_mm": round(rain_mm, 1),
                    "wind_kmh": round(wind_kmh, 1),
                    "weather_code": wmo_code,
                    "alert_color": color,
                }
            )

            # Emit actionable RawSignal only when meteorological thresholds warrant operational alert
            if color != "GREEN":
                hazard_cat = "CYCLONE_SURGE" if (hub["is_port"] and wind_kmh >= 50.0) else "HEAVY_RAIN"
                bulletins.append(
                    {
                        "bulletin_id": f"LIVE_METEO_{hub['entity_id']}_{obs_date}",
                        "alert_color": color,
                        "wind_speed_kmph": wind_kmh,
                        "rainfall_24h_mm": rain_mm,
                        "hazard_category": hazard_cat,
                        "issued_at": now_iso,
                        "latitude": hub["lat"],
                        "longitude": hub["lon"],
                        "region": hub["region"],
                        "estimated_duration_days": 2.0 if color == "YELLOW" else 3.0,
                        "headline": (
                            f"Live Weather {color} Advisory at {hub['name']}: "
                            f"wind {wind_kmh:.1f} km/h, rain {rain_mm:.1f} mm"
                        ),
                        "text": (
                            f"Live Open-Meteo telemetry for {hub['name']} ({hub['entity_id']}) on {obs_date}: "
                            f"peak 10m wind {wind_kmh:.1f} km/h, 24h precipitation {rain_mm:.1f} mm."
                        ),
                    }
                )

        return bulletins, telemetry

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

