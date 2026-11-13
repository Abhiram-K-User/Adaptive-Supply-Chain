import { useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Anchor,
  ArrowRightLeft,
  BookOpen,
  Boxes,
  Building2,
  CheckCircle2,
  CloudRain,
  Loader2,
  MapPin,
  Play,
  RotateCcw,
  ShieldCheck,
  SlidersHorizontal,
  Wind,
  X,
} from "lucide-react";
import { asciApi } from "../../api/client";
import type {
  CanonicalEntity,
  DisruptionEvent,
  FeedsStatusResponse,
  NetworkEdgeSummary,
  PlanResponse,
} from "../../types/asci";

interface NodeDetailDrawerProps {
  nodeId: string | null;
  onClose: () => void;
  entities: CanonicalEntity[];
  baseEdges: NetworkEdgeSummary[];
  events: DisruptionEvent[];
  planResponse: PlanResponse | null;
  feedsStatus: FeedsStatusResponse | null;
  onRunPlanForEvent?: (eventId: string) => void;
  onMitigateEvent?: (
    eventId: string,
    planId?: string | null,
    sessionId?: string | null
  ) => void;
  onReopenEvent?: (eventId: string) => void;
  onOpenWhatIf?: () => void;
  busy?: boolean;
  mitigatingEventId?: string | null;
}

interface OutcomesPayload {
  baseline?: {
    avg_daily_teu?: number;
    avg_vessel_calls?: number;
  } | null;
  recovery_curves?: Record<string, number[]>;
  recent_observations?: Array<{
    obs_date: string;
    vessel_calls: number;
    teu_volume: number;
    source: string;
  }>;
}

const ENTITY_ROLE_LABELS: Record<string, string> = {
  PORT: "Seaport Gateway",
  PLANT: "Assembly Plant",
  ICD: "Inland Container Hub",
  CFS: "Freight Consolidation Depot",
  CORRIDOR_JUNCTION: "Transport Junction",
};

const EVENT_TYPE_LABELS: Record<string, string> = {
  HAZARD_PORT: "Port Weather / Hazard",
  HAZARD_ROAD: "Road Blockage / Flooding",
  PORT_CONGESTION_STRIKE: "Strike & Terminal Congestion",
  RAIL_DISRUPTION: "Rail Line Disruption",
  SHIPPING_SCHEDULE: "Vessel Schedule Delay",
  TRADE_POLICY: "Customs / Trade Restriction",
  PLANT_OUTAGE: "Factory Operations Outage",
};

const COMMODITY_LABELS: Record<string, string> = {
  POWERTRAIN_CKD: "Powertrain Kits",
  EV_BATTERY_PACKS: "EV Battery Packs",
  SEMICONDUCTORS_ECU: "Semiconductors & ECUs",
  BODY_CHASSIS_PARTS: "Body & Chassis Parts",
  GENERAL_AUTO_PARTS: "General Auto Parts",
};

const MODE_LABELS: Record<string, string> = {
  INTERMODAL_RAIL: "Rail Freight",
  RAIL: "Rail Freight",
  ROAD: "Road Truck",
  COASTAL_FEEDER: "Coastal Ship",
};

const TRUST_LABELS: Record<string, string> = {
  TIER_A: "Official Authority",
  TIER_B: "News & Trade Report",
  TIER_C: "Field Update",
};

function formatSourceLabel(rawFeed: string): string {
  return rawFeed
    .split(",")
    .map((part) => {
      const p = part.trim();
      if (p.startsWith("GDELT:")) return `News (${p.slice(6)})`;
      if (p.startsWith("GDACS")) return "Global Disaster Alert (GDACS)";
      if (p.startsWith("IMD") || p.startsWith("OPEN_METEO")) return "Weather Radar";
      if (p.startsWith("PORTWATCH")) return "Port Traffic Monitor";
      if (p === "UI_WORKBENCH") return "Control Tower Report";
      return p.replace(/_/g, " ");
    })
    .join(" · ");
}

function formatHumanLabel(code: string, map: Record<string, string>): string {
  if (map[code]) return map[code];
  return code
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function NodeDetailDrawer({
  nodeId,
  onClose,
  entities,
  baseEdges,
  events,
  planResponse,
  feedsStatus,
  onRunPlanForEvent,
  onMitigateEvent,
  onReopenEvent,
  onOpenWhatIf,
  busy = false,
  mitigatingEventId = null,
}: NodeDetailDrawerProps) {
  const [outcomes, setOutcomes] = useState<OutcomesPayload | null>(null);
  const [loadingOutcomes, setLoadingOutcomes] = useState(false);

  useEffect(() => {
    if (!nodeId) {
      setOutcomes(null);
      return;
    }
    let active = true;
    setLoadingOutcomes(true);
    asciApi
      .getOutcomesForEntity(nodeId, 30)
      .then((res) => {
        if (active) setOutcomes(res as OutcomesPayload);
      })
      .catch(() => {
        if (active) setOutcomes(null);
      })
      .finally(() => {
        if (active) setLoadingOutcomes(false);
      });
    return () => {
      active = false;
    };
  }, [nodeId]);

  useEffect(() => {
    if (!nodeId) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [nodeId, onClose]);

  if (!nodeId) return null;

  const entity = entities.find((e) => e.id === nodeId) ?? null;
  const dash = planResponse?.dashboard ?? null;
  const planNode = dash?.geospatial_network?.nodes?.find((n) => n.data.id === nodeId) ?? null;

  const relatedEvents = events.filter(
    (ev) =>
      ev.primary_entity_id === nodeId || ev.affected_entity_ids.includes(nodeId)
  );

  const hasActiveRelated = relatedEvents.some(
    (ev) => ev.status === "NEW" || ev.status === "UPDATED"
  );
  const hasMitigatedRelated = relatedEvents.some(
    (ev) => ev.status === "MITIGATED"
  );
  const hasActivePrimary = relatedEvents.some(
    (ev) =>
      ev.primary_entity_id === nodeId &&
      (ev.status === "NEW" || ev.status === "UPDATED")
  );
  const activePrimaryMaxSev = relatedEvents
    .filter(
      (ev) =>
        ev.primary_entity_id === nodeId &&
        (ev.status === "NEW" || ev.status === "UPDATED")
    )
    .reduce((acc, ev) => Math.max(acc, ev.severity), 0);
  const activeAffectedMaxSev = relatedEvents
    .filter((ev) => ev.status === "NEW" || ev.status === "UPDATED")
    .reduce((acc, ev) => Math.max(acc, ev.severity), 0);
  const anyActiveInCorridor = events.some(
    (ev) => ev.status === "NEW" || ev.status === "UPDATED"
  );

  const rawCapMult = planNode?.data.capacity_multiplier ?? 1.0;
  const rawStatus = planNode?.data.status ?? "NORMAL";
  const isNodeCleared =
    !hasActiveRelated &&
    (hasMitigatedRelated ||
      (!anyActiveInCorridor && (rawStatus === "DISRUPTED" || rawStatus === "RESTRICTED")));

  const opStatus = hasActivePrimary
    ? activePrimaryMaxSev >= 0.7 || rawStatus === "DISRUPTED"
      ? "DISRUPTED"
      : "RESTRICTED"
    : hasActiveRelated
    ? rawStatus === "NORMAL" || rawStatus === "MITIGATED"
      ? "RESTRICTED"
      : rawStatus
    : isNodeCleared
    ? "MITIGATED"
    : rawStatus;

  const fallbackCapMult = hasActivePrimary
    ? Math.max(0.1, Number((1 - activePrimaryMaxSev).toFixed(2)))
    : hasActiveRelated
    ? Math.max(0.35, Number((1 - activeAffectedMaxSev * 0.45).toFixed(2)))
    : rawCapMult;
  const capMult = isNodeCleared
    ? 1.0
    : rawCapMult < 0.99
    ? rawCapMult
    : fallbackCapMult;

  const weather =
    feedsStatus?.weather_telemetry?.find((w) => w.entity_id === nodeId) ?? null;

  const plantRisk =
    dash?.line_stop_forecast?.find((row) => row.plant_id === nodeId) ?? null;

  const nodeAllocations = (planResponse?.plan?.allocations ?? []).filter(
    (a) =>
      a.origin_id === nodeId ||
      a.destination_id === nodeId ||
      a.path.includes(nodeId)
  );

  const connectedEdges = baseEdges.filter(
    (e) => e.source === nodeId || e.target === nodeId
  );

  const relatedEvidence = (dash?.evidence_provenance ?? []).filter((doc) =>
    doc.entity_ids.includes(nodeId)
  );

  const hazardCurve =
    outcomes?.recovery_curves?.HAZARD_PORT ??
    outcomes?.recovery_curves?.HAZARD_WEATHER ??
    [];

  const statusTone =
    opStatus === "DISRUPTED"
      ? "border-rose-300 bg-rose-50 text-rose-800 dark:border-rose-900/60 dark:bg-rose-950/50 dark:text-rose-300"
      : opStatus === "RESTRICTED"
      ? "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/50 dark:text-amber-300"
      : opStatus === "MITIGATED"
      ? "border-teal-300 bg-teal-50 text-teal-800 dark:border-teal-800 dark:bg-teal-950/50 dark:text-teal-300"
      : "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/50 dark:text-emerald-300";

  const entityName = entity?.name ?? planNode?.data.label ?? nodeId;
  const entityType = entity?.entity_type ?? planNode?.data.entity_type ?? "NODE";
  const entityRoleLabel = ENTITY_ROLE_LABELS[entityType] ?? "Logistics Facility";
  const region = entity?.region ?? planNode?.data.region ?? "South India Corridor";

  const entityNameMap = new Map<string, string>(
    entities.map((e) => [e.id, e.name])
  );
  const getReadableName = (id: string) => entityNameMap.get(id) ?? id;

  const passingCargoTeu = nodeAllocations.reduce((sum, a) => sum + a.flow_teu, 0);
  const statusBadgeText =
    opStatus === "DISRUPTED"
      ? `Major Disruption · ${Math.round(capMult * 100)}% Capacity`
      : opStatus === "RESTRICTED"
      ? `Partial Delay · ${Math.round(capMult * 100)}% Capacity`
      : opStatus === "MITIGATED"
      ? "Resolved · Reroute Active"
      : "Operating Normally";

  return (
    <div
      className="fixed inset-0 z-50 overflow-hidden bg-black/55 backdrop-blur-xs transition-opacity"
      onClick={onClose}
    >
      <div className="fixed inset-y-0 right-0 flex max-w-full pl-10">
        <aside
          className="w-screen max-w-md bg-white border-l border-light-border dark:bg-dark-surface dark:border-dark-border shadow-2xl flex flex-col"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-start justify-between gap-3 border-b border-light-border px-5 py-4 bg-light-elevated dark:border-dark-border dark:bg-dark-card">
            <div className="flex items-start gap-2.5 min-w-0">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-google-blue/10 text-google-blue border border-google-blue/20">
                {entityType === "PORT" ? (
                  <Anchor className="h-4 w-4" />
                ) : entityType === "PLANT" ? (
                  <Building2 className="h-4 w-4" />
                ) : (
                  <Boxes className="h-4 w-4" />
                )}
              </div>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-1.5">
                  <h3 className="text-sm font-bold text-light-text-primary dark:text-dark-text-primary truncate">
                    {entityName}
                  </h3>
                  <span
                    className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${statusTone}`}
                  >
                    {statusBadgeText}
                  </span>
                </div>
                <p className="mt-0.5 text-[11px] text-light-text-muted dark:text-dark-text-muted truncate">
                  {entityRoleLabel} &middot; {region}
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close node details"
              className="rounded-lg p-1.5 text-light-text-muted hover:bg-light-hover hover:text-light-text-primary dark:text-dark-text-muted dark:hover:bg-dark-elevated dark:hover:text-dark-text-primary transition"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Scrollable Body */}
          <div className="flex-1 overflow-y-auto p-5 space-y-5 text-xs">
            {/* Quick Operational Specs */}
            <section className="grid grid-cols-3 gap-2.5">
              <div className="rounded-xl border border-light-border bg-light-surface-subtle p-2.5 dark:border-dark-border dark:bg-dark-card">
                <div className="text-[10px] font-semibold uppercase text-light-text-muted dark:text-dark-text-muted">
                  Operating Level
                </div>
                <div className="mt-0.5 text-sm font-bold text-light-text-primary dark:text-dark-text-primary">
                  {(capMult * 100).toFixed(0)}%
                </div>
                {capMult < 0.99 && (
                  <div className="text-[10px] text-rose-600 dark:text-rose-400">
                    {Math.round((1 - capMult) * 100)}% reduced
                  </div>
                )}
              </div>
              <div className="rounded-xl border border-light-border bg-light-surface-subtle p-2.5 dark:border-dark-border dark:bg-dark-card">
                <div className="text-[10px] font-semibold uppercase text-light-text-muted dark:text-dark-text-muted">
                  {entity?.daily_demand_teu
                    ? "Daily Need"
                    : entity?.daily_capacity_teu
                    ? "Daily Capacity"
                    : "Cargo Volume"}
                </div>
                <div className="mt-0.5 text-sm font-bold text-teal-700 dark:text-accent-cyan">
                  {entity?.daily_demand_teu
                    ? `${entity.daily_demand_teu.toLocaleString()} / day`
                    : entity?.daily_capacity_teu
                    ? `${entity.daily_capacity_teu.toLocaleString()} / day`
                    : passingCargoTeu > 0
                    ? `${Math.round(passingCargoTeu).toLocaleString()} / day`
                    : "Transit Hub"}
                </div>
                <div className="text-[10px] text-light-text-muted dark:text-dark-text-muted">
                  containers
                </div>
              </div>
              <div className="rounded-xl border border-light-border bg-light-surface-subtle p-2.5 dark:border-dark-border dark:bg-dark-card">
                <div className="text-[10px] font-semibold uppercase text-light-text-muted dark:text-dark-text-muted">
                  Connected Routes
                </div>
                <div className="mt-0.5 text-sm font-bold text-light-text-primary dark:text-dark-text-primary">
                  {connectedEdges.length}
                </div>
                <div className="text-[10px] text-light-text-muted dark:text-dark-text-muted">
                  road &amp; rail
                </div>
              </div>
            </section>

            {entity && (
              <div className="flex items-center gap-2 text-[11px] text-light-text-muted dark:text-dark-text-muted">
                <MapPin className="h-3.5 w-3.5 text-google-blue shrink-0" />
                <span>
                  Location: {entity.latitude.toFixed(2)}&deg;N, {entity.longitude.toFixed(2)}&deg;E
                  {entity.days_of_cover
                    ? ` · Safety stock: ${entity.days_of_cover} days`
                    : ""}
                </span>
              </div>
            )}

            {/* Plant Line-Stop Risk */}
            {plantRisk && (
              <section className="rounded-xl border border-light-border bg-white p-3.5 space-y-2 dark:border-dark-border dark:bg-dark-card">
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-light-text-primary dark:text-dark-text-primary">
                    <Activity className="h-3.5 w-3.5 text-google-red" />
                    Factory Buffer &amp; Shutdown Risk
                  </span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                      plantRisk.critical
                        ? "bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-300"
                        : "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300"
                    }`}
                  >
                    {plantRisk.critical ? "At Risk of Halt" : "Supply Safe"}
                  </span>
                </div>
                <div className="grid grid-cols-3 gap-2 text-[11px]">
                  <div>
                    <span className="text-light-text-muted dark:text-dark-text-muted block">Stock Left</span>
                    <span className="font-bold">{plantRisk.days_of_cover.toFixed(1)} days</span>
                  </div>
                  <div>
                    <span className="text-light-text-muted dark:text-dark-text-muted block">Est. Delay</span>
                    <span className="font-bold">+{plantRisk.expected_delay_days.toFixed(1)} days</span>
                  </div>
                  <div>
                    <span className="text-light-text-muted dark:text-dark-text-muted block">Time Margin</span>
                    <span className="font-bold">
                      {plantRisk.time_to_line_stop_days.toFixed(1)} days ({Math.round(plantRisk.line_stop_risk * 100)}% risk)
                    </span>
                  </div>
                </div>
              </section>
            )}

            {/* Active Disruptions */}
            <section className="space-y-2">
              <div className="flex items-center justify-between">
                <h4 className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-light-text-primary dark:text-dark-text-primary">
                  <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
                  Current Disruptions ({relatedEvents.length})
                </h4>
              </div>
              {relatedEvents.length === 0 ? (
                <div className="rounded-xl border border-dashed border-light-border p-3 text-[11px] text-light-text-muted dark:border-dark-border dark:text-dark-text-muted">
                  No active disruptions reported at this location.
                </div>
              ) : (
                <div className="space-y-2.5">
                  {relatedEvents.map((ev) => {
                    const isMitigated = ev.status === "MITIGATED";
                    const hasActivePlan =
                      planResponse?.event_id === ev.event_id && Boolean(planResponse.plan);
                    const matchedPlan = hasActivePlan ? planResponse!.plan! : null;
                    const matchedVerif = hasActivePlan ? planResponse!.verification : null;
                    const sevPct = Math.round(ev.severity * 100);
                    const impactLabel =
                      ev.severity >= 0.7
                        ? "High Impact"
                        : ev.severity >= 0.4
                        ? "Moderate Impact"
                        : "Minor Impact";
                    const eventTypeLabel = formatHumanLabel(ev.event_type, EVENT_TYPE_LABELS);
                    const otherAffected = ev.affected_entity_ids
                      .filter((id) => id !== nodeId)
                      .map(getReadableName);
                    const detailText =
                      ev.raw_text &&
                      ev.raw_text.trim() !== ev.raw_headline.trim()
                        ? ev.raw_text.trim()
                        : null;
                    const railSharePct = matchedPlan
                      ? Math.round((matchedPlan.mode_split?.INTERMODAL_RAIL ?? 0) * 100)
                      : 0;
                    const isDirectSource = ev.primary_entity_id === nodeId;
                    const primaryReadable = getReadableName(ev.primary_entity_id);
                    const reportedTime = (() => {
                      const d = new Date(ev.timestamp);
                      return Number.isNaN(d.getTime())
                        ? null
                        : d.toLocaleString(undefined, {
                            month: "short",
                            day: "numeric",
                            hour: "numeric",
                            minute: "2-digit",
                          });
                    })();

                    const fixHighlightRoutes = matchedPlan
                      ? [...matchedPlan.allocations]
                          .sort((a, b) => {
                            const aBypass = a.path.includes(ev.primary_entity_id) ? 0 : 1;
                            const bBypass = b.path.includes(ev.primary_entity_id) ? 0 : 1;
                            if (aBypass !== bBypass) return bBypass - aBypass;
                            return b.flow_teu - a.flow_teu;
                          })
                          .slice(0, 3)
                      : [];

                    return (
                      <div
                        key={ev.event_id}
                        className={`rounded-xl border p-3.5 space-y-2.5 ${
                          isMitigated
                            ? "border-emerald-200 bg-emerald-50/50 dark:border-emerald-900/50 dark:bg-emerald-950/20"
                            : "border-amber-200 bg-amber-50/50 dark:border-amber-900/50 dark:bg-amber-950/25"
                        }`}
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span
                            className={`text-[11px] font-bold flex items-center gap-1 ${
                              isMitigated
                                ? "text-emerald-800 dark:text-emerald-300"
                                : "text-amber-900 dark:text-amber-300"
                            }`}
                          >
                            {isMitigated && <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />}
                            {eventTypeLabel} &middot;{" "}
                            {isMitigated ? "Resolved" : "Active Alert"}
                          </span>
                          <span
                            className={`rounded px-2 py-0.5 text-[10px] font-bold ${
                              isMitigated
                                ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-300"
                                : "bg-amber-200/70 text-amber-900 dark:bg-amber-900/60 dark:text-amber-200"
                            }`}
                          >
                            {impactLabel} ({sevPct}%) &middot; ~{ev.estimated_duration_days}d
                          </span>
                        </div>

                        <div className="space-y-1.5">
                          <p className="text-xs font-semibold text-light-text-primary dark:text-dark-text-primary leading-snug">
                            {ev.raw_headline}
                          </p>
                          {detailText && (
                            <p className="text-[11px] text-light-text-secondary dark:text-dark-text-secondary leading-relaxed">
                              {detailText}
                            </p>
                          )}
                          <div className="text-[11px] text-light-text-secondary dark:text-dark-text-secondary">
                            <span className="font-semibold text-light-text-primary dark:text-dark-text-primary">
                              Impact here:{" "}
                            </span>
                            {isDirectSource
                              ? `Direct disruption at ${entityName} (${sevPct}% severity for ~${ev.estimated_duration_days} days).`
                              : `Spillover congestion & rerouting from ${primaryReadable}${
                                  rawCapMult < 0.99 && !isMitigated
                                    ? ` (reduced local capacity to ${Math.round(rawCapMult * 100)}%)`
                                    : ""
                                }.`}
                            {reportedTime ? ` Detected ${reportedTime}.` : ""}
                          </div>
                        </div>

                        {otherAffected.length > 0 && (
                          <div className="rounded-lg bg-white/70 px-2.5 py-1.5 text-[11px] text-light-text-secondary dark:bg-dark-surface/60 dark:text-dark-text-secondary">
                            <span className="font-semibold text-light-text-primary dark:text-dark-text-primary">
                              Ripple effect:{" "}
                            </span>
                            Also impacts{" "}
                            {otherAffected.slice(0, 3).join(", ")}
                            {otherAffected.length > 3
                              ? ` and ${otherAffected.length - 3} other location${
                                  otherAffected.length - 3 === 1 ? "" : "s"
                                }`
                              : ""}
                            .
                          </div>
                        )}

                        {matchedPlan && (
                          <div className="rounded-lg border border-google-blue/25 bg-white/90 p-2.5 text-[11px] space-y-1.5 dark:bg-dark-surface/80 dark:border-google-blue/30">
                            <div className="flex items-center justify-between font-semibold">
                              <span className="text-google-blue">
                                {isMitigated ? "Applied Fix & Bypass Plan" : "Fix To Be Applied"}
                              </span>
                              <span
                                className={`font-bold ${
                                  matchedPlan.unmet_demand_teu <= 0.01 &&
                                  (matchedVerif?.passed ?? true)
                                    ? "text-emerald-600 dark:text-emerald-400"
                                    : "text-rose-600 dark:text-rose-400"
                                }`}
                              >
                                {matchedPlan.unmet_demand_teu <= 0.01
                                  ? "All deliveries covered"
                                  : `${matchedPlan.unmet_demand_teu.toFixed(0)} containers short`}
                              </span>
                            </div>
                            <p className="text-[10px] text-light-text-secondary dark:text-dark-text-secondary">
                              {isMitigated ? "Rerouted" : "Will shift"} {railSharePct}% of freight
                              onto rail and alternate gateways across {matchedPlan.allocations.length}{" "}
                              corridor routes &middot; Est. logistics cost $
                              {matchedPlan.objective_cost.toLocaleString(undefined, {
                                maximumFractionDigits: 0,
                              })}
                              .
                            </p>
                            {fixHighlightRoutes.length > 0 && (
                              <div className="border-t border-light-border/70 dark:border-dark-border/70 pt-1.5 space-y-1">
                                <div className="text-[10px] font-semibold text-light-text-primary dark:text-dark-text-primary">
                                  Key diversion corridors:
                                </div>
                                {fixHighlightRoutes.map((route, idx) => (
                                  <div
                                    key={idx}
                                    className="flex items-center justify-between text-[10px] text-light-text-secondary dark:text-dark-text-secondary"
                                  >
                                    <span className="truncate pr-2">
                                      &bull; {getReadableName(route.origin_id)} &rarr;{" "}
                                      {getReadableName(route.destination_id)} (
                                      {formatHumanLabel(route.mode, MODE_LABELS)})
                                    </span>
                                    <span className="shrink-0 font-semibold text-teal-700 dark:text-accent-cyan">
                                      {route.flow_teu.toFixed(0)} containers/d
                                    </span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}

                        {!isMitigated && !matchedPlan && (
                          <div className="rounded-lg border border-google-blue/20 bg-white/80 p-2.5 text-[11px] space-y-1 dark:bg-dark-surface/75 dark:border-google-blue/25">
                            <div className="font-semibold text-google-blue">
                              Fix To Be Applied
                            </div>
                            <p className="text-[10px] text-light-text-secondary dark:text-dark-text-secondary">
                              Clicking <strong>Apply &amp; Fix</strong> recalculates dedicated diversion
                              corridors around {entityName}, shifts container flow onto unaffected rail
                              and neighboring ports, and resolves this alert independently.
                            </p>
                          </div>
                        )}

                        {isMitigated && !matchedPlan && (
                          <div className="rounded-lg border border-emerald-200 bg-white/80 p-2 text-[11px] text-emerald-800 dark:border-emerald-900/50 dark:bg-dark-surface/70 dark:text-emerald-300">
                            Recovery diversion plan {ev.applied_plan_id ? `(${ev.applied_plan_id})` : ""}{" "}
                            applied: shipments rerouted onto alternate ports and rail links so factory
                            schedules stay protected.
                          </div>
                        )}

                        <div className="flex flex-wrap items-center justify-between gap-2 pt-1 text-[10px] text-light-text-muted dark:text-dark-text-muted border-t border-black/5 dark:border-white/5">
                          <span>
                            {formatSourceLabel(ev.source_feed)} &middot; {ev.corroboration_count}{" "}
                            {ev.corroboration_count === 1 ? "report" : "reports"} &middot;{" "}
                            {Math.round(ev.confidence * 100)}% reliable
                          </span>
                          <div className="flex items-center gap-2">
                            {onRunPlanForEvent && !isMitigated && (
                              <button
                                type="button"
                                disabled={busy}
                                onClick={() => onRunPlanForEvent(ev.event_id)}
                                className="inline-flex items-center gap-1 rounded-md bg-[#101C2C] px-2.5 py-1 text-[10px] font-semibold text-white hover:bg-slate-800 transition disabled:opacity-50 dark:bg-accent-cyan dark:text-[#090D14] dark:hover:bg-cyan-400"
                              >
                                {busy && mitigatingEventId !== ev.event_id ? (
                                  <Loader2 className="h-3 w-3 animate-spin" />
                                ) : (
                                  <Play className="h-3 w-3 fill-current" />
                                )}
                                <span>{matchedPlan ? "Recalculate Routes" : "Optimize"}</span>
                              </button>
                            )}
                            {onMitigateEvent && !isMitigated && (
                              <button
                                type="button"
                                disabled={busy}
                                onClick={() =>
                                  onMitigateEvent(
                                    ev.event_id,
                                    matchedPlan?.plan_id ?? null,
                                    hasActivePlan ? planResponse?.session_id ?? null : null
                                  )
                                }
                                className="inline-flex items-center gap-1 rounded-md bg-emerald-600 px-2.5 py-1 text-[10px] font-semibold text-white hover:bg-emerald-700 transition disabled:opacity-60"
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
                                disabled={busy}
                                onClick={() => onReopenEvent(ev.event_id)}
                                className="inline-flex items-center gap-1 rounded-md border border-light-border bg-white px-2.5 py-1 text-[10px] font-semibold text-light-text-secondary hover:text-light-text-primary transition disabled:opacity-50 dark:border-dark-border dark:bg-dark-card dark:text-dark-text-secondary"
                              >
                                <RotateCcw className="h-3 w-3" />
                                <span>Reopen Alert</span>
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>

            {/* Live Weather Telemetry */}
            {weather && (
              <section className="rounded-xl border border-light-border bg-white p-3.5 space-y-1.5 dark:border-dark-border dark:bg-dark-card">
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-light-text-primary dark:text-dark-text-primary">
                    <CloudRain className="h-3.5 w-3.5 text-google-blue" />
                    Local Weather ({weather.obs_date})
                  </span>
                  <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300">
                    {weather.alert_color === "RED"
                      ? "Severe Weather"
                      : weather.alert_color === "ORANGE"
                      ? "Weather Watch"
                      : "Clear"}
                  </span>
                </div>
                <div className="flex items-center gap-4 text-[11px] text-light-text-secondary dark:text-dark-text-secondary">
                  <span>Rainfall: <strong>{weather.rain_mm} mm</strong></span>
                  <span className="inline-flex items-center gap-1">
                    <Wind className="h-3 w-3" />
                    Wind Speed: <strong>{weather.wind_kmh} km/h</strong>
                  </span>
                </div>
              </section>
            )}

            {/* Rerouted Shipments */}
            <section className="space-y-2">
              <h4 className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-light-text-primary dark:text-dark-text-primary">
                <ArrowRightLeft className="h-3.5 w-3.5 text-teal-600 dark:text-accent-cyan" />
                Shipments Moving Through Here ({nodeAllocations.length})
              </h4>
              {nodeAllocations.length === 0 ? (
                <div className="rounded-xl border border-dashed border-light-border p-3 text-[11px] text-light-text-muted dark:border-dark-border dark:text-dark-text-muted">
                  No cargo shipments are scheduled through this location in the current route plan.
                </div>
              ) : (
                <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                  {nodeAllocations.slice(0, 8).map((alloc, i) => (
                    <div
                      key={`${alloc.origin_id}-${alloc.destination_id}-${alloc.commodity}-${i}`}
                      className="flex items-center justify-between rounded-lg border border-light-border bg-light-surface-subtle px-3 py-2 text-[11px] dark:border-dark-border dark:bg-dark-card"
                    >
                      <div className="min-w-0 pr-2">
                        <div className="font-semibold text-light-text-primary dark:text-dark-text-primary truncate">
                          {getReadableName(alloc.origin_id)} &rarr; {getReadableName(alloc.destination_id)}
                        </div>
                        <div className="text-[10px] text-light-text-muted dark:text-dark-text-muted">
                          {formatHumanLabel(alloc.commodity, COMMODITY_LABELS)} &middot;{" "}
                          {formatHumanLabel(alloc.mode, MODE_LABELS)}
                        </div>
                      </div>
                      <span className="shrink-0 font-semibold text-teal-700 dark:text-accent-cyan">
                        {alloc.flow_teu.toFixed(0)} containers/d
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* Supporting Reports & Past Cases */}
            {relatedEvidence.length > 0 && (
              <section className="space-y-2">
                <h4 className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-light-text-primary dark:text-dark-text-primary">
                  <BookOpen className="h-3.5 w-3.5 text-purple-600 dark:text-accent-purple" />
                  Supporting Context &amp; Past Cases ({relatedEvidence.length})
                </h4>
                <div className="space-y-1.5">
                  {relatedEvidence.slice(0, 4).map((ev) => (
                    <div
                      key={ev.citation_id}
                      className="rounded-xl border border-light-border bg-white p-2.5 text-[11px] dark:border-dark-border dark:bg-dark-card"
                    >
                      <div className="flex items-center justify-between text-[10px]">
                        <span className="font-semibold text-teal-700 dark:text-accent-cyan">
                          {ev.source}
                        </span>
                        <span className="text-light-text-muted dark:text-dark-text-muted">
                          {TRUST_LABELS[ev.trust_tier] ?? "Verified Source"}
                        </span>
                      </div>
                      <p className="mt-1 text-light-text-secondary dark:text-dark-text-secondary leading-relaxed">
                        {ev.snippet}
                      </p>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* Normal Traffic & Recovery Outlook (shown when historical baseline exists) */}
            {(loadingOutcomes || outcomes?.baseline) && (
              <section className="rounded-xl border border-light-border bg-light-surface-subtle p-3 space-y-1.5 dark:border-dark-border dark:bg-dark-card">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-light-text-primary dark:text-dark-text-primary">
                    Normal Traffic &amp; Recovery Outlook
                  </span>
                  {loadingOutcomes && (
                    <span className="text-[10px] text-light-text-muted">Loading...</span>
                  )}
                </div>
                {outcomes?.baseline && (
                  <div className="text-[11px] text-light-text-secondary dark:text-dark-text-secondary space-y-1.5">
                    <div>
                      Usual daily volume:{" "}
                      <strong>{outcomes.baseline.avg_daily_teu ?? "N/A"} containers/day</strong>
                      {outcomes.baseline.avg_vessel_calls
                        ? ` · ${outcomes.baseline.avg_vessel_calls} ship arrivals/day`
                        : ""}
                    </div>
                    {hazardCurve.length > 0 && (
                      <div>
                        <div className="text-[10px] text-light-text-muted mb-1">
                          Typical capacity recovery after disruption:
                        </div>
                        <div className="flex flex-wrap gap-1">
                          {hazardCurve.slice(0, 7).map((mult, idx) => (
                            <span
                              key={idx}
                              className="rounded bg-white px-1.5 py-0.5 text-[10px] border border-light-border dark:bg-dark-surface dark:border-dark-border"
                            >
                              Day {idx + 1}: {Math.round(mult * 100)}%
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </section>
            )}
          </div>

          {/* Footer Quick Actions */}
          {onOpenWhatIf && (
            <div className="border-t border-light-border px-5 py-3 bg-light-elevated dark:border-dark-border dark:bg-dark-card flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  onClose();
                  onOpenWhatIf();
                }}
                className="inline-flex items-center gap-1.5 rounded-lg bg-[#101C2C] px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 transition dark:bg-accent-cyan dark:text-[#090D14] dark:hover:bg-cyan-400"
              >
                <SlidersHorizontal className="h-3.5 w-3.5" />
                <span>Open Route Planner &amp; Simulator</span>
              </button>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
