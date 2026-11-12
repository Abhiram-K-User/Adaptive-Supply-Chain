import { Activity, Cpu, Play, Radio, ShieldCheck, Sliders, Sparkles } from "lucide-react";
import type {
  ActiveWorkspaceTab,
  HealthResponse,
  LLMStatusResponse,
} from "../types/asci";

interface HeaderBarProps {
  health: HealthResponse | null;
  llmStatus: LLMStatusResponse | null;
  nodeCount: number;
  edgeCount: number;
  activeTab: ActiveWorkspaceTab;
  onSelectTab: (tab: ActiveWorkspaceTab) => void;
  onPollLive: () => void;
  onPollReplay: () => void;
  autoPollEnabled: boolean;
  onToggleAutoPoll: () => void;
  onRunMichaungDemo: () => void;
  busy: boolean;
}

const TABS: Array<{
  id: ActiveWorkspaceTab;
  label: string;
  planned?: boolean;
}> = [
  { id: "command", label: "Command Center" },
  { id: "evidence", label: "Evidence & Playbooks" },
  { id: "trace", label: "Computation Trace" },
  { id: "whatif", label: "What-If Sandbox", planned: true },
  { id: "outcomes", label: "Outcomes & Loop L1", planned: true },
];

export function HeaderBar({
  health,
  llmStatus,
  nodeCount,
  edgeCount,
  activeTab,
  onSelectTab,
  onPollLive,
  onPollReplay,
  autoPollEnabled,
  onToggleAutoPoll,
  onRunMichaungDemo,
  busy,
}: HeaderBarProps) {
  const isLiveLlm = Boolean(llmStatus?.configured);

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-[#060a14]/95 backdrop-blur">
      <div className="mx-auto flex max-w-[1680px] flex-wrap items-center justify-between gap-3 px-4 py-2.5">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-sky-500/40 bg-sky-500/15 text-sky-400">
            <Activity className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-bold tracking-tight text-slate-100 sm:text-base">
                ASCI v2.0 — Adaptive Supply Chain Intelligence
              </h1>
              <span className="hidden rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-300 sm:inline-block">
                React + TS + Cytoscape.js
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              South India Automotive Logistics Corridor · Agentic-RAG + Multi-Commodity OR-Tools / HiGHS
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-panel2 px-2.5 py-1 text-[11px] font-medium text-slate-200">
            <ShieldCheck className="h-3.5 w-3.5 text-sky-400" />
            Scale:{" "}
            <strong className="font-semibold text-white">
              {health?.network_scale ?? "..."}
            </strong>
            <span className="text-slate-400">
              ({nodeCount}n / {edgeCount}e)
            </span>
          </span>

          <span
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium ${
              isLiveLlm
                ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                : "border-amber-500/40 bg-amber-500/10 text-amber-300"
            }`}
          >
            <Cpu className="h-3.5 w-3.5" />
            {llmStatus
              ? isLiveLlm
                ? `LLM: ${llmStatus.active_provider} (${llmStatus.model})`
                : "LLM: deterministic offline"
              : "LLM: checking..."}
          </span>

          <span className="hidden rounded-full border border-line bg-panel2 px-2.5 py-1 text-[11px] text-slate-300 xl:inline-flex">
            DB: {health?.persistence ?? "..."}
          </span>

          <button
            type="button"
            disabled={busy}
            onClick={onPollLive}
            className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/50 bg-emerald-500/15 px-3 py-1.5 text-xs font-semibold text-emerald-200 transition hover:bg-emerald-500/25 disabled:opacity-50"
          >
            <Radio className="h-3.5 w-3.5 text-emerald-400" />
            Poll Live Feeds
          </button>

          <button
            type="button"
            disabled={busy}
            onClick={onPollReplay}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-panel2 px-2.5 py-1.5 text-xs font-semibold text-slate-200 transition hover:border-sky-400/60 hover:bg-slate-800 disabled:opacity-50"
          >
            Replay Sample
          </button>

          <button
            type="button"
            onClick={onToggleAutoPoll}
            className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-[11px] font-semibold transition ${
              autoPollEnabled
                ? "border-emerald-400/50 bg-emerald-500/15 text-emerald-300"
                : "border-line bg-panel2 text-slate-400 hover:text-slate-200"
            }`}
          >
            Auto 60s: {autoPollEnabled ? "ON" : "OFF"}
          </button>

          <button
            type="button"
            disabled={busy}
            onClick={onRunMichaungDemo}
            className="inline-flex items-center gap-1.5 rounded-lg bg-sky-500 px-3 py-1.5 text-xs font-semibold text-slate-950 transition hover:bg-sky-400 disabled:opacity-50"
          >
            <Play className="h-3.5 w-3.5 fill-current" />
            Cyclone Michaung Demo
          </button>
        </div>
      </div>

      <nav className="mx-auto flex max-w-[1680px] flex-wrap items-center gap-1 border-t border-line/70 px-4 py-1.5">
        {TABS.map((tab) => {
          const selected = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => onSelectTab(tab.id)}
              className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition ${
                selected
                  ? "bg-sky-500/15 text-sky-300 ring-1 ring-inset ring-sky-400/40"
                  : "text-slate-400 hover:bg-panel2 hover:text-slate-200"
              }`}
            >
              {tab.planned ? (
                <Sliders className="h-3.5 w-3.5 text-amber-400" />
              ) : (
                <Sparkles className="h-3.5 w-3.5 text-sky-400" />
              )}
              <span>{tab.label}</span>
              {tab.planned && (
                <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-amber-300">
                  Placeholder
                </span>
              )}
            </button>
          );
        })}
      </nav>
    </header>
  );
}

