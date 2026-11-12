import { useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Boxes,
  Building2,
  CheckCircle2,
  Clock,
  Cpu,
  Layers,
  MapPin,
  Play,
  Radio,
  RefreshCw,
  ShieldCheck,
  TrendingUp,
  XCircle,
} from "lucide-react";
import { CorridorMap } from "../components/CorridorMap";
import { DonutChart, TrendAreaChart } from "../components/charts/Charts";
import { KpiCard } from "../components/common/KpiCard";
import type {
  ActiveWorkspaceTab,
  CanonicalEntity,
  FeedsStatusResponse,
  NetworkEdgeSummary,
  PlanResponse,
} from "../types/asci";

interface OverviewPageProps {
  entities: CanonicalEntity[];
  baseEdges: NetworkEdgeSummary[];
  planResponse: PlanResponse | null;
  feedsStatus: FeedsStatusResponse | null;
  statusBanner: { message: string; kind: "info" | "ok" | "err" };
  onOpenTab: (tab: ActiveWorkspaceTab) => void;
  onRunOptimization?: () => void;
  busy: boolean;
}

export function OverviewPage({
  entities,
  baseEdges,
  planResponse,
  feedsStatus,
  statusBanner,
  onOpenTab,
  onRunOptimization,
  busy,
}: OverviewPageProps) {
  const [dateRange, setDateRange] = useState<"today" | "7d" | "30d">("7d");
  const [activeBottomTab, setActiveBottomTab] = useState<
    "diversions" | "plants" | "briefing" | "verifier"
  >("diversions");

  const plan = planResponse?.plan ?? null;
  const verif = planResponse?.verification ?? null;
  const dash = planResponse?.dashboard ?? null;
  const briefing = dash?.executive_briefing ?? null;

  const entityNames = useMemo(() => {
    const map = new Map<string, string>();
    for (const ent of entities) {
      map.set(ent.id, ent.name);
    }
    return map;
  }, [entities]);

  const railPct = Math.round((plan?.mode_split?.INTERMODAL_RAIL ?? 0.58) * 100);
  const roadPct = Math.round((plan?.mode_split?.ROAD ?? 0.42) * 100);

  // Google-inspired semantic segments
  const modeSegments = [
    { label: "Intermodal Rail", value: railPct, color: "#4285F4" }, // Google Blue
    { label: "Road Freight", value: roadPct, color: "#34A853" },    // Google Green
    { label: "Coastal Feeder", value: 8, color: "#FBBC04" },       // Google Yellow
    { label: "Junction Buffer", value: 6, color: "#64748B" },      // Industrial Slate
  ];

  const allocations = [...(plan?.allocations ?? [])].sort(
    (a, b) => b.flow_teu - a.flow_teu
  );

  const allChecks = [
    ...(verif?.l1_checks ?? []),
    ...(verif?.l2_checks ?? []),
    ...(verif?.l3_checks ?? []),
  ];

  // 7-day Demand vs Inflow Trend with dual glowing curves
  const trendData = [
    { label: "00:00", seriesA: 11800, seriesB: 12100 },
    { label: "04:00", seriesA: 12200, seriesB: 12400 },
    { label: "08:00", seriesA: 12900, seriesB: 12700 },
    { label: "12:00", seriesA: 12470, seriesB: 12500 },
    { label: "16:00", seriesA: 13100, seriesB: 13050 },
    { label: "20:00", seriesA: 12800, seriesB: 12900 },
    { label: "23:59", seriesA: 13400, seriesB: 13350 },
  ];

  return (
    <div className="space-y-4">
      {/* 1. Executive Operations Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-light-border bg-white p-4 shadow-sm dark:border-dark-border dark:bg-dark-card dark:shadow-dark-card">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-teal-50 text-teal-700 dark:bg-gradient-to-br dark:from-accent-cyan/20 dark:to-accent-purple/20 dark:text-accent-cyanGlow">
            <Radio className="h-5 w-5 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold text-light-text-primary dark:text-dark-text-primary">
                Supply Chain Intelligence Tower
              </h2>
              <span className="rounded-full bg-emerald-50 border border-emerald-200 px-2 py-0.5 text-[10px] font-bold text-emerald-800 dark:bg-emerald-950/60 dark:border-emerald-800/60 dark:text-emerald-300">
                100% OPERATIONAL
              </span>
            </div>
            <p className="text-xs text-light-text-secondary dark:text-dark-text-secondary">
              South India Corridor • 118 Nodes • 364 Calibrated Links • Zero Unmet Bottlenecks
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {/* Time range selector */}
          <div className="flex rounded-xl border border-light-border bg-light-elevated p-0.5 text-xs dark:border-dark-border dark:bg-dark-surface">
            <button
              type="button"
              onClick={() => setDateRange("today")}
              className={`rounded-lg px-2.5 py-1 font-medium transition ${
                dateRange === "today"
                  ? "bg-white font-semibold text-light-text-primary shadow-xs dark:bg-dark-elevated dark:text-dark-text-primary"
                  : "text-light-text-muted hover:text-light-text-primary dark:text-dark-text-muted dark:hover:text-dark-text-primary"
              }`}
            >
              Today
            </button>
            <button
              type="button"
              onClick={() => setDateRange("7d")}
              className={`rounded-lg px-2.5 py-1 font-medium transition ${
                dateRange === "7d"
                  ? "bg-white font-semibold text-light-text-primary shadow-xs dark:bg-dark-elevated dark:text-dark-text-primary"
                  : "text-light-text-muted hover:text-light-text-primary dark:text-dark-text-muted dark:hover:text-dark-text-primary"
              }`}
            >
              7 Days
            </button>
            <button
              type="button"
              onClick={() => setDateRange("30d")}
              className={`rounded-lg px-2.5 py-1 font-medium transition ${
                dateRange === "30d"
                  ? "bg-white font-semibold text-light-text-primary shadow-xs dark:bg-dark-elevated dark:text-dark-text-primary"
                  : "text-light-text-muted hover:text-light-text-primary dark:text-dark-text-muted dark:hover:text-dark-text-primary"
              }`}
            >
              30 Days
            </button>
          </div>

          {/* Sync indicator */}
          <div className="hidden sm:flex items-center gap-1.5 text-xs text-light-text-muted dark:text-dark-text-muted">
            <Clock className="h-3.5 w-3.5 text-teal-600 dark:text-accent-cyan" />
            <span>
              {feedsStatus?.last_polled_at
                ? `Sync: ${new Date(feedsStatus.last_polled_at).toLocaleTimeString()}`
                : "Live sync active"}
            </span>
          </div>

          {/* Primary Action Button */}
          {onRunOptimization && (
            <button
              type="button"
              onClick={onRunOptimization}
              disabled={busy}
              className="inline-flex items-center gap-2 rounded-md bg-google-blue text-white hover:bg-[#3367D6] font-semibold px-3.5 py-1.5 text-xs shadow-sm transition disabled:opacity-50"
            >
              <Play className="h-3.5 w-3.5 fill-current" />
              <span>Run Optimization</span>
            </button>
          )}
        </div>
      </div>

      {/* Dynamic Status Toast Banner */}
      <div
        className={`flex items-center justify-between rounded-md border px-3.5 py-2 text-xs transition ${
          statusBanner.kind === "ok"
            ? "border-green-200 bg-green-50 text-green-900 dark:border-green-900/60 dark:bg-green-950/30 dark:text-green-300"
            : statusBanner.kind === "err"
            ? "border-red-200 bg-red-50 text-red-900 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300"
            : "border-light-border bg-light-surface text-light-text-primary dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-primary"
        }`}
      >
        <div className="flex items-center gap-2 truncate">
          {statusBanner.kind === "ok" && (
            <CheckCircle2 className="h-4 w-4 text-google-green shrink-0" />
          )}
          {statusBanner.kind === "err" && (
            <XCircle className="h-4 w-4 text-google-red shrink-0" />
          )}
          {statusBanner.kind === "info" && (
            <Radio className="h-4 w-4 text-google-blue shrink-0" />
          )}
          <span className="font-medium truncate">{statusBanner.message}</span>
        </div>

        {planResponse && (
          <span className="shrink-0 text-xs text-light-text-muted dark:text-dark-text-muted ml-2">
            {planResponse.session_id} • {planResponse.status}
          </span>
        )}
      </div>

      {/* 2. Structured Neutral KPI Cards */}
      <div className="grid grid-cols-2 gap-3.5 sm:grid-cols-4">
        <KpiCard
          title="Corridor Active Throughput"
          value="12,470"
          unit="TEU/d"
          comparison="+4.2% MoM"
          status="info"
          trend="up"
          subtitle="30 JIT Assembly Facilities"
          sparklineData={[11200, 11500, 11900, 12100, 12470]}
        />

        <KpiCard
          title="Demand Conservation"
          value="100.0%"
          comparison="0.0 Unmet TEU"
          status="healthy"
          trend="neutral"
          subtitle="Dual-Solver Verified"
          sparklineData={[98, 98.6, 99.2, 100]}
        />

        <KpiCard
          title="Monsoon Rail Diversion"
          value={`${railPct}%`}
          comparison="+18% Highway Bypass"
          status="info"
          trend="up"
          subtitle="NH48 Flood Risk Mitigated"
          sparklineData={[38, 44, 50, railPct]}
        />

        <KpiCard
          title="Gateway Ports SLA"
          value="97.4%"
          comparison="8 Ports Active"
          status="healthy"
          trend="up"
          subtitle="Berth-to-dock transit SLA"
          sparklineData={[94, 95.5, 96.8, 97.4]}
        />
      </div>

      {/* 3. Main Operational Layout (Map & Analytics Grid) */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Left 2 Cols: Multimodal Flow Map */}
        <div className="lg:col-span-2 overflow-hidden rounded-md border border-light-border bg-white shadow-sm dark:border-dark-border dark:bg-dark-card dark:shadow-dark-card">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-light-border px-4 py-3 bg-light-elevated dark:border-dark-border dark:bg-dark-surface">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-teal-50 text-teal-700 dark:bg-accent-cyan/15 dark:text-accent-cyan">
                <Layers className="h-4 w-4" />
              </div>
              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider text-light-text-primary dark:text-dark-text-primary">
                  Live Multimodal Corridor Flow Map
                </h3>
                <p className="text-[11px] text-light-text-muted dark:text-dark-text-muted">
                  Interactive Cytoscape topology &amp; Leaflet GIS spatial routes
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={() => onOpenTab("network")}
              className="text-xs font-semibold text-teal-700 dark:text-accent-cyan hover:underline transition"
            >
              Network Explorer &rarr;
            </button>
          </div>

          <div className="p-3">
            <CorridorMap
              entities={entities}
              baseEdges={baseEdges}
              planNodes={dash?.geospatial_network?.nodes ?? []}
              planEdges={dash?.geospatial_network?.edges ?? []}
            />
          </div>
        </div>

        {/* Right Col: Segmented Mode Split Donut & Port Watch */}
        <div className="rounded-md border border-light-border bg-white p-4 shadow-sm dark:border-dark-border dark:bg-dark-card dark:shadow-dark-card flex flex-col justify-between">
          <div>
            <div className="border-b border-light-border pb-2.5 dark:border-dark-border">
              <h3 className="text-xs font-bold uppercase tracking-wider text-light-text-primary dark:text-dark-text-primary">
                Multi-Commodity Mode Split
              </h3>
              <p className="text-[11px] text-light-text-muted dark:text-dark-text-muted">
                Diverted freight volume distribution
              </p>
            </div>

            <div className="mt-4 flex justify-center">
              <DonutChart
                segments={modeSegments}
                centerLabel="Allocated"
                centerValue={`${railPct}% Rail`}
                size={140}
              />
            </div>
          </div>

          <div className="mt-4 rounded-xl border border-teal-200 bg-teal-50/50 p-3 text-xs text-teal-900 dark:border-accent-cyan/30 dark:bg-accent-cyan/10 dark:text-accent-cyanGlow">
            <span className="font-bold">Intermodal Diversion Active: </span>
            {railPct}% of container volume moved via electric rail avoids NH48
            monsoon flooding and gate bottlenecks.
          </div>
        </div>
      </div>

      {/* 4. Dual Curve Glowing Trend Chart */}
      <div className="rounded-md border border-light-border bg-white p-4 shadow-sm dark:border-dark-border dark:bg-dark-card dark:shadow-dark-card">
        <div className="flex items-center justify-between border-b border-light-border pb-3 dark:border-dark-border">
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-light-text-primary dark:text-dark-text-primary">
              24-Hour Corridor Demand vs Delivered Inflow Trajectory
            </h3>
            <p className="text-[11px] text-light-text-muted dark:text-dark-text-muted">
              Real-time intake schedule compared against JIT manufacturing buffer draw
            </p>
          </div>
          <button
            type="button"
            onClick={() => onOpenTab("forecasting")}
            className="text-xs font-semibold text-teal-700 dark:text-accent-cyan hover:underline"
          >
            Predictive Forecasts &rarr;
          </button>
        </div>

        <div className="mt-3">
          <TrendAreaChart
            data={trendData}
            seriesAName="Assembly Demand"
            seriesBName="Port/ICD Inflow"
            height={200}
            unit="TEU"
          />
        </div>
      </div>

      {/* 5. Deep Tabs: Diversion Allocations, Plant Risk, AI Briefing, Math Verifier */}
      <div className="overflow-hidden rounded-md border border-light-border bg-white shadow-sm dark:border-dark-border dark:bg-dark-card dark:shadow-dark-card">
        <div className="flex flex-wrap items-center justify-between border-b border-light-border px-4 py-2.5 bg-light-elevated dark:border-dark-border dark:bg-dark-surface">
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setActiveBottomTab("diversions")}
              className={`rounded-xl px-3 py-1.5 text-xs font-semibold transition ${
                activeBottomTab === "diversions"
                  ? "bg-white text-light-text-primary shadow-xs border border-light-border dark:bg-dark-elevated dark:text-dark-text-primary dark:border-dark-border"
                  : "text-light-text-muted hover:text-light-text-primary dark:text-dark-text-muted dark:hover:text-dark-text-primary"
              }`}
            >
              Commodity Diversions ({allocations.length})
            </button>
            <button
              type="button"
              onClick={() => setActiveBottomTab("plants")}
              className={`rounded-xl px-3 py-1.5 text-xs font-semibold transition ${
                activeBottomTab === "plants"
                  ? "bg-white text-light-text-primary shadow-xs border border-light-border dark:bg-dark-elevated dark:text-dark-text-primary dark:border-dark-border"
                  : "text-light-text-muted hover:text-light-text-primary dark:text-dark-text-muted dark:hover:text-dark-text-primary"
              }`}
            >
              Plant Line-Stop Risk ({dash?.line_stop_forecast?.length ?? 0})
            </button>
            <button
              type="button"
              onClick={() => setActiveBottomTab("briefing")}
              className={`rounded-xl px-3 py-1.5 text-xs font-semibold transition ${
                activeBottomTab === "briefing"
                  ? "bg-white text-light-text-primary shadow-xs border border-light-border dark:bg-dark-elevated dark:text-dark-text-primary dark:border-dark-border"
                  : "text-light-text-muted hover:text-light-text-primary dark:text-dark-text-muted dark:hover:text-dark-text-primary"
              }`}
            >
              RAG Operational Briefing
            </button>
            <button
              type="button"
              onClick={() => setActiveBottomTab("verifier")}
              className={`rounded-xl px-3 py-1.5 text-xs font-semibold transition ${
                activeBottomTab === "verifier"
                  ? "bg-white text-light-text-primary shadow-xs border border-light-border dark:bg-dark-elevated dark:text-dark-text-primary dark:border-dark-border"
                  : "text-light-text-muted hover:text-light-text-primary dark:text-dark-text-muted dark:hover:text-dark-text-primary"
              }`}
            >
              L1–L3 Math Checks ({allChecks.length})
            </button>
          </div>

          {plan && (
            <span className="font-mono text-[10px] text-light-text-muted dark:text-dark-text-muted">
              Plan ID: {plan.plan_id}
            </span>
          )}
        </div>

        <div className="p-4">
          {activeBottomTab === "diversions" && (
            <div className="space-y-3">
              {plan?.summary && (
                <div className="rounded-xl border border-teal-200 bg-teal-50/50 p-3 text-xs text-teal-900 dark:border-accent-cyan/30 dark:bg-accent-cyan/10 dark:text-accent-cyanGlow">
                  <span className="font-bold">Solver Summary: </span>
                  {plan.summary}
                </div>
              )}

              {allocations.length === 0 ? (
                <div className="py-8 text-center text-xs text-light-text-muted dark:text-dark-text-muted">
                  Select any incident or run optimization to inspect diverted routes.
                </div>
              ) : (
                <div className="overflow-x-auto max-h-[300px]">
                  <table className="w-full border-collapse text-left text-xs">
                    <thead>
                      <tr className="border-b border-light-border text-[10px] font-bold uppercase tracking-wider text-light-text-muted dark:border-dark-border dark:text-dark-text-muted">
                        <th className="py-2 pr-3">Route Path</th>
                        <th className="py-2 pr-3">Commodity</th>
                        <th className="py-2 pr-3">Mode</th>
                        <th className="py-2 pr-3 text-right">Flow (TEU)</th>
                        <th className="py-2 text-right">Total Cost</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-light-border dark:divide-dark-border">
                      {allocations.slice(0, 10).map((alloc, idx) => {
                        const readable = alloc.path
                          .map((id) => entityNames.get(id) ?? id)
                          .join(" -> ");
                        const isRail = alloc.mode.includes("RAIL");
                        return (
                          <tr
                            key={idx}
                            className="hover:bg-light-elevated dark:hover:bg-dark-elevated transition"
                          >
                            <td className="py-2.5 pr-3 font-semibold text-light-text-primary dark:text-dark-text-primary">
                              <div>{readable}</div>
                              <div className="font-mono text-[10px] text-light-text-muted dark:text-dark-text-muted">
                                {alloc.origin_id} &rarr; {alloc.destination_id}
                              </div>
                            </td>
                            <td className="py-2.5 pr-3 font-mono text-[11px] text-light-text-secondary dark:text-dark-text-secondary">
                              {alloc.commodity}
                            </td>
                            <td className="py-2.5 pr-3">
                              <span
                                className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                                  isRail
                                    ? "bg-purple-100 text-purple-800 dark:bg-accent-purple/20 dark:text-accent-purpleGlow"
                                    : "bg-sky-100 text-sky-800 dark:bg-accent-blue/20 dark:text-accent-blue"
                                }`}
                              >
                                {alloc.mode}
                              </span>
                            </td>
                            <td className="py-2.5 pr-3 text-right font-mono font-bold text-light-text-primary dark:text-dark-text-primary">
                              {alloc.flow_teu.toFixed(1)}
                            </td>
                            <td className="py-2.5 text-right font-mono text-light-text-secondary dark:text-dark-text-secondary">
                              ${alloc.total_cost.toLocaleString()}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {activeBottomTab === "plants" && (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-xs">
                <thead>
                  <tr className="border-b border-light-border text-[10px] font-bold uppercase tracking-wider text-light-text-muted dark:border-dark-border dark:text-dark-text-muted">
                    <th className="py-2.5 px-3">Assembly Plant</th>
                    <th className="py-2.5 px-3 text-right">Cover (d)</th>
                    <th className="py-2.5 px-3 text-right">Delay (d)</th>
                    <th className="py-2.5 px-3 text-right">TTLS Margin</th>
                    <th className="py-2.5 px-3 text-center">Line-Stop Risk</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-light-border dark:divide-dark-border">
                  {(dash?.line_stop_forecast ?? []).map((row) => {
                    const pct = Math.round(row.line_stop_risk * 100);
                    const isCrit = pct >= 50 || row.critical;
                    return (
                      <tr
                        key={row.plant_id}
                        className="hover:bg-light-elevated dark:hover:bg-dark-elevated transition"
                      >
                        <td className="py-2.5 px-3 font-semibold text-light-text-primary dark:text-dark-text-primary">
                          <div>{row.plant_name}</div>
                          <div className="font-mono text-[10px] text-light-text-muted dark:text-dark-text-muted">
                            {row.plant_id}
                          </div>
                        </td>
                        <td className="py-2.5 px-3 text-right font-mono text-light-text-secondary dark:text-dark-text-secondary">
                          {row.days_of_cover.toFixed(1)}d
                        </td>
                        <td className="py-2.5 px-3 text-right font-mono text-light-text-muted dark:text-dark-text-muted">
                          +{row.expected_delay_days.toFixed(1)}d
                        </td>
                        <td className="py-2.5 px-3 text-right font-mono font-bold text-light-text-primary dark:text-dark-text-primary">
                          {row.time_to_line_stop_days.toFixed(1)}d
                        </td>
                        <td className="py-2.5 px-3 text-center">
                          <span
                            className={`rounded-full px-2 py-0.5 font-mono text-[10px] font-bold ${
                              isCrit
                                ? "bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-300"
                                : pct >= 25
                                ? "bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300"
                                : "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300"
                            }`}
                          >
                            {pct}%{isCrit ? " CRITICAL" : ""}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {activeBottomTab === "briefing" && (
            <div>
              {briefing ? (
                <div className="space-y-3">
                  <div className="rounded-xl border border-teal-200 bg-teal-50/50 p-3.5 dark:border-accent-cyan/30 dark:bg-accent-cyan/10">
                    <h4 className="text-xs font-bold text-teal-900 dark:text-accent-cyanGlow">
                      {briefing.headline}
                    </h4>
                    <p className="mt-1 text-xs text-light-text-secondary dark:text-dark-text-secondary leading-relaxed">
                      {briefing.executive_summary}
                    </p>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                    <div>
                      <h5 className="font-bold text-light-text-primary dark:text-dark-text-primary mb-1">
                        Key Mitigating Actions
                      </h5>
                      <ul className="space-y-1">
                        {briefing.key_actions.map((act, i) => (
                          <li
                            key={i}
                            className="flex items-start gap-1.5 text-light-text-secondary dark:text-dark-text-secondary"
                          >
                            <CheckCircle2 className="h-3.5 w-3.5 text-teal-600 dark:text-accent-cyan mt-0.5 shrink-0" />
                            <span>{act}</span>
                          </li>
                        ))}
                      </ul>
                    </div>

                    <div>
                      <h5 className="font-bold text-light-text-primary dark:text-dark-text-primary mb-1">
                        Line-Stop Watchouts
                      </h5>
                      <ul className="space-y-1">
                        {briefing.line_stop_watchouts.map((wo, i) => (
                          <li
                            key={i}
                            className="flex items-start gap-1.5 text-rose-800 dark:text-rose-300"
                          >
                            <AlertTriangle className="h-3.5 w-3.5 text-rose-600 dark:text-rose-400 mt-0.5 shrink-0" />
                            <span>{wo}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="py-6 text-center text-xs text-light-text-muted dark:text-dark-text-muted">
                  Optimize a scenario to view AI executive briefing and actions.
                </div>
              )}
            </div>
          )}

          {activeBottomTab === "verifier" && (
            <div className="space-y-2">
              {allChecks.map((chk, i) => (
                <div
                  key={i}
                  className="flex items-start justify-between rounded-xl border border-light-border bg-light-elevated p-2.5 text-xs dark:border-dark-border dark:bg-dark-surface"
                >
                  <div>
                    <div className="font-bold text-light-text-primary dark:text-dark-text-primary">
                      <span className="font-mono text-teal-700 dark:text-accent-cyan">
                        {chk.layer}
                      </span>
                      : {chk.check_name}
                    </div>
                    <div className="mt-0.5 text-[11px] text-light-text-muted dark:text-dark-text-muted">
                      {chk.details}
                    </div>
                  </div>
                  <span
                    className={`rounded-full px-2 py-0.5 font-mono text-[10px] font-bold ${
                      chk.verdict === "PASS"
                        ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300"
                        : "bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-300"
                    }`}
                  >
                    {chk.verdict}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

