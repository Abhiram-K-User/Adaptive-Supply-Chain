"""Suite S6: frozen-origin Michaung backtest against cached, genuine PortWatch AIS.

November 2023 mean vessel calls provide the pre-event baseline. The fixed seeded
recovery prior forecasts 3–15 December without fitting to the held-out observations.
Vessel activity is a capacity proxy, not observed TEU throughput or a causal label.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, date, datetime
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator
from scipy.stats import spearmanr

from asci.benchmarks.common import event_fixture, outcome, run_event
from asci.core.contracts import PipelineConfig
from asci.stages import WalkingSkeletonPipeline

HISTORICAL_PATH = Path(__file__).resolve().parents[3] / "data/seeds/cyclone_michaung_historical.json"


class SuiteS6Config(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    baseline_start: date = date(2023, 11, 1)
    baseline_end: date = date(2023, 11, 30)
    forecast_end: date = date(2023, 12, 15)
    initial_capacity_ratio: float = Field(default=0.15, ge=0.05, le=1)
    initial_duration_days: float = Field(default=5, gt=0)
    disruption_threshold: float = Field(default=0.7, gt=0, lt=1)
    random_seed: int = 42

    @model_validator(mode="after")
    def ordered_windows(self):
        if not self.baseline_start <= self.baseline_end < self.forecast_end:
            raise ValueError("Baseline must precede the forecast window")
        return self


def load_history(path: Path = HISTORICAL_PATH) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    features = data["features"]
    if not features or set(data["entity_mapping"].values()) != {"PORT_CHENNAI", "PORT_KAMARAJAR"}:
        raise ValueError("Michaung history must contain Chennai and Kamarajar observations")
    if not data.get("source_url", "").startswith("https://"):
        raise ValueError("Historical data must retain its HTTPS source provenance")
    digest = hashlib.sha256(json.dumps(features, sort_keys=True).encode()).hexdigest()
    if data.get("observations_sha256") != digest:
        raise ValueError("Historical observation checksum mismatch")
    seen = set()
    for row in features:
        attr = row["attributes"]
        day = str(attr["date"])[:10]
        date.fromisoformat(day)
        key = (attr["portid"], day)
        calls = attr["portcalls"]
        if (key in seen or not isinstance(calls, (float, int)) or isinstance(calls, bool)
                or not math.isfinite(calls) or calls < 0 or attr["portid"] not in data["entity_mapping"]):
            raise ValueError(f"Invalid historical observation: {key}")
        seen.add(key)
    return data


class SuiteS6Runner:
    def run_suite(self, network_scale: str = "v1_corridor", history_path: Path = HISTORICAL_PATH,
                  config: SuiteS6Config | None = None) -> dict[str, Any]:
        data = load_history(history_path)
        settings = config or SuiteS6Config()
        origin = date.fromisoformat(data["forecast_origin"])
        if not settings.baseline_end < origin <= settings.forecast_end:
            raise ValueError("Baseline must end before the frozen forecast origin")
        cfg = PipelineConfig(network_scale=network_scale, risk_mode="DETERMINISTIC", random_seed=settings.random_seed)
        pipe = WalkingSkeletonPipeline.from_config(cfg)
        try:
            return self._evaluate(data, pipe, cfg, settings, origin)
        finally:
            pipe.stage_c.timeseries_store._conn.close()
            pipe.stage_c.decision_store._conn.close()

    def _evaluate(self, data, pipe, cfg, settings, origin):
        records = []
        summaries = []
        failures = []
        for portid, entity in data["entity_mapping"].items():
            rows = sorted([r["attributes"] for r in data["features"] if r["attributes"]["portid"] == portid],
                          key=lambda r: r["date"])
            before = [float(r["portcalls"]) for r in rows if settings.baseline_start <= date.fromisoformat(r["date"][:10]) <= settings.baseline_end]
            if len(before) != (settings.baseline_end - settings.baseline_start).days + 1 or mean(before) <= 0:
                raise ValueError(f"Incomplete or nonpositive pre-event baseline for {entity}")
            baseline = mean(before)
            curve = pipe.stage_c.timeseries_store.get_recovery_curve(entity, "HAZARD_PORT")
            port_records = []
            for row in rows:
                day = date.fromisoformat(row["date"][:10])
                if not origin <= day <= settings.forecast_end:
                    continue
                offset = (day - origin).days
                predicted = settings.initial_capacity_ratio if offset == 0 else (curve[offset - 1] if offset <= len(curve) else 1.0)
                observed = float(row["portcalls"]) / baseline
                event = event_fixture(entity, case_id=f"S6_{portid}_{day}", severity=1.0 - predicted,
                                      timestamp=datetime.combine(day, datetime.min.time(), tzinfo=UTC),
                                      duration=max(0.5, settings.initial_duration_days - offset))
                final = run_event(pipe, event, cfg)
                record = {"entity_id": entity, "date": day.isoformat(), "portcalls": row["portcalls"],
                          "baseline_calls": baseline, "observed_activity_ratio": observed,
                          "predicted_capacity_ratio": predicted, "absolute_error": abs(predicted - observed),
                          **outcome(final)}
                port_records.append(record)
                records.append(record)
                if record["l1_l2_breaches"]:
                    failures.append(f"{entity}/{day}: mathematical breach")
            if len(port_records) != (settings.forecast_end - origin).days + 1:
                raise ValueError(f"Incomplete forecast-window coverage for {entity}")
            forecasts = [r["predicted_capacity_ratio"] for r in port_records]
            observed = [r["observed_activity_ratio"] for r in port_records]
            correlation = float(spearmanr(forecasts, observed).statistic) if len(set(observed)) > 1 and len(set(forecasts)) > 1 else None
            predicted_drop = next((date.fromisoformat(r["date"]) for r in port_records if r["predicted_capacity_ratio"] < settings.disruption_threshold), None)
            observed_drop = next((date.fromisoformat(r["date"]) for r in port_records if r["observed_activity_ratio"] < settings.disruption_threshold), None)
            summaries.append({
                "entity_id": entity, "baseline_calls": baseline, "observations": len(port_records),
                "mae": mean(r["absolute_error"] for r in port_records), "spearman_rho": correlation,
                "disruption_direction_agreement": mean(float((p < settings.disruption_threshold) == (o < settings.disruption_threshold)) for p, o in zip(forecasts, observed, strict=True)),
                "lead_time_days": (observed_drop - predicted_drop).days if observed_drop and predicted_drop else None,
                "peak_observed_drop": 1 - min(observed),
            })
        return {"suite": "S6", "passed": not failures, "failures": failures, "network_scale": cfg.network_scale,
                "config": settings.model_dump(mode="json"), "event_source_url": data.get("event_source_url"),
                "source_url": data["source_url"], "observations_sha256": data["observations_sha256"],
                "forecast_origin": origin.isoformat(), "ports": summaries, "records": records,
                "mean_absolute_error": float(np.mean([r["absolute_error"] for r in records])),
                "limitations": ["AIS daily vessel calls are a noisy proxy for terminal capacity, not TEU observations.",
                                "The existing seed recovery prior has no independent training provenance; results are retrospective alignment, not a validated historical forecast.",
                                "Lead time is relative to an assumed forecast origin, not a measured live warning timestamp.",
                                "Historical reports establish event timing; severity is a model assumption."]}
