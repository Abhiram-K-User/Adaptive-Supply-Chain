import { useMemo, useState } from "react";
import {
  CheckCircle2,
  FileText,
  GitBranch,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { CorridorMap } from "./CorridorMap";
import { LiveFeedStrip } from "./LiveFeedStrip";
import type {
  ActiveWorkspaceTab,
  CanonicalEntity,
  FeedsStatusResponse,
  NetworkEdgeSummary,
  PlanResponse,
} from "../types/asci";

interface OverviewCommandViewProps {
  entities: CanonicalEntity[];
  baseEdges: NetworkEdgeSummary[];
  planResponse: PlanResponse | null;
  feedsStatus: FeedsStatusResponse | null;
  statusBanner: { message: string; kind: "info" | "ok" | "err" };
  plannerComments: string;
  onChangePlannerComments: (val: string) => void;
  onRecordDecision: (decision: "APPROVE" | "EDIT" | "REJECT", customEdits?: Record<string, unknown>) => void;
  onOpenTab: (tab: ActiveWorkspaceTab) => void;
  busy: boolean;
}

type BottomTab = "diversion" | "plants" | "verifier";

export function OverviewCommandView({
  entities,
  baseEdges,
  planResponse,
  feedsStatus,
  statusBanner,
  plannerComments,
  onChangePlannerComments,
  onRecordDecision,
  onOpenTab,
  busy,
}: OverviewCommandViewProps) {
  const [bottomTab, setBottomTab] = useState<BottomTab>("diversion");
  const [editDrawerOpen, setEditDrawerOpen] = useState(false);
  const [editModJson, setEditModJson] = useState('{"manual_rail_floor_pct": 60}');

  const entityNames = useMemo(() => {
    const map = new Map<string, string>();
    for (const ent of entities) {
      map.set(ent.id, ent.name);
    }
    return map;
  }, [entities]);

  const plan = planResponse?.plan ?? null;
  const verif = planResponse?.verification ?? null;
  const dash = planResponse?.dashboard ?? null;
  const briefing = dash?.executive_briefing ?? null;

  const railSharePct = ((plan?.mode_split?.INTERMODAL_RAIL ?? 0) * 100).toFixed(1);
  const roadSharePct = ((plan?.mode_split?.ROAD ?? 0) * 100).toFixed(1);

  const allChecks = [
    ...(verif?.l1_checks ?? []),
    ...(verif?.l2_checks ?? []),
    ...(verif?.l3_checks ?? []),
  ];

  const allocations = [...(plan?.allocations ?? [])].sort(
    (a, b) => b.flow_teu - a.flow_teu
  );

  const bannerTone =
    statusBanner.kind === "ok"
      ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-200"
      : statusBanner.kind === "err"
      ? "border-red-500/40 bg-red-500/10 text-red-200"
      : "border-line bg-panel text-slate-300";

  const handleConfirmEdit = () => {
    try {
      const parsed = JSON.parse(editModJson) as Record<string, unknown>;
      onRecordDecision("EDIT", parsed);
      setEditDrawerOpen(false);
    } catch {
      onRecordDecision("EDIT", { raw_note: editModJson });
      setEditDrawerOpen(false);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_390px]">
      {/* Center Column */}
      <div className="min-w-0 space-y-3">
        <div
          className={`flex items-center justify-between rounded-xl border px-3.5 py-2 text-xs ${bannerTone}`}
        >
          <span>{statusBanner.message}</span>
          {planResponse && (
            <span className="font-mono text-[11px] text-slate-400">
              {planResponse.session_id} · {planResponse.status}
            </span>
          )}
        </div>

        <LiveFeedStrip feedsStatus={feedsStatus} />

        {/* KPI Strip */}
        <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
          <div className="rounded-xl border border-line bg-panel px-3.5 py-2.5">
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Objective Cost ({plan?.risk_mode ?? "—"})
            </div>
            <div className="mt-1 font-mono text-lg font-extrabold text-white">
              {plan ? `$${plan.objective_cost.toLocaleString(undefined, { maximumFractionDigits: 1 })}` : "—"}
            </div>
            <div className="text-[10px] text-slate-400">
              Engine: {plan?.solver_engine ?? "OR-Tools / HiGHS"}
            </div>
          </div>

          <div className="rounded-xl border border-line bg-panel px-3.5 py-2.5">
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Unmet Demand (TEU)
            </div>
            <div
              className={`mt-1 font-mono text-lg font-extrabold ${
                plan
                  ? plan.unmet_demand_teu <= 0.01
                    ? "text-emerald-400"
                    : "text-red-400"
                  : "text-white"
              }`}
            >
              {plan ? plan.unmet_demand_teu.toFixed(1) : "—"}
            </div>
            <div className="text-[10px] text-slate-400">
              Corridor demand fulfillment
            </div>
          </div>

          <div className="rounded-xl border border-line bg-panel px-3.5 py-2.5">
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Rail Mode Share
            </div>
            <div className="mt-1 font-mono text-lg font-extrabold text-purple-300">
              {plan ? `${railSharePct}%` : "—"}
            </div>
            <div className="text-[10px] text-slate-400">
              {plan ? `Road share: ${roadSharePct}%` : "Intermodal diversion"}
            </div>
          </div>

          <div className="rounded-xl border border-line bg-panel px-3.5 py-2.5">
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
              L1–L3 Verifier
            </div>
            <div
              className={`mt-1 font-mono text-lg font-extrabold ${
                verif
                  ? verif.passed
                    ? "text-emerald-400"
                    : "text-red-400"
                  : "text-white"
              }`}
            >
              {verif ? verif.overall_verdict : "—"}
            </div>
            <div className="text-[10px] text-slate-400">
              {verif ? `${allChecks.length} assertions executed` : "Gate G2/G3 checks"}
            </div>
          </div>
        </div>

        {/* Interactive Cytoscape.js Map */}
        <CorridorMap
          entities={entities}
          baseEdges={baseEdges}
          planNodes={dash?.geospatial_network?.nodes ?? []}
          planEdges={dash?.geospatial_network?.edges ?? []}
        />

        {/* Deep Analysis Tabs */}
        <section className="rounded-xl border border-line bg-panel shadow-lg shadow-black/25">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-3 py-2">
            <div className="flex flex-wrap gap-1.5">
              <button
                type="button"
                onClick={() => setBottomTab("diversion")}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                  bottomTab === "diversion"
                    ? "border border-sky-400/50 bg-sky-500/15 text-sky-300"
                    : "text-slate-400 hover:bg-panel2 hover:text-slate-200"
                }`}
              >
                Where Freight Was Diverted ({allocations.length})
              </button>
              <button
                type="button"
                onClick={() => setBottomTab("plants")}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                  bottomTab === "plants"
                    ? "border border-sky-400/50 bg-sky-500/15 text-sky-300"
                    : "text-slate-400 hover:bg-panel2 hover:text-slate-200"
                }`}
              >
                Plant Line-Stop Risk ({dash?.line_stop_forecast?.length ?? 0})
              </button>
              <button
                type="button"
                onClick={() => setBottomTab("verifier")}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                  bottomTab === "verifier"
                    ? "border border-sky-400/50 bg-sky-500/15 text-sky-300"
                    : "text-slate-400 hover:bg-panel2 hover:text-slate-200"
                }`}
              >
                L1–L3 Math Checks ({allChecks.length})
              </button>
            </div>
            {plan && (
              <span className="font-mono text-[10px] text-slate-400">
                {plan.plan_id}
              </span>
            )}
          </div>

          <div className="max-h-[340px] overflow-auto p-3.5">
            {bottomTab === "diversion" && (
              <div className="space-y-3">
                {plan?.summary && (
                  <div className="rounded-lg border border-line bg-[#0a1122] px-3 py-2 text-xs text-slate-300">
                    <span className="font-semibold text-sky-300">Solver Summary: </span>
                    {plan.summary}
                  </div>
                )}

                {allocations.length === 0 ? (
                  <div className="py-6 text-center text-xs text-slate-400">
                    Run a scenario plan to inspect commodity path allocations.
                  </div>
                ) : (
                  <table className="w-full border-collapse text-left text-xs">
                    <thead>
                      <tr className="border-b border-line text-[10px] uppercase tracking-wider text-slate-400">
                        <th className="py-2 pr-2">Route Path</th>
                        <th className="py-2 pr-2">Commodity</th>
                        <th className="py-2 pr-2">Mode</th>
                        <th className="py-2 pr-2 text-right">Flow (TEU)</th>
                        <th className="py-2 text-right">Cost</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line/60">
                      {allocations.slice(0, 20).map((alloc, idx) => {
                        const readablePath = alloc.path
                          .map((id) => entityNames.get(id) ?? id)
                          .join(" -> ");
                        const isRail = alloc.mode.toUpperCase().includes("RAIL");
                        return (
                          <tr key={`${alloc.origin_id}-${alloc.destination_id}-${idx}`}>
                            <td className="py-2 pr-2 font-medium text-slate-200">
                              <div>{readablePath}</div>
                              <div className="font-mono text-[10px] text-slate-500">
                                {alloc.origin_id} -&gt; {alloc.destination_id}
                              </div>
                            </td>
                            <td className="py-2 pr-2 font-mono text-[11px] text-slate-300">
                              {alloc.commodity}
                            </td>
                            <td className="py-2 pr-2">
                              <span
                                className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                                  isRail
                                    ? "bg-purple-500/15 text-purple-300"
                                    : "bg-sky-500/15 text-sky-300"
                                }`}
                              >
                                {alloc.mode}
                              </span>
                            </td>
                            <td className="py-2 pr-2 text-right font-mono font-bold text-white">
                              {alloc.flow_teu.toFixed(1)}
                            </td>
                            <td className="py-2 text-right font-mono text-slate-300">
                              ${alloc.total_cost.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>
            )}

            {bottomTab === "plants" && (
              <div>
                {(dash?.line_stop_forecast?.length ?? 0) === 0 ? (
                  <div className="py-6 text-center text-xs text-slate-400">
                    No plant risk forecast loaded yet.
                  </div>
                ) : (
                  <table className="w-full border-collapse text-left text-xs">
                    <thead>
                      <tr className="border-b border-line text-[10px] uppercase tracking-wider text-slate-400">
                        <th className="py-2 pr-2">Assembly Plant</th>
                        <th className="py-2 pr-2 text-right">Cover (d)</th>
                        <th className="py-2 pr-2 text-right">Delay (d)</th>
                        <th className="py-2 pr-2 text-right">TTLS (d)</th>
                        <th className="py-2 text-right">Line-Stop Risk</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line/60">
                      {(dash?.line_stop_forecast ?? []).map((row) => {
                        const pct = Math.round(row.line_stop_risk * 100);
                        const tone =
                          pct >= 50 || row.critical
                            ? "bg-red-500/15 text-red-300"
                            : pct >= 25
                            ? "bg-amber-500/15 text-amber-300"
                            : "bg-emerald-500/15 text-emerald-300";
                        return (
                          <tr key={row.plant_id}>
                            <td className="py-2 pr-2">
                              <div className="font-semibold text-slate-100">{row.plant_name}</div>
                              <div className="font-mono text-[10px] text-slate-500">
                                {row.plant_id}
                              </div>
                            </td>
                            <td className="py-2 pr-2 text-right font-mono text-slate-300">
                              {row.days_of_cover.toFixed(2)}
                            </td>
                            <td className="py-2 pr-2 text-right font-mono text-slate-300">
                              {row.expected_delay_days.toFixed(2)}
                            </td>
                            <td className="py-2 pr-2 text-right font-mono text-slate-200">
                              {row.time_to_line_stop_days.toFixed(2)}
                            </td>
                            <td className="py-2 text-right">
                              <span className={`rounded-full px-2 py-0.5 font-mono text-[11px] font-bold ${tone}`}>
                                {pct}%{row.critical ? " CRIT" : ""}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>
            )}

            {bottomTab === "verifier" && (
              <div className="space-y-2.5">
                {allChecks.map((chk) => (
                  <div
                    key={`${chk.layer}-${chk.check_name}`}
                    className="flex items-start justify-between gap-3 rounded-lg border border-line bg-[#0a1122] px-3 py-2 text-xs"
                  >
                    <div>
                      <div className="font-mono font-bold text-slate-100">
                        {chk.layer}: {chk.check_name}
                      </div>
                      <div className="mt-0.5 text-[11px] text-slate-400">{chk.details}</div>
                    </div>
                    <span
                      className={`shrink-0 rounded-full px-2 py-0.5 font-mono text-[10px] font-bold ${
                        chk.verdict === "PASS"
                          ? "bg-emerald-500/15 text-emerald-300"
                          : "bg-red-500/15 text-red-300"
                      }`}
                    >
                      {chk.verdict}
                    </span>
                  </div>
                ))}

                {/* Gate G3 Placeholder Rules per project_context.md Sec 2 */}
                <div className="mt-3 rounded-lg border border-dashed border-amber-500/40 bg-amber-500/5 p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold uppercase tracking-wider text-amber-300">
                      Gate G3 Pending Verifier Rules (Placeholder)
                    </span>
                    <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber-300">
                      M2 / M1 Roadmap
                    </span>
                  </div>
                  <div className="mt-2 grid gap-1.5 text-[11px] text-slate-300 sm:grid-cols-3">
                    <div className="rounded border border-line/70 bg-[#0a1122] p-2">
                      <div className="font-mono text-[10px] font-bold text-amber-200">
                        L3: LINE_STOP_SAFETY_THRESHOLD
                      </div>
                      <div className="mt-0.5 text-[10px] text-slate-400">
                        Not yet enforced in Stage D
                      </div>
                    </div>
                    <div className="rounded border border-line/70 bg-[#0a1122] p-2">
                      <div className="font-mono text-[10px] font-bold text-amber-200">
                        L3: PLAN_CHURN_LIMIT
                      </div>
                      <div className="mt-0.5 text-[10px] text-slate-400">
                        Allocation churn stability bound pending
                      </div>
                    </div>
                    <div className="rounded border border-line/70 bg-[#0a1122] p-2">
                      <div className="font-mono text-[10px] font-bold text-amber-200">
                        CLAIM_CITATION_BLOCKING
                      </div>
                      <div className="mt-0.5 text-[10px] text-slate-400">
                        Soft strip active today; hard Gate G3 block pending
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>
      </div>

      {/* Right Rail: Briefing, Evidence Preview, Decision Memory */}
      <aside className="space-y-3">
        {/* RAG & LLM Executive Briefing */}
        <section className="rounded-xl border border-line bg-panel shadow-lg shadow-black/25">
          <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
            <h2 className="text-xs font-bold uppercase tracking-wider text-sky-300">
              RAG & LLM Executive Briefing
            </h2>
            {briefing ? (
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${
                  briefing.mode === "live_llm"
                    ? "bg-emerald-500/15 text-emerald-300"
                    : "bg-slate-700 text-slate-200"
                }`}
              >
                {briefing.mode === "live_llm"
                  ? `LIVE LLM (${briefing.provider})`
                  : "GROUNDED OFFLINE"}
              </span>
            ) : (
              <span className="text-[10px] text-slate-500">Idle</span>
            )}
          </div>

          <div className="space-y-3 p-3.5 text-xs">
            {!briefing ? (
              <p className="text-slate-400">
                Select a disruption event or run Cyclone Michaung Demo to generate a
                citation-verified executive briefing.
              </p>
            ) : (
              <>
                <div className="text-sm font-bold leading-snug text-white">
                  {briefing.headline}
                </div>
                <p className="leading-relaxed text-slate-300">
                  {briefing.executive_summary}
                </p>

                <div className="flex flex-wrap items-center gap-1.5">
                  {briefing.cited_ids.map((cid) => (
                    <button
                      key={cid}
                      type="button"
                      onClick={() => onOpenTab("evidence")}
                      className="rounded border border-sky-400/40 bg-sky-500/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-sky-300 hover:bg-sky-500/20"
                    >
                      [{cid}]
                    </button>
                  ))}
                  {briefing.rejected_citations.map((cid) => (
                    <span
                      key={cid}
                      className="rounded border border-red-400/40 bg-red-500/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-red-300"
                    >
                      Blocked: {cid}
                    </span>
                  ))}
                  <span
                    className={`ml-auto inline-flex items-center gap-1 text-[10px] font-semibold ${
                      briefing.citation_verified ? "text-emerald-300" : "text-amber-300"
                    }`}
                  >
                    <ShieldCheck className="h-3 w-3" />
                    {briefing.citation_verified ? "Citations Verified" : "Hallucinated Tag Stripped"}
                  </span>
                </div>

                {briefing.key_actions.length > 0 && (
                  <div>
                    <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      Recommended Actions
                    </div>
                    <ul className="list-disc space-y-1 pl-4 text-slate-200">
                      {briefing.key_actions.map((act, idx) => (
                        <li key={idx}>{act}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {briefing.line_stop_watchouts.length > 0 && (
                  <div>
                    <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-amber-400">
                      Line-Stop Watchouts
                    </div>
                    <ul className="list-disc space-y-1 pl-4 text-amber-200/90">
                      {briefing.line_stop_watchouts.map((w, idx) => (
                        <li key={idx}>{w}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
          </div>
        </section>

        {/* Evidence Quick Preview */}
        <section className="rounded-xl border border-line bg-panel shadow-lg shadow-black/25">
          <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
            <h2 className="text-xs font-bold uppercase tracking-wider text-sky-300">
              Retrieved Evidence ({dash?.evidence_provenance?.length ?? 0})
            </h2>
            <button
              type="button"
              onClick={() => onOpenTab("evidence")}
              className="inline-flex items-center gap-1 text-[11px] font-semibold text-sky-400 hover:text-sky-300"
            >
              <FileText className="h-3 w-3" />
              Explore All
            </button>
          </div>
          <div className="max-h-52 space-y-2 overflow-y-auto p-3">
            {(dash?.evidence_provenance?.length ?? 0) === 0 ? (
              <div className="text-xs text-slate-400">
                No evidence documents attached yet.
              </div>
            ) : (
              (dash?.evidence_provenance ?? []).slice(0, 3).map((doc) => (
                <div
                  key={doc.citation_id}
                  className="rounded-lg border border-line bg-[#0a1122] p-2.5 text-[11px]"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono font-bold text-sky-300">
                      [{doc.citation_id}]
                    </span>
                    <span className="rounded bg-panel2 px-1.5 py-0.5 text-[10px] font-semibold text-slate-300">
                      {doc.trust_tier}
                    </span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-slate-300">{doc.snippet}</p>
                </div>
              ))
            )}
          </div>
        </section>

        {/* Human Action Gateway (Loop L2 Decision Memory) */}
        <section className="rounded-xl border border-line bg-panel shadow-lg shadow-black/25">
          <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
            <h2 className="text-xs font-bold uppercase tracking-wider text-sky-300">
              Planner Sign-Off (Loop L2)
            </h2>
            <button
              type="button"
              onClick={() => onOpenTab("trace")}
              className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-400 hover:text-sky-300"
            >
              <GitBranch className="h-3 w-3" />
              Trace ({dash?.trace_timeline?.length ?? 0})
            </button>
          </div>

          <div className="space-y-2.5 p-3.5">
            <input
              type="text"
              value={plannerComments}
              onChange={(e) => onChangePlannerComments(e.target.value)}
              placeholder="Planner sign-off comment or edit rationale..."
              className="w-full rounded-lg border border-line bg-[#090f1d] px-2.5 py-1.5 text-xs text-slate-100 focus:border-sky-400 focus:outline-none"
            />

            {editDrawerOpen && (
              <div className="space-y-2 rounded-lg border border-amber-500/40 bg-amber-500/5 p-2.5">
                <div className="text-[11px] font-semibold text-amber-300">
                  Manual Plan Override Metadata (stored in SQLite human_decisions)
                </div>
                <textarea
                  rows={2}
                  value={editModJson}
                  onChange={(e) => setEditModJson(e.target.value)}
                  className="w-full rounded border border-line bg-[#090f1d] p-2 font-mono text-[11px] text-slate-100"
                />
                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setEditDrawerOpen(false)}
                    className="rounded px-2 py-1 text-[11px] text-slate-400 hover:text-white"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    disabled={busy || !plan}
                    onClick={handleConfirmEdit}
                    className="rounded bg-amber-500 px-2.5 py-1 text-[11px] font-bold text-slate-950 hover:bg-amber-400 disabled:opacity-50"
                  >
                    Submit EDIT Decision
                  </button>
                </div>
              </div>
            )}

            <div className="grid grid-cols-3 gap-2">
              <button
                type="button"
                disabled={busy || !plan}
                onClick={() => onRecordDecision("APPROVE")}
                className="inline-flex items-center justify-center gap-1 rounded-lg bg-emerald-500 px-2.5 py-2 text-xs font-bold text-slate-950 transition hover:bg-emerald-400 disabled:opacity-40"
              >
                <CheckCircle2 className="h-3.5 w-3.5" />
                Approve
              </button>
              <button
                type="button"
                disabled={busy || !plan}
                onClick={() => setEditDrawerOpen((prev) => !prev)}
                className="inline-flex items-center justify-center gap-1 rounded-lg border border-amber-400/60 bg-amber-500/15 px-2.5 py-2 text-xs font-bold text-amber-300 transition hover:bg-amber-500/25 disabled:opacity-40"
              >
                Edit Plan
              </button>
              <button
                type="button"
                disabled={busy || !plan}
                onClick={() => onRecordDecision("REJECT")}
                className="inline-flex items-center justify-center gap-1 rounded-lg border border-red-500/60 bg-red-500/15 px-2.5 py-2 text-xs font-bold text-red-300 transition hover:bg-red-500/25 disabled:opacity-40"
              >
                <XCircle className="h-3.5 w-3.5" />
                Reject
              </button>
            </div>
          </div>
        </section>
      </aside>
    </div>
  );
}

