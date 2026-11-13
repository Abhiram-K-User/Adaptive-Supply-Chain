import { useMemo, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  CloudRain,
  Eye,
  Filter,
  Loader2,
  Play,
  Radio,
  RefreshCw,
  RotateCcw,
  Search,
  Send,
  ShieldAlert,
  ShieldCheck,
  Wind,
  XCircle,
} from "lucide-react";
import { KpiCard } from "./common/KpiCard";
import { SCENARIO_PRESETS, type ScenarioPreset } from "../data/presets";
import type {
  DisruptionEvent,
  FeedsStatusResponse,
  PlanResponse,
  TrustTier,
} from "../types/asci";
import type { PlannerControlsState } from "./EventWorkbench";

interface RiskViewProps {
  events: DisruptionEvent[];
  feedsStatus: FeedsStatusResponse | null;
  selectedEventId: string | null;
  planResponse: PlanResponse | null;
  statusBanner?: { message: string; kind: "info" | "ok" | "err" };
  onSelectEventAndPlan: (eventId: string) => void;
  onMitigateEvent?: (
    eventId: string,
    planId?: string | null,
    sessionId?: string | null
  ) => void;
  onReopenEvent?: (eventId: string) => void;
  onOpenOptimizationTab?: () => void;
  controls: PlannerControlsState;
  onChangeControls: (patch: Partial<PlannerControlsState>) => void;
  onIngestAndPlan: () => void;
  onPollLive: () => void;
  busy: boolean;
  mitigatingEventId?: string | null;
}

export function RiskView({
  events,
  feedsStatus,
  selectedEventId,
  planResponse,
  statusBanner,
  onSelectEventAndPlan,
  onMitigateEvent,
  onReopenEvent,
  onOpenOptimizationTab,
  controls,
  onChangeControls,
  onIngestAndPlan,
  onPollLive,
  busy,
  mitigatingEventId = null,
}: RiskViewProps) {
  const [filterSeverity, setFilterSeverity] = useState<string>("ALL");
  const [filterType, setFilterType] = useState<string>("ALL");

  const weather = feedsStatus?.weather_telemetry ?? [];
  const sources = feedsStatus?.source_statuses ?? [];

  const activeEvents = events.filter(
    (e) => e.status === "NEW" || e.status === "UPDATED"
  );
  const mitigatedEvents = events.filter((e) => e.status === "MITIGATED");
  const criticalEvents = activeEvents.filter((e) => e.severity >= 0.6);
  const avgConfidence =
    events.reduce((sum, e) => sum + e.confidence, 0) / (events.length || 1);

  const applyPreset = (preset: ScenarioPreset) => {
    onChangeControls({
      headline: preset.headline,
      rawText: preset.text,
      trustTier: preset.trustTier,
      affectedEntityIds: preset.affectedIds,
    });
  };

  const filteredEvents = useMemo(() => {
    return events.filter((e) => {
      if (filterSeverity === "HIGH" && e.severity < 0.6) return false;
      if (filterSeverity === "MEDIUM" && (e.severity < 0.3 || e.severity >= 0.6))
        return false;
      if (filterSeverity === "LOW" && e.severity >= 0.3) return false;
      if (filterType !== "ALL" && e.event_type !== filterType) return false;
      return true;
    });
  }, [events, filterSeverity, filterType]);

  return (
    <div className="space-y-4">
      {statusBanner && (
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
          {planResponse && onOpenOptimizationTab && (
            <button
              type="button"
              onClick={onOpenOptimizationTab}
              className="ml-3 shrink-0 font-semibold text-google-blue hover:underline"
            >
              Inspect Optimization &rarr;
            </button>
          )}
        </div>
      )}

      {/* 1. Neutral Risk Overview Cards */}
      <div className="grid grid-cols-2 gap-3.5 sm:grid-cols-4">
        <KpiCard
          title="Active Disruptions"
          value={activeEvents.length}
          comparison={
            mitigatedEvents.length > 0
              ? `${mitigatedEvents.length} Mitigated · ${criticalEvents.length} High`
              : criticalEvents.length > 0
              ? `${criticalEvents.length} High Severity`
              : "All Nominal"
          }
          status={activeEvents.length === 0 ? "healthy" : criticalEvents.length > 0 ? "critical" : "warning"}
          trend={activeEvents.length === 0 ? "up" : "down"}
          subtitle="Grounded in SQLite EventStore"
          sparklineData={[1, 2, 3, Math.max(1, activeEvents.length), activeEvents.length]}
        />

        <KpiCard
          title="Perception Confidence"
          value={`${Math.round(avgConfidence * 100)}%`}
          comparison="Stage A Extractor"
          status="healthy"
          trend="up"
          subtitle="Multi-feed corroboration score"
          sparklineData={[82, 85, 87, 89, Math.round(avgConfidence * 100)]}
        />

        <KpiCard
          title="Corridor Weather Alerts"
          value={
            weather.filter(
              (w) => w.alert_color === "RED" || w.alert_color === "ORANGE"
            ).length
          }
          comparison="Open-Meteo Radar"
          status={
            weather.filter(
              (w) => w.alert_color === "RED" || w.alert_color === "ORANGE"
            ).length > 0
              ? "warning"
              : "healthy"
          }
          trend="down"
          subtitle="Ports under cyclone watch"
          sparklineData={[0, 1, 2, 1, 2]}
        />

        <KpiCard
          title="Live Signal Adapters"
          value={`${sources.filter((s) => s.fetch_mode.startsWith("live")).length} / ${sources.length || 4}`}
          comparison="GDACS • GDELT • IMD"
          status="info"
          trend="up"
          subtitle="Real-time multi-modal feeds"
          sparklineData={[3, 4, 4, 4, 4]}
        />
      </div>

      {/* 2. Live Feed Status Strip */}
      <div className="rounded-md border border-light-border bg-white p-4 shadow-sm dark:border-dark-border dark:bg-dark-card dark:shadow-dark-card">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-light-border dark:border-dark-border pb-3">
          <div className="flex items-center gap-2">
            <Radio className="h-4 w-4 text-teal-600 dark:text-accent-cyan animate-pulse" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-light-text-primary dark:text-dark-text-primary">
              Multi-Source Ingestion Pipeline Feeds
            </h3>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onPollLive}
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-lg border border-light-border bg-light-surface-subtle px-3 py-1.5 text-xs font-semibold text-light-text-primary hover:border-teal-400 hover:bg-white transition disabled:opacity-50 dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-primary dark:hover:border-accent-cyan dark:hover:bg-dark-card"
            >
              <RefreshCw
                className={`h-3.5 w-3.5 text-teal-600 dark:text-accent-cyan ${busy ? "animate-spin" : ""}`}
              />
              <span>Trigger Live Poll Now</span>
            </button>
          </div>
        </div>

        {/* Source Cards */}
        <div className="mt-3 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
          {sources.map((src) => {
            const isLive = src.fetch_mode.startsWith("live");
            return (
              <div
                key={src.source}
                className="rounded-xl border border-light-border bg-light-surface-subtle p-2.5 text-xs dark:border-dark-border dark:bg-dark-surface"
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-light-text-primary dark:text-dark-text-primary truncate">
                    {src.source}
                  </span>
                  <span
                    className={`rounded px-1.5 py-0.5 font-mono text-[9px] font-bold ${
                      isLive
                        ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-400"
                        : "bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-400"
                    }`}
                  >
                    {isLive ? "LIVE" : "FALLBACK"}
                  </span>
                </div>
                <div className="mt-1 flex items-center justify-between text-[11px] text-light-text-secondary dark:text-dark-text-secondary">
                  <span>Signals: {src.signals_fetched}</span>
                  <span className="font-semibold text-light-text-primary dark:text-dark-text-primary">
                    {src.corridor_events_grounded} Grounded
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Weather Telemetry Row */}
        {weather.length > 0 && (
          <div className="mt-3 grid grid-cols-2 gap-2 border-t border-light-border dark:border-dark-border pt-3 sm:grid-cols-3 lg:grid-cols-6">
            {weather.map((row) => (
              <div
                key={row.entity_id}
                className={`rounded-xl border p-2 text-xs transition ${
                  row.alert_color === "RED"
                    ? "border-rose-300 bg-rose-50/70 text-rose-900 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-300"
                    : row.alert_color === "ORANGE"
                    ? "border-amber-300 bg-amber-50/70 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-300"
                    : "border-light-border bg-light-surface-subtle text-light-text-primary dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-primary"
                }`}
              >
                <div className="flex items-center justify-between font-semibold">
                  <span className="truncate">{row.name.split(" ")[0]}</span>
                  <span className="font-mono text-[9px] font-bold">
                    {row.alert_color}
                  </span>
                </div>
                <div className="mt-0.5 flex items-center justify-between font-mono text-[10px] text-light-text-secondary dark:text-dark-text-secondary">
                  <span className="flex items-center gap-0.5">
                    <Wind className="h-2.5 w-2.5 text-teal-600 dark:text-accent-cyan" />
                    {row.wind_kmh.toFixed(0)} km/h
                  </span>
                  <span className="flex items-center gap-0.5">
                    <CloudRain className="h-2.5 w-2.5 text-sky-600 dark:text-accent-blue" />
                    {row.rain_mm.toFixed(1)} mm
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 3. Disruption Events & Ingestion Workbench */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Left 2 Cols: Active Corroborated Disruption Events List */}
        <div className="lg:col-span-2 overflow-hidden rounded-md border border-light-border bg-white shadow-sm dark:border-dark-border dark:bg-dark-card dark:shadow-dark-card">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-light-border dark:border-dark-border p-3.5 bg-light-surface-subtle dark:bg-dark-surface">
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-light-text-primary dark:text-dark-text-primary">
                Corroborated Disruption Incidents ({filteredEvents.length})
              </h3>
              <p className="text-[11px] text-light-text-secondary dark:text-dark-text-secondary">
                Select any incident to run Stage B–D sensitivity mitigation
              </p>
            </div>

            <div className="flex items-center gap-2">
              <select
                value={filterSeverity}
                onChange={(e) => setFilterSeverity(e.target.value)}
                className="h-8 rounded-lg border border-light-border bg-white px-2.5 text-xs text-light-text-primary focus:outline-none dark:border-dark-border dark:bg-dark-card dark:text-dark-text-primary"
              >
                <option value="ALL">All Severities</option>
                <option value="HIGH">High Severity (&ge; 60%)</option>
                <option value="MEDIUM">Medium Severity (30-60%)</option>
                <option value="LOW">Low Severity (&lt; 30%)</option>
              </select>
            </div>
          </div>

          <div className="max-h-[520px] overflow-y-auto divide-y divide-light-border dark:divide-dark-border p-3 space-y-2.5">
            {filteredEvents.map((ev) => {
              const isSelected = selectedEventId === ev.event_id;
              const isHigh = ev.severity >= 0.6;
              const isMitigated = ev.status === "MITIGATED";
              const isPlanned =
                planResponse?.event_id === ev.event_id && Boolean(planResponse.plan);
              const matchedPlan = isPlanned ? planResponse!.plan! : null;
              const matchedVerif = isPlanned ? planResponse!.verification : null;

              return (
                <div
                  key={ev.event_id}
                  className={`rounded-xl border p-3.5 transition ${
                    isMitigated
                      ? "border-emerald-300 bg-emerald-50/40 dark:border-emerald-900/60 dark:bg-emerald-950/20"
                      : isSelected
                      ? "border-teal-500 bg-teal-50/40 shadow-xs dark:border-accent-cyan dark:bg-accent-cyan/10"
                      : "border-light-border bg-white hover:border-slate-300 dark:border-dark-border dark:bg-dark-card dark:hover:border-dark-hover"
                  }`}
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="flex items-center gap-2">
                      {isMitigated ? (
                        <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
                      ) : (
                        <AlertTriangle
                          className={`h-4 w-4 shrink-0 ${
                            isHigh ? "text-rose-600 dark:text-rose-400" : "text-amber-500 dark:text-amber-400"
                          }`}
                        />
                      )}
                      <span className="font-bold text-xs text-light-text-primary dark:text-dark-text-primary">
                        {ev.event_type}
                      </span>
                      <span className="font-mono text-[10px] text-light-text-muted dark:text-dark-text-muted">
                        {ev.event_id}
                      </span>
                      <span
                        className={`rounded px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase ${
                          isMitigated
                            ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300"
                            : "bg-slate-100 text-slate-700 dark:bg-dark-elevated dark:text-slate-300"
                        }`}
                      >
                        {ev.status}
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={`rounded px-2 py-0.5 font-mono text-[10px] font-bold ${
                          isMitigated
                            ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-400"
                            : isHigh
                            ? "bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-400"
                            : "bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-400"
                        }`}
                      >
                        Severity {Math.round(ev.severity * 100)}%
                      </span>
                      {!isMitigated && (
                        <button
                          type="button"
                          onClick={() => onSelectEventAndPlan(ev.event_id)}
                          disabled={busy}
                          className="inline-flex items-center gap-1 rounded-lg bg-[#101C2C] px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-slate-800 transition disabled:opacity-50 dark:bg-accent-cyan dark:text-[#090D14] dark:hover:bg-cyan-400"
                        >
                          {busy && isSelected ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            <Play className="h-3 w-3 fill-current" />
                          )}
                          <span>{isPlanned ? "Re-Optimize" : "Optimize"}</span>
                        </button>
                      )}
                      {onMitigateEvent && !isMitigated && (
                        <button
                          type="button"
                          onClick={() =>
                            onMitigateEvent(
                              ev.event_id,
                              matchedPlan?.plan_id ?? null,
                              isPlanned ? planResponse?.session_id ?? null : null
                            )
                          }
                          disabled={busy}
                          className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-emerald-700 transition disabled:opacity-60"
                        >
                          {mitigatingEventId === ev.event_id ? (
                            <>
                              <Loader2 className="h-3 w-3 animate-spin" />
                              <span>Recalculating routes...</span>
                            </>
                          ) : (
                            <>
                              <ShieldCheck className="h-3 w-3" />
                              <span>Apply &amp; Fix</span>
                            </>
                          )}
                        </button>
                      )}
                      {onReopenEvent && isMitigated && (
                        <button
                          type="button"
                          onClick={() => onReopenEvent(ev.event_id)}
                          disabled={busy}
                          className="inline-flex items-center gap-1 rounded-lg border border-light-border bg-white px-2.5 py-1 text-[11px] font-semibold text-light-text-secondary hover:text-light-text-primary transition disabled:opacity-50 dark:border-dark-border dark:bg-dark-card dark:text-dark-text-secondary"
                        >
                          <RotateCcw className="h-3 w-3" />
                          <span>Reopen</span>
                        </button>
                      )}
                    </div>
                  </div>

                  <p className="mt-2 text-xs text-light-text-secondary leading-relaxed dark:text-dark-text-secondary">
                    {ev.raw_headline}
                  </p>

                  {matchedPlan && (
                    <div className="mt-2.5 rounded-lg border border-google-blue/25 bg-google-blue/5 p-2.5 text-[11px] dark:border-google-blue/30 dark:bg-google-blue/10">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-semibold text-google-blue">
                          Mitigation Plan {matchedPlan.plan_id} ({matchedVerif?.overall_verdict ?? "PASS"})
                        </span>
                        <div className="flex items-center gap-3 font-mono text-[10px] text-light-text-primary dark:text-dark-text-primary">
                          <span>
                            Unmet:{" "}
                            <strong
                              className={
                                matchedPlan.unmet_demand_teu <= 0.01
                                  ? "text-emerald-600 dark:text-emerald-400"
                                  : "text-rose-600 dark:text-rose-400"
                              }
                            >
                              {matchedPlan.unmet_demand_teu.toFixed(1)} TEU
                            </strong>
                          </span>
                          <span>
                            Cost: <strong>${matchedPlan.objective_cost.toLocaleString(undefined, { maximumFractionDigits: 0 })}</strong>
                          </span>
                          <span>
                            Rail: <strong>{Math.round((matchedPlan.mode_split?.INTERMODAL_RAIL ?? 0) * 100)}%</strong> ({matchedPlan.allocations.length} routes)
                          </span>
                        </div>
                      </div>
                      {onOpenOptimizationTab && (
                        <div className="mt-1.5 flex items-center justify-between text-[10px] text-light-text-muted dark:text-dark-text-muted">
                          <span className="truncate">{matchedPlan.summary}</span>
                          <button
                            type="button"
                            onClick={onOpenOptimizationTab}
                            className="ml-2 shrink-0 font-semibold text-google-blue hover:underline"
                          >
                            View Routes &amp; Verifier &rarr;
                          </button>
                        </div>
                      )}
                    </div>
                  )}

                  {isMitigated && ev.applied_plan_id && !matchedPlan && (
                    <div className="mt-2 text-[10px] font-mono text-emerald-700 dark:text-emerald-400">
                      Disruption mitigated with applied plan {ev.applied_plan_id}
                    </div>
                  )}

                  <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 text-[11px] text-light-text-muted dark:text-dark-text-muted border-t border-light-border dark:border-dark-border pt-2">
                    <div className="flex items-center gap-3">
                      <span>
                        Target:{" "}
                        <strong className="text-light-text-primary dark:text-dark-text-primary">
                          {ev.primary_entity_id}
                        </strong>
                      </span>
                      <span>
                        Confidence:{" "}
                        <strong className="text-light-text-primary dark:text-dark-text-primary">
                          {Math.round(ev.confidence * 100)}%
                        </strong>
                      </span>
                      <span>
                        Corroborations:{" "}
                        <strong className="text-light-text-primary dark:text-dark-text-primary">
                          {ev.corroboration_count}
                        </strong>
                      </span>
                    </div>
                    <span className="font-mono text-[10px]">
                      Source: {ev.source_feed}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Col: Ingestion Workbench & Security Presets */}
        <div className="rounded-md border border-light-border bg-white p-4 shadow-sm dark:border-dark-border dark:bg-dark-card dark:shadow-dark-card space-y-4">
          <div className="border-b border-light-border dark:border-dark-border pb-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-light-text-primary dark:text-dark-text-primary">
              Scenario Ingestion Workbench
            </h3>
            <p className="text-[11px] text-light-text-secondary dark:text-dark-text-secondary">
              Submit raw operational intelligence to Stage A parser
            </p>
          </div>

          {/* Quick Scenario Buttons */}
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-light-text-muted dark:text-dark-text-muted mb-1.5">
              Quick Test Presets
            </div>
            <div className="grid grid-cols-2 gap-2">
              {SCENARIO_PRESETS.map((preset) => (
                <button
                  key={preset.id}
                  type="button"
                  onClick={() => applyPreset(preset)}
                  className="rounded-xl border border-light-border bg-light-surface-subtle p-2.5 text-left hover:border-teal-400 hover:bg-white transition dark:border-dark-border dark:bg-dark-surface dark:hover:border-accent-cyan dark:hover:bg-dark-card"
                >
                  <div className="flex items-center gap-1 text-[11px] font-bold text-light-text-primary dark:text-dark-text-primary">
                    {preset.id === "injection_trap" && (
                      <ShieldAlert className="h-3 w-3 text-rose-600 dark:text-rose-400 shrink-0" />
                    )}
                    <span className="truncate">{preset.label}</span>
                  </div>
                  <div className="truncate text-[10px] text-light-text-muted dark:text-dark-text-muted">
                    {preset.subtitle}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Input Form */}
          <div className="space-y-3 text-xs">
            <div>
              <label className="block text-[11px] font-semibold text-light-text-secondary dark:text-dark-text-secondary mb-1">
                Disruption Alert Headline
              </label>
              <input
                type="text"
                value={controls.headline}
                onChange={(e) => onChangeControls({ headline: e.target.value })}
                className="w-full rounded-lg border border-light-border bg-light-surface-subtle p-2 text-xs text-light-text-primary focus:border-teal-500 focus:bg-white focus:outline-none dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-primary dark:focus:border-accent-cyan dark:focus:bg-dark-card"
              />
            </div>

            <div>
              <label className="block text-[11px] font-semibold text-light-text-secondary dark:text-dark-text-secondary mb-1">
                Raw Operational Text
              </label>
              <textarea
                rows={3}
                value={controls.rawText}
                onChange={(e) => onChangeControls({ rawText: e.target.value })}
                className="w-full rounded-lg border border-light-border bg-light-surface-subtle p-2 text-xs text-light-text-primary focus:border-teal-500 focus:bg-white focus:outline-none font-mono text-[11px] dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-primary dark:focus:border-accent-cyan dark:focus:bg-dark-card"
              />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-[10px] font-semibold text-light-text-muted dark:text-dark-text-muted mb-1">
                  Trust Tier
                </label>
                <select
                  value={controls.trustTier}
                  onChange={(e) =>
                    onChangeControls({
                      trustTier: e.target.value as TrustTier,
                    })
                  }
                  className="w-full rounded-lg border border-light-border bg-light-surface-subtle p-1.5 text-xs text-light-text-primary focus:outline-none dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-primary"
                >
                  <option value="TIER_A">Tier A (Verified Authority)</option>
                  <option value="TIER_B">Tier B (Industry Feed)</option>
                  <option value="TIER_C">Tier C (Unconfirmed Chatter)</option>
                </select>
              </div>

              <div>
                <label className="block text-[10px] font-semibold text-light-text-muted dark:text-dark-text-muted mb-1">
                  LLM Stage A Parser
                </label>
                <select
                  value={controls.llmProvider}
                  onChange={(e) =>
                    onChangeControls({
                      llmProvider: e.target.value as any,
                      enableLlm: e.target.value !== "deterministic",
                    })
                  }
                  className="w-full rounded-lg border border-light-border bg-light-surface-subtle p-1.5 text-xs text-light-text-primary focus:outline-none dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-primary"
                >
                  <option value="auto">Auto Select</option>
                  <option value="groq">Groq (Llama-3.3)</option>
                  <option value="gemini">Google Gemini</option>
                  <option value="deterministic">Deterministic Offline</option>
                </select>
              </div>
            </div>

            <button
              type="button"
              onClick={onIngestAndPlan}
              disabled={busy}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-teal-600 hover:bg-teal-700 p-2.5 text-xs font-semibold text-white transition disabled:opacity-50 shadow-sm dark:bg-accent-cyan dark:text-[#090D14] dark:hover:bg-cyan-400"
            >
              <Send className="h-3.5 w-3.5" />
              <span>Ingest Signal &amp; Run Optimization</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
