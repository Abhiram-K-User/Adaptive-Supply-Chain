import { Activity, BarChart3, Clock, Lock, RefreshCcw } from "lucide-react";

export function OutcomesMonitoringPlaceholderView() {
  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-dashed border-amber-500/50 bg-amber-500/5 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <RefreshCcw className="h-4 w-4 text-amber-300" />
            <h2 className="text-sm font-bold text-amber-200">
              Realized Outcomes (Loop L1) &amp; Scheduled Monitoring — Placeholders
            </h2>
          </div>
          <span className="rounded-full border border-amber-500/40 bg-amber-500/15 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-300">
            Phases 4, 7 &amp; 8 Roadmap
          </span>
        </div>
        <p className="mt-2 text-xs leading-relaxed text-slate-300">
          These panels reflect features explicitly listed as pending in{" "}
          <code className="text-slate-200">project_context.md</code> Sec. 2 &amp; Sec. 7.
          They are surfaced here as honest UI placeholders until the corresponding backend
          endpoints and background workers are implemented.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Loop L1 / POST /outcomes */}
        <section className="rounded-xl border border-line bg-panel p-4">
          <div className="flex items-center justify-between">
            <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-slate-200">
              <Activity className="h-4 w-4 text-amber-400" />
              Loop L1: Realized Outcomes
            </h3>
            <span className="rounded bg-amber-500/15 px-1.5 py-0.5 font-mono text-[10px] text-amber-300">
              POST /outcomes
            </span>
          </div>
          <p className="mt-2 text-xs leading-relaxed text-slate-400">
            Planned endpoint to ingest actual realized post-event port throughput and
            recovery timestamps, recalibrating USKL{" "}
            <code className="text-slate-300">TimeSeriesStore</code> recovery curves and
            corridor link multipliers.
          </p>
          <div className="mt-3 space-y-2 rounded-lg border border-dashed border-line bg-[#0a1122] p-3 text-[11px] text-slate-400">
            <div>Port Entity: <span className="font-mono text-slate-300">PORT_CHENNAI (placeholder)</span></div>
            <div>Observed TEU/day vs Baseline: <span className="font-mono text-slate-300">—</span></div>
            <button
              type="button"
              disabled
              className="mt-1 flex w-full cursor-not-allowed items-center justify-center gap-1.5 rounded border border-line bg-panel2 py-1.5 font-semibold text-slate-500"
            >
              <Lock className="h-3 w-3" />
              Ingest Outcome (Awaiting POST /outcomes)
            </button>
          </div>
        </section>

        {/* Live Feed Scheduler */}
        <section className="rounded-xl border border-line bg-panel p-4">
          <div className="flex items-center justify-between">
            <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-slate-200">
              <Clock className="h-4 w-4 text-amber-400" />
              Scheduled Feed Worker
            </h3>
            <span className="rounded bg-amber-500/15 px-1.5 py-0.5 font-mono text-[10px] text-amber-300">
              Phase 8 / M5
            </span>
          </div>
          <p className="mt-2 text-xs leading-relaxed text-slate-400">
            Manual <code className="text-sky-300">POST /ingest/replay</code> polling for
            GDACS, GDELT/RSS, IMD, and PortWatch is live in the top bar. Automated cron/daemon
            polling + stale event expiration (<code className="text-slate-300">expire_stale_events()</code>)
            is scheduled for Phase 8.
          </p>
          <div className="mt-3 space-y-1.5 rounded-lg border border-line bg-[#0a1122] p-3 text-[11px]">
            <div className="flex justify-between">
              <span className="text-slate-400">GDACS / GDELT / IMD / PortWatch</span>
              <span className="text-emerald-300">Manual Poll Live</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Background Scheduler Worker</span>
              <span className="text-amber-300">Planned</span>
            </div>
          </div>
        </section>

        {/* Suites S2-S6 Backtests */}
        <section className="rounded-xl border border-line bg-panel p-4">
          <div className="flex items-center justify-between">
            <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-slate-200">
              <BarChart3 className="h-4 w-4 text-amber-400" />
              Benchmark Suites S1–S6
            </h3>
            <span className="rounded bg-amber-500/15 px-1.5 py-0.5 font-mono text-[10px] text-amber-300">
              Gate G3 / G5
            </span>
          </div>
          <p className="mt-2 text-xs leading-relaxed text-slate-400">
            <code className="text-emerald-300">Suite S1</code> (statistical solver/CVaR
            parity across v0_core &amp; v1_corridor) is implemented in{" "}
            <code className="text-slate-300">scripts/run_suite_s1.py</code>. Suites S2–S6
            are queued:
          </p>
          <ul className="mt-3 space-y-1.5 rounded-lg border border-line bg-[#0a1122] p-3 text-[11px] text-slate-300">
            <li className="flex justify-between">
              <span>S1: Core Solver &amp; v1 Scale</span>
              <span className="font-mono text-emerald-300">PASS (CLI)</span>
            </li>
            <li className="flex justify-between">
              <span>S3: Prompt-Injection Red-Team</span>
              <span className="font-mono text-amber-300">Placeholder</span>
            </li>
            <li className="flex justify-between">
              <span>S4: Randomized Fault Runner</span>
              <span className="font-mono text-amber-300">Placeholder</span>
            </li>
            <li className="flex justify-between">
              <span>S6: Cyclone Michaung Backtest</span>
              <span className="font-mono text-amber-300">Placeholder</span>
            </li>
          </ul>
        </section>
      </div>
    </div>
  );
}

