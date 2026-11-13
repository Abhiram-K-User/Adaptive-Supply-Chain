import { useCallback, useEffect, useState } from "react";
import { asciApi } from "./api/client";
import { SCENARIO_PRESETS } from "./data/presets";
import { type PlannerControlsState } from "./components/EventWorkbench";
import { Sidebar } from "./components/layout/Sidebar";
import { TopNavbar } from "./components/layout/TopNavbar";
import { GlobalSearchModal } from "./components/layout/GlobalSearchModal";
import { NotificationDrawer } from "./components/layout/NotificationDrawer";
import { OverviewPage } from "./pages/OverviewPage";
import { NetworkView } from "./components/NetworkView";
import { InventoryView } from "./components/InventoryView";
import { ForecastingView } from "./components/ForecastingView";
import { SuppliersView } from "./components/SuppliersView";
import { RiskView } from "./components/RiskView";
import { OptimizationView } from "./components/OptimizationView";
import { AnalyticsView } from "./components/AnalyticsView";

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

  const [activeTab, setActiveTab] = useState<ActiveWorkspaceTab>("overview");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);

  const [busy, setBusy] = useState(false);
  const [plannerComments, setPlannerComments] = useState(
    "Approved in ASCI Control Tower React Console"
  );
  const [statusBanner, setStatusBanner] = useState<{
    message: string;
    kind: "info" | "ok" | "err";
  }>({
    message:
      "Ready. South India logistics corridor calibrated (118 nodes, 364 edges). Select an event or run optimization.",
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
    controllerMode: "learned_mlp",
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
      (a, b) => b.severity * b.confidence - a.severity * a.confidence
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
          controller_mode: cfg.controllerMode,
          enable_llm: cfg.enableLlm,
          llm_provider: cfg.llmProvider,
        });
        setPlanResponse(res);
        setStatusBanner({
          message: `Completed ${res.session_id} (${res.status}) · Policy: ${cfg.controllerMode} · Verifier: ${
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
        const msg = err instanceof Error ? err.message : String(err);
        setStatusBanner({
          message: `Backend notice: ${msg}. (Start backend server on port 8000 via 'python -m uvicorn backend.app.main:app' to stream live corridor data)`,
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
      message:
        "Polling LIVE GDACS, GDELT/India News RSS, Open-Meteo Weather & PortWatch...",
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
        message: `Live feed poll error: ${
          err instanceof Error ? err.message : String(err)
        }`,
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
      setActiveTab("overview");
      await runPlanForEvent(ev.event_id, cfg);
    } catch (err) {
      setStatusBanner({
        message: `Ingestion error: ${
          err instanceof Error ? err.message : String(err)
        }`,
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
        message:
          `Decision #${res.decision_id} (${res.decision}) saved to Decision Memory for ${res.plan_id}` +
          (res.indexed_citation_id
            ? ` · Indexed Loop L4 Playbook [${res.indexed_citation_id}]`
            : "."),
        kind: "ok",
      });
    } catch (err) {
      setStatusBanner({
        message: `Decision error: ${
          err instanceof Error ? err.message : String(err)
        }`,
        kind: "err",
      });
    } finally {
      setBusy(false);
    }
  };

  // Map legacy tabs to corresponding views
  const normalizedTab =
    activeTab === "command"
      ? "overview"
      : activeTab === "evidence" || activeTab === "trace"
      ? "analytics"
      : activeTab === "whatif"
      ? "optimization"
      : activeTab === "outcomes"
      ? "forecasting"
      : activeTab;

  return (
    <div
      className={`min-h-screen w-full grid transition-[grid-template-columns] duration-200 ${
        sidebarCollapsed
          ? "grid-cols-[76px_minmax(0,1fr)]"
          : "grid-cols-[260px_minmax(0,1fr)]"
      } bg-transparent text-light-text-primary dark:text-dark-text-primary`}
    >
      {/* 1. Left Enterprise Sidebar (Column 1 of Grid) */}
      <Sidebar
        activeTab={normalizedTab}
        onSelectTab={setActiveTab}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((prev) => !prev)}
        health={health}
        nodeCount={entities.length}
        edgeCount={baseEdges.length}
        disruptionCount={events.length}
      />

      {/* 2. Main Workspace (Column 2 of Grid - Automatically Resizes) */}
      <div className="flex flex-col min-w-0 h-screen overflow-y-auto">
        {/* Top Navbar */}
        <TopNavbar
          activeTab={normalizedTab}
          health={health}
          llmStatus={llmStatus}
          feedsStatus={feedsStatus}
          nodeCount={entities.length}
          edgeCount={baseEdges.length}
          alertCount={events.length}
          onOpenSearch={() => setSearchOpen(true)}
          onOpenNotifications={() => setNotificationsOpen(true)}
          onPollLive={() => void handlePollLive()}
          onRunMichaungDemo={handleRunMichaungDemo}
          onRunOptimization={() => {
            const top = pickTopActiveEvent(events);
            if (top) void runPlanForEvent(top.event_id);
            else handleRunMichaungDemo();
          }}
          autoPollEnabled={autoPollEnabled}
          onToggleAutoPoll={() => setAutoPollEnabled((prev) => !prev)}
          busy={busy}
          collapsedSidebar={sidebarCollapsed}
        />

        {/* Dynamic Page Views */}
        <main className="flex-1 p-5 max-w-[1720px] w-full mx-auto">
          {normalizedTab === "overview" && (
            <OverviewPage
              entities={entities}
              baseEdges={baseEdges}
              planResponse={planResponse}
              feedsStatus={feedsStatus}
              statusBanner={statusBanner}
              onOpenTab={setActiveTab}
              onRunOptimization={() => {
                const top = pickTopActiveEvent(events);
                if (top) void runPlanForEvent(top.event_id);
                else handleRunMichaungDemo();
              }}
              busy={busy}
            />
          )}

          {normalizedTab === "network" && (
            <NetworkView
              entities={entities}
              baseEdges={baseEdges}
              planResponse={planResponse}
              onSelectEntity={(ent) =>
                setStatusBanner({
                  message: `Selected ${ent.name} (${ent.id} · ${ent.entity_type} · ${ent.region})`,
                  kind: "info",
                })
              }
            />
          )}

          {normalizedTab === "inventory" && (
            <InventoryView
              entities={entities}
              planResponse={planResponse}
            />
          )}

          {normalizedTab === "forecasting" && (
            <ForecastingView
              entities={entities}
              planResponse={planResponse}
            />
          )}

          {normalizedTab === "suppliers" && (
            <SuppliersView
              entities={entities}
              feedsStatus={feedsStatus}
            />
          )}

          {normalizedTab === "risk" && (
            <RiskView
              events={events}
              feedsStatus={feedsStatus}
              selectedEventId={selectedEventId}
              onSelectEventAndPlan={(id) => void runPlanForEvent(id)}
              controls={controls}
              onChangeControls={updateControls}
              onIngestAndPlan={() => void handleIngestAndPlan()}
              onPollLive={() => void handlePollLive()}
              busy={busy}
            />
          )}

          {normalizedTab === "optimization" && (
            <OptimizationView
              entities={entities}
              activeEvent={
                events.find((e) => e.event_id === selectedEventId) ??
                pickTopActiveEvent(events)
              }
              planResponse={planResponse}
              controls={controls}
              onChangeControls={updateControls}
              onRunOptimization={() => {
                const top = pickTopActiveEvent(events);
                if (top) void runPlanForEvent(top.event_id);
                else handleRunMichaungDemo();
              }}
              onRecordDecision={handleRecordDecision}
              plannerComments={plannerComments}
              onChangePlannerComments={setPlannerComments}
              busy={busy}
            />
          )}

          {normalizedTab === "analytics" && (
            <AnalyticsView
              entities={entities}
              planResponse={planResponse}
            />
          )}
        </main>
      </div>

      {/* 3. Global Search Modal (Ctrl+K) */}
      <GlobalSearchModal
        isOpen={searchOpen}
        onClose={() => setSearchOpen(false)}
        entities={entities}
        events={events}
        onSelectTab={setActiveTab}
        onSelectEvent={(id) => void runPlanForEvent(id)}
      />

      {/* 4. Live Notifications & Telemetry Drawer */}
      <NotificationDrawer
        isOpen={notificationsOpen}
        onClose={() => setNotificationsOpen(false)}
        events={events}
        feedsStatus={feedsStatus}
        onSelectEvent={(id) => void runPlanForEvent(id)}
      />
    </div>
  );
}

export default App;
