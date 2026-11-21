"""Restartable feed worker with signal deduplication and a durable webhook outbox."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import sqlite3
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from asci.core.registry import get_canonical_registry
from asci.ingestion.gdacs_adapter import GDACSAdapter
from asci.ingestion.portwatch_detector import PortWatchAnomalyDetector
from asci.stages.stage_a_events import StageAEventPerception
from asci.uskl.event_store import SQLiteEventStore
from asci.uskl.timeseries_store import TimeSeriesStore

logger = logging.getLogger(__name__)


class IngestionDaemon:
    """Single worker per data directory. Services stop promptly between bounded polls.

    Live fetch failures are reported; historical fallback alerts are never emitted as
    current alerts. Webhooks have at-least-once delivery with an idempotency key.
    """

    def __init__(self, data_dir: Path, *, network_scale: str = "v1_corridor", webhook_url: str | None = None,
                 interval_seconds: float = 60, replay: bool = False, adapters=None, client=None,
                 webhook_batch_size: int = 10, webhook_timeout: float = 10,
                 retry_base_seconds: float = 2, retry_max_seconds: float = 3600) -> None:
        if any(not math.isfinite(x) or x <= 0 for x in
               (interval_seconds, webhook_timeout, retry_base_seconds, retry_max_seconds)) or webhook_batch_size < 1:
            raise ValueError("Polling interval must be positive")
        if retry_max_seconds < retry_base_seconds:
            raise ValueError("Maximum retry delay must cover the initial delay")
        if webhook_url:
            url = httpx.URL(webhook_url)
            if url.scheme not in ("https", "http") or not url.host or url.userinfo:
                raise ValueError("Webhook URL must use HTTP(S) without embedded credentials")
        data_dir.mkdir(parents=True, exist_ok=True)
        self._lock_file = (data_dir / "ingestion.lock").open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self._lock_file.seek(0)
                if not self._lock_file.read(1):
                    self._lock_file.write(b"0")
                    self._lock_file.flush()
                self._lock_file.seek(0)
                msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._lock_file.close()
            raise RuntimeError("An ingestion worker already owns this data directory") from exc
        self.webhook_batch_size = webhook_batch_size
        self.retry_base_seconds, self.retry_max_seconds = retry_base_seconds, retry_max_seconds
        self.interval_seconds, self.replay, self.webhook_url = interval_seconds, replay, webhook_url
        self.registry = get_canonical_registry(network_scale=network_scale)
        self.events = SQLiteEventStore(data_dir / "events.db", registry=self.registry)
        self.timeseries = TimeSeriesStore(data_dir / "timeseries.db", registry=self.registry)
        self.stage_a = StageAEventPerception(registry=self.registry)
        self.adapters = adapters if adapters is not None else [GDACSAdapter(), PortWatchAnomalyDetector(
            registry=self.registry, timeseries_store=self.timeseries)]
        # A single transaction commits the event, deduplication and delivery intent.
        self.ledger = self.events._conn
        with self.events._get_connection() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS ingestion_seen (digest TEXT PRIMARY KEY)")
            conn.execute("CREATE TABLE IF NOT EXISTS ingestion_outbox (digest TEXT PRIMARY KEY, destination TEXT NOT NULL, payload TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, retry_at REAL NOT NULL DEFAULT 0)")
        self.client = client or httpx.Client(timeout=webhook_timeout, follow_redirects=False)
        self._owns_client = client is None

    def poll_once(self, stop: threading.Event | None = None) -> dict[str, Any]:
        stop = stop or threading.Event()
        report: dict[str, Any] = {"persisted": 0, "duplicates": 0, "rejected": 0, "webhooks_delivered": 0,
                                  "errors": [], "sources": []}
        report["expired"] = self.events.expire_stale_events() if not self.replay else 0
        for adapter in self.adapters:
            if stop.is_set():
                break
            try:
                signals = adapter.fetch(use_fallback=self.replay, allow_fallback=self.replay)
                mode = getattr(adapter, "last_fetch_mode", "live")
                report["sources"].append({"name": type(adapter).__name__, "mode": mode, "signals": len(signals)})
                if not self.replay and mode in ("fallback", "unavailable"):
                    report["errors"].append(f"{type(adapter).__name__}: live feed unavailable; fallback alerts suppressed")
                    continue
                for signal in signals:
                    if stop.is_set():
                        break
                    inferred_time = signal.metadata.get("publication_time_inferred", False)
                    identity = signal.model_dump(mode="json", exclude={"published_at"} if inferred_time else set())
                    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, allow_nan=False).encode()).hexdigest()
                    try:
                        event = self.stage_a.parse_raw_signal(signal)
                    except ValueError:
                        report["rejected"] += 1
                        continue
                    if not self.replay and event.timestamp + timedelta(days=event.estimated_duration_days) <= datetime.now(UTC):
                        report["rejected"] += 1
                        continue
                    with self.events._get_connection() as conn:
                        if conn.execute("SELECT 1 FROM ingestion_seen WHERE digest=?", (digest,)).fetchone():
                            report["duplicates"] += 1
                            continue
                        saved = self.events.upsert_with_corroboration(event)
                        conn.execute("INSERT INTO ingestion_seen VALUES (?)", (digest,))
                        if self.webhook_url:
                            conn.execute("INSERT INTO ingestion_outbox (digest,destination,payload) VALUES (?,?,?)",
                                         (digest, self.webhook_url, json.dumps({"idempotency_key": digest, "replay": self.replay, "event": saved.model_dump(mode="json")})))
                    report["persisted"] += 1
            except (httpx.HTTPError, ValueError, OSError, sqlite3.Error) as exc:
                report["errors"].append(f"{type(adapter).__name__}: {type(exc).__name__}")
        pending = self.ledger.execute("SELECT digest,destination,payload,attempts FROM ingestion_outbox WHERE retry_at<=? ORDER BY rowid LIMIT ?", (time.time(), self.webhook_batch_size)).fetchall()
        for digest, destination, payload, attempts in pending:
            if stop.is_set():
                break
            try:
                response = self.client.post(destination, json=json.loads(payload), headers={"Idempotency-Key": digest})
                response.raise_for_status()
            except httpx.HTTPError:
                with self.events._get_connection() as conn:
                    conn.execute("UPDATE ingestion_outbox SET attempts=?,retry_at=? WHERE digest=?",
                                 (attempts + 1, time.time() + min(self.retry_max_seconds, self.retry_base_seconds * 2 ** min(attempts, 20)), digest))
                report["errors"].append("Webhook delivery failed; queued for retry")
            else:
                with self.events._get_connection() as conn:
                    conn.execute("DELETE FROM ingestion_outbox WHERE digest=?", (digest,))
                report["webhooks_delivered"] += 1
        report["webhooks_pending"] = self.ledger.execute("SELECT count(*) FROM ingestion_outbox").fetchone()[0]
        return report

    def run(self, stop: threading.Event) -> None:
        while not stop.is_set():
            logger.info("Ingestion poll: %s", json.dumps(self.poll_once(stop)))
            stop.wait(self.interval_seconds)

    def close(self) -> None:
        self.events._conn.close()
        self.timeseries._conn.close()
        self._lock_file.close()
        if self._owns_client:
            self.client.close()
