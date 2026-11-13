import { useCallback, useEffect, useState } from "react";
import { asciApi } from "./api/client";
import { SCENARIO_PRESETS } from "./data/presets";
import { type PlannerControlsState } from "./components/EventWorkbench";
import { Sidebar } from "./components/layout/Sidebar";
import { TopNavbar } from "./components/layout/TopNavbar";
import { GlobalSearchModal } from "./components/layout/GlobalSearchModal";
import { NodeDetailDrawer } from "./components/layout/NodeDetailDrawer";
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
  const [inspectedNodeId, setInspectedNodeId] = useState<string | null>(null);

  const [busy, setBusy] = useState(false);
  const [mitigatingEventId, setMitigatingEventId] = useState<string | null>(null);
  const pauseMs = (ms: number) =>
    new Promise<void>((resolve) => window.setTimeout(resolve, ms));
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
      (e) => e.status === "NEW" || e.status === "UPDATED"
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
      const isMichaungBatch =
        cfg.headline === INITIAL_PRESET.headline &&
        (INITIAL_PRESET.incidents?.length ?? 0) > 0;

      if (isMichaungBatch && INITIAL_PRESET.incidents) {
        setStatusBanner({
          message: `Generating ${INITIAL_PRESET.incidents.length} port-specific Cyclone Michaung disruptions across the East Coast...`,
          kind: "info",
        });
        const createdEvents = [];
        for (const inc of INITIAL_PRESET.incidents) {
          const created = await asciApi.ingestEvent({
            raw_headline: inc.headline,
            raw_text: inc.text,
            trust_tier: inc.trustTier,
            primary_entity_id: inc.primaryEntityId,
            affected_entity_ids: inc.affectedEntityIds,
            event_type: inc.eventType,
            severity: inc.severity,
            estimated_duration_days: inc.estimatedDurationDays,
            enable_llm: false,
            llm_provider: cfg.llmProvider,
          });
          createdEvents.push(created);
        }
        await refreshEvents();
        setActiveTab("overview");
        if (createdEvents[0]) {
          await runPlanForEvent(createdEvents[0].event_id, cfg);
        }
        return;
      }

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
      if (decision === "APPROVE") {
        await refreshEvents();
      }
      setStatusBanner({
        message:
          `Decision #${res.decision_id} (${res.decision}) saved for ${res.plan_id}` +
          (res.event_status === "MITIGATED" ? " · Disruption marked MITIGATED" : "") +
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

  const handleMitigateEvent = useCallback(
    async (eventId: string, planId?: string | null, sessionId?: string | null) => {
      const targetEv = events.find((e) => e.event_id === eventId);
      const targetLabel = targetEv?.primary_entity_id ?? eventId;
      setBusy(true);
      setMitigatingEventId(eventId);
      setStatusBanner({
        message: `Recalculating bypass & rail diversion routes for ${targetLabel}...`,
        kind: "info",
      });
      try {
        const calcStart = Date.now();
        let effectivePlanId = planId ?? null;
        let effectiveSessionId = sessionId ?? null;

        // Calculate dedicated recovery routes for this port if not currently planned
        if (!effectivePlanId || planResponse?.event_id !== eventId) {
          const generated = await asciApi.generatePlan(eventId, {
            lambda_cost_budget: controls.lambdaBudget,
            k_hop_neighborhood: controls.kHop,
            risk_mode: controls.riskMode,
            propagation_tier: controls.propagationTier,
            solver_type: controls.solverType,
            controller_mode: controls.controllerMode,
            enable_llm: false,
            llm_provider: controls.llmProvider,
          });
          setPlanResponse(generated);
          setSelectedEventId(eventId);
          effectivePlanId = generated.plan?.plan_id ?? null;
          effectiveSessionId = generated.session_id ?? null;
        }

        const phase1Remaining = 1300 - (Date.now() - calcStart);
        if (phase1Remaining > 0) {
          await pauseMs(phase1Remaining);
        }

        setStatusBanner({
          message: `Applying recalculated diversion routes and restoring capacity at ${targetLabel}...`,
          kind: "info",
        });

        const res = await asciApi.mitigateEvent(eventId, {
          plan_id: effectivePlanId ?? undefined,
          session_id: effectiveSessionId ?? undefined,
          planner_id: "control_tower_operator",
          comments: plannerComments.trim() || "Mitigation plan applied from Control Tower UI",
        });

        await pauseMs(700);
        const updatedEvents = await refreshEvents();
        const remainingActive = updatedEvents.filter(
          (e) => e.status === "NEW" || e.status === "UPDATED"
        );

        if (remainingActive.length > 0) {
          const nextEv = pickTopActiveEvent(remainingActive);
          if (nextEv) {
            setStatusBanner({
              message: `Fixed ${res.event.primary_entity_id} · Re-optimizing routes around ${remainingActive.length} remaining disrupted port${remainingActive.length === 1 ? "" : "s"} (${nextEv.primary_entity_id})...`,
              kind: "info",
            });
            const nextPlan = await asciApi.generatePlan(nextEv.event_id, {
              lambda_cost_budget: controls.lambdaBudget,
              k_hop_neighborhood: controls.kHop,
              risk_mode: controls.riskMode,
              propagation_tier: controls.propagationTier,
              solver_type: controls.solverType,
              controller_mode: controls.controllerMode,
              enable_llm: controls.enableLlm,
              llm_provider: controls.llmProvider,
            });
            setSelectedEventId(nextEv.event_id);
            setPlanResponse(nextPlan);
            setStatusBanner({
              message:
                `Fixed ${res.event.primary_entity_id} (${eventId})` +
                (res.plan_id ? ` via ${res.plan_id}` : "") +
                ` · ${remainingActive.length} port disruption${remainingActive.length === 1 ? "" : "s"} still active (${nextEv.primary_entity_id} requires individual fix).`,
              kind: "ok",
            });
            return;
          }
        }

        setStatusBanner({
          message:
            `Mitigated ${res.event.primary_entity_id} (${eventId})` +
            (res.plan_id ? ` via ${res.plan_id}` : "") +
            (res.indexed_citation_id ? ` · Playbook [${res.indexed_citation_id}]` : "") +
            " · All active corridor disruptions resolved.",
          kind: "ok",
        });
      } catch (err) {
        setStatusBanner({
          message: `Mitigation error: ${err instanceof Error ? err.message : String(err)}`,
          kind: "err",
        });
      } finally {
        setMitigatingEventId(null);
        setBusy(false);
      }
    },
    [
      controls,
      events,
      pickTopActiveEvent,
      planResponse?.event_id,
      plannerComments,
      refreshEvents,
    ]
  );

  const handleReopenEvent = useCallback(
    async (eventId: string) => {
      setBusy(true);
      try {
        const ev = await asciApi.reopenEvent(eventId);
        await refreshEvents();
        setStatusBanner({
          message: `Reopened disruption ${ev.event_id} (${ev.primary_entity_id}) for active planning.`,
          kind: "info",
        });
      } catch (err) {
        setStatusBanner({
          message: `Reopen error: ${err instanceof Error ? err.message : String(err)}`,
          kind: "err",
        });
      } finally {
        setBusy(false);
      }
    },
    [refreshEvents]
  );

  const runSelectedOrTopOptimization = useCallback(() => {
    const target =
      events.find((e) => e.event_id === selectedEventId) ??
      pickTopActiveEvent(events);
    if (target) void runPlanForEvent(target.event_id);
    else handleRunMichaungDemo();
  }, [events, selectedEventId, pickTopActiveEvent, runPlanForEvent]);

  const activeDisruptionCount = events.filter(
    (e) => e.status === "NEW" || e.status === "UPDATED"
  ).length;

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
        disruptionCount={activeDisruptionCount}
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
          alertCount={activeDisruptionCount}
          onOpenSearch={() => setSearchOpen(true)}
          onOpenNotifications={() => setNotificationsOpen(true)}
          onPollLive={() => void handlePollLive()}
          onRunMichaungDemo={handleRunMichaungDemo}
          onRunOptimization={runSelectedOrTopOptimization}
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
              events={events}
              planResponse={planResponse}
              feedsStatus={feedsStatus}
              statusBanner={statusBanner}
              onOpenTab={setActiveTab}
              onRunOptimization={runSelectedOrTopOptimization}
              onMitigateEvent={(eid, pid, sid) => void handleMitigateEvent(eid, pid, sid)}
              onSelectNode={setInspectedNodeId}
              busy={busy}
              mitigatingEventId={mitigatingEventId}
            />
          )}

          {normalizedTab === "network" && (
            <NetworkView
              entities={entities}
              baseEdges={baseEdges}
              events={events}
              planResponse={planResponse}
              onSelectNode={setInspectedNodeId}
              onSelectEntity={(ent) => {
                setInspectedNodeId(ent.id);
                setStatusBanner({
                  message: `Selected ${ent.name} (${ent.id} · ${ent.entity_type} · ${ent.region})`,
                  kind: "info",
                });
              }}
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
              planResponse={planResponse}
              statusBanner={statusBanner}
              onSelectEventAndPlan={(id) => void runPlanForEvent(id)}
              onMitigateEvent={(eid, pid, sid) => void handleMitigateEvent(eid, pid, sid)}
              onReopenEvent={(eid) => void handleReopenEvent(eid)}
              onOpenOptimizationTab={() => setActiveTab("optimization")}
              controls={controls}
              onChangeControls={updateControls}
              onIngestAndPlan={() => void handleIngestAndPlan()}
              onPollLive={() => void handlePollLive()}
              busy={busy}
              mitigatingEventId={mitigatingEventId}
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
              onRunOptimization={runSelectedOrTopOptimization}
              onMitigateEvent={(eid, pid, sid) => void handleMitigateEvent(eid, pid, sid)}
              onRecordDecision={handleRecordDecision}
              plannerComments={plannerComments}
              onChangePlannerComments={setPlannerComments}
              busy={busy}
              mitigatingEventId={mitigatingEventId}
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

      {/* 5. Interactive Node Operations & Disruptions Sidebar */}
      <NodeDetailDrawer
        nodeId={inspectedNodeId}
        onClose={() => setInspectedNodeId(null)}
        entities={entities}
        baseEdges={baseEdges}
        events={events}
        planResponse={planResponse}
        feedsStatus={feedsStatus}
        onRunPlanForEvent={(id) => void runPlanForEvent(id)}
        onMitigateEvent={(eid, pid, sid) => void handleMitigateEvent(eid, pid, sid)}
        onReopenEvent={(eid) => void handleReopenEvent(eid)}
        onOpenWhatIf={() => setActiveTab("optimization")}
        busy={busy}
        mitigatingEventId={mitigatingEventId}
      />
    </div>
  );
}

export default App;
