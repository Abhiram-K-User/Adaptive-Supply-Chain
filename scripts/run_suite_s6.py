"""Run the Michaung historical backtest offline on cached, checksum-verified AIS data."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from asci.benchmarks.common import write_report  # noqa: E402
from asci.benchmarks.suite_s6 import HISTORICAL_PATH, SuiteS6Config, SuiteS6Runner  # noqa: E402


def run_cli(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale", choices=["v0_core", "v1_corridor", "both"], default="both")
    parser.add_argument("--history", type=Path, default=HISTORICAL_PATH)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/suite_s6_report.json"))
    args = parser.parse_args(argv)
    try:
        config = SuiteS6Config.model_validate_json(args.config.read_text(encoding="utf-8-sig")) if args.config else SuiteS6Config()
        reports = {}
        for scale in (["v0_core", "v1_corridor"] if args.scale == "both" else [args.scale]):
            report = SuiteS6Runner().run_suite(scale, args.history, config)
            reports[scale] = report
            print(f"[S6 | {scale}] observations={len(report['records'])}, MAE={report['mean_absolute_error']:.4f}, passed={report['passed']}", flush=True)
        failures = [f"{scale}: {f}" for scale, r in reports.items() for f in r["failures"]]
        write_report(args.output, {"suite": "S6", "passed": not failures, "failures": failures, "reports": reports})
        return int(bool(failures))
    except (ValueError, OSError, KeyError, RuntimeError) as exc:
        print(f"S6 error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(run_cli())
