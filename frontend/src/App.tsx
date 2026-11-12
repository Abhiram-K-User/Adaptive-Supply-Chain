import { useCallback, useEffect, useState } from "react";
import { asciApi } from "./api/client";
import { SCENARIO_PRESETS } from "./data/presets";
import {
  EventWorkbench,
  type PlannerControlsState,
} from "./components/EventWorkbench";
import { EvidenceView } from "./components/EvidenceView";
import { HeaderBar } from "./components/HeaderBar";
import { OutcomesMonitoringPlaceholderView } from "./components/OutcomesMonitoringPlaceholderView";
import { OverviewCommandView } from "./components/OverviewCommandView";
import { TraceView } from "./components/TraceView";
import { WhatIfPlaceholderView } from "./components/WhatIfPlaceholderView";
import type {
  ActiveWorkspaceTab,
  CanonicalEntity,
  DisruptionEvent,
  FeedsStatusResponse,
  HealthResponse,
  LLMStatusResponse,
  NetworkEdgeSummary,
  PlanResponse,
} from "./types/asci";

const INITIAL_PRESET = SCENARIO_PRESETS[0];

export function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [llmStatus, setLlmStatus] = useState<LLMStatusResponse | null>(null);
  const [entities, setEntities] = useState<CanonicalEntity[]>([]);
  const [baseEdges, setBaseEdges] = useState<NetworkEdgeSummary[]>([]);
  const [events, setEvents] = useState<DisruptionEvent[]>([]);
  const [feedsStatus, setFeedsStatus] = useState<FeedsStatusResponse | null>(null);
  const [autoPollEnabled, setAutoPollEnabled] = useState(false);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [planResponse, setPlanResponse] = useState<PlanResponse | null>(null);

  const [activeTab, setActiveTab] = useState<ActiveWorkspaceTab>("command");
  const [busy, setBusy] = useState(false);
  const [plannerComments, setPlannerComments] = useState(
    "Approved in ASCI Control Tower React Console"
  );
  const [statusBanner, setStatusBanner] = useState<{
    message: string;
    kind: "info" | "ok" | "err";
  }>({
    message:
      "Ready. Click 'Run Cyclone Michaung Demo' or select any event to optimize.",
    kind: "info",
  });

  const [controls, setControls] = useState<PlannerControlsState>({
    headline: INITIAL_PRESET.headline,
    rawText: INITIAL_PRESET.text,
    trustTier: INITIAL_PRESET.trustTier,
    affectedEntityIds: INITIAL_PRESET.affectedIds,
    riskMode: "CVAR",
    propagationTier: 2,
    solverType: "OR_TOOLS",
    kHop: 2,
    lambdaBudget: 0.05,
    enableLlm: true,
    llmProvider: "auto",
  });

  const updateControls = (patch: Partial<PlannerControlsState>) => {
    setControls((prev) => ({ ...prev, ...patch }));
  };

  const pickTopActiveEvent = useCallback((list: DisruptionEvent[]) => {
    const active = list.filter(
      (e) => e.status !== "EXPIRED" && e.status !== "RETRACTED"
    );
    const pool = active.length > 0 ? active : list;
    if (pool.length === 0) return null;
    return [...pool].sort(
      (a, b) =>
        b.severity * b.confidence - a.severity * a.confidence
    )[0];
  }, []);

  const refreshEvents = useCallback(async () => {
    const list = await asciApi.listEvents();
    setEvents(list);
    return list;
  }, []);

  const runPlanForEvent = useCallback(
    async (eventId: string, overrideControls?: PlannerControlsState) => {
      const cfg = overrideControls ?? controls;
      setSelectedEventId(eventId);
      setBusy(true);
      setStatusBanner({
        message: `Running Stage B->E optimization & RAG briefing for ${eventId}...`,
        kind: "info",
      });
      try {
        const res = await asciApi.generatePlan(eventId, {
          lambda_cost_budget: cfg.lambdaBudget,
          k_hop_neighborhood: cfg.kHop,
          risk_mode: cfg.riskMode,
          propagation_tier: cfg.propagationTier,
          solver_type: cfg.solverType,
          enable_llm: cfg.enableLlm,
          llm_provider: cfg.llmProvider,
        });
        setPlanResponse(res);
        setStatusBanner({
          message: `Completed ${res.session_id} (${res.status}) · Verifier: ${
            res.verification?.overall_verdict ?? "N/A"
          } · Unmet TEU: ${res.plan?.unmet_demand_teu.toFixed(1) ?? "N/A"}`,
          kind: res.verification?.passed ? "ok" : "err",
        });
      } catch (err) {
        setStatusBanner({
          message: `Plan error: ${err instanceof Error ? err.message : String(err)}`,
          kind: "err",
        });
      } finally {
        setBusy(false);
      }
    },
    [controls]
  );

  useEffect(() => {
    let active = true;
    const bootstrap = async () => {
      try {
        const [h, l, reg, net, evs, fs] = await Promise.all([
          asciApi.getHealth(),
          asciApi.getLlmStatus(),
          asciApi.getRegistry(),
          asciApi.getNetwork(),
          asciApi.listEvents(),
          asciApi.getFeedsStatus(),
        ]);
        if (!active) return;
        setHealth(h);
        setLlmStatus(l);
        setEntities(reg);
        setBaseEdges(net.edges);
        setEvents(evs);
        setFeedsStatus(fs);

        if (fs.poll_interval_seconds > 0) {
          setAutoPollEnabled(true);
        }

        if (evs.length > 0 && !selectedEventId) {
          const topEv = pickTopActiveEvent(evs);
          if (topEv) {
            void runPlanForEvent(topEv.event_id);
          }
        }
      } catch (err) {
        if (!active) return;
        setStatusBanner({
          message: `Backend connection error: ${
            err instanceof Error ? err.message : String(err)
          }`,
          kind: "err",
        });
      }
    };
    void bootstrap();
    return () => {
      active = false;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handlePollLive = useCallback(async () => {
    setBusy(true);
    setStatusBanner({
      message: "Polling LIVE GDACS, GDELT/India News RSS, Open-Meteo Weather & PortWatch...",
      kind: "info",
    });
    try {
      const rep = await asciApi.pollLiveFeeds();
      const [evs, fs] = await Promise.all([
        refreshEvents(),
        asciApi.getFeedsStatus(),
      ]);
      setFeedsStatus(fs);
      const topEv = pickTopActiveEvent(evs);
      if (topEv) {
        await runPlanForEvent(topEv.event_id);
      }
      setStatusBanner({
        message: `Live Poll: fetched ${rep.signals_collected} signals -> ${rep.events_persisted} corridor events (${evs.length} total). Optimized ${topEv ? topEv.primary_entity_id : "corridor"}.`,
        kind: "ok",
      });
    } catch (err) {
      setStatusBanner({
        message: `Live feed poll error: ${err instanceof Error ? err.message : String(err)}`,
        kind: "err",
      });
    } finally {
      setBusy(false);
    }
  }, [pickTopActiveEvent, refreshEvents, runPlanForEvent]);

  useEffect(() => {
    if (!autoPollEnabled) return;
    const ms = Math.max(15000, (feedsStatus?.poll_interval_seconds || 60) * 1000);
    const id = window.setInterval(() => {
      void handlePollLive();
    }, ms);
    return () => window.clearInterval(id);
  }, [autoPollEnabled, feedsStatus?.poll_interval_seconds, handlePollLive]);

  const handlePollReplay = async () => {
    setBusy(true);
    setStatusBanner({
      message: "Polling deterministic replay fixtures (GDACS, GDELT/RSS, IMD, PortWatch)...",
      kind: "info",
    });
    try {
      const rep = await asciApi.pollReplayFeeds(true);
      const [evs, fs] = await Promise.all([
        refreshEvents(),
        asciApi.getFeedsStatus(),
      ]);
      setFeedsStatus(fs);
      const topEv = pickTopActiveEvent(evs);
      if (topEv) {
        await runPlanForEvent(topEv.event_id);
      }
      setStatusBanner({
        message: `Replay Poll: collected ${rep.signals_collected} signals into ${rep.events_persisted} canonical events. Optimized ${topEv ? topEv.primary_entity_id : "corridor"}.`,
        kind: "ok",
      });
    } catch (err) {
      setStatusBanner({
        message: `Feed poll error: ${err instanceof Error ? err.message : String(err)}`,
        kind: "err",
      });
    } finally {
      setBusy(false);
    }
  };

  const handleIngestAndPlan = async (overridePreset?: PlannerControlsState) => {
    const cfg = overridePreset ?? controls;
    setBusy(true);
    setStatusBanner({
      message: "Running Stage A entity resolution & disruption perception...",
      kind: "info",
    });
    try {
      const ev = await asciApi.ingestEvent({
        raw_headline: cfg.headline,
        raw_text: cfg.rawText,
        trust_tier: cfg.trustTier,
        affected_entity_ids: cfg.affectedEntityIds,
        enable_llm: cfg.enableLlm,
        llm_provider: cfg.llmProvider,
      });
      await refreshEvents();
      setActiveTab("command");
      await runPlanForEvent(ev.event_id, cfg);
    } catch (err) {
      setStatusBanner({
        message: `Ingestion error: ${err instanceof Error ? err.message : String(err)}`,
        kind: "err",
      });
      setBusy(false);
    }
  };

  const handleRunMichaungDemo = () => {
    const nextControls: PlannerControlsState = {
      ...controls,
      headline: INITIAL_PRESET.headline,
      rawText: INITIAL_PRESET.text,
      trustTier: INITIAL_PRESET.trustTier,
      affectedEntityIds: INITIAL_PRESET.affectedIds,
      riskMode: "CVAR",
      propagationTier: 2,
      enableLlm: true,
    };
    setControls(nextControls);
    void handleIngestAndPlan(nextControls);
  };

  const handleRecordDecision = async (
    decision: "APPROVE" | "EDIT" | "REJECT",
    modifications?: Record<string, unknown>
  ) => {
    if (!planResponse?.plan) return;
    setBusy(true);
    try {
      const res = await asciApi.recordDecision({
        plan_id: planResponse.plan.plan_id,
        session_id: planResponse.session_id,
        decision,
        planner_id: "control_tower_operator",
        comments: plannerComments.trim() || `Recorded ${decision} from React UI`,
        modifications: modifications ?? {},
      });
      setStatusBanner({
        message: `Decision #${res.decision_id} (${res.decision}) saved to Decision Memory for ${res.plan_id}.`,
        kind: "ok",
      });
    } catch (err) {
      setStatusBanner({
        message: `Decision error: ${err instanceof Error ? err.message : String(err)}`,
        kind: "err",
      });
    } finally {
      setBusy(false);
    }
  };

  const selectedEvent =
    events.find((e) => e.event_id === selectedEventId) ?? null;

  return (
    <div className="min-h-screen bg-canvas text-slate-100">
      <HeaderBar
        health={health}
        llmStatus={llmStatus}
        nodeCount={entities.length}
        edgeCount={baseEdges.length}
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        onPollLive={() => void handlePollLive()}
        onPollReplay={() => void handlePollReplay()}
        autoPollEnabled={autoPollEnabled}
        onToggleAutoPoll={() => setAutoPollEnabled((prev) => !prev)}
        onRunMichaungDemo={handleRunMichaungDemo}
        busy={busy}
      />

      <main className="mx-auto max-w-[1680px] p-3.5">
        {activeTab === "command" && (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-[320px_minmax(0,1fr)]">
            <EventWorkbench
              controls={controls}
              onChangeControls={updateControls}
              events={events}
              selectedEventId={selectedEventId}
              onSelectEventAndPlan={(eventId) => void runPlanForEvent(eventId)}
              onIngestAndPlan={() => void handleIngestAndPlan()}
              busy={busy}
            />
            <OverviewCommandView
              entities={entities}
              baseEdges={baseEdges}
              planResponse={planResponse}
              feedsStatus={feedsStatus}
              statusBanner={statusBanner}
              plannerComments={plannerComments}
              onChangePlannerComments={setPlannerComments}
              onRecordDecision={(d, mods) => void handleRecordDecision(d, mods)}
              onOpenTab={setActiveTab}
              busy={busy}
            />
          </div>
        )}

        {activeTab === "evidence" && (
          <EvidenceView
            sessionEvidence={planResponse?.dashboard?.evidence_provenance ?? []}
          />
        )}

        {activeTab === "trace" && <TraceView planResponse={planResponse} />}

        {activeTab === "whatif" && (
          <WhatIfPlaceholderView
            entities={entities}
            activeEvent={selectedEvent}
            activePlan={planResponse}
          />
        )}

        {activeTab === "outcomes" && <OutcomesMonitoringPlaceholderView />}
      </main>
    </div>
  );
}

export default App;

