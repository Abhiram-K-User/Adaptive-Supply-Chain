"""
CLI entrypoint for Gate G2 Statistical Suite S1 Benchmark Runner.
Usage:
    PYTHONPATH=src python scripts/run_suite_s1.py --scale both --output artifacts/suite_s1_report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Ensure src is importable when running directly as `python scripts/run_suite_s1.py`
ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from asci.benchmarks.suite_s1 import SuiteS1Report, SuiteS1Runner  # noqa: E402


def _check_gate_g2_thresholds(report: SuiteS1Report) -> list[str]:
    failures: list[str] = []
    if report.reproducibility_rate < 100.0:
        failures.append(f"{report.network_scale}: reproducibility_rate={report.reproducibility_rate}% < 100%")
    if report.l1_l2_breach_count > 0:
        failures.append(f"{report.network_scale}: l1_l2_breach_count={report.l1_l2_breach_count} > 0")
    if report.max_dual_rel_diff_pct >= 0.1:
        failures.append(f"{report.network_scale}: max_dual_rel_diff_pct={report.max_dual_rel_diff_pct}% >= 0.1%")
    if report.network_scale == "v1_corridor":
        if not (100 <= report.node_count <= 150 and 300 <= report.edge_count <= 500):
            failures.append(
                f"v1_corridor: out-of-range graph dims ({report.node_count} nodes, {report.edge_count} edges)"
            )
        for bid, unmet in report.bottleneck_unmet_teu.items():
            if unmet > 0.0:
                failures.append(f"v1_corridor: bottleneck {bid} still has unmet={unmet} TEU")
    return failures


def run_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Gate G2 Statistical Suite S1 Benchmark")
    parser.add_argument(
        "--scale",
        choices=["v0_core", "v1_corridor", "both"],
        default="both",
        help="Target corridor scale profile(s) to benchmark",
    )
    parser.add_argument(
        "--full-sweep",
        action="store_true",
        help="Include every canonical entity in an exhaustive single-event sweep",
    )
    parser.add_argument(
        "--skip-repro-check",
        action="store_true",
        help="Skip duplicate pass determinism check per case",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write full JSON benchmark report",
    )
    args = parser.parse_args(argv)

    scales: list[str] = ["v0_core", "v1_corridor"] if args.scale == "both" else [args.scale]
    runner = SuiteS1Runner()
    reports: dict[str, SuiteS1Report] = {}
    all_failures: list[str] = []

    for scale in scales:
        rep = runner.run_suite(
            network_scale=scale,  # type: ignore[arg-type]
            full_sweep=args.full_sweep,
            verify_repro=not args.skip_repro_check,
        )
        reports[scale] = rep
        all_failures.extend(_check_gate_g2_thresholds(rep))
        print(
            f"[Suite S1 | {rep.network_scale}] nodes={rep.node_count}, edges={rep.edge_count}, "
            f"cases={rep.total_cases}, repro={rep.reproducibility_rate}%, "
            f"L1/L2_breaches={rep.l1_l2_breach_count}, max_dual_gap={rep.max_dual_rel_diff_pct:.6f}%, "
            f"mean_unmet={rep.mean_unmet_demand_pct:.3f}%, "
            f"bottlenecks={rep.bottleneck_unmet_teu}, "
            f"mean_total={rep.mean_total_ms:.2f}ms (P95={rep.p95_total_ms:.2f}ms)"
        )

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "reports": {k: v.model_dump(mode="json") for k, v in reports.items()},
            "gate_g2_passed": len(all_failures) == 0,
            "failures": all_failures,
        }
        args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote Suite S1 JSON report to {args.output}")

    if all_failures:
        for err in all_failures:
            print(f"GATE G2 FAILURE: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())

