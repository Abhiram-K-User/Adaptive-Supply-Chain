"""Run reproducible compound-event timelines and export their measured results.

Example: python scripts/run_suite_s2.py --days 7 --cases 10 --scale both
Exit codes: 0=checks passed, 1=benchmark failure, 2=configuration/execution error.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pydantic import TypeAdapter  # noqa: E402

from asci.benchmarks.common import write_report  # noqa: E402
from asci.benchmarks.suite_s2 import DEFAULT_START, SuiteS2Case, SuiteS2Runner  # noqa: E402
from asci.core.contracts import PipelineConfig  # noqa: E402


def run_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7, help="Timeline length, at least seven days")
    parser.add_argument("--cases", type=int, default=None, help="Number of cases (default: 10 or case-file length)")
    parser.add_argument("--scale", choices=["v0_core", "v1_corridor", "both"], default="v1_corridor")
    parser.add_argument("--seed", type=int, default=42, help="Seed for case generation and pipeline execution")
    parser.add_argument("--start", type=datetime.fromisoformat, default=DEFAULT_START,
                        help="Timezone-aware ISO-8601 start (default: 2026-11-01T00:00:00+00:00)")
    parser.add_argument("--case-file", type=Path, help="JSON array of SuiteS2Case definitions instead of sampled inputs")
    parser.add_argument("--pipeline-config", type=Path, help="JSON PipelineConfig overrides; --scale and --seed take precedence")
    parser.add_argument("--max-joint-scenarios", type=int, default=256, help="Bound for joint scenario expansion (minimum: 9)")
    parser.add_argument("--output", type=Path, default=Path("artifacts/suite_s2_report.json"))
    args = parser.parse_args(argv)
    reports = {}
    try:
        definitions = TypeAdapter(list[SuiteS2Case]).validate_json(args.case_file.read_text(encoding="utf-8")) if args.case_file else None
        cases = args.cases if args.cases is not None else (len(definitions) if definitions is not None else 10)
        config_data = json.loads(args.pipeline_config.read_text(encoding="utf-8")) if args.pipeline_config else {}
        if not isinstance(config_data, dict) or set(config_data) - PipelineConfig.model_fields.keys():
            raise ValueError("Pipeline configuration must be an object containing only supported PipelineConfig fields")
        config = PipelineConfig.model_validate(config_data)
        if config.enable_llm:
            raise ValueError("S2 runs offline; enable_llm must be false")
        scales = ["v0_core", "v1_corridor"] if args.scale == "both" else [args.scale]
        for scale in scales:
            def progress(record, current_scale=scale):
                if "error" in record:
                    print(f"[S2 | {current_scale}] {record['case_id']} day={record['day']}: {record['error']}", file=sys.stderr, flush=True)
                if record["day"] == args.days - 1:
                    print(f"[S2 | {current_scale}] case {record['case'] + 1}/{cases} evaluated", flush=True)

            report = SuiteS2Runner().run_suite(
                days=args.days, cases=cases, network_scale=scale, seed=args.seed, start=args.start,
                case_definitions=definitions, pipeline_config=config, max_joint_scenarios=args.max_joint_scenarios,
                on_progress=progress,
            )
            reports[scale] = report
            summary = report["summary"]
            print(f"[S2 | {scale}] snapshots={summary['total_snapshots']}, passed={summary['passed_snapshots']}, "
                  f"repro={summary['reproducibility_rate']:.1%}, L1/L2 breaches={summary['l1_l2_breach_snapshots']}, "
                  f"execution_errors={summary['execution_errors']}, shortage_snapshots={summary['shortage_snapshots']}", flush=True)
        failures = [f"{scale}: {failure}" for scale, report in reports.items() for failure in report["failures"]]
        write_report(args.output, {"suite": "S2", "passed": not failures, "reports": reports, "failures": failures})
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Suite S2 error: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote Suite S2 report to {args.output}")
    for failure in failures:
        print(f"Suite S2 failure: {failure}", file=sys.stderr)
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(run_cli())
