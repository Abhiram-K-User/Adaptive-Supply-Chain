import { useState } from "react";
import { SlidersHorizontal, Play, AlertTriangle, CheckCircle, XCircle, AlertCircle } from "lucide-react";
import type { CanonicalEntity, DisruptionEvent, PlanResponse, MitigationPlan, VerificationReport } from "../types/asci";

// ── Types ────────────────────────────────────────────────────────────────────

interface WhatIfRequest {
  event_id?: string;
  target_entity_id: string;
  capacity_multiplier: number;
  duration_days: number;
  risk_mode: "DETERMINISTIC" | "EXPECTED_COST" | "CVAR";
  propagation_tier: 1 | 2;
  baseline_plan_id?: string;
}

interface WhatIfResponse {
  simulated_plan: MitigationPlan | null;
  verification: VerificationReport | null;
  cost_delta: number;
  unmet_demand_delta_teu: number;
  rail_share_delta_pct: number;
  baseline_total_cost: number;
  simulated_total_cost: number;
}

// ── Props ────────────────────────────────────────────────────────────────────

interface WhatIfPlaceholderViewProps {
  entities: CanonicalEntity[];
  activeEvent: DisruptionEvent | null;
  activePlan: PlanResponse | null;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtCost(v: number) {
  return `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function fmtDelta(v: number, prefix = "+") {
  return v >= 0 ? `${prefix}${v.toLocaleString(undefined, { maximumFractionDigits: 1 })}` : v.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

function VerdictIcon({ verdict }: { verdict: "PASS" | "FAIL" | "WARN" }) {
  if (verdict === "PASS") return <CheckCircle className="h-3.5 w-3.5 text-google-green" />;
  if (verdict === "FAIL") return <XCircle className="h-3.5 w-3.5 text-google-red" />;
  return <AlertTriangle className="h-3.5 w-3.5 text-google-yellow" />;
}

// ── Main Component ───────────────────────────────────────────────────────────

export function WhatIfPlaceholderView({
  entities,
  activeEvent,
  activePlan,
}: WhatIfPlaceholderViewProps) {
  // Controls
  const [targetEntityId, setTargetEntityId] = useState(
    activeEvent?.primary_entity_id ?? "PORT_CHENNAI"
  );
  const [capacityMultiplier, setCapacityMultiplier] = useState(0.35);
  const [durationDays, setDurationDays] = useState(
    activeEvent?.estimated_duration_days ?? 4.0
  );
  const [riskMode, setRiskMode] = useState<"DETERMINISTIC" | "EXPECTED_COST" | "CVAR">("CVAR");

  // API state
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<WhatIfResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const portsAndHubs = entities.filter(
    (e) => e.entity_type === "PORT" || e.entity_type === "ICD"
  );

  async function runWhatIf() {
    setLoading(true);
    setError(null);
    setResult(null);

    const payload: WhatIfRequest = {
      event_id: activeEvent?.event_id,
      target_entity_id: targetEntityId,
      capacity_multiplier: capacityMultiplier,
      duration_days: durationDays,
      risk_mode: riskMode,
      propagation_tier: 2,
      baseline_plan_id: activePlan?.plan?.plan_id,
    };

    try {
      const res = await fetch("/whatif", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
          const rawText = await res.text();
          try {
            const parsed = JSON.parse(rawText) as { detail?: unknown; message?: unknown; error?: unknown };
            const msg = parsed?.detail ?? parsed?.message ?? parsed?.error;
            if (msg) detail = typeof msg === "string" ? msg : JSON.stringify(msg);
            else if (rawText.trim()) detail = rawText.trim();
          } catch {
            if (rawText.trim()) detail = rawText.trim();
          }
        } catch { /* ignore */ }
        throw new Error(detail);
      }

      const data = (await res.json()) as WhatIfResponse;
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  // ── Verification layer summaries ──────────────────────────────────────────
  const verif = result?.verification;
  const layerChecks = verif
    ? [
        { label: "L1", checks: verif.l1_checks },
        { label: "L2", checks: verif.l2_checks },
        { label: "L3", checks: verif.l3_checks },
      ]
    : [];

  return (
    <div className="space-y-4">
      {/* ── Header ── */}
      <div className="flex items-center gap-2 pb-1">
        <SlidersHorizontal className="h-4 w-4 text-google-blue" />
        <h2 className="text-sm font-bold text-light-text-primary dark:text-dark-text-primary">
          What-If Sensitivity Sandbox
        </h2>
        <span className="ml-auto rounded-full border border-google-blue/30 bg-google-blue/10 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-google-blue">
          POST /whatif
        </span>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* ── Controls ── */}
        <section className="rounded-xl border border-light-border dark:border-dark-border bg-light-card dark:bg-dark-card p-4 space-y-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-light-text-secondary dark:text-dark-text-secondary">
            Sensitivity Controls
          </h3>

          {/* Target Port / ICD */}
          <div>
            <label className="mb-1 block text-xs font-semibold text-light-text-secondary dark:text-dark-text-secondary">
              Target Port / ICD Override
            </label>
            <select
              value={targetEntityId}
              onChange={(e) => setTargetEntityId(e.target.value)}
              className="w-full rounded-lg border border-light-border dark:border-dark-border bg-light-secondary dark:bg-dark-elevated px-3 py-2 text-xs text-light-text-primary dark:text-dark-text-primary focus:outline-none focus:ring-1 focus:ring-google-blue"
            >
              {portsAndHubs.map((ent) => (
                <option key={ent.id} value={ent.id}>
                  {ent.name} ({ent.id})
                </option>
              ))}
            </select>
          </div>

          {/* Capacity Multiplier */}
          <div>
            <div className="mb-1 flex justify-between text-xs">
              <span className="font-semibold text-light-text-secondary dark:text-dark-text-secondary">
                Remaining Capacity Multiplier
              </span>
              <span
                className={`font-mono font-bold ${
                  capacityMultiplier < 0.4
                    ? "text-google-red"
                    : capacityMultiplier < 0.7
                    ? "text-google-yellow"
                    : "text-google-green"
                }`}
              >
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
              className="w-full accent-google-blue"
            />
          </div>

          {/* Duration Days */}
          <div>
            <div className="mb-1 flex justify-between text-xs">
              <span className="font-semibold text-light-text-secondary dark:text-dark-text-secondary">
                Simulated Disruption Duration
              </span>
              <span className="font-mono font-bold text-google-blue">
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
              className="w-full accent-google-blue"
            />
          </div>

          {/* Risk Mode */}
          <div>
            <label className="mb-1 block text-xs font-semibold text-light-text-secondary dark:text-dark-text-secondary">
              Risk Mode
            </label>
            <div className="flex gap-2">
              {(["DETERMINISTIC", "EXPECTED_COST", "CVAR"] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setRiskMode(mode)}
                  className={`flex-1 rounded-lg border px-2 py-1.5 text-[10px] font-bold uppercase tracking-wide transition-colors ${
                    riskMode === mode
                      ? "border-google-blue bg-google-blue/15 text-google-blue"
                      : "border-light-border dark:border-dark-border bg-transparent text-light-text-secondary dark:text-dark-text-secondary hover:border-google-blue/40"
                  }`}
                >
                  {mode === "EXPECTED_COST" ? "EXP. COST" : mode}
                </button>
              ))}
            </div>
          </div>

          {/* Run Button */}
          <button
            type="button"
            disabled={loading}
            onClick={runWhatIf}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-google-blue px-3 py-2.5 text-xs font-bold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? (
              <>
                <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
                Running Simulation…
              </>
            ) : (
              <>
                <Play className="h-3.5 w-3.5" />
                Run Sensitivity Re-Optimization
              </>
            )}
          </button>

          {/* Error */}
          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-google-red/40 bg-google-red/10 p-3 text-xs text-google-red">
              <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}
        </section>

        {/* ── Results ── */}
        <section className="rounded-xl border border-light-border dark:border-dark-border bg-light-card dark:bg-dark-card p-4 space-y-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-light-text-secondary dark:text-dark-text-secondary">
            Baseline vs What-If Delta
          </h3>

          {!result && !loading && (
            <div className="flex h-40 flex-col items-center justify-center gap-2 text-center text-xs text-light-text-secondary dark:text-dark-text-secondary">
              <SlidersHorizontal className="h-8 w-8 opacity-20" />
              <p className="opacity-60">Configure controls and run to see sensitivity deltas</p>
            </div>
          )}

          {loading && (
            <div className="flex h-40 flex-col items-center justify-center gap-3 text-xs text-light-text-secondary dark:text-dark-text-secondary">
              <span className="h-6 w-6 animate-spin rounded-full border-2 border-google-blue border-t-transparent" />
              <p>Simulating…</p>
            </div>
          )}

          {result && !loading && (
            <div className="space-y-3">
              {/* Delta cards grid */}
              <div className="grid grid-cols-2 gap-3">
                {/* Total Cost */}
                <div className="col-span-2 rounded-lg border border-light-border dark:border-dark-border bg-light-secondary dark:bg-dark-elevated p-3">
                  <div className="text-[10px] font-bold uppercase text-light-text-secondary dark:text-dark-text-secondary mb-2">
                    Total Cost
                  </div>
                  <div className="flex items-end justify-between gap-2">
                    <div className="text-xs text-light-text-secondary dark:text-dark-text-secondary">
                      <div>Baseline</div>
                      <div className="font-mono font-bold text-light-text-primary dark:text-dark-text-primary">
                        {fmtCost(result.baseline_total_cost)}
                      </div>
                    </div>
                    <div
                      className={`text-sm font-bold font-mono ${
                        result.cost_delta > 0 ? "text-google-red" : result.cost_delta < 0 ? "text-google-green" : "text-light-text-secondary dark:text-dark-text-secondary"
                      }`}
                    >
                      {result.cost_delta >= 0 ? "▲" : "▼"} {fmtDelta(Math.abs(result.cost_delta))}
                    </div>
                    <div className="text-xs text-right text-light-text-secondary dark:text-dark-text-secondary">
                      <div>Simulated</div>
                      <div className="font-mono font-bold text-light-text-primary dark:text-dark-text-primary">
                        {fmtCost(result.simulated_total_cost)}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Unmet Demand */}
                <div className="rounded-lg border border-light-border dark:border-dark-border bg-light-secondary dark:bg-dark-elevated p-3">
                  <div className="text-[10px] font-bold uppercase text-light-text-secondary dark:text-dark-text-secondary mb-1">
                    Unmet Demand
                  </div>
                  <div
                    className={`font-mono text-sm font-bold ${
                      result.unmet_demand_delta_teu > 0 ? "text-google-red" : "text-google-green"
                    }`}
                  >
                    {fmtDelta(result.unmet_demand_delta_teu)} TEU
                  </div>
                  <div className="text-[10px] text-light-text-secondary dark:text-dark-text-secondary mt-0.5">delta vs baseline</div>
                </div>

                {/* Rail Share */}
                <div className="rounded-lg border border-light-border dark:border-dark-border bg-light-secondary dark:bg-dark-elevated p-3">
                  <div className="text-[10px] font-bold uppercase text-light-text-secondary dark:text-dark-text-secondary mb-1">
                    Rail Share Δ
                  </div>
                  <div
                    className={`font-mono text-sm font-bold ${
                      result.rail_share_delta_pct >= 0 ? "text-google-green" : "text-google-red"
                    }`}
                  >
                    {fmtDelta(result.rail_share_delta_pct)}%
                  </div>
                  <div className="text-[10px] text-light-text-secondary dark:text-dark-text-secondary mt-0.5">mode shift delta</div>
                </div>
              </div>

              {/* Verification */}
              {verif && (
                <div className="rounded-lg border border-light-border dark:border-dark-border bg-light-secondary dark:bg-dark-elevated p-3">
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-[10px] font-bold uppercase text-light-text-secondary dark:text-dark-text-secondary">
                      Verification Status
                    </div>
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${
                        verif.overall_verdict === "PASS"
                          ? "bg-google-green/10 text-google-green"
                          : verif.overall_verdict === "FAIL"
                          ? "bg-google-red/10 text-google-red"
                          : "bg-google-yellow/10 text-google-yellow"
                      }`}
                    >
                      {verif.overall_verdict}
                    </span>
                  </div>
                  <div className="space-y-1">
                    {layerChecks.map(({ label, checks }) => {
                      const worst = checks.some((c) => c.verdict === "FAIL")
                        ? "FAIL"
                        : checks.some((c) => c.verdict === "WARN")
                        ? "WARN"
                        : "PASS";
                      return (
                        <div key={label} className="flex items-center gap-2 text-xs">
                          <VerdictIcon verdict={worst as "PASS" | "FAIL" | "WARN"} />
                          <span className="font-mono font-bold text-light-text-primary dark:text-dark-text-primary w-5">{label}</span>
                          <span className="text-light-text-secondary dark:text-dark-text-secondary">
                            {checks.length} check{checks.length !== 1 ? "s" : ""} —{" "}
                            {worst}
                          </span>
                        </div>
                      );
                    })}
                    {verif.failed_checks.length > 0 && (
                      <div className="mt-1.5 text-[10px] text-google-red">
                        Failed: {verif.failed_checks.join(", ")}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
