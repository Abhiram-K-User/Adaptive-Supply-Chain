import { useState } from "react";
import { Cpu, GitCommitHorizontal, Lock, RefreshCw } from "lucide-react";
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

  const activeSessionId = planResponse?.session_id ?? "";
  const traces = fetchedTraces ?? planResponse?.dashboard?.trace_timeline ?? [];
  const totalDurationMs = traces.reduce((acc, item) => acc + item.duration_ms, 0);
  const totalCost = traces.reduce((acc, item) => acc + item.cost, 0);

  const handleFetchTrace = async (e: React.FormEvent) => {
    e.preventDefault();
    const sid = (lookupSessionId || activeSessionId).trim();
    if (!sid) return;
    setLoading(true);
    setError(null);
    try {
      const items = await asciApi.getSessionTraces(sid);
      setFetchedTraces(items);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-line bg-panel p-4 shadow-lg shadow-black/25">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-bold text-white">
              <GitCommitHorizontal className="h-4 w-4 text-sky-400" />
              Chronological Operator Execution Trace
            </h2>
            <p className="mt-0.5 text-xs text-slate-400">
              Live audit log backed by <code className="text-sky-300">GET /traces/&#123;session_id&#125;</code> and <code className="text-slate-300">DecisionTraceStore</code>
            </p>
          </div>

          <form onSubmit={handleFetchTrace} className="flex flex-wrap items-center gap-2">
            <input
              type="text"
              value={lookupSessionId}
              onChange={(e) => setLookupSessionId(e.target.value)}
              placeholder={activeSessionId || "SESS_XXXXXXXX"}
              className="w-48 rounded-lg border border-line bg-[#090f1d] px-2.5 py-1.5 font-mono text-xs text-slate-100 focus:border-sky-400 focus:outline-none"
            />
            <button
              type="submit"
              disabled={loading || (!lookupSessionId && !activeSessionId)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-panel2 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:border-sky-400/60 disabled:opacity-50"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
              Load Session Trace
            </button>
            {fetchedTraces !== null && (
              <button
                type="button"
                onClick={() => setFetchedTraces(null)}
                className="rounded-lg px-2 py-1 text-xs text-slate-400 hover:text-white"
              >
                Use Current Plan
              </button>
            )}
          </form>
        </div>

        {error && (
          <div className="mt-3 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-200">
            {error}
          </div>
        )}

        <div className="mt-3 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
          <div className="rounded-lg border border-line bg-[#0a1122] px-3 py-2">
            <div className="text-[10px] font-bold uppercase text-slate-400">
              Session ID
            </div>
            <div className="mt-0.5 font-mono text-xs font-bold text-white">
              {activeSessionId || lookupSessionId || "—"}
            </div>
          </div>
          <div className="rounded-lg border border-line bg-[#0a1122] px-3 py-2">
            <div className="text-[10px] font-bold uppercase text-slate-400">
              Operator Steps
            </div>
            <div className="mt-0.5 font-mono text-xs font-bold text-sky-300">
              {traces.length} (Gate G1 cadence: 5)
            </div>
          </div>
          <div className="rounded-lg border border-line bg-[#0a1122] px-3 py-2">
            <div className="text-[10px] font-bold uppercase text-slate-400">
              Total Duration
            </div>
            <div className="mt-0.5 font-mono text-xs font-bold text-white">
              {totalDurationMs.toFixed(1)} ms
            </div>
          </div>
          <div className="rounded-lg border border-line bg-[#0a1122] px-3 py-2">
            <div className="text-[10px] font-bold uppercase text-slate-400">
              Compute Cost
            </div>
            <div className="mt-0.5 font-mono text-xs font-bold text-emerald-300">
              {totalCost.toFixed(4)} units
            </div>
          </div>
        </div>

        <div className="mt-3 overflow-x-auto">
          {traces.length === 0 ? (
            <div className="rounded-lg border border-dashed border-line py-8 text-center text-xs text-slate-400">
              No trace entries loaded yet. Generate a plan in Command Center or enter a
              saved session ID above.
            </div>
          ) : (
            <table className="w-full border-collapse text-left text-xs">
              <thead>
                <tr className="border-b border-line text-[10px] uppercase tracking-wider text-slate-400">
                  <th className="py-2 pr-3">Step</th>
                  <th className="py-2 pr-3">Operator</th>
                  <th className="py-2 pr-3">Input Summary</th>
                  <th className="py-2 pr-3">Output Summary</th>
                  <th className="py-2 pr-3 text-right">Seed</th>
                  <th className="py-2 pr-3 text-right">Duration</th>
                  <th className="py-2 text-right">Cost</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line/60">
                {traces.map((step) => (
                  <tr key={step.step_index}>
                    <td className="py-2.5 pr-3 font-mono font-bold text-slate-400">
                      #{step.step_index}
                    </td>
                    <td className="py-2.5 pr-3">
                      <span className="rounded border border-sky-400/30 bg-sky-500/10 px-2 py-0.5 font-mono text-[11px] font-bold text-sky-300">
                        {step.operator_type}
                      </span>
                    </td>
                    <td className="py-2.5 pr-3 text-slate-300">{step.input_summary}</td>
                    <td className="py-2.5 pr-3 text-slate-200">{step.output_summary}</td>
                    <td className="py-2.5 pr-3 text-right font-mono text-slate-400">
                      {step.seed}
                    </td>
                    <td className="py-2.5 pr-3 text-right font-mono text-slate-200">
                      {step.duration_ms.toFixed(2)} ms
                    </td>
                    <td className="py-2.5 text-right font-mono text-emerald-300">
                      {step.cost.toFixed(4)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {/* Planned Phase 5-6 / Gate G4 Agentic Loop & Learned Policy Placeholder */}
      <section className="rounded-xl border border-dashed border-amber-500/50 bg-panel p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Cpu className="h-4 w-4 text-amber-400" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-amber-300">
              Phase 5–6 Controller Telemetry & Gate G4 Policy Controls (Placeholder)
            </h3>
          </div>
          <span className="rounded bg-amber-500/15 px-2 py-0.5 text-[10px] font-bold uppercase text-amber-300">
            Not Yet Implemented (M1 Roadmap)
          </span>
        </div>

        <p className="mt-2 text-xs text-slate-300">
          Today&apos;s Stage C executes deterministic single-pass retrieval + scenario synthesis
          under the 5-step Gate G1 cadence (<code className="text-slate-200">project_context.md</code> Sec. 5.6).
          The following iterative RAG &amp; learned controller widgets are reserved placeholders
          for Phases 5–6:
        </p>

        <div className="mt-3 grid grid-cols-1 gap-2.5 md:grid-cols-3">
          <div className="rounded-lg border border-line bg-[#0a1122] p-3 text-xs">
            <div className="flex items-center gap-1.5 font-semibold text-slate-200">
              <Lock className="h-3.5 w-3.5 text-amber-400" />
              Controller Policy Mode
            </div>
            <p className="mt-1 text-[11px] text-slate-400">
              Placeholder selector for <code className="text-slate-300">Rule-Router</code> vs{" "}
              <code className="text-slate-300">No-RAG / Fixed-RAG</code> baselines vs{" "}
              <code className="text-slate-300">PyTorch Masked MLP (Gate G4)</code>.
            </p>
          </div>
          <div className="rounded-lg border border-line bg-[#0a1122] p-3 text-xs">
            <div className="flex items-center gap-1.5 font-semibold text-slate-200">
              <Lock className="h-3.5 w-3.5 text-amber-400" />
              Iterative GRADE / REWRITE Loop
            </div>
            <p className="mt-1 text-[11px] text-slate-400">
              Placeholder progression chart showing <code className="text-slate-300">RETRIEVE_DECISIONS</code>{" "}
              &amp; evidence sufficiency grading per controller step.
            </p>
          </div>
          <div className="rounded-lg border border-line bg-[#0a1122] p-3 text-xs">
            <div className="flex items-center gap-1.5 font-semibold text-slate-200">
              <Lock className="h-3.5 w-3.5 text-amber-400" />
              Loop L3 Regret &amp; Calibration
            </div>
            <p className="mt-1 text-[11px] text-slate-400">
              Placeholder telemetry for oracle trajectory labeling, cost-regret tradeoff,
              and ECE/AUROC scoring (Phase 6–7).
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}

