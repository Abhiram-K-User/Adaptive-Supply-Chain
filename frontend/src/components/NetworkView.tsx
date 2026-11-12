import { useMemo, useState } from "react";
import {
  Anchor,
  ArrowRight,
  Boxes,
  Building,
  CheckCircle2,
  Filter,
  Layers,
  MapPin,
  Navigation,
  Network as NetworkIcon,
  Search,
} from "lucide-react";
import { CorridorMap } from "./CorridorMap";
import { KpiCard } from "./common/KpiCard";
import type {
  CanonicalEntity,
  NetworkEdgeSummary,
  PlanResponse,
} from "../types/asci";

interface NetworkViewProps {
  entities: CanonicalEntity[];
  baseEdges: NetworkEdgeSummary[];
  planResponse: PlanResponse | null;
  onSelectEntity?: (entity: CanonicalEntity) => void;
}

export function NetworkView({
  entities,
  baseEdges,
  planResponse,
  onSelectEntity,
}: NetworkViewProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedType, setSelectedType] = useState<string>("ALL");
  const [selectedRegion, setSelectedRegion] = useState<string>("ALL");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const dash = planResponse?.dashboard ?? null;
  const planNodes = dash?.geospatial_network?.nodes ?? [];
  const planEdges = dash?.geospatial_network?.edges ?? [];

  const entityCounts = useMemo(() => {
    const counts: Record<string, number> = { ALL: entities.length };
    for (const ent of entities) {
      counts[ent.entity_type] = (counts[ent.entity_type] || 0) + 1;
    }
    return counts;
  }, [entities]);

  const regions = useMemo(() => {
    const set = new Set<string>();
    for (const ent of entities) {
      if (ent.region) set.add(ent.region);
    }
    return ["ALL", ...Array.from(set).sort()];
  }, [entities]);

  const filteredEntities = useMemo(() => {
    return entities.filter((ent) => {
      if (selectedType !== "ALL" && ent.entity_type !== selectedType)
        return false;
      if (selectedRegion !== "ALL" && ent.region !== selectedRegion)
        return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          ent.name.toLowerCase().includes(q) ||
          ent.id.toLowerCase().includes(q) ||
          ent.region.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [entities, selectedType, selectedRegion, searchQuery]);

  const selectedEntity = useMemo(
    () => entities.find((e) => e.id === selectedNodeId) ?? null,
    [entities, selectedNodeId]
  );

  const connectedEdges = useMemo(() => {
    if (!selectedNodeId) return [];
    return baseEdges.filter(
      (e) => e.source === selectedNodeId || e.target === selectedNodeId
    );
  }, [baseEdges, selectedNodeId]);

  const roadCount = baseEdges.filter((e) => e.mode === "ROAD").length;
  const railCount = baseEdges.filter(
    (e) => e.mode.includes("RAIL") || e.mode.includes("INTERMODAL")
  ).length;

  return (
    <div className="space-y-4">
      {/* Network Header Neutral KPI Cards */}
      <div className="grid grid-cols-2 gap-3.5 sm:grid-cols-4">
        <KpiCard
          title="Topology Scale"
          value={`${entities.length} Nodes`}
          comparison={`${entityCounts["PORT"] || 0} Ports`}
          status="info"
          trend="up"
          subtitle={`${entityCounts["PLANT"] || 0} Plants • ${entityCounts["ICD"] || 0} ICDs`}
          sparklineData={[23, 42, 75, 100, entities.length]}
        />

        <KpiCard
          title="Calibrated Transit Links"
          value={`${baseEdges.length} Links`}
          comparison={`${railCount} Rail Corridors`}
          status="healthy"
          trend="up"
          subtitle={`${roadCount} Road corridors & expressways`}
          sparklineData={[42, 90, 180, 290, baseEdges.length]}
        />

        <KpiCard
          title="Gateway Capacity"
          value="29,500"
          unit="TEU/d"
          comparison="8 Maritime Ports"
          status="healthy"
          trend="up"
          subtitle="Gateways across 4 southern states"
          sparklineData={[24000, 26000, 27500, 29500]}
        />

        <KpiCard
          title="Plant JIT Demand"
          value="12,470"
          unit="TEU/d"
          comparison="30 Facilities"
          status="info"
          trend="neutral"
          subtitle="Assembly & OEM automotive clusters"
          sparklineData={[10500, 11200, 11900, 12470]}
        />
      </div>

      {/* Main Interactive Map Section */}
      <div className="overflow-hidden rounded-md border border-light-border bg-white shadow-sm dark:border-dark-border dark:bg-dark-card dark:shadow-dark-card">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-light-border px-4 py-3 bg-light-elevated dark:border-dark-border dark:bg-dark-surface">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-teal-50 text-teal-700 dark:bg-accent-cyan/15 dark:text-accent-cyan">
              <NetworkIcon className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-xs font-bold uppercase tracking-wider text-light-text-primary dark:text-dark-text-primary">
                Live Multimodal Corridor Visualization
              </h2>
              <p className="text-[11px] text-light-text-muted dark:text-dark-text-muted">
                Interactive Cytoscape.js &amp; Leaflet GIS with OSMnx calibrated transit links
              </p>
            </div>
          </div>

          <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 text-[10px] font-semibold text-emerald-800 dark:border-emerald-800/60 dark:bg-emerald-950/40 dark:text-emerald-300">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
            OSMnx Calibrated
          </span>
        </div>

        {/* Map Container */}
        <div className="p-3">
          <CorridorMap
            entities={entities}
            baseEdges={baseEdges}
            planNodes={planNodes}
            planEdges={planEdges}
          />
        </div>
      </div>

      {/* Facility Directory & Node Connectivity Details */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Left: Filterable Node Directory */}
        <div className="lg:col-span-2 overflow-hidden rounded-md border border-light-border bg-white shadow-sm dark:border-dark-border dark:bg-dark-card dark:shadow-dark-card">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-light-border p-3.5 bg-light-elevated dark:border-dark-border dark:bg-dark-surface">
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-light-text-primary dark:text-dark-text-primary">
                Corridor Facilities Directory ({filteredEntities.length})
              </h3>
              <p className="text-[11px] text-light-text-muted dark:text-dark-text-muted">
                Select any facility to inspect connectivity and throughput
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-light-text-muted dark:text-dark-text-muted" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Filter facility name..."
                  className="h-8 rounded-xl border border-light-border bg-white pl-8 pr-2.5 text-xs text-light-text-primary placeholder-light-text-muted focus:border-teal-500 focus:outline-none dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-primary"
                />
              </div>

              <select
                value={selectedType}
                onChange={(e) => setSelectedType(e.target.value)}
                className="h-8 rounded-xl border border-light-border bg-white px-2.5 text-xs text-light-text-primary focus:outline-none dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-primary"
              >
                <option value="ALL">All Types ({entities.length})</option>
                <option value="PORT">Ports ({entityCounts["PORT"] || 0})</option>
                <option value="PLANT">Plants ({entityCounts["PLANT"] || 0})</option>
                <option value="ICD">ICDs ({entityCounts["ICD"] || 0})</option>
                <option value="CFS">CFSs ({entityCounts["CFS"] || 0})</option>
                <option value="CORRIDOR_JUNCTION">Junctions ({entityCounts["CORRIDOR_JUNCTION"] || 0})</option>
              </select>

              <select
                value={selectedRegion}
                onChange={(e) => setSelectedRegion(e.target.value)}
                className="h-8 rounded-xl border border-light-border bg-white px-2.5 text-xs text-light-text-primary focus:outline-none dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-primary"
              >
                {regions.map((reg) => (
                  <option key={reg} value={reg}>
                    {reg === "ALL" ? "All Regions" : reg}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="max-h-[380px] overflow-y-auto divide-y divide-light-border dark:divide-dark-border">
            {filteredEntities.map((ent) => {
              const isSelected = selectedNodeId === ent.id;
              return (
                <div
                  key={ent.id}
                  onClick={() => {
                    setSelectedNodeId(ent.id);
                    if (onSelectEntity) onSelectEntity(ent);
                  }}
                  className={`flex items-center justify-between p-3 cursor-pointer transition ${
                    isSelected
                      ? "bg-teal-50/70 border-l-4 border-l-teal-600 dark:bg-accent-cyan/15 dark:border-l-accent-cyan"
                      : "hover:bg-light-elevated dark:hover:bg-dark-elevated"
                  }`}
                >
                  <div className="flex items-center gap-3 min-w-0 pr-2">
                    <div
                      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl text-xs font-bold ${
                        ent.entity_type === "PORT"
                          ? "bg-sky-100 text-sky-800 dark:bg-accent-blue/20 dark:text-accent-blue"
                          : ent.entity_type === "PLANT"
                          ? "bg-purple-100 text-purple-800 dark:bg-accent-purple/20 dark:text-accent-purpleGlow"
                          : ent.entity_type === "ICD"
                          ? "bg-amber-100 text-amber-800 dark:bg-accent-amber/20 dark:text-accent-amber"
                          : "bg-slate-100 text-slate-800 dark:bg-dark-elevated dark:text-dark-text-secondary"
                      }`}
                    >
                      {ent.entity_type === "PORT" && <Anchor className="h-4 w-4" />}
                      {ent.entity_type === "PLANT" && <Building className="h-4 w-4" />}
                      {ent.entity_type === "ICD" && <Boxes className="h-4 w-4" />}
                      {ent.entity_type !== "PORT" &&
                        ent.entity_type !== "PLANT" &&
                        ent.entity_type !== "ICD" && (
                          <MapPin className="h-4 w-4" />
                        )}
                    </div>

                    <div className="min-w-0 truncate">
                      <div className="font-semibold text-xs text-light-text-primary dark:text-dark-text-primary truncate">
                        {ent.name}
                      </div>
                      <div className="flex items-center gap-2 text-[10px] text-light-text-muted dark:text-dark-text-muted font-mono truncate">
                        <span>{ent.id}</span>
                        <span>•</span>
                        <span>{ent.region}</span>
                        {ent.daily_capacity_teu && (
                          <>
                            <span>•</span>
                            <span className="text-emerald-700 dark:text-accent-cyan font-medium">
                              Cap: {ent.daily_capacity_teu.toLocaleString()} TEU/d
                            </span>
                          </>
                        )}
                        {ent.daily_demand_teu && (
                          <>
                            <span>•</span>
                            <span className="text-purple-700 dark:text-accent-purpleGlow font-medium">
                              Dem: {ent.daily_demand_teu.toLocaleString()} TEU/d
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                  <span className="shrink-0 text-xs font-medium text-teal-600 dark:text-accent-cyan">
                    Inspect &rarr;
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right: Selected Node Inspection Panel */}
        <div className="rounded-md border border-light-border bg-white p-4 shadow-sm dark:border-dark-border dark:bg-dark-card dark:shadow-dark-card">
          <div className="flex items-center justify-between border-b border-light-border pb-3 dark:border-dark-border">
            <h3 className="text-xs font-bold uppercase tracking-wider text-light-text-primary dark:text-dark-text-primary">
              Facility Connectivity
            </h3>
            {selectedEntity && (
              <span className="rounded-md bg-teal-50 px-2 py-0.5 font-mono text-[10px] font-bold text-teal-700 dark:bg-accent-cyan/15 dark:text-accent-cyan">
                {selectedEntity.entity_type}
              </span>
            )}
          </div>

          {selectedEntity ? (
            <div className="mt-3 space-y-4">
              <div>
                <h4 className="text-sm font-bold text-light-text-primary dark:text-dark-text-primary">
                  {selectedEntity.name}
                </h4>
                <div className="font-mono text-[11px] text-light-text-muted dark:text-dark-text-muted">
                  ID: {selectedEntity.id}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="rounded-xl border border-light-border bg-light-elevated p-2 dark:border-dark-border dark:bg-dark-surface">
                  <div className="text-[10px] text-light-text-muted dark:text-dark-text-muted">State / Region</div>
                  <div className="font-semibold text-light-text-primary dark:text-dark-text-primary">
                    {selectedEntity.region}
                  </div>
                </div>
                <div className="rounded-xl border border-light-border bg-light-elevated p-2 dark:border-dark-border dark:bg-dark-surface">
                  <div className="text-[10px] text-light-text-muted dark:text-dark-text-muted">Coordinates</div>
                  <div className="font-mono text-[10px] text-light-text-primary dark:text-dark-text-primary">
                    {selectedEntity.latitude.toFixed(3)}°N, {selectedEntity.longitude.toFixed(3)}°E
                  </div>
                </div>

                {selectedEntity.days_of_cover !== undefined &&
                  selectedEntity.days_of_cover !== null && (
                    <div className="rounded-xl border border-light-border bg-light-elevated p-2 dark:border-dark-border dark:bg-dark-surface">
                      <div className="text-[10px] text-light-text-muted dark:text-dark-text-muted">
                        Days of Cover
                      </div>
                      <div className="font-mono font-bold text-light-text-primary dark:text-dark-text-primary">
                        {selectedEntity.days_of_cover.toFixed(1)} days
                      </div>
                    </div>
                  )}

                {selectedEntity.daily_demand_teu && (
                  <div className="rounded-xl border border-light-border bg-light-elevated p-2 dark:border-dark-border dark:bg-dark-surface">
                    <div className="text-[10px] text-light-text-muted dark:text-dark-text-muted">Daily Demand</div>
                    <div className="font-mono font-bold text-purple-700 dark:text-accent-purpleGlow">
                      {selectedEntity.daily_demand_teu.toLocaleString()} TEU
                    </div>
                  </div>
                )}
              </div>

              {/* Connected Links */}
              <div>
                <div className="text-[11px] font-bold uppercase tracking-wider text-light-text-muted dark:text-dark-text-muted mb-1.5">
                  Connected Links ({connectedEdges.length})
                </div>
                <div className="max-h-[160px] overflow-y-auto space-y-1.5">
                  {connectedEdges.map((edge) => {
                    const isOutbound = edge.source === selectedEntity.id;
                    const neighborId = isOutbound ? edge.target : edge.source;
                    const isRail = edge.mode.includes("RAIL");
                    return (
                      <div
                        key={edge.id}
                        className="flex items-center justify-between rounded-xl border border-light-border bg-light-elevated p-2 text-xs dark:border-dark-border dark:bg-dark-surface"
                      >
                        <div className="flex items-center gap-1.5 truncate">
                          {isOutbound ? (
                            <ArrowRight className="h-3 w-3 text-emerald-600 dark:text-accent-cyan shrink-0" />
                          ) : (
                            <ArrowRight className="h-3 w-3 text-sky-600 dark:text-accent-blue rotate-180 shrink-0" />
                          )}
                          <span className="font-mono text-[11px] text-light-text-primary dark:text-dark-text-primary truncate">
                            {neighborId}
                          </span>
                        </div>

                        <div className="flex items-center gap-2 shrink-0 font-mono text-[10px]">
                          <span
                            className={`rounded px-1.5 py-0.2 font-bold ${
                              isRail
                                ? "bg-purple-100 text-purple-800 dark:bg-accent-purple/20 dark:text-accent-purpleGlow"
                                : "bg-sky-100 text-sky-800 dark:bg-accent-blue/20 dark:text-accent-blue"
                            }`}
                          >
                            {edge.mode}
                          </span>
                          <span className="text-light-text-muted dark:text-dark-text-muted">
                            {edge.distance_km.toFixed(0)} km
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          ) : (
            <div className="py-12 text-center text-xs text-light-text-muted dark:text-dark-text-muted">
              Select any facility from the directory to inspect transit routes, modes, and capacity.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
