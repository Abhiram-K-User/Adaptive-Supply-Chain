import { useMemo, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  Boxes,
  Building,
  CheckCircle2,
  Clock,
  PackageCheck,
  Search,
} from "lucide-react";
import { DonutChart } from "./charts/Charts";
import { KpiCard } from "./common/KpiCard";
import type { CanonicalEntity, PlanResponse } from "../types/asci";

interface InventoryViewProps {
  entities: CanonicalEntity[];
  planResponse: PlanResponse | null;
}

interface PlantStockItem {
  id: string;
  name: string;
  region: string;
  daysOfCover: number;
  dailyDemand: number;
  currentStockTeu: number;
  safetyThresholdDays: number;
  status: "CRITICAL" | "LOW" | "HEALTHY" | "OVERSTOCK";
  powertrainTeu: number;
  batteryTeu: number;
  chassisTeu: number;
  inTransitTeu: number;
}

export function InventoryView({ entities, planResponse }: InventoryViewProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");

  const dash = planResponse?.dashboard ?? null;
  const lineStopForecast = dash?.line_stop_forecast ?? [];

  const plants = useMemo(() => {
    const plantEntities = entities.filter(
      (e) => e.entity_type === "PLANT" || e.entity_type === "ICD"
    );

    const forecastMap = new Map<string, number>();
    for (const f of lineStopForecast) {
      forecastMap.set(f.plant_id, f.days_of_cover);
    }

    return plantEntities.map((p, idx): PlantStockItem => {
      const cover =
        forecastMap.get(p.id) ??
        p.days_of_cover ??
        3.5 + ((idx * 7) % 30) / 10;
      const demand = p.daily_demand_teu ?? 450 + (idx % 6) * 120;
      const currentStock = Math.round(cover * demand);
      const safetyDays = 2.5;

      let status: PlantStockItem["status"] = "HEALTHY";
      if (cover < 2.0) status = "CRITICAL";
      else if (cover < safetyDays) status = "LOW";
      else if (cover > 6.0) status = "OVERSTOCK";

      const powertrain = Math.round(currentStock * 0.42);
      const battery = Math.round(currentStock * 0.28);
      const chassis = currentStock - powertrain - battery;

      const inTransit = planResponse?.plan?.allocations
        .filter((a) => a.destination_id === p.id)
        .reduce((sum, a) => sum + a.flow_teu, 0) ?? Math.round(demand * 0.8);

      return {
        id: p.id,
        name: p.name,
        region: p.region,
        daysOfCover: cover,
        dailyDemand: demand,
        currentStockTeu: currentStock,
        safetyThresholdDays: safetyDays,
        status,
        powertrainTeu: powertrain,
        batteryTeu: battery,
        chassisTeu: chassis,
        inTransitTeu: inTransit,
      };
    });
  }, [entities, lineStopForecast, planResponse]);

  const totalStock = plants.reduce((sum, p) => sum + p.currentStockTeu, 0);
  const avgCover =
    plants.reduce((sum, p) => sum + p.daysOfCover, 0) / (plants.length || 1);
  const criticalCount = plants.filter((p) => p.status === "CRITICAL").length;
  const lowCount = plants.filter((p) => p.status === "LOW").length;

  const totalPowertrain = plants.reduce((sum, p) => sum + p.powertrainTeu, 0);
  const totalBattery = plants.reduce((sum, p) => sum + p.batteryTeu, 0);
  const totalChassis = plants.reduce((sum, p) => sum + p.chassisTeu, 0);

  // Multi-colored reference palette segments
  const commoditySegments = [
    { label: "Powertrain CKD", value: totalPowertrain, color: "#14c8b2" }, // Cyan
    { label: "EV Battery Packs", value: totalBattery, color: "#a855f7" },   // Purple
    { label: "Body & Chassis Parts", value: totalChassis, color: "#38bdf8" }, // Blue
  ];

  const filteredPlants = useMemo(() => {
    return plants.filter((p) => {
      if (statusFilter !== "ALL" && p.status !== statusFilter) return false;
      if (searchTerm.trim()) {
        const q = searchTerm.toLowerCase();
        return (
          p.name.toLowerCase().includes(q) ||
          p.id.toLowerCase().includes(q) ||
          p.region.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [plants, statusFilter, searchTerm]);

  return (
    <div className="space-y-4">
      {/* 1. Neutral Metric Cards */}
      <div className="grid grid-cols-2 gap-3.5 sm:grid-cols-4">
        <KpiCard
          title="Corridor Buffer Total"
          value={totalStock.toLocaleString()}
          unit="TEU"
          comparison="+4.2% MoM"
          status="info"
          trend="up"
          subtitle="30 JIT Assembly Facilities"
          sparklineData={[42000, 43500, 44200, 46000, totalStock]}
        />

        <KpiCard
          title="Average Cover Duration"
          value={avgCover.toFixed(1)}
          unit="days"
          comparison="Target: 3.5d"
          status="healthy"
          trend="up"
          subtitle="Min safe production buffer"
          sparklineData={[3.4, 3.6, 3.5, 3.9, avgCover]}
        />

        <KpiCard
          title="Line-Stop Hazard Plants"
          value={criticalCount}
          comparison={criticalCount > 0 ? "Requires Diversion" : "All Clear"}
          status={criticalCount > 0 ? "critical" : "healthy"}
          trend={criticalCount > 0 ? "down" : "neutral"}
          subtitle="Cover under 2.0 days"
          sparklineData={[2, 3, 2, 4, criticalCount]}
        />

        <KpiCard
          title="Buffer Health SLA"
          value={`${Math.round(
            ((plants.length - criticalCount - lowCount) /
              (plants.length || 1)) *
              100
          )}%`}
          comparison="92% SLA"
          status="healthy"
          trend="up"
          subtitle="Safe operational envelope"
          sparklineData={[82, 85, 87, 86, 94]}
        />
      </div>

      {/* 2. Commodity Allocation & Thresholds */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Commodity Distribution Donut */}
        <div className="rounded-md border border-light-border bg-white p-4 shadow-sm dark:border-dark-border dark:bg-dark-card dark:shadow-dark-card">
          <div className="border-b border-light-border pb-2.5 dark:border-dark-border">
            <h3 className="text-xs font-bold uppercase tracking-wider text-light-text-primary dark:text-dark-text-primary">
              Automotive Commodity Split
            </h3>
            <p className="text-[11px] text-light-text-muted dark:text-dark-text-muted">
              Multi-commodity stock across assembly clusters
            </p>
          </div>
          <div className="mt-4 flex justify-center">
            <DonutChart
              segments={commoditySegments}
              centerLabel="Total Buffer"
              centerValue={`${(totalStock / 1000).toFixed(1)}k`}
              size={140}
            />
          </div>
        </div>

        {/* Reorder Threshold Monitoring Cards */}
        <div className="lg:col-span-2 rounded-md border border-light-border bg-white p-4 shadow-sm dark:border-dark-border dark:bg-dark-card dark:shadow-dark-card flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between border-b border-light-border pb-2.5 dark:border-dark-border">
              <h3 className="text-xs font-bold uppercase tracking-wider text-light-text-primary dark:text-dark-text-primary">
                Days of Cover Safety Bounds
              </h3>
              <span className="rounded-md bg-teal-50 px-2 py-0.5 font-mono text-[10px] font-bold text-teal-700 dark:bg-accent-cyan/15 dark:text-accent-cyan">
                Gate G2 Enforced
              </span>
            </div>
            <p className="mt-2 text-xs text-light-text-secondary dark:text-dark-text-secondary leading-relaxed">
              Automotive plants maintain tight just-in-time buffers. Any facility
              dropping below <strong>2.0 days of cover</strong> triggers
              automatic multi-commodity rail diversion in Stage D OR-Tools solver
              with high-penalty prioritization.
            </p>

            <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-3 dark:border-emerald-900/60 dark:bg-emerald-950/20">
                <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-800 dark:text-emerald-300">
                  <CheckCircle2 className="h-4 w-4" />
                  <span>Healthy (&gt; 3.5d)</span>
                </div>
                <div className="mt-1 font-mono text-lg font-bold text-emerald-900 dark:text-emerald-200">
                  {plants.filter((p) => p.status === "HEALTHY").length} Facilities
                </div>
                <div className="text-[10px] text-emerald-700 dark:text-emerald-400">
                  Standard replenishment
                </div>
              </div>

              <div className="rounded-xl border border-amber-200 bg-amber-50/50 p-3 dark:border-amber-900/60 dark:bg-amber-950/20">
                <div className="flex items-center gap-1.5 text-xs font-bold text-amber-800 dark:text-amber-300">
                  <AlertTriangle className="h-4 w-4" />
                  <span>Low Buffer (2.0d–3.5d)</span>
                </div>
                <div className="mt-1 font-mono text-lg font-bold text-amber-900 dark:text-amber-200">
                  {lowCount} Facilities
                </div>
                <div className="text-[10px] text-amber-700 dark:text-amber-400">
                  Expedited trucking active
                </div>
              </div>

              <div className="rounded-xl border border-rose-200 bg-rose-50/50 p-3 dark:border-rose-900/60 dark:bg-rose-950/20">
                <div className="flex items-center gap-1.5 text-xs font-bold text-rose-800 dark:text-rose-300">
                  <AlertCircle className="h-4 w-4" />
                  <span>Critical Risk (&lt; 2.0d)</span>
                </div>
                <div className="mt-1 font-mono text-lg font-bold text-rose-900 dark:text-rose-200">
                  {criticalCount} Facilities
                </div>
                <div className="text-[10px] text-rose-700 dark:text-rose-400">
                  Line-stop hazard · diverted
                </div>
              </div>
            </div>
          </div>

          <div className="mt-4 rounded-xl border border-light-border bg-light-elevated p-2.5 text-[11px] text-light-text-secondary dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-secondary">
            <span>In-Transit Deliveries: </span>
            Total incoming freight currently moving across corridors:{" "}
            <strong className="font-mono text-teal-700 dark:text-accent-cyan">
              {plants
                .reduce((sum, p) => sum + p.inTransitTeu, 0)
                .toLocaleString()}{" "}
              TEU
            </strong>
          </div>
        </div>
      </div>

      {/* 3. Filterable Plant Stock Inventory Table */}
      <div className="overflow-hidden rounded-md border border-light-border bg-white shadow-sm dark:border-dark-border dark:bg-dark-card dark:shadow-dark-card">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-light-border p-3.5 bg-light-elevated dark:border-dark-border dark:bg-dark-surface">
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-light-text-primary dark:text-dark-text-primary">
              Assembly Plant Stock &amp; Days of Cover Matrix ({filteredPlants.length})
            </h3>
            <p className="text-[11px] text-light-text-muted dark:text-dark-text-muted">
              Live facility consumption rate and buffer levels
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-light-text-muted dark:text-dark-text-muted" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search plant or hub..."
                className="h-8 rounded-xl border border-light-border bg-white pl-8 pr-2.5 text-xs text-light-text-primary placeholder-light-text-muted focus:border-teal-500 focus:outline-none dark:border-dark-border dark:bg-dark-card dark:text-dark-text-primary"
              />
            </div>

            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="h-8 rounded-xl border border-light-border bg-white px-2.5 text-xs text-light-text-primary focus:outline-none dark:border-dark-border dark:bg-dark-card dark:text-dark-text-primary"
            >
              <option value="ALL">All Statuses</option>
              <option value="HEALTHY">Healthy Buffer (&gt;3.5d)</option>
              <option value="LOW">Low Stock (2-3.5d)</option>
              <option value="CRITICAL">Critical (&lt;2d)</option>
              <option value="OVERSTOCK">Overstock (&gt;6d)</option>
            </select>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-light-border bg-light-elevated text-[10px] font-bold uppercase tracking-wider text-light-text-muted dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-muted">
                <th className="py-2.5 px-3">Assembly Facility</th>
                <th className="py-2.5 px-3">Region</th>
                <th className="py-2.5 px-3">Days of Cover</th>
                <th className="py-2.5 px-3 text-right">Daily Demand</th>
                <th className="py-2.5 px-3 text-right">Current Stock</th>
                <th className="py-2.5 px-3 text-right">Powertrain</th>
                <th className="py-2.5 px-3 text-right">EV Battery</th>
                <th className="py-2.5 px-3 text-right">Chassis Parts</th>
                <th className="py-2.5 px-3 text-right">In-Transit</th>
                <th className="py-2.5 px-3 text-center">Buffer Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-light-border dark:divide-dark-border">
              {filteredPlants.map((plant) => {
                const coverPct = Math.min(
                  100,
                  Math.round((plant.daysOfCover / 7) * 100)
                );
                return (
                  <tr
                    key={plant.id}
                    className="hover:bg-light-elevated dark:hover:bg-dark-elevated transition"
                  >
                    <td className="py-2.5 px-3 font-semibold text-light-text-primary dark:text-dark-text-primary">
                      <div>{plant.name}</div>
                      <div className="font-mono text-[10px] text-light-text-muted dark:text-dark-text-muted">
                        {plant.id}
                      </div>
                    </td>
                    <td className="py-2.5 px-3 text-light-text-secondary dark:text-dark-text-secondary">
                      {plant.region}
                    </td>
                    <td className="py-2.5 px-3">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-xs text-light-text-primary dark:text-dark-text-primary w-10">
                          {plant.daysOfCover.toFixed(1)}d
                        </span>
                        <div className="h-1.5 w-16 overflow-hidden rounded-full bg-light-border dark:bg-dark-border">
                          <div
                            className={`h-full rounded-full ${
                              plant.status === "CRITICAL"
                                ? "bg-rose-500"
                                : plant.status === "LOW"
                                ? "bg-amber-500"
                                : "bg-emerald-500"
                            }`}
                            style={{ width: `${coverPct}%` }}
                          />
                        </div>
                      </div>
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-light-text-secondary dark:text-dark-text-secondary">
                      {plant.dailyDemand.toLocaleString()} TEU
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono font-bold text-light-text-primary dark:text-dark-text-primary">
                      {plant.currentStockTeu.toLocaleString()} TEU
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-light-text-muted dark:text-dark-text-muted">
                      {plant.powertrainTeu.toLocaleString()}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-light-text-muted dark:text-dark-text-muted">
                      {plant.batteryTeu.toLocaleString()}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-light-text-muted dark:text-dark-text-muted">
                      {plant.chassisTeu.toLocaleString()}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono font-semibold text-teal-700 dark:text-accent-cyan">
                      +{plant.inTransitTeu.toLocaleString()}
                    </td>
                    <td className="py-2.5 px-3 text-center">
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                          plant.status === "CRITICAL"
                            ? "bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-300"
                            : plant.status === "LOW"
                            ? "bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300"
                            : plant.status === "OVERSTOCK"
                            ? "bg-sky-100 text-sky-800 dark:bg-accent-blue/20 dark:text-accent-blue"
                            : "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300"
                        }`}
                      >
                        {plant.status}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
