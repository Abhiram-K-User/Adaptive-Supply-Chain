import { useEffect, useState } from "react";
import { GitCommitHorizontal, RefreshCw } from "lucide-react";
import { asciApi } from "../api/client";
import type { OperatorTraceEntry, PlanResponse } from "../types/asci";

interface TraceViewProps {
  planResponse: PlanResponse | null;
}

export function TraceView({ planResponse }: TraceViewProps) {
  const [lookupSessionId, setLookupSessionId] = useState("");
  const [fetchedTraces, setFetchedTraces] = useState<OperatorTraceEntry[] | null>(
    null
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadedSessionId, setLoadedSessionId] = useState("");
  const [selectedStep, setSelectedStep] = useState<number | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const activeSessionId = planResponse?.session_id ?? "";
  const sessionId = loadedSessionId || activeSessionId;
  const traces = fetchedTraces ?? planResponse?.dashboard?.trace_timeline ?? [];
  useEffect(() => {
    setLoadedSessionId("");
    setFetchedTraces(null);
    setSelectedStep(null);
  }, [activeSessionId]);

  useEffect(() => {
    if (!sessionId || !autoRefresh) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const items = await asciApi.getSessionTraces(sessionId);
        if (!cancelled) {
          setFetchedTraces(items);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) timer = setTimeout(poll, 1000);
      }
    };
    void poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [sessionId, autoRefresh]);

  const totalDurationMs = traces.reduce((acc, item) => acc + item.duration_ms, 0);
  const totalCost = traces.reduce((acc, item) => acc + item.cost, 0);
  const inspected = traces.find(t => t.step_index === selectedStep) ?? traces[traces.length - 1];
  let cumulative = 0;
  const points = traces.map((item, index) => {
    cumulative += item.cost;
    return { x: 30 + index * 640 / Math.max(1, traces.length - 1),
      costY: 170 - 140 * cumulative / Math.max(totalCost, 0.000001),
      gainY: item.metrics?.sufficiency_after === undefined ? null : 170 - 140 * item.metrics.sufficiency_after };
  });

  const handleFetchTrace = async (e: React.FormEvent) => {
    e.preventDefault();
    const sid = (lookupSessionId || activeSessionId).trim();
    if (!sid) return;
    setLoading(true);
    setError(null);
    try {
      const items = await asciApi.getSessionTraces(sid);
      setLoadedSessionId(sid);
      setSelectedStep(null);
      setFetchedTraces(items);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-light-border bg-white p-4 shadow-sm dark:border-dark-border dark:bg-dark-card dark:shadow-dark-card">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-bold text-light-text-primary dark:text-dark-text-primary">
              <GitCommitHorizontal className="h-4 w-4 text-teal-600 dark:text-accent-cyan" />
              Chronological Operator Execution Trace
            </h2>
            <p className="mt-0.5 text-xs text-light-text-secondary dark:text-dark-text-secondary">
              Inspect operator costs, evidence grading, and query rewrites as a session runs.
            </p>
          </div>

          <form onSubmit={handleFetchTrace} className="flex flex-wrap items-center gap-2">
            <input
              type="text"
              value={lookupSessionId}
              onChange={(e) => setLookupSessionId(e.target.value)}
              placeholder={activeSessionId || "SESS_XXXXXXXX"}
              className="w-48 rounded-lg border border-light-border bg-light-surface-subtle px-2.5 py-1.5 font-mono text-xs text-light-text-primary focus:border-teal-500 focus:bg-white focus:outline-none dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-primary dark:focus:border-accent-cyan"
            />
            <button
              type="submit"
              disabled={loading || (!lookupSessionId && !activeSessionId)}
              className="inline-flex items-center gap-1.5 rounded-lg bg-[#101C2C] px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50 transition shadow-xs dark:bg-accent-cyan dark:text-[#090D14] dark:hover:bg-cyan-400"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
              <span>Load Session</span>
            </button>
            {fetchedTraces !== null && (
              <button
                type="button"
                onClick={() => { setLoadedSessionId(""); setFetchedTraces(null); setLookupSessionId(""); }}
                className="rounded-lg px-2 py-1 text-xs text-light-text-muted hover:text-light-text-primary dark:text-dark-text-muted dark:hover:text-dark-text-primary"
              >
                Use Current Plan
              </button>
            )}
          </form>
        </div>

        {error && (
          <div className="mt-3 rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-xs text-rose-800 dark:border-rose-900/50 dark:bg-rose-950/40 dark:text-rose-300">
            {error}
          </div>
        )}

        <div className="mt-3 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
          <div className="rounded-xl border border-light-border bg-light-surface-subtle px-3 py-2 dark:border-dark-border dark:bg-dark-surface">
            <div className="text-[10px] font-bold uppercase text-light-text-muted dark:text-dark-text-muted">
              Session ID
            </div>
            <div className="mt-0.5 font-mono text-xs font-bold text-light-text-primary dark:text-dark-text-primary truncate">
              {sessionId || "—"}
            </div>
          </div>
          <div className="rounded-xl border border-light-border bg-light-surface-subtle px-3 py-2 dark:border-dark-border dark:bg-dark-surface">
            <div className="text-[10px] font-bold uppercase text-light-text-muted dark:text-dark-text-muted">
              Operator Steps
            </div>
            <div className="mt-0.5 font-mono text-xs font-bold text-teal-700 dark:text-accent-cyan">
              {traces.length} steps executed
            </div>
          </div>
          <div className="rounded-xl border border-light-border bg-light-surface-subtle px-3 py-2 dark:border-dark-border dark:bg-dark-surface">
            <div className="text-[10px] font-bold uppercase text-light-text-muted dark:text-dark-text-muted">
              Total Wall Duration
            </div>
            <div className="mt-0.5 font-mono text-xs font-bold text-light-text-primary dark:text-dark-text-primary">
              {totalDurationMs.toFixed(1)} ms
            </div>
          </div>
          <div className="rounded-xl border border-light-border bg-light-surface-subtle px-3 py-2 dark:border-dark-border dark:bg-dark-surface">
            <div className="text-[10px] font-bold uppercase text-light-text-muted dark:text-dark-text-muted">
              Compute Budget Cost
            </div>
            <div className="mt-0.5 font-mono text-xs font-bold text-purple-700 dark:text-accent-purple">
              ${totalCost.toFixed(4)}
            </div>
          </div>
        </div>

        {traces.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5 rounded-xl border border-light-border bg-light-surface-subtle px-3 py-2 text-[11px] dark:border-dark-border dark:bg-dark-surface">
            <span className="font-bold uppercase text-light-text-muted dark:text-dark-text-muted mr-1">
              Operator Sequence:
            </span>
            {traces.map((t, idx) => (
              <span key={`${t.step_index}-${idx}`} className="inline-flex items-center gap-1">
                <span className="rounded bg-white px-1.5 py-0.5 font-mono text-[10px] font-semibold text-slate-700 border border-light-border dark:bg-dark-card dark:text-slate-200 dark:border-dark-border">
                  {t.operator_type}
                </span>
                {idx < traces.length - 1 && (
                  <span className="text-light-text-muted dark:text-dark-text-muted">&rarr;</span>
                )}
              </span>
            ))}
          </div>
        )}
      </section>

      {traces.length > 0 && <section className="rounded-2xl border border-light-border bg-white p-4 dark:border-dark-border dark:bg-dark-card">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-bold">Cost and evidence sufficiency by step</h3>
          <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={autoRefresh}
            onChange={e => setAutoRefresh(e.target.checked)} />Live refresh</label>
        </div>
        <p className="mt-1 text-xs text-light-text-secondary dark:text-dark-text-secondary">
          Blue: cumulative compute cost (0–${totalCost.toFixed(4)}). Green: graded evidence sufficiency (0–1).
          Sufficiency measures coverage; it is not a probability of correctness. Select a step to inspect it.
        </p>
        <svg viewBox="0 0 710 200" role="img" aria-label="Cumulative operator cost and measured evidence sufficiency" className="mt-3 w-full max-h-56">
          <path d="M30 20 V170 H685" fill="none" stroke="currentColor" opacity="0.25" />
          <polyline points={points.map(p => `${p.x},${p.costY}`).join(" ")} fill="none" stroke="#4285F4" strokeWidth="2" />
          {points.map((p, idx) => <g key={idx}>
            <circle cx={p.x} cy={p.costY} r="5" fill="#4285F4" />
            {p.gainY !== null && <circle cx={p.x} cy={p.gainY} r="5" fill="#34A853"><title>Sufficiency {traces[idx].metrics?.sufficiency_after}</title></circle>}
            <text x={p.x} y="190" textAnchor="middle" fill="currentColor" fontSize="11">{traces[idx].step_index}</text>
          </g>)}
        </svg>
        <label className="text-xs">Inspect step
          <select className="ml-2 rounded border border-light-border bg-light-surface-subtle p-1 dark:bg-dark-surface dark:border-dark-border"
            value={inspected?.step_index ?? ""} onChange={e => setSelectedStep(Number(e.target.value))}>
            {traces.map(t => <option key={t.step_index} value={t.step_index}>#{t.step_index} {t.operator_type}</option>)}
          </select>
        </label>
        {inspected && <div className="mt-3 rounded-xl border border-light-border p-3 text-xs dark:border-dark-border" aria-live="polite">
          <strong>#{inspected.step_index} {inspected.operator_type}</strong>
          <p className="mt-1">{inspected.output_summary}</p>
          {inspected.metrics?.sufficiency_after !== undefined && <p className="mt-2">
            Sufficiency: {inspected.metrics.sufficiency_after.toFixed(3)} · Change: {((inspected.metrics.sufficiency_after - (inspected.metrics.sufficiency_before ?? 0))).toFixed(3)} · Step cost: ${inspected.cost.toFixed(4)}
          </p>}
          {(inspected.metrics?.query || inspected.metrics?.query_before) && <p className="mt-2 break-words"><strong>Query:</strong> {inspected.metrics.query_before ?? inspected.metrics.query}</p>}
          {inspected.metrics?.query_after && <p className="mt-2 break-words"><strong>Rewritten query:</strong> {inspected.metrics.query_after}</p>}
        </div>}
      </section>}

      {/* Timeline Steps */}
      <section className="space-y-3">
        {traces.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-light-border bg-white p-8 text-center text-xs text-light-text-muted dark:border-dark-border dark:bg-dark-card dark:text-dark-text-muted">
            No operator execution trace loaded. Run an optimization scenario to populate trace timeline.
          </div>
        ) : (
          <div className="relative border-l-2 border-light-border dark:border-dark-border ml-4 pl-6 space-y-4">
            {traces.map((trace) => (
              <div
                key={`${trace.step_index}-${trace.operator_type}`}
                className="relative rounded-2xl border border-light-border bg-white p-3.5 shadow-sm hover:shadow-md transition dark:border-dark-border dark:bg-dark-card dark:shadow-dark-card"
              >
                {/* Node on timeline */}
                <span className="absolute -left-[31px] top-3.5 flex h-4 w-4 items-center justify-center rounded-full bg-teal-600 ring-4 ring-white dark:bg-accent-cyan dark:ring-dark-bg" />

                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-light-border dark:border-dark-border pb-2">
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-teal-50 px-1.5 py-0.5 font-mono text-[10px] font-bold text-teal-800 dark:bg-teal-950/60 dark:text-accent-cyan">
                      Step #{trace.step_index}
                    </span>
                    <span className="font-mono text-xs font-bold text-light-text-primary dark:text-dark-text-primary">
                      {trace.operator_type}
                    </span>
                  </div>

                  <div className="flex items-center gap-3 font-mono text-[11px] text-light-text-muted dark:text-dark-text-muted">
                    <span>{trace.duration_ms.toFixed(1)}ms</span>
                    <span>•</span>
                    <span>Cost: ${trace.cost.toFixed(4)}</span>
                    <span>•</span>
                    <span>Seed: {trace.seed}</span>
                  </div>
                </div>

                <div className="mt-2.5 grid grid-cols-1 gap-2 text-xs sm:grid-cols-2">
                  <div className="rounded-xl border border-light-border bg-light-surface-subtle p-2 font-mono text-[11px] text-light-text-secondary dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-secondary">
                    <div className="text-[10px] font-bold uppercase text-light-text-muted dark:text-dark-text-muted mb-1">
                      Input Payload Summary
                    </div>
                    {trace.input_summary}
                  </div>
                  <div className="rounded-xl border border-light-border bg-light-surface-subtle p-2 font-mono text-[11px] text-light-text-primary dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-primary">
                    <div className="text-[10px] font-bold uppercase text-light-text-muted dark:text-dark-text-muted mb-1">
                      Output Result Summary
                    </div>
                    {trace.output_summary}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
