"""Durability, single-worker exclusion, strict live feeds and delivery integration."""
import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from asci.core.state import RawSignal
from asci.ingestion.daemon import IngestionDaemon
from asci.ingestion.gdacs_adapter import GDACSAdapter
from asci.ingestion.portwatch_detector import PortWatchAnomalyDetector


class Feed:
    last_fetch_mode = "live"

    def __init__(self):
        self.signals = [RawSignal(signal_id="WORKER_TEST", source_feed="GDACS",
                                 raw_headline="Cyclone closes Chennai Port", raw_text="Cyclone closes Chennai Port",
                                 hint_entity_id="PORT_CHENNAI", metadata={"publication_time_inferred": True},
                                 hint_severity=0.6, published_at=datetime.now(UTC))]

    def fetch(self, **kwargs):
        return self.signals


def test_revision_restart_and_process_lock(tmp_path):
    feed = Feed()
    worker = IngestionDaemon(tmp_path, adapters=[feed])
    try:
        assert worker.poll_once()["persisted"] == 1
        with pytest.raises(RuntimeError, match="already owns"):
            IngestionDaemon(tmp_path, adapters=[])
        original = worker.events.list_events()[0]
        feed.signals = [feed.signals[0].model_copy(update={"published_at": datetime.now(UTC)})]
        assert worker.poll_once()["duplicates"] == 1
        feed.signals = [feed.signals[0].model_copy(update={"hint_severity": 0.9})]
        assert worker.poll_once()["persisted"] == 1
        assert worker.events.list_events()[0].severity > original.severity
    finally:
        worker.close()
    worker = IngestionDaemon(tmp_path, adapters=[feed])
    try:
        assert worker.poll_once()["duplicates"] == 1
        feed.signals = [feed.signals[0].model_copy(update={"published_at": datetime.now(UTC)-timedelta(days=90), "signal_id": "STALE"})]
        assert worker.poll_once()["rejected"] == 1
    finally:
        worker.close()


def test_transaction_rolls_back_event_when_outbox_fails(tmp_path):
    worker = IngestionDaemon(tmp_path, adapters=[Feed()], webhook_url="http://127.0.0.1:9/hook")
    try:
        with worker.events._get_connection() as conn:
            conn.execute("CREATE TRIGGER reject_outbox BEFORE INSERT ON ingestion_outbox BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        assert worker.poll_once()["errors"]
        assert worker.events.list_events() == []
        assert worker.ledger.execute("SELECT count(*) FROM ingestion_seen").fetchone()[0] == 0
    finally:
        worker.close()


def test_http_delivery_retry_survives_restart_and_keeps_destination(tmp_path):
    received = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append((self.headers["Idempotency-Key"], json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            self.send_response(503 if len(received) == 1 else 204)
            self.end_headers()

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    worker = IngestionDaemon(tmp_path, adapters=[Feed()], webhook_url=f"http://127.0.0.1:{server.server_port}/hook")
    try:
        first = worker.poll_once()
        assert first["webhooks_pending"] == 1
        worker.close()
        worker = IngestionDaemon(tmp_path, adapters=[], webhook_url="http://127.0.0.1:9/changed")
        with worker.events._get_connection() as conn:
            conn.execute("UPDATE ingestion_outbox SET retry_at=0")
        assert worker.poll_once()["webhooks_delivered"] == 1
        assert worker.poll_once()["webhooks_pending"] == 0
        assert received[0] == received[1]
    finally:
        worker.close()
        server.shutdown()
        server.server_close()
        thread.join()


def test_live_failure_does_not_ingest_fallback(monkeypatch):
    detector = PortWatchAnomalyDetector()
    def fail():
        raise httpx.ConnectError("offline")
    monkeypatch.setattr(detector, "_fetch_live_arcgis_observations", fail)
    try:
        assert detector.fetch(use_fallback=False, allow_fallback=False) == []
        assert detector.last_fetch_mode == "unavailable"
        assert detector.timeseries_store._conn.execute("SELECT count(*) FROM daily_port_observations").fetchone()[0] == 0
    finally:
        detector.timeseries_store._conn.close()


def test_live_portwatch_names_and_units(monkeypatch):
    def get(*_args, **kwargs):
        assert "port235" in kwargs["params"]["where"]
        return httpx.Response(200, request=httpx.Request("GET", "https://example.org"), json={"features": [
            {"attributes": {"portname": "Chennai (Madras)", "date": 1701648000000, "portcalls": 3,
                            "import_cargo": 100000, "export_cargo": 200000}}]})
    monkeypatch.setattr(httpx, "get", get)
    detector = PortWatchAnomalyDetector()
    try:
        rows = detector._fetch_live_arcgis_observations()
        assert rows[0].entity_id == "PORT_CHENNAI"
        assert rows[0].teu_volume is None  # metric tonnes must never become TEU
        assert rows[0].source.endswith("VESSEL_CALLS_ONLY")
    finally:
        detector.timeseries_store._conn.close()


@pytest.mark.parametrize("kwargs", [{"interval_seconds": float("nan")}, {"webhook_batch_size": 0},
                                    {"webhook_url": "file:///tmp/x"}])
def test_invalid_config(tmp_path, kwargs):
    with pytest.raises(ValueError):
        IngestionDaemon(tmp_path, **kwargs)


def test_nested_event_transaction_rollback(tmp_path):
    worker = IngestionDaemon(tmp_path, adapters=[Feed()])
    try:
        with pytest.raises(sqlite3.IntegrityError):
            with worker.events._get_connection() as conn:
                worker.events.save_event(worker.stage_a.parse_raw_signal(Feed().signals[0]))
                conn.execute("INSERT INTO ingestion_seen VALUES (NULL)")
                raise sqlite3.IntegrityError("rollback")
        assert not worker.events.list_events()
    finally:
        worker.close()


def test_worker_restart_preserves_realized_recovery(tmp_path):
    worker = IngestionDaemon(tmp_path, adapters=[])
    with worker.timeseries._get_connection() as conn:
        conn.execute("UPDATE recovery_curves SET capacity_multiplier=.77 WHERE entity_id='PORT_CHENNAI' AND day_offset=1")
    worker.close()
    worker = IngestionDaemon(tmp_path, adapters=[])
    try:
        assert worker.timeseries.get_recovery_curve("PORT_CHENNAI", "HAZARD_PORT")[0] == .77
    finally:
        worker.close()


def test_worker_events_are_visible_to_running_api(tmp_path):
    from fastapi.testclient import TestClient

    from asci.api.main import create_app

    with TestClient(create_app(data_dir=tmp_path, network_scale="v0_core")) as api:
        worker = IngestionDaemon(tmp_path, adapters=[Feed()], network_scale="v0_core")
        try:
            assert worker.poll_once()["persisted"] == 1
            response = api.get("/events")
            assert response.status_code == 200
            assert any(event["primary_entity_id"] == "PORT_CHENNAI" for event in response.json())
        finally:
            worker.close()


def test_malformed_gdacs_record_does_not_hide_valid_alerts():
    payload = {"features": [None, {"geometry": {"type": "Point", "coordinates": ["bad", "data"]}},
                            {"properties": {"eventid": "GOOD", "name": "Cyclone at Chennai"},
                             "geometry": {"type": "Point", "coordinates": [80.2, 13.1]}}]}
    signals = GDACSAdapter.parse_feature_collection(payload)
    assert len(signals) == 1 and signals[0].signal_id == "SIG_GOOD"


def test_legacy_port_database_migrates_without_inventing_teu(tmp_path):
    from asci.uskl.timeseries_store import PortObservation, TimeSeriesStore
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE daily_port_observations (entity_id TEXT NOT NULL, obs_date TEXT NOT NULL, vessel_calls REAL NOT NULL, teu_volume REAL NOT NULL, source TEXT NOT NULL, PRIMARY KEY(entity_id,obs_date))")
        conn.execute("INSERT INTO daily_port_observations VALUES ('PORT_CHENNAI','2026-11-01',8,1000,'MEASURED')")
    store = TimeSeriesStore(path)
    try:
        store.ingest_observations([PortObservation("PORT_CHENNAI", "2026-11-02", 0, None, "IMF_PORTWATCH_LIVE_VESSEL_CALLS_ONLY")])
        series = store.query_recent_series("PORT_CHENNAI")
        assert series[0].teu_volume == 1000
        assert series[1].teu_volume is None
        assert store.detect_anomalies()[0].observed_teu is None
    finally:
        store._conn.close()


def test_live_calls_preserve_measured_teu_and_its_provenance(tmp_path):
    from asci.uskl.timeseries_store import PortObservation, TimeSeriesStore
    path = tmp_path / "observations.db"
    store = TimeSeriesStore(path)
    store.record_realized_outcome("PORT_CHENNAI", "HAZARD_PORT", 1, 1200,
                                  vessel_calls=2, obs_date="2026-11-21")
    store.ingest_observations([PortObservation("PORT_CHENNAI", "2026-11-21", 3, None, "IMF_PORTWATCH_LIVE_VESSEL_CALLS_ONLY")])
    store._conn.close()
    store = TimeSeriesStore(path)
    try:
        row = store.query_recent_series("PORT_CHENNAI")[-1]
        assert row.vessel_calls == 3 and row.source == "IMF_PORTWATCH_LIVE_VESSEL_CALLS_ONLY"
        assert row.teu_volume == 1200 and row.teu_source == "REALIZED_OUTCOME_FEEDBACK_L1"
        store.ingest_observations([PortObservation("PORT_CHENNAI", "2026-11-21", 4, 0, "MEASURED_TERMINAL")])
        row = store.query_recent_series("PORT_CHENNAI")[-1]
        assert row.teu_volume == 0 and row.teu_source == "MEASURED_TERMINAL"
    finally:
        store._conn.close()


@pytest.mark.parametrize("calls,teu", [(-1, 100), (1, -1), (float("nan"), None), (1, float("inf"))])
def test_invalid_measurement_batch_does_not_partially_write(calls, teu):
    from asci.uskl.timeseries_store import PortObservation, TimeSeriesStore
    store = TimeSeriesStore()
    try:
        with pytest.raises(ValueError, match="finite, nonnegative"):
            store.ingest_observations([PortObservation("PORT_CHENNAI", "2026-11-20", 5, 1000),
                                       PortObservation("PORT_CHENNAI", "2026-11-21", calls, teu)])
        assert store.query_recent_series("PORT_CHENNAI") == []
    finally:
        store._conn.close()
