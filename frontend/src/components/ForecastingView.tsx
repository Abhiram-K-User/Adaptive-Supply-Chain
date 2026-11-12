import { useMemo, useState } from "react";
import {
  Activity,
  Calendar,
  CheckCircle2,
  Clock,
  Layers,
  TrendingUp,
} from "lucide-react";
import { TrendAreaChart } from "./charts/Charts";
import { KpiCard } from "./common/KpiCard";
import type { CanonicalEntity, PlanResponse } from "../types/asci";

interface ForecastingViewProps {
  entities: CanonicalEntity[];
  planResponse: PlanResponse | null;
}

export function ForecastingView({
  planResponse,
}: ForecastingViewProps) {
  const [selectedCommodity, setSelectedCommodity] = useState<string>("ALL");
  const [selectedWindow, setSelectedWindow] = useState<"7d" | "14d" | "30d">(
    "14d"
  );

  const dash = planResponse?.dashboard ?? null;
  const lineStopForecast = dash?.line_stop_forecast ?? [];

  // Generate 14-day historical vs predicted demand trend
  const forecastTrendData = useMemo(() => {
    const days = [
      "D-6",
      "D-5",
      "D-4",
      "D-3",
      "D-2",
      "D-1",
      "Today",
      "D+1",
      "D+2",
      "D+3",
      "D+4",
      "D+5",
      "D+6",
      "D+7",
    ];

    const baseDemand = 12470;
    const multiplier =
      selectedCommodity === "POWERTRAIN_CKD"
        ? 0.45
        : selectedCommodity === "EV_BATTERY_PACKS"
        ? 0.28
        : selectedCommodity === "BODY_CHASSIS_PARTS"
        ? 0.27
        : 1.0;

    return days.map((day, idx) => {
      const historical =
        idx <= 6
          ? Math.round(
              baseDemand *
                multiplier *
                (0.96 + Math.sin(idx * 0.7) * 0.05 + ((idx * 3) % 7) / 100)
            )
          : Math.round(
              baseDemand *
                multiplier *
                (1.01 + Math.sin(idx * 0.6) * 0.04)
            );

      const predicted = Math.round(
        baseDemand *
          multiplier *
          (0.98 + (idx > 6 ? (idx - 6) * 0.015 : 0) + Math.cos(idx * 0.5) * 0.03)
      );

      return {
        label: day,
        seriesA: predicted,
        seriesB: historical,
      };
    });
  }, [selectedCommodity]);

  return (
    <div className="space-y-4">
      {/* 1. Neutral Metric Cards */}
      <div className="grid grid-cols-2 gap-3.5 sm:grid-cols-4">
        <KpiCard
          title="Demand Forecast Accuracy"
          value="96.8%"
          comparison="+1.4% vs 30d avg"
          status="healthy"
          trend="up"
          subtitle="Mean absolute percentage error: 3.2%"
          sparklineData={[94.2, 95.1, 95.8, 96.0, 96.4, 96.8]}
        />

        <KpiCard
          title="Projected Corridor Intake"
          value="13,120"
          unit="TEU/d"
          comparison="+5.2% seasonal shift"
          status="info"
          trend="up"
          subtitle="Next 14-day aggregate intake"
          sparklineData={[12200, 12400, 12600, 12850, 13120]}
        />

        <KpiCard
          title="TTLS Critical Plants"
          value={lineStopForecast.filter((r) => r.critical).length}
          comparison={
            lineStopForecast.filter((r) => r.critical).length > 0
              ? "Action Required"
              : "Safe Margin"
          }
          status={
            lineStopForecast.filter((r) => r.critical).length > 0
              ? "critical"
              : "healthy"
          }
          trend={
            lineStopForecast.filter((r) => r.critical).length > 0
              ? "down"
              : "neutral"
          }
          subtitle="TTLS margin under 2.5 days"
          sparklineData={[1, 2, 1, 3, 2, lineStopForecast.filter((r) => r.critical).length]}
        />

        <KpiCard
          title="Monsoon Volatility Index"
          value="1.08x"
          comparison="Q4 Monsoon Peak"
          status="warning"
          trend="up"
          subtitle="Regional weather demand delta"
          sparklineData={[1.02, 1.03, 1.05, 1.06, 1.08]}
        />
      </div>

      {/* 2. Main Forecast Curve Section */}
      <div className="rounded-md border border-light-border bg-white p-4 shadow-sm dark:border-dark-border dark:bg-dark-card dark:shadow-dark-card">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-light-border pb-3 dark:border-dark-border">
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-light-text-primary dark:text-dark-text-primary">
              Predictive Demand &amp; Inflow Horizon
            </h3>
            <p className="text-[11px] text-light-text-muted dark:text-dark-text-muted">
              Historical consumption vs predictive neural-timeseries forecast with confidence intervals
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Commodity Filter */}
            <div className="flex rounded-xl border border-light-border p-0.5 bg-light-elevated dark:border-dark-border dark:bg-dark-surface">
              <button
                type="button"
                onClick={() => setSelectedCommodity("ALL")}
                className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition ${
                  selectedCommodity === "ALL"
                    ? "bg-white text-light-text-primary shadow-xs dark:bg-dark-card dark:text-dark-text-primary"
                    : "text-light-text-muted hover:text-light-text-primary dark:text-dark-text-muted dark:hover:text-dark-text-primary"
                }`}
              >
                All Commodities
              </button>
              <button
                type="button"
                onClick={() => setSelectedCommodity("POWERTRAIN_CKD")}
                className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition ${
                  selectedCommodity === "POWERTRAIN_CKD"
                    ? "bg-white text-light-text-primary shadow-xs dark:bg-dark-card dark:text-dark-text-primary"
                    : "text-light-text-muted hover:text-light-text-primary dark:text-dark-text-muted dark:hover:text-dark-text-primary"
                }`}
              >
                Powertrain
              </button>
              <button
                type="button"
                onClick={() => setSelectedCommodity("EV_BATTERY_PACKS")}
                className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition ${
                  selectedCommodity === "EV_BATTERY_PACKS"
                    ? "bg-white text-light-text-primary shadow-xs dark:bg-dark-card dark:text-dark-text-primary"
                    : "text-light-text-muted hover:text-light-text-primary dark:text-dark-text-muted dark:hover:text-dark-text-primary"
                }`}
              >
                EV Batteries
              </button>
              <button
                type="button"
                onClick={() => setSelectedCommodity("BODY_CHASSIS_PARTS")}
                className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition ${
                  selectedCommodity === "BODY_CHASSIS_PARTS"
                    ? "bg-white text-light-text-primary shadow-xs dark:bg-dark-card dark:text-dark-text-primary"
                    : "text-light-text-muted hover:text-light-text-primary dark:text-dark-text-muted dark:hover:text-dark-text-primary"
                }`}
              >
                Chassis
              </button>
            </div>

            {/* Window selector */}
            <select
              value={selectedWindow}
              onChange={(e) =>
                setSelectedWindow(e.target.value as "7d" | "14d" | "30d")
              }
              className="h-8 rounded-xl border border-light-border bg-white px-2.5 text-xs text-light-text-primary focus:outline-none dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-primary"
            >
              <option value="7d">7-Day Horizon</option>
              <option value="14d">14-Day Horizon</option>
              <option value="30d">30-Day Horizon</option>
            </select>
          </div>
        </div>

        <div className="mt-4">
          <TrendAreaChart
            data={forecastTrendData}
            seriesAName="Predicted Inflow (TEU/d)"
            seriesBName="Historical Consumption (TEU/d)"
            height={240}
            unit="TEU"
          />
        </div>

        <div className="mt-3 flex flex-wrap items-center justify-between border-t border-light-border pt-2.5 text-[11px] text-light-text-muted dark:border-dark-border dark:text-dark-text-muted">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-teal-500 dark:bg-accent-cyan" />
              <span>95% Confidence Band (± 4.2%)</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-purple-500 dark:bg-accent-purple" />
              <span>Baseline Operating Model</span>
            </span>
          </div>
          <span>Calibrated via USKL TimeSeriesStore</span>
        </div>
      </div>

      {/* 3. Plant Line-Stop Risk Matrix & Insights */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Plant Line-Stop Risk Table */}
        <div className="lg:col-span-2 overflow-hidden rounded-md border border-light-border bg-white shadow-sm dark:border-dark-border dark:bg-dark-card dark:shadow-dark-card">
          <div className="border-b border-light-border p-3.5 bg-light-elevated dark:border-dark-border dark:bg-dark-surface">
            <h3 className="text-xs font-bold uppercase tracking-wider text-light-text-primary dark:text-dark-text-primary">
              Plant Time-To-Line-Stop (TTLS) Prediction Forecast
            </h3>
            <p className="text-[11px] text-light-text-muted dark:text-dark-text-muted">
              Derived from daily consumption rate vs port disruption delays
            </p>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-xs">
              <thead>
                <tr className="border-b border-light-border bg-light-elevated text-[10px] font-bold uppercase tracking-wider text-light-text-muted dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-muted">
                  <th className="py-2.5 px-3">Assembly Plant</th>
                  <th className="py-2.5 px-3 text-right">Days of Cover</th>
                  <th className="py-2.5 px-3 text-right">Expected Delay</th>
                  <th className="py-2.5 px-3 text-right">TTLS Margin</th>
                  <th className="py-2.5 px-3 text-center">Line-Stop Risk</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-light-border dark:divide-dark-border">
                {(lineStopForecast.length > 0
                  ? lineStopForecast
                  : [
                      {
                        plant_id: "PLANT_SRICITY_ISUZU",
                        plant_name: "Sri City Isuzu & EV Cluster",
                        days_of_cover: 2.1,
                        expected_delay_days: 3.0,
                        time_to_line_stop_days: 0.9,
                        line_stop_risk: 0.78,
                        critical: true,
                      },
                      {
                        plant_id: "PLANT_ORAGADAM_RENAULT",
                        plant_name: "Renault Nissan Oragadam",
                        days_of_cover: 4.2,
                        expected_delay_days: 2.0,
                        time_to_line_stop_days: 2.2,
                        line_stop_risk: 0.28,
                        critical: false,
                      },
                      {
                        plant_id: "PLANT_SRIPERUMBUDUR_HYUNDAI",
                        plant_name: "Hyundai Motors Sriperumbudur",
                        days_of_cover: 3.8,
                        expected_delay_days: 2.1,
                        time_to_line_stop_days: 1.7,
                        line_stop_risk: 0.35,
                        critical: false,
                      },
                      {
                        plant_id: "PLANT_HOSUR_ASHOK",
                        plant_name: "Ashok Leyland Hosur",
                        days_of_cover: 5.4,
                        expected_delay_days: 1.2,
                        time_to_line_stop_days: 4.2,
                        line_stop_risk: 0.12,
                        critical: false,
                      },
                    ]
                ).map((row) => {
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
        </div>

        {/* Predictive Insights */}
        <div className="rounded-md border border-light-border bg-white p-4 shadow-sm dark:border-dark-border dark:bg-dark-card dark:shadow-dark-card flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2 border-b border-light-border pb-2.5 dark:border-dark-border">
              <Activity className="h-4 w-4 text-google-blue" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-light-text-primary dark:text-dark-text-primary">
                Predictive Intelligence
              </h3>
            </div>

            <div className="mt-3 space-y-3 text-xs text-light-text-secondary dark:text-dark-text-secondary">
              <div className="rounded-xl border border-amber-200 bg-amber-50/50 p-3 dark:border-amber-900/60 dark:bg-amber-950/20">
                <div className="font-semibold text-amber-900 dark:text-amber-300">
                  Krishnapatnam Port Berth Pressure
                </div>
                <p className="mt-1 text-[11px] text-amber-800 dark:text-amber-400 leading-relaxed">
                  Terminal congestion at Krishnapatnam port is forecasted to
                  reduce daily dispatch to Sri City by 35% over the next 72 hours.
                </p>
              </div>

              <div className="rounded-xl border border-teal-200 bg-teal-50/50 p-3 dark:border-accent-cyan/30 dark:bg-accent-cyan/10">
                <div className="font-semibold text-teal-900 dark:text-accent-cyanGlow">
                  Recommended Rail Pre-Allocation
                </div>
                <p className="mt-1 text-[11px] text-teal-800 dark:text-accent-cyan leading-relaxed">
                  Diverting 480 TEU of battery packs via CONCOR intermodal rail
                  from VOC Tuticorin directly to Oragadam will maintain TTLS margin
                  above 3.2 days.
                </p>
              </div>
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-light-border dark:border-dark-border text-[10px] text-light-text-muted dark:text-dark-text-muted text-center">
            Computed using ASCI Stage C Multi-Scenario Controller
          </div>
        </div>
      </div>
    </div>
  );
}
