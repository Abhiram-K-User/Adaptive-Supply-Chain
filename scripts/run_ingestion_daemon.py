"""Foreground service entrypoint; run under systemd or a container restart policy."""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from asci.ingestion.daemon import IngestionDaemon  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("local_data"))
    parser.add_argument("--scale", choices=["v0_core", "v1_corridor"], default="v1_corridor")
    parser.add_argument("--interval", type=float, default=60)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--webhook-batch-size", type=int, default=10)
    parser.add_argument("--webhook-timeout", type=float, default=10)
    parser.add_argument("--retry-base-seconds", type=float, default=2)
    parser.add_argument("--retry-max-seconds", type=float, default=3600)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, lambda *_: stop.set())
    try:
        daemon = IngestionDaemon(args.data_dir, network_scale=args.scale, interval_seconds=args.interval,
                                 replay=args.replay, webhook_url=os.getenv("ASCI_WEBHOOK_URL"),
                                 webhook_batch_size=args.webhook_batch_size, webhook_timeout=args.webhook_timeout,
                                 retry_base_seconds=args.retry_base_seconds, retry_max_seconds=args.retry_max_seconds)
    except (ValueError, RuntimeError, OSError) as exc:
        logger = logging.getLogger(__name__)
        logger.error("Worker configuration failed: %s", exc)
        return 2
    try:
        if args.once:
            report = daemon.poll_once()
            print(json.dumps(report, indent=2))
            return int(bool(report["errors"]))
        daemon.run(stop)
        return 0
    finally:
        daemon.close()


if __name__ == "__main__":
    raise SystemExit(main())
