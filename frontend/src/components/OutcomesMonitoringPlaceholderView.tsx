import { Activity, BarChart3, Clock, Loader2, RefreshCcw } from "lucide-react";
import { useState } from "react";
import type { CanonicalEntity } from "../types/asci";

interface OutcomeResult {
  entity_id: string;
  hazard_type: string;
  day_offset: number;
  observed_teu: number;
  baseline_teu: number;
  realized_multiplier: number;
  deviation_pct: number;
}

interface OutcomesMonitoringPlaceholderViewProps {
  entities: CanonicalEntity[];
}

export function OutcomesMonitoringPlaceholderView({
  entities,
}: OutcomesMonitoringPlaceholderViewProps) {
  const portEntities = entities.filter((e) => e.entity_type === "PORT");

  const [portId, setPortId] = useState(portEntities[0]?.id ?? "");
  const [observedTeu, setObservedTeu] = useState<number>(5000);
  const [vesselCalls, setVesselCalls] = useState<number>(12);
  const [dayOffset, setDayOffset] = useState<number>(3);
  const [hazardType, setHazardType] = useState<string>("HAZARD_PORT");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<OutcomeResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const inputClass =
    "border border-light-border dark:border-dark-border bg-light-bg dark:bg-dark-bg rounded px-2 py-1.5 text-xs w-full text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-google-blue";

  const labelClass = "block text-[11px] font-medium text-slate-400 mb-0.5";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setResult(null);
    setError(null);

    const obsDate = new Date().toISOString().slice(0, 10);
    const params = new URLSearchParams({
      entity_id: portId,
      hazard_type: hazardType,
      day_offset: String(dayOffset),
      observed_teu: String(observedTeu),
      vessel_calls: String(vesselCalls),
      obs_date: obsDate,
    });

    try {
      const resp = await fetch(`/outcomes?${params.toString()}`, {
        method: "POST",
      });
      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${text}`);
      }
      const data: OutcomeResult = await resp.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  function deviationColor(pct: number) {
    if (pct < -10) return "text-red-400";
    if (pct < 0) return "text-yellow-400";
    return "text-emerald-400";
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-light-border dark:border-dark-border bg-light-surface dark:bg-dark-surface p-4 shadow-subtle">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-google-blue/15 text-google-blue">
              <RefreshCcw className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-light-text-primary dark:text-dark-text-primary">
                Closed-Loop Trajectory Calibration &amp; Realized Outcomes (Loop L1)
              </h2>
              <p className="text-[11px] text-light-text-muted dark:text-dark-text-muted">
                Ingest post-event port throughput observations to empirically recalibrate recovery curves in <code className="font-mono text-google-blue">TimeSeriesStore</code>.
              </p>
            </div>
          </div>
          <span className="rounded-full border border-google-green/40 bg-google-green/10 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-google-green">
            POST /outcomes Active
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Loop L1 / POST /outcomes — REAL FORM */}
        <section className="rounded-xl border border-light-border dark:border-dark-border bg-light-card dark:bg-dark-card p-4">
          <div className="flex items-center justify-between">
            <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-slate-200">
              <Activity className="h-4 w-4 text-google-blue" />
              Loop L1: Realized Outcomes
            </h3>
            <span className="rounded bg-google-blue/15 px-1.5 py-0.5 font-mono text-[10px] text-google-blue">
              POST /outcomes
            </span>
          </div>

          <form onSubmit={handleSubmit} className="mt-3 space-y-2.5">
            {/* Port Selector */}
            <div>
              <label className={labelClass}>Port Selector</label>
              <select
                value={portId}
                onChange={(e) => setPortId(e.target.value)}
                className={inputClass}
                required
              >
                {portEntities.length === 0 ? (
                  <option value="">No PORT entities available</option>
                ) : (
                  portEntities.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({p.id})
                    </option>
                  ))
                )}
              </select>
            </div>

            {/* Observed TEU/day */}
            <div>
              <label className={labelClass}>Observed TEU/day</label>
              <input
                type="number"
                min={0}
                step={100}
                value={observedTeu}
                onChange={(e) => setObservedTeu(Number(e.target.value))}
                className={inputClass}
                required
              />
            </div>

            {/* Vessel Calls */}
            <div>
              <label className={labelClass}>Vessel Calls</label>
              <input
                type="number"
                min={0}
                step={1}
                value={vesselCalls}
                onChange={(e) => setVesselCalls(Number(e.target.value))}
                className={inputClass}
                required
              />
            </div>

            {/* Day Offset */}
            <div>
              <label className={labelClass}>Day Offset (since event)</label>
              <input
                type="number"
                min={0}
                max={90}
                step={1}
                value={dayOffset}
                onChange={(e) => setDayOffset(Number(e.target.value))}
                className={inputClass}
                required
              />
            </div>

            {/* Hazard Type */}
            <div>
              <label className={labelClass}>Hazard Type</label>
              <select
                value={hazardType}
                onChange={(e) => setHazardType(e.target.value)}
                className={inputClass}
              >
                <option value="HAZARD_PORT">HAZARD_PORT</option>
                <option value="HAZARD_ROAD">HAZARD_ROAD</option>
                <option value="HAZARD_RAIL">HAZARD_RAIL</option>
                <option value="HAZARD_LABOUR">HAZARD_LABOUR</option>
                <option value="HAZARD_WEATHER">HAZARD_WEATHER</option>
              </select>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading || portEntities.length === 0}
              className="mt-1 flex w-full items-center justify-center gap-1.5 rounded bg-google-blue px-4 py-2 text-xs font-semibold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? (
                <>
                  <Loader2 className="h-3 w-3 animate-spin" />
                  Submitting…
                </>
              ) : (
                "Record Realized Outcome (Loop L1 Calibrate)"
              )}
            </button>
          </form>

          {/* Error */}
          {error && (
            <div className="mt-3 rounded border border-red-500/40 bg-red-500/10 px-3 py-2 text-[11px] text-red-400">
              {error}
            </div>
          )}

          {/* Result */}
          {result && (
            <div className="mt-3 space-y-1.5 rounded-lg border border-light-border dark:border-dark-border bg-[#0a1122] p-3 text-[11px]">
              <div className="flex justify-between">
                <span className="text-slate-400">Realized Multiplier</span>
                <span className="font-mono font-semibold text-slate-200">
                  {result.realized_multiplier.toFixed(2)}x&nbsp;
                  <span className="text-slate-400 font-normal">
                    ({result.baseline_teu.toLocaleString()} → {result.observed_teu.toLocaleString()} TEU)
                  </span>
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Deviation</span>
                <span className={`font-mono font-semibold ${deviationColor(result.deviation_pct)}`}>
                  {result.deviation_pct > 0 ? "+" : ""}
                  {result.deviation_pct.toFixed(1)}%
                </span>
              </div>
              <div className="mt-1.5 flex items-center gap-1.5 rounded bg-emerald-500/10 px-2 py-1 text-emerald-300">
                <RefreshCcw className="h-3 w-3 flex-shrink-0" />
                <span>Recovery curve updated</span>
              </div>
            </div>
          )}
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
