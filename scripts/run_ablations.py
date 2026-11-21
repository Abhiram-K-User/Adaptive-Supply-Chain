"""Run Phase 8's nine paired studies; no Phase 9 container/sign-off orchestration."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import platform
import sys
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from asci.benchmarks.ablations.control import run_control_studies  # noqa: E402
from asci.benchmarks.ablations.dataset import AblationConfig  # noqa: E402
from asci.benchmarks.ablations.graph import run_graph_studies  # noqa: E402
from asci.benchmarks.ablations.retrieval import run_retrieval_studies  # noqa: E402
from asci.benchmarks.common import write_report  # noqa: E402
from asci.benchmarks.suite_s6 import SuiteS6Runner  # noqa: E402
from asci.core.io import write_text  # noqa: E402
from asci.llm.client import load_local_dotenv  # noqa: E402


def provenance():
    root = Path(__file__).resolve().parents[1]
    files = sorted([*root.glob("src/asci/**/*.py"), *root.glob("data/seeds/*.json"), Path(__file__).resolve()])
    hashes = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    return {"source_sha256": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
            "file_hashes": hashes, "python": platform.python_version(),
            "packages": {name: version(name) for name in ("numpy", "scipy", "networkx", "ortools", "pydantic", "torch")}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--cases", type=int)
    parser.add_argument("--scale", choices=["both", "v0_core", "v1_corridor"], default="both")
    parser.add_argument("--studies", default="1,2,3,4,5,6,7,8,9")
    parser.add_argument("--record-llm", action="store_true", help="Allow genuine provider calls for missing planner replays")
    parser.add_argument("--output-dir", type=Path, default=Path("local_data/review/ablations"))
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.config.read_text(encoding="utf-8")) if args.config else {}
        if args.cases is not None:
            data["cases"] = args.cases
        if args.record_llm:
            data["record_llm"] = True
        config = AblationConfig.model_validate(data)
        source = provenance()
        selected = {int(x) for x in args.studies.split(",")}
        if not selected or not selected <= set(range(1, 10)):
            raise ValueError("Studies must be numbers 1 through 9")
        load_local_dotenv()
        scales = ("v0_core", "v1_corridor") if args.scale == "both" else (args.scale,)
        reports = []
        args.output_dir.mkdir(parents=True, exist_ok=True)
        write_report(args.output_dir / "manifest.json", {"phase": 8, "completed": False, "selected_studies": sorted(selected),
                     "network_scales": list(scales), "config": config.model_dump(mode="json"), "studies": [], "provenance": source})
        for scale in scales:
            groups = []
            if selected & {1, 7}:
                groups.append(("graph", lambda scale=scale: run_graph_studies(config, scale)))
            if selected & {3, 4, 5}:
                groups.append(("retrieval", lambda scale=scale: run_retrieval_studies(config, scale)))
            if selected & {2, 6, 8}:
                groups.append(("control", lambda scale=scale: run_control_studies(config, scale, include_llm=6 in selected)))
            if 9 in selected:
                def alignment(scale=scale):
                    backtest = SuiteS6Runner().run_suite(scale)
                    return [{"study": 9, "completed": backtest["passed"], "summary": {p["entity_id"]: p for p in backtest["ports"]},
                             "records": backtest["records"], "source_url": backtest["source_url"],
                             "observations_sha256": backtest["observations_sha256"], "limitations": backtest["limitations"]}]
                groups.append(("historical", alignment))
            for name, run in groups:
                print(f"[{scale}] Starting {name} studies", flush=True)
                for report in run():
                    if report["study"] not in selected:
                        continue
                    report.update({"network_scale": scale, "config": config.model_dump(mode="json"),
                                   "generated_at": datetime.now(UTC).isoformat(), "provenance": source})
                    numerical = {k: v for k, v in report.items() if k not in ("generated_at",)}
                    report["report_sha256"] = hashlib.sha256(json.dumps(numerical, sort_keys=True, allow_nan=False).encode()).hexdigest()
                    path = args.output_dir / f"study_{report['study']}_{scale}.json"
                    write_report(path, report)
                    reports.append(report)
                    print(f"  Study {report['study']}: completed={report['completed']}; {path}", flush=True)
        manifest = {"phase": 8, "completed": len(reports) == len(selected)*len(scales) and all(r["completed"] for r in reports),
                    "provenance": source,
                    "selected_studies": sorted(selected), "network_scales": list(scales),
                    "config": config.model_dump(mode="json"),
                    "studies": [{"study": r["study"], "network_scale": r["network_scale"], "completed": r["completed"],
                                 "targets": r.get("targets", {}), "summary": r["summary"],
                                 "adaptive_metrics": r.get("adaptive_metrics"), "limitations": r["limitations"],
                                 "report_sha256": r["report_sha256"]} for r in reports]}
        with io.StringIO(newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["study", "network_scale", "variant", "metric", "value", "ci95_low", "ci95_high"])
            for report in reports:
                for variant, metrics in report["summary"].items():
                    for metric, value in metrics.items():
                        if isinstance(value, dict) and "mean" in value:
                            writer.writerow([report["study"], report["network_scale"], variant, metric, value["mean"], *value["ci95"]])
                        elif isinstance(value, (int, float, str)) or value is None:
                            writer.writerow([report["study"], report["network_scale"], variant, metric, value, "", ""])
                for variant, metrics in (report.get("adaptive_metrics") or {}).items():
                    for metric in ("compute_savings", "auroc", "ece", "extra_regret_vs_full", "planner_calls", "planner_original_latency_ms"):
                        writer.writerow([report["study"], report["network_scale"], variant, metric, metrics[metric], "", ""])
                for metric in ("tail_regret_reduction", "mean_cost_increase", "recall_gain", "agentic_cost_ratio_to_no_rag"):
                    if metric in report:
                        writer.writerow([report["study"], report["network_scale"], "comparison", metric, report[metric], "", ""])
            write_text(args.output_dir / "summary.csv", stream.getvalue())
        write_report(args.output_dir / "manifest.json", manifest)
        return 0 if manifest["completed"] else 1
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        failure = {"completed": False, "error": str(exc), "type": type(exc).__name__}
        write_report(args.output_dir / "failure.json", failure)
        if "manifest" in locals():
            write_report(args.output_dir / "manifest.json", {**manifest, **failure})
        print(f"Ablation execution failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
