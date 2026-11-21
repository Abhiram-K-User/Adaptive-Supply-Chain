"""Explicit online refresh of the immutable S6 source snapshot (never called by benchmarks)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

URL = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Ports_Data/FeatureServer/0/query"


def main() -> None:
    params = {
        "where": "portid IN ('port235','port534') AND date >= DATE '2023-11-01' AND date <= DATE '2023-12-15'",
        "outFields": "portid,portname,date,portcalls,portcalls_container,import_container,export_container",
        "f": "json", "resultRecordCount": "2000", "orderByFields": "date,portid",
    }
    response = httpx.get(URL, params=params, timeout=60)
    response.raise_for_status()
    payload = response.json()
    if "error" in payload or payload.get("exceededTransferLimit") or not payload.get("features"):
        raise RuntimeError(f"Incomplete PortWatch download: {payload.get('error', 'empty or truncated')}")
    # Keep the unmodified server response for the two named historical ports.
    features = payload["features"]
    if not features:
        raise RuntimeError(f"Port names did not match: {sorted({f['attributes']['portname'] for f in payload['features']})}")
    data = {
        "source": "IMF PortWatch daily AIS estimates", "source_url": str(response.url),
        "retrieved_at": datetime.now(UTC).isoformat(),
        "raw_response_sha256": hashlib.sha256(response.content).hexdigest(),
        "observations_sha256": hashlib.sha256(json.dumps(features, sort_keys=True).encode()).hexdigest(),
        "entity_mapping": {"port235": "PORT_CHENNAI", "port534": "PORT_KAMARAJAR"},
        "event_source_url": "https://internal.imd.gov.in/press_release/20231204_pr_2671.pdf",
        "forecast_origin": "2023-12-03",
        "units": {"portcalls": "vessel calls/day", "import_container": "metric tonnes/day",
                  "export_container": "metric tonnes/day"},
        "features": features,
    }
    target = Path(__file__).resolve().parents[1] / "data/seeds/cyclone_michaung_historical.json"
    target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Cached {len(features)} observations for {sorted({f['attributes']['portname'] for f in features})}")


if __name__ == "__main__":
    main()
