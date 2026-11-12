import { useState } from "react";
import { Lock, SlidersHorizontal } from "lucide-react";
import type { CanonicalEntity, DisruptionEvent, PlanResponse } from "../types/asci";

interface WhatIfPlaceholderViewProps {
  entities: CanonicalEntity[];
  activeEvent: DisruptionEvent | null;
  activePlan: PlanResponse | null;
}

export function WhatIfPlaceholderView({
  entities,
  activeEvent,
  activePlan,
}: WhatIfPlaceholderViewProps) {
  const [targetEntityId, setTargetEntityId] = useState(
    activeEvent?.primary_entity_id ?? "PORT_CHENNAI"
  );
  const [capacityMultiplier, setCapacityMultiplier] = useState(0.35);
  const [durationDays, setDurationDays] = useState(
    activeEvent?.estimated_duration_days ?? 4.0
  );

  const portsAndHubs = entities.filter(
    (e) => e.entity_type === "PORT" || e.entity_type === "ICD"
  );

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-dashed border-amber-500/50 bg-amber-500/5 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="h-4 w-4 text-amber-300" />
            <h2 className="text-sm font-bold text-amber-200">
              Interactive What-If Sandbox — Placeholder (PRD 10.2: POST /whatif)
            </h2>
          </div>
          <span className="rounded-full border border-amber-500/40 bg-amber-500/15 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-300">
            Backend Endpoint Not Implemented Yet
          </span>
        </div>
        <p className="mt-2 text-xs leading-relaxed text-slate-300">
          Per <code className="text-slate-200">project_context.md</code> Sec. 2 &amp; Sec. 7
          (Phase 4 / Team Lane M3), <code className="text-amber-200">POST /whatif</code> is
          planned to accept custom node capacity multipliers and hazard durations to compute
          instant side-by-side sensitivity deltas against the active baseline plan without
          mutating persisted events.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Controls Preview */}
        <section className="rounded-xl border border-line bg-panel p-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
            Sensitivity Controls (Preview Only)
          </h3>

          <div className="mt-3 space-y-4">
            <div>
              <label className="mb-1 block text-xs font-semibold text-slate-400">
                Target Port / ICD Override
              </label>
              <select
                value={targetEntityId}
                onChange={(e) => setTargetEntityId(e.target.value)}
                className="w-full rounded-lg border border-line bg-[#090f1d] px-3 py-2 text-xs text-slate-100"
              >
                {portsAndHubs.map((ent) => (
                  <option key={ent.id} value={ent.id}>
                    {ent.name} ({ent.id})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <div className="mb-1 flex justify-between text-xs">
                <span className="font-semibold text-slate-400">
                  Remaining Capacity Multiplier
                </span>
                <span className="font-mono font-bold text-amber-300">
                  {Math.round(capacityMultiplier * 100)}%
                </span>
              </div>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={capacityMultiplier}
                onChange={(e) => setCapacityMultiplier(Number(e.target.value))}
                className="w-full accent-amber-400"
              />
            </div>

            <div>
              <div className="mb-1 flex justify-between text-xs">
                <span className="font-semibold text-slate-400">
                  Simulated Disruption Duration
                </span>
                <span className="font-mono font-bold text-amber-300">
                  {durationDays.toFixed(1)} days
                </span>
              </div>
              <input
                type="range"
                min={0.5}
                max={14}
                step={0.5}
                value={durationDays}
                onChange={(e) => setDurationDays(Number(e.target.value))}
                className="w-full accent-amber-400"
              />
            </div>

            <button
              type="button"
              disabled
              className="flex w-full cursor-not-allowed items-center justify-center gap-2 rounded-lg border border-dashed border-amber-500/40 bg-panel2 px-3 py-2 text-xs font-bold text-slate-400 opacity-75"
            >
              <Lock className="h-3.5 w-3.5 text-amber-400" />
              Run Sensitivity Re-Optimization (Awaiting POST /whatif)
            </button>
          </div>
        </section>

        {/* Side-by-Side Comparison Placeholder */}
        <section className="rounded-xl border border-line bg-panel p-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
            Baseline vs What-If Delta Panel (Placeholder)
          </h3>

          <div className="mt-3 grid grid-cols-2 gap-3">
            <div className="rounded-lg border border-line bg-[#0a1122] p-3">
              <div className="text-[10px] font-bold uppercase text-sky-300">
                Active Plan Baseline
              </div>
              <div className="mt-2 space-y-1.5 text-xs">
                <div className="flex justify-between">
                  <span className="text-slate-400">Plan ID</span>
                  <span className="font-mono text-slate-200">
                    {activePlan?.plan?.plan_id ?? "None loaded"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Objective Cost</span>
                  <span className="font-mono font-bold text-white">
                    {activePlan?.plan
                      ? `$${activePlan.plan.objective_cost.toLocaleString(undefined, {
                          maximumFractionDigits: 1,
                        })}`
                      : "—"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Unmet TEU</span>
                  <span className="font-mono text-emerald-300">
                    {activePlan?.plan
                      ? activePlan.plan.unmet_demand_teu.toFixed(1)
                      : "—"}
                  </span>
                </div>
              </div>
            </div>

            <div className="rounded-lg border border-dashed border-amber-500/40 bg-[#0a1122] p-3">
              <div className="text-[10px] font-bold uppercase text-amber-300">
                What-If Sandbox Delta
              </div>
              <div className="mt-2 space-y-1.5 text-xs text-slate-500">
                <div className="flex justify-between">
                  <span>Cost Delta</span>
                  <span className="font-mono">Pending /whatif</span>
                </div>
                <div className="flex justify-between">
                  <span>Mode Shift Delta</span>
                  <span className="font-mono">Pending /whatif</span>
                </div>
                <div className="flex justify-between">
                  <span>TTLS Margin Delta</span>
                  <span className="font-mono">Pending /whatif</span>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

