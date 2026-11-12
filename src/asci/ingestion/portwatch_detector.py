"""
IMF PortWatch AIS Anomaly Detector.
Ingests daily port call volume series into TimeSeriesStore and emits RawSignals
when vessel calls drop significantly below calibrated port baselines.
"""

from __future__ import annotations

import csv
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from asci.core.registry import CanonicalEntityRegistry, get_canonical_registry
from asci.core.state import DisruptionEventType, RawSignal, TrustTier
from asci.ingestion.base import default_feeds_dir
from asci.uskl.timeseries_store import PortAnomaly, PortObservation, TimeSeriesStore

PORTWATCH_ARCGIS_URL = (
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/"
    "Daily_Ports_Data/FeatureServer/0/query"
)
_PORTWATCH_NAME_TO_ID: dict[str, str] = {
    "chennai": "PORT_CHENNAI",
    "ennore": "PORT_KAMARAJAR",
    "kamarajar": "PORT_KAMARAJAR",
    "kattupalli": "PORT_KATTUPALLI",
    "krishnapatnam": "PORT_KRISHNAPATNAM",
    "tuticorin": "PORT_VOC",
    "cochin": "PORT_COCHIN",
    "kochi": "PORT_COCHIN",
    "mangalore": "PORT_NMPT",
}


class PortWatchAnomalyDetector:
    """Detects significant AIS vessel arrival drops relative to baseline port norms."""

    def __init__(
        self,
        timeseries_store: TimeSeriesStore | None = None,
        registry: CanonicalEntityRegistry | None = None,
        fallback_path: str | Path | None = None,
        timeout_sec: float | None = None,
    ) -> None:
        self.registry = registry or get_canonical_registry()
        self.timeseries_store = timeseries_store or TimeSeriesStore(registry=self.registry)
        self.fallback_path = (
            Path(fallback_path)
            if fallback_path
            else default_feeds_dir() / "portwatch_daily_sample.csv"
        )
        env_timeout = os.environ.get("ASCI_FEED_TIMEOUT_SECONDS")
        self.timeout_sec = (
            timeout_sec
            if timeout_sec is not None
            else (float(env_timeout) if env_timeout else 6.0)
        )
        self.api_url = os.environ.get("ASCI_PORTWATCH_API_URL") or PORTWATCH_ARCGIS_URL
        self.last_fetch_mode: str = "uninitialized"
        self.last_error: str | None = None
        self.last_fetched_at: str | None = None
        self.last_observation_count: int = 0

    def load_csv_observations(self, csv_path: str | Path | None = None) -> list[PortObservation]:
        """Parse PortWatch daily CSV series into PortObservation records."""
        path = Path(csv_path) if csv_path else self.fallback_path
        if not path.exists():
            return []

        observations: list[PortObservation] = []
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                entity_id = row["entity_id"].strip()
                if not self.registry.validate_id(entity_id):
                    continue
                observations.append(
                    PortObservation(
                        entity_id=entity_id,
                        obs_date=row["obs_date"].strip(),
                        vessel_calls=float(row["vessel_calls"]),
                        teu_volume=float(row["teu_volume"]),
                        source="IMF_PORTWATCH",
                    )
                )
        return observations

    def _fetch_live_arcgis_observations(self) -> list[PortObservation]:
        """Attempt live IMF PortWatch ArcGIS query for major South India ports."""
        resp = httpx.get(
            self.api_url,
            params={
                "where": "portname IN ('Chennai','Ennore','Tuticorin','Cochin','Krishnapatnam')",
                "outFields": "portname,date,portcalls,import_cargo,export_cargo",
                "resultRecordCount": "35",
                "f": "json",
            },
            headers={"User-Agent": "ASCI-Control-Tower/2.0"},
            timeout=self.timeout_sec,
        )
        resp.raise_for_status()
        payload: dict[str, Any] = resp.json()
        if "error" in payload:
            raise ValueError(f"PortWatch API error: {payload['error']}")

        observations: list[PortObservation] = []
        for feat in payload.get("features", []):
            attrs = feat.get("attributes", {}) if isinstance(feat, dict) else {}
            pname = str(attrs.get("portname") or "").strip().lower()
            entity_id = _PORTWATCH_NAME_TO_ID.get(pname)
            if not entity_id or not self.registry.validate_id(entity_id):
                continue

            raw_date = attrs.get("date")
            if isinstance(raw_date, (int, float)):
                obs_date = datetime.fromtimestamp(float(raw_date) / 1000.0, tz=UTC).strftime(
                    "%Y-%m-%d"
                )
            elif isinstance(raw_date, str) and raw_date.strip():
                obs_date = raw_date.strip()[:10]
            else:
                continue

            calls = float(attrs.get("portcalls") or 0.0)
            teu_approx = float(attrs.get("import_cargo") or 0.0) + float(
                attrs.get("export_cargo") or 0.0
            )
            observations.append(
                PortObservation(
                    entity_id=entity_id,
                    obs_date=obs_date,
                    vessel_calls=calls,
                    teu_volume=max(0.0, teu_approx),
                    source="IMF_PORTWATCH_LIVE",
                )
            )
        return observations

    def fetch(self, use_fallback: bool = True) -> list[RawSignal]:
        """Ingest live or fallback PortWatch observations and emit anomaly signals."""
        observations: list[PortObservation] = []
        self.last_error = None

        if not use_fallback:
            try:
                observations = self._fetch_live_arcgis_observations()
                if observations:
                    self.last_fetch_mode = "live"
                else:
                    self.last_error = "PortWatch live query returned 0 matching rows"
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                observations = []

        if not observations:
            self.last_fetch_mode = "fallback"
            observations = self.load_csv_observations()

        self.last_fetched_at = datetime.now(UTC).isoformat()
        self.last_observation_count = len(observations)
        if not observations:
            return []

        self.timeseries_store.ingest_observations(observations)
        anomalies = self.timeseries_store.detect_anomalies(z_threshold=-2.0, min_drop_ratio=0.35)
        return [self.anomaly_to_signal(a) for a in anomalies]

    def anomaly_to_signal(self, anomaly: PortAnomaly) -> RawSignal:
        """Convert a statistical port drop anomaly into an untrusted RawSignal container."""
        entity = self.registry.get(anomaly.entity_id)
        severity = min(0.95, max(0.35, round(anomaly.drop_ratio, 2)))
        pct_drop = round(anomaly.drop_ratio * 100.0, 1)

        try:
            pub_dt = datetime.fromisoformat(f"{anomaly.obs_date}T12:00:00+00:00")
        except ValueError:
            pub_dt = datetime.now(UTC)

        headline = (
            f"PortWatch Anomaly: {entity.name} vessel calls dropped {pct_drop}% "
            f"({anomaly.observed_calls} vs baseline {anomaly.baseline_calls})"
        )
        body = (
            f"IMF PortWatch AIS monitoring flagged an abrupt arrival contraction at {entity.name} "
            f"({anomaly.entity_id}) on {anomaly.obs_date}: observed {anomaly.observed_calls} vessel calls "
            f"({anomaly.observed_teu} TEU) compared to rolling baseline {anomaly.baseline_calls} calls "
            f"(z-score {anomaly.z_score})."
        )

        return RawSignal(
            signal_id=f"SIG_PW_{anomaly.entity_id}_{anomaly.obs_date}",
            source_feed="IMF_PORTWATCH",
            trust_tier=TrustTier.TIER_A,
            raw_headline=headline,
            raw_text=body,
            published_at=pub_dt,
            latitude=entity.latitude,
            longitude=entity.longitude,
            hint_entity_id=entity.id,
            hint_event_type=DisruptionEventType.HAZARD_PORT,
            hint_severity=severity,
            hint_duration_days=3.0 if severity >= 0.7 else 2.0,
            metadata={
                "z_score": anomaly.z_score,
                "drop_ratio": anomaly.drop_ratio,
                "obs_date": anomaly.obs_date,
            },
        )

