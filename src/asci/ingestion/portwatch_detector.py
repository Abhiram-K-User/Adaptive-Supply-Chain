"""
IMF PortWatch AIS Anomaly Detector.
Ingests daily port call volume series into TimeSeriesStore and emits RawSignals
when vessel calls drop significantly below calibrated port baselines.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

from asci.core.registry import CanonicalEntityRegistry, get_canonical_registry
from asci.core.state import DisruptionEventType, RawSignal, TrustTier
from asci.ingestion.base import default_feeds_dir
from asci.uskl.timeseries_store import PortAnomaly, PortObservation, TimeSeriesStore


class PortWatchAnomalyDetector:
    """Detects significant AIS vessel arrival drops relative to baseline port norms."""

    def __init__(
        self,
        timeseries_store: TimeSeriesStore | None = None,
        registry: CanonicalEntityRegistry | None = None,
        fallback_path: str | Path | None = None,
    ) -> None:
        self.registry = registry or get_canonical_registry()
        self.timeseries_store = timeseries_store or TimeSeriesStore(registry=self.registry)
        self.fallback_path = (
            Path(fallback_path)
            if fallback_path
            else default_feeds_dir() / "portwatch_daily_sample.csv"
        )

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

    def fetch(self, use_fallback: bool = True) -> list[RawSignal]:
        """Ingest PortWatch observations and convert detected anomalies into RawSignals."""
        _ = use_fallback
        observations = self.load_csv_observations()
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

