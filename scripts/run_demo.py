"""
One-command demo launcher for the ASCI Control Tower & Multi-Provider LLM UI.

Usage:
    PYTHONPATH=src python scripts/run_demo.py --scale v1_corridor --preload --open
"""

from __future__ import annotations

import argparse
import os
import threading
import time
import webbrowser

import uvicorn

from asci.api.main import create_app
from asci.llm import MultiProviderLLMClient, load_local_dotenv


def main() -> int:
    load_local_dotenv()
    parser = argparse.ArgumentParser(
        description="Launch the ASCI v2.0 Interactive Control Tower Demo UI."
    )
    parser.add_argument(
        "--scale",
        choices=["v0_core", "v1_corridor"],
        default=os.environ.get("ASCI_NETWORK_SCALE", "v1_corridor"),
        help="Corridor network scale to serve (default: v1_corridor).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000).")
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("ASCI_DATA_DIR", "./local_data"),
        help="Optional directory for SQLite + JSONL persistence (default: ./local_data).",
    )
    parser.add_argument(
        "--ephemeral",
        action="store_true",
        help="Run in-memory only (no persistence); overrides --data-dir.",
    )
    parser.add_argument(
        "--preload",
        action="store_true",
        help="Preload GDACS/GDELT/RSS/Weather/PortWatch feeds before opening UI.",
    )
    parser.add_argument(
        "--replay-only",
        action="store_true",
        help="Force offline replay fixtures instead of live internet feeds during preload.",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the Control Tower dashboard in your default browser.",
    )
    args = parser.parse_args()

    if args.ephemeral:
        data_dir = None  # run in-memory
    else:
        data_dir = args.data_dir  # "./local_data" by default

    llm_status = MultiProviderLLMClient().get_status()
    app = create_app(data_dir=data_dir, network_scale=args.scale)

    live_enabled = (
        os.environ.get("ASCI_LIVE_FEEDS_ENABLED", "true").strip().lower()
        not in ("0", "false", "no")
    )

    if args.preload:
        from fastapi.testclient import TestClient

        use_live = live_enabled and not args.replay_only
        endpoint = "/ingest/live" if use_live else "/ingest/replay?use_fallback=true"
        with TestClient(app) as client:
            resp = client.post(endpoint)
            if resp.status_code == 200:
                payload = resp.json()
                print(
                    f"[ASCI Demo] Preloaded ({payload.get('mode', 'replay')}) "
                    f"{payload['signals_collected']} signals -> {payload['events_persisted']} corridor events."
                )

    url = f"http://{args.host}:{args.port}/"
    print(f"[ASCI Demo] Corridor Scale : {args.scale}")
    print(
        f"[ASCI Demo] LLM Mode       : {llm_status['mode']} "
        f"(provider={llm_status['active_provider']}, model={llm_status['model']})"
    )
    print(f"[ASCI Demo] Control Tower  : {url}")
    print(f"[ASCI Demo] Swagger Docs   : {url}docs")

    if args.open:
        def _open_browser() -> None:
            time.sleep(1.2)
            webbrowser.open(url)

        threading.Thread(target=_open_browser, daemon=True).start()

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

