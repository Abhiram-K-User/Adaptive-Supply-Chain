import { AlertTriangle, Send, ShieldAlert } from "lucide-react";
import { SCENARIO_PRESETS, type ScenarioPreset } from "../data/presets";
import type {
  DisruptionEvent,
  LLMProvider,
  RiskMode,
  SolverType,
  TrustTier,
} from "../types/asci";

export interface PlannerControlsState {
  headline: string;
  rawText: string;
  trustTier: TrustTier;
  affectedEntityIds: string[];
  riskMode: RiskMode;
  propagationTier: 1 | 2;
  solverType: SolverType;
  kHop: number;
  lambdaBudget: number;
  enableLlm: boolean;
  llmProvider: LLMProvider;
}

interface EventWorkbenchProps {
  controls: PlannerControlsState;
  onChangeControls: (patch: Partial<PlannerControlsState>) => void;
  events: DisruptionEvent[];
  selectedEventId: string | null;
  onSelectEventAndPlan: (eventId: string) => void;
  onIngestAndPlan: () => void;
  busy: boolean;
}

const PRESET_RING: Record<ScenarioPreset["badgeTone"], string> = {
  amber: "hover:border-amber-400/60",
  sky: "hover:border-sky-400/60",
  purple: "hover:border-purple-400/60",
  red: "hover:border-red-400/60 border-red-500/30",
};

export function EventWorkbench({
  controls,
  onChangeControls,
  events,
  selectedEventId,
  onSelectEventAndPlan,
  onIngestAndPlan,
  busy,
}: EventWorkbenchProps) {
  const applyPreset = (preset: ScenarioPreset) => {
    onChangeControls({
      headline: preset.headline,
      rawText: preset.text,
      trustTier: preset.trustTier,
      affectedEntityIds: preset.affectedIds,
    });
  };

  return (
    <aside className="space-y-3">
      <section className="rounded-xl border border-line bg-panel shadow-lg shadow-black/25">
        <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
          <h2 className="text-xs font-bold uppercase tracking-wider text-sky-300">
            1. Disruption Scenario Input
          </h2>
          <span className="text-[10px] font-semibold text-slate-400">Stage A + D</span>
        </div>

        <div className="space-y-3 p-3.5">
          <div className="grid grid-cols-2 gap-1.5">
            {SCENARIO_PRESETS.map((preset) => (
              <button
                key={preset.id}
                type="button"
                onClick={() => applyPreset(preset)}
                className={`rounded-lg border border-line bg-panel2 px-2.5 py-2 text-left transition ${PRESET_RING[preset.badgeTone]}`}
              >
                <div className="flex items-center gap-1 text-[11px] font-bold text-slate-100">
                  {preset.id === "injection_trap" && (
                    <ShieldAlert className="h-3 w-3 shrink-0 text-red-400" />
                  )}
                  <span className="truncate">{preset.label}</span>
                </div>
                <div className="truncate text-[10px] text-slate-400">{preset.subtitle}</div>
              </button>
            ))}
          </div>

          <div>
            <label className="mb-1 block text-[11px] font-semibold text-slate-400">
              Alert Headline
            </label>
            <input
              type="text"
              value={controls.headline}
              onChange={(e) => onChangeControls({ headline: e.target.value })}
              className="w-full rounded-lg border border-line bg-[#090f1d] px-2.5 py-1.5 text-xs text-slate-100 focus:border-sky-400 focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-1 block text-[11px] font-semibold text-slate-400">
              Raw Field Bulletin
            </label>
            <textarea
              rows={3}
              value={controls.rawText}
              onChange={(e) => onChangeControls({ rawText: e.target.value })}
              className="w-full rounded-lg border border-line bg-[#090f1d] px-2.5 py-1.5 text-xs text-slate-100 focus:border-sky-400 focus:outline-none"
            />
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-slate-400">
                Trust Tier
              </label>
              <select
                value={controls.trustTier}
                onChange={(e) =>
                  onChangeControls({ trustTier: e.target.value as TrustTier })
                }
                className="w-full rounded-lg border border-line bg-[#090f1d] px-2 py-1.5 text-xs text-slate-100 focus:border-sky-400 focus:outline-none"
              >
                <option value="TIER_A">TIER_A (Official)</option>
                <option value="TIER_B">TIER_B (Trade Press)</option>
                <option value="TIER_C">TIER_C (Chatter)</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-slate-400">
                Risk Mode
              </label>
              <select
                value={controls.riskMode}
                onChange={(e) =>
                  onChangeControls({ riskMode: e.target.value as RiskMode })
                }
                className="w-full rounded-lg border border-line bg-[#090f1d] px-2 py-1.5 text-xs text-slate-100 focus:border-sky-400 focus:outline-none"
              >
                <option value="CVAR">CVAR (Tail-Risk)</option>
                <option value="EXPECTED_COST">EXPECTED_COST</option>
                <option value="DETERMINISTIC">DETERMINISTIC</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-slate-400">
                Propagation Tier
              </label>
              <select
                value={controls.propagationTier}
                onChange={(e) =>
                  onChangeControls({ propagationTier: Number(e.target.value) as 1 | 2 })
                }
                className="w-full rounded-lg border border-line bg-[#090f1d] px-2 py-1.5 text-xs text-slate-100 focus:border-sky-400 focus:outline-none"
              >
                <option value={2}>Tier 2 (Dynamic BPR)</option>
                <option value={1}>Tier 1 (BFS Hop-Decay)</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-slate-400">
                Solver Engine
              </label>
              <select
                value={controls.solverType}
                onChange={(e) =>
                  onChangeControls({ solverType: e.target.value as SolverType })
                }
                className="w-full rounded-lg border border-line bg-[#090f1d] px-2 py-1.5 text-xs text-slate-100 focus:border-sky-400 focus:outline-none"
              >
                <option value="OR_TOOLS">OR-Tools + HiGHS</option>
                <option value="NETWORKX">NetworkX Fallback</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-slate-400">
                k-Hop Radius ({controls.kHop})
              </label>
              <input
                type="range"
                min={1}
                max={4}
                step={1}
                value={controls.kHop}
                onChange={(e) => onChangeControls({ kHop: Number(e.target.value) })}
                className="w-full accent-sky-400"
              />
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-slate-400">
                LLM Provider
              </label>
              <select
                value={controls.llmProvider}
                onChange={(e) =>
                  onChangeControls({ llmProvider: e.target.value as LLMProvider })
                }
                className="w-full rounded-lg border border-line bg-[#090f1d] px-2 py-1.5 text-xs text-slate-100 focus:border-sky-400 focus:outline-none"
              >
                <option value="auto">Auto (.env)</option>
                <option value="groq">Groq</option>
                <option value="gemini">Gemini</option>
                <option value="openai">OpenAI</option>
                <option value="ollama">Ollama</option>
                <option value="deterministic">Deterministic</option>
              </select>
            </div>
          </div>

          <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-line/70 bg-[#0a1122] px-2.5 py-2 text-xs text-slate-200">
            <input
              type="checkbox"
              checked={controls.enableLlm}
              onChange={(e) => onChangeControls({ enableLlm: e.target.checked })}
              className="rounded accent-sky-400"
            />
            <span>Enable LLM Stage A + RAG Executive Briefing</span>
          </label>

          <button
            type="button"
            disabled={busy}
            onClick={onIngestAndPlan}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-sky-500 px-3 py-2 text-xs font-bold text-slate-950 transition hover:bg-sky-400 disabled:opacity-50"
          >
            <Send className="h-3.5 w-3.5" />
            {busy ? "Optimizing Corridor..." : "Ingest Alert & Optimize Plan"}
          </button>
        </div>
      </section>

      <section className="rounded-xl border border-line bg-panel shadow-lg shadow-black/25">
        <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
          <h2 className="text-xs font-bold uppercase tracking-wider text-sky-300">
            2. Persisted Disruption Events
          </h2>
          <span className="rounded-full bg-panel2 px-2 py-0.5 text-[11px] font-semibold text-slate-200">
            {events.length}
          </span>
        </div>

        <div className="max-h-[420px] space-y-2 overflow-y-auto p-3">
          {events.length === 0 ? (
            <div className="rounded-lg border border-dashed border-line p-4 text-center text-xs text-slate-400">
              No persisted events yet. Poll replay feeds or ingest an alert above.
            </div>
          ) : (
            events.map((ev) => {
              const selected = ev.event_id === selectedEventId;
              return (
                <button
                  key={ev.event_id}
                  type="button"
                  onClick={() => onSelectEventAndPlan(ev.event_id)}
                  className={`w-full rounded-lg border p-2.5 text-left transition ${
                    selected
                      ? "border-sky-400 bg-sky-500/10"
                      : "border-line bg-[#0a1122] hover:border-sky-400/50"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-[11px] font-bold text-slate-100">
                      {ev.primary_entity_id}
                    </span>
                    <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[10px] font-semibold text-amber-300">
                      {ev.event_type} · {Math.round(ev.severity * 100)}%
                    </span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-[11px] text-slate-300">
                    {ev.raw_headline}
                  </p>
                  <div className="mt-1.5 flex items-center justify-between text-[10px] text-slate-400">
                    <span>
                      {ev.status} · Corrob: {ev.corroboration_count}
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <AlertTriangle className="h-3 w-3 text-slate-500" />
                      Conf {Math.round(ev.confidence * 100)}% · {ev.estimated_duration_days}d
                    </span>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </section>
    </aside>
  );
}

