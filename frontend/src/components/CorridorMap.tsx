import { useEffect, useMemo, useRef, useState } from "react";
import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import {
  Compass,
  Eye,
  EyeOff,
  Focus,
  Globe,
  Map as MapIcon,
  Maximize2,
  Network,
} from "lucide-react";
import type {
  CanonicalEntity,
  CytoscapeEdge,
  CytoscapeNode,
  NetworkEdgeSummary,
} from "../types/asci";

interface CorridorMapProps {
  entities: CanonicalEntity[];
  baseEdges: NetworkEdgeSummary[];
  planNodes: CytoscapeNode[];
  planEdges: CytoscapeEdge[];
}

interface InspectedElement {
  kind: "node" | "edge";
  title: string;
  subtitle: string;
  details: Array<{ label: string; value: string }>;
}

type ViewMode = "india_map" | "cytoscape";
type TileStyle = "dark" | "voyager";

const MAP_SCALE = 155;

export function CorridorMap({
  entities,
  baseEdges,
  planNodes,
  planEdges,
}: CorridorMapProps) {
  const leafletContainerRef = useRef<HTMLDivElement | null>(null);
  const leafletMapRef = useRef<L.Map | null>(null);
  const baseLayerGroupRef = useRef<L.LayerGroup | null>(null);
  const overlayGroupRef = useRef<L.LayerGroup | null>(null);

  const cyContainerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);

  const [viewMode, setViewMode] = useState<ViewMode>("india_map");
  const [tileStyle, setTileStyle] = useState<TileStyle>("dark");
  const [activeOnly, setActiveOnly] = useState(true);
  const [inspected, setInspected] = useState<InspectedElement | null>(null);

  const entityById = useMemo(() => {
    const map = new Map<string, CanonicalEntity>();
    for (const ent of entities) {
      map.set(ent.id, ent);
    }
    return map;
  }, [entities]);

  const {
    filteredNodes,
    filteredEdges,
    hasFlows,
    nodeLookup,
  } = useMemo(() => {
    const hasPlanData = planNodes.length > 0 && planEdges.length > 0;
    const rawNodes: CytoscapeNode[] = hasPlanData
      ? planNodes
      : entities.map((e) => ({
          data: {
            id: e.id,
            label: e.name,
            entity_type: e.entity_type,
            lat: e.latitude,
            lon: e.longitude,
            region: e.region,
            capacity_multiplier: 1.0,
            status: "NORMAL",
          },
        }));

    const rawEdges: CytoscapeEdge[] = hasPlanData
      ? planEdges
      : baseEdges.map((edge) => ({
          data: {
            id: edge.id,
            source: edge.source,
            target: edge.target,
            mode: edge.mode,
            distance_km: edge.distance_km,
            capacity_multiplier: 1.0,
            freight_flow_teu: 0,
          },
        }));

    const lookup = new Map<string, CytoscapeNode["data"]>();
    for (const n of rawNodes) {
      lookup.set(n.data.id, n.data);
    }

    const anyActiveFlows = rawEdges.some((e) => (e.data.freight_flow_teu ?? 0) > 0);
    const keepActiveNodes = new Set<string>();

    const keptEdges = rawEdges.filter((edge) => {
      const flow = Number(edge.data.freight_flow_teu ?? 0);
      const disrupted = Number(edge.data.capacity_multiplier ?? 1) < 0.99;
      if (!activeOnly || !anyActiveFlows) {
        return true;
      }
      if (flow > 0 || disrupted) {
        keepActiveNodes.add(edge.data.source);
        keepActiveNodes.add(edge.data.target);
        return true;
      }
      return false;
    });

    const keptNodes = rawNodes.filter((node) => {
      if (!activeOnly || !anyActiveFlows) {
        return true;
      }
      return (
        keepActiveNodes.has(node.data.id) ||
        node.data.status !== "NORMAL" ||
        node.data.entity_type === "PORT"
      );
    });

    return {
      filteredNodes: keptNodes,
      filteredEdges: keptEdges,
      hasFlows: anyActiveFlows,
      nodeLookup: lookup,
    };
  }, [entities, baseEdges, planNodes, planEdges, activeOnly]);

  // ---------------------------------------------------------------------------
  // 1. Real Interactive India Map (Leaflet)
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (viewMode !== "india_map") {
      if (leafletMapRef.current) {
        leafletMapRef.current.remove();
        leafletMapRef.current = null;
        baseLayerGroupRef.current = null;
        overlayGroupRef.current = null;
      }
      return;
    }

    const container = leafletContainerRef.current;
    if (!container) return;

    if (!leafletMapRef.current) {
      const map = L.map(container, {
        center: [12.1, 78.6],
        zoom: 6,
        minZoom: 4,
        maxZoom: 14,
        zoomControl: true,
        attributionControl: true,
      });

      const baseGroup = L.layerGroup().addTo(map);
      const layerGroup = L.layerGroup().addTo(map);
      leafletMapRef.current = map;
      baseLayerGroupRef.current = baseGroup;
      overlayGroupRef.current = layerGroup;
    }

    const baseGroup = baseLayerGroupRef.current;
    if (!baseGroup) return;
    baseGroup.clearLayers();

    if (tileStyle === "dark") {
      L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        {
          maxZoom: 16,
          attribution: "Tiles &copy; Esri — Dark Gray Canvas",
        }
      ).addTo(baseGroup);
      L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
        {
          maxZoom: 16,
        }
      ).addTo(baseGroup);
    } else {
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors",
      }).addTo(baseGroup);
    }
  }, [viewMode, tileStyle]);

  // Render corridors and facility markers on Leaflet overlay group
  useEffect(() => {
    if (viewMode !== "india_map") return;
    const map = leafletMapRef.current;
    const group = overlayGroupRef.current;
    if (!map || !group) return;

    group.clearLayers();

    // Draw edges first (background links -> road flows -> rail flows)
    const sortedEdges = [...filteredEdges].sort(
      (a, b) => Number(a.data.freight_flow_teu ?? 0) - Number(b.data.freight_flow_teu ?? 0)
    );

    for (const edge of sortedEdges) {
      const src = nodeLookup.get(edge.data.source);
      const dst = nodeLookup.get(edge.data.target);
      if (!src || !dst) continue;

      const flow = Number(edge.data.freight_flow_teu ?? 0);
      const isRail = String(edge.data.mode || "").toUpperCase().includes("RAIL");
      const disrupted = Number(edge.data.capacity_multiplier ?? 1) < 0.99;

      let color = "#475569";
      let weight = 1.3;
      let opacity = 0.42;
      let dashArray: string | undefined = undefined;

      if (flow > 0) {
        color = isRail ? "#c084fc" : "#38bdf8";
        weight = Math.min(7, Math.max(2.8, 2.2 + flow / 700));
        opacity = 0.92;
        dashArray = isRail ? "7 5" : undefined;
      } else if (disrupted) {
        color = "#f59e0b";
        weight = 2.0;
        opacity = 0.72;
        dashArray = "4 4";
      }

      const line = L.polyline(
        [
          [src.lat, src.lon],
          [dst.lat, dst.lon],
        ],
        { color, weight, opacity, dashArray }
      );

      if (flow > 0 || disrupted) {
        line.bindTooltip(
          `<strong>${src.label} -&gt; ${dst.label}</strong><br/>Mode: ${edge.data.mode} · Flow: ${flow.toFixed(1)} TEU/d`,
          { sticky: true, className: "asci-map-tooltip" }
        );
      }

      line.on("click", () => {
        setInspected({
          kind: "edge",
          title: `${src.label} -> ${dst.label}`,
          subtitle: `${edge.data.source} -> ${edge.data.target} · ${edge.data.mode}`,
          details: [
            { label: "Distance", value: `${Number(edge.data.distance_km ?? 0).toFixed(1)} km` },
            {
              label: "Link Capacity",
              value: `${(Number(edge.data.capacity_multiplier ?? 1) * 100).toFixed(0)}%`,
            },
            {
              label: "Allocated Freight",
              value: `${flow.toFixed(1)} TEU/day`,
            },
          ],
        });
      });

      line.addTo(group);
    }

    // Draw nodes on top
    for (const node of filteredNodes) {
      const d = node.data;
      let fill = "#64748b";
      let radius = 4.5;
      let stroke = "#080d19";
      let strokeWeight = 1.5;

      if (d.entity_type === "PORT") {
        fill = "#38bdf8";
        radius = 7.5;
      } else if (d.entity_type === "PLANT") {
        fill = "#10b981";
        radius = 6.5;
      } else if (d.entity_type === "ICD" || d.entity_type === "CFS") {
        fill = "#a855f7";
        radius = 5.5;
      }

      if (d.status === "RESTRICTED") {
        fill = "#f59e0b";
        radius = 9;
        stroke = "#fef3c7";
        strokeWeight = 2.5;
      } else if (d.status === "DISRUPTED") {
        fill = "#ef4444";
        radius = 10.5;
        stroke = "#fee2e2";
        strokeWeight = 3;
      }

      if (d.status === "DISRUPTED" || d.status === "RESTRICTED") {
        L.circleMarker([d.lat, d.lon], {
          radius: radius + 7,
          color: fill,
          weight: 1.5,
          opacity: 0.65,
          fillColor: fill,
          fillOpacity: 0.14,
          interactive: false,
        }).addTo(group);
      }

      const marker = L.circleMarker([d.lat, d.lon], {
        radius,
        color: stroke,
        weight: strokeWeight,
        fillColor: fill,
        fillOpacity: 0.95,
      });

      marker.bindTooltip(
        `<strong>${d.label}</strong><br/>${d.entity_type} · ${d.region} · ${d.status}`,
        { direction: "top", offset: [0, -6], className: "asci-map-tooltip" }
      );

      marker.on("click", () => {
        const fullEnt = entityById.get(String(d.id));
        setInspected({
          kind: "node",
          title: String(d.label || d.id),
          subtitle: `${d.id} · ${d.entity_type} · ${d.region}`,
          details: [
            { label: "Operational Status", value: String(d.status) },
            {
              label: "Capacity Multiplier",
              value: `${(Number(d.capacity_multiplier ?? 1) * 100).toFixed(0)}%`,
            },
            {
              label: "Coordinates",
              value: `${Number(d.lat).toFixed(3)}, ${Number(d.lon).toFixed(3)}`,
            },
            ...(fullEnt?.daily_capacity_teu
              ? [{ label: "Port Capacity", value: `${fullEnt.daily_capacity_teu} TEU/d` }]
              : []),
            ...(fullEnt?.daily_demand_teu
              ? [{ label: "Plant Demand", value: `${fullEnt.daily_demand_teu} TEU/d` }]
              : []),
          ],
        });
      });

      marker.addTo(group);
    }

    if (filteredNodes.length > 0 && !hasFlows) {
      const bounds = L.latLngBounds(
        filteredNodes.map((n) => [n.data.lat, n.data.lon] as [number, number])
      );
      map.fitBounds(bounds.pad(0.14));
    }
  }, [viewMode, filteredNodes, filteredEdges, nodeLookup, entityById, hasFlows]);

  // Cleanup Leaflet on unmount
  useEffect(() => {
    return () => {
      leafletMapRef.current?.remove();
      leafletMapRef.current = null;
    };
  }, []);

  // ---------------------------------------------------------------------------
  // 2. Optional Cytoscape.js Pure Graph Topology View
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (viewMode !== "cytoscape") {
      cyRef.current?.destroy();
      cyRef.current = null;
      return;
    }

    const el = cyContainerRef.current;
    if (!el) return;

    cyRef.current?.destroy();

    const cyElements: ElementDefinition[] = [
      ...filteredNodes.map((n) => ({
        group: "nodes" as const,
        data: {
          ...n.data,
          shortLabel: n.data.label.split(" ").slice(0, 2).join(" "),
        },
        position: {
          x: (Number(n.data.lon) - 78.2) * MAP_SCALE,
          y: (11.8 - Number(n.data.lat)) * MAP_SCALE,
        },
      })),
      ...filteredEdges.map((e) => ({
        group: "edges" as const,
        data: {
          ...e.data,
          isRail: String(e.data.mode || "").toUpperCase().includes("RAIL") ? "yes" : "no",
          hasFlow: Number(e.data.freight_flow_teu ?? 0) > 0 ? "yes" : "no",
        },
      })),
    ];

    const cy = cytoscape({
      container: el,
      elements: cyElements,
      layout: { name: "preset" },
      minZoom: 0.35,
      maxZoom: 4.5,
      wheelSensitivity: 0.2,
      style: [
        {
          selector: "node",
          style: {
            label: "data(shortLabel)",
            color: "#e2e8f0",
            "font-size": 9,
            "font-weight": 600,
            "text-valign": "bottom",
            "text-margin-y": 4,
            "text-outline-width": 2,
            "text-outline-color": "#080d19",
            width: 14,
            height: 14,
            "background-color": "#64748b",
            "border-width": 1.5,
            "border-color": "#080d19",
          },
        },
        {
          selector: 'node[entity_type="PORT"]',
          style: { "background-color": "#38bdf8", width: 20, height: 20, shape: "diamond" },
        },
        {
          selector: 'node[entity_type="PLANT"]',
          style: { "background-color": "#10b981", width: 17, height: 17 },
        },
        {
          selector: 'node[entity_type="ICD"], node[entity_type="CFS"]',
          style: { "background-color": "#a855f7", width: 13, height: 13 },
        },
        {
          selector: 'node[status="RESTRICTED"]',
          style: {
            "background-color": "#f59e0b",
            width: 24,
            height: 24,
            "border-width": 2.5,
            "border-color": "#fef3c7",
          },
        },
        {
          selector: 'node[status="DISRUPTED"]',
          style: {
            "background-color": "#ef4444",
            width: 26,
            height: 26,
            "border-width": 3,
            "border-color": "#fee2e2",
          },
        },
        {
          selector: "edge",
          style: {
            width: 1.1,
            "line-color": "#334155",
            "target-arrow-color": "#334155",
            "target-arrow-shape": "triangle",
            "arrow-scale": 0.65,
            "curve-style": "bezier",
            opacity: 0.4,
          },
        },
        {
          selector: 'edge[hasFlow="yes"]',
          style: {
            width: 3.4,
            "line-color": "#38bdf8",
            "target-arrow-color": "#38bdf8",
            opacity: 0.96,
            "z-index": 20,
          },
        },
        {
          selector: 'edge[hasFlow="yes"][isRail="yes"]',
          style: {
            width: 4.0,
            "line-color": "#c084fc",
            "target-arrow-color": "#c084fc",
            "line-style": "dashed",
            opacity: 0.98,
            "z-index": 25,
          },
        },
      ],
    });

    cy.fit(undefined, 36);
    cyRef.current = cy;

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [viewMode, filteredNodes, filteredEdges]);

  // ---------------------------------------------------------------------------
  // Zoom Handlers (work across both India Map & Cytoscape Graph)
  // ---------------------------------------------------------------------------
  const zoomAllIndia = () => {
    if (viewMode === "india_map" && leafletMapRef.current) {
      leafletMapRef.current.setView([20.5, 79.0], 4.5);
    } else {
      cyRef.current?.fit(undefined, 36);
    }
  };

  const zoomSouthCorridor = () => {
    if (viewMode === "india_map" && leafletMapRef.current) {
      if (filteredNodes.length > 0) {
        const bounds = L.latLngBounds(
          filteredNodes.map((n) => [n.data.lat, n.data.lon] as [number, number])
        );
        leafletMapRef.current.fitBounds(bounds.pad(0.14));
      } else {
        leafletMapRef.current.setView([12.1, 78.6], 6);
      }
    } else {
      cyRef.current?.fit(undefined, 36);
    }
  };

  const zoomChennaiHub = () => {
    if (viewMode === "india_map" && leafletMapRef.current) {
      leafletMapRef.current.setView([13.08, 80.05], 9.5);
    } else if (cyRef.current) {
      const targets = cyRef.current.nodes().filter((n) => {
        const id = String(n.data("id") || "");
        return (
          id.includes("CHENNAI") ||
          id.includes("KAMARAJAR") ||
          id.includes("SRIPERUMBUDUR") ||
          id.includes("ORAGADAM")
        );
      });
      cyRef.current.fit(targets.length > 0 ? targets : undefined, 48);
    }
  };

  const zoomDisrupted = () => {
    const affected = filteredNodes.filter((n) => n.data.status !== "NORMAL");
    if (viewMode === "india_map" && leafletMapRef.current) {
      if (affected.length > 0) {
        const bounds = L.latLngBounds(
          affected.map((n) => [n.data.lat, n.data.lon] as [number, number])
        );
        leafletMapRef.current.fitBounds(bounds.pad(0.4), { maxZoom: 9 });
      } else {
        zoomSouthCorridor();
      }
    } else if (cyRef.current) {
      const targets = cyRef.current.nodes('[status != "NORMAL"]');
      cyRef.current.fit(targets.length > 0 ? targets : undefined, 72);
    }
  };

  return (
    <section className="rounded-xl border border-line bg-panel shadow-lg shadow-black/25">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2.5">
        <div className="flex items-center gap-2">
          <Compass className="h-4 w-4 text-sky-400" />
          <h2 className="text-xs font-bold uppercase tracking-wider text-sky-300">
            India Corridor Geospatial Map & Reallocated Flows
          </h2>
          <span className="rounded-full bg-panel2 px-2 py-0.5 text-[11px] font-medium text-slate-300">
            {filteredNodes.length} nodes · {filteredEdges.length} links
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {/* Map vs Cytoscape View Switcher */}
          <div className="inline-flex rounded-md border border-line bg-[#090f1d] p-0.5">
            <button
              type="button"
              onClick={() => setViewMode("india_map")}
              className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-[11px] font-semibold transition ${
                viewMode === "india_map"
                  ? "bg-sky-500/20 text-sky-300"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              <MapIcon className="h-3 w-3" />
              India Map
            </button>
            <button
              type="button"
              onClick={() => setViewMode("cytoscape")}
              className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-[11px] font-semibold transition ${
                viewMode === "cytoscape"
                  ? "bg-sky-500/20 text-sky-300"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              <Network className="h-3 w-3" />
              Graph
            </button>
          </div>

          {viewMode === "india_map" && (
            <button
              type="button"
              onClick={() =>
                setTileStyle((prev) => (prev === "dark" ? "voyager" : "dark"))
              }
              className="rounded-md border border-line bg-panel2 px-2 py-1 text-[11px] font-semibold text-slate-200 hover:border-sky-400/50"
            >
              {tileStyle === "dark" ? "Dark Tiles" : "Street Tiles"}
            </button>
          )}

          {hasFlows && (
            <button
              type="button"
              onClick={() => setActiveOnly((prev) => !prev)}
              className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-semibold transition ${
                activeOnly
                  ? "border-sky-400/50 bg-sky-500/15 text-sky-300"
                  : "border-line bg-panel2 text-slate-300 hover:text-white"
              }`}
            >
              {activeOnly ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}
              {activeOnly ? "Active Only" : "All Links"}
            </button>
          )}

          <button
            type="button"
            onClick={zoomAllIndia}
            className="inline-flex items-center gap-1 rounded-md border border-line bg-panel2 px-2 py-1 text-[11px] font-semibold text-slate-200 hover:border-sky-400/50"
          >
            <Globe className="h-3 w-3 text-sky-400" />
            All India
          </button>
          <button
            type="button"
            onClick={zoomSouthCorridor}
            className="inline-flex items-center gap-1 rounded-md border border-line bg-panel2 px-2 py-1 text-[11px] font-semibold text-slate-200 hover:border-sky-400/50"
          >
            <Maximize2 className="h-3 w-3" />
            South India
          </button>
          <button
            type="button"
            onClick={zoomChennaiHub}
            className="inline-flex items-center gap-1 rounded-md border border-line bg-panel2 px-2 py-1 text-[11px] font-semibold text-slate-200 hover:border-sky-400/50"
          >
            Chennai Hub
          </button>
          <button
            type="button"
            onClick={zoomDisrupted}
            className="inline-flex items-center gap-1 rounded-md border border-line bg-panel2 px-2 py-1 text-[11px] font-semibold text-slate-200 hover:border-red-400/50"
          >
            <Focus className="h-3 w-3 text-red-400" />
            Disrupted
          </button>
        </div>
      </div>

      <div className="relative">
        {viewMode === "india_map" ? (
          <div ref={leafletContainerRef} className="z-10 h-[430px] w-full" />
        ) : (
          <div
            ref={cyContainerRef}
            className="h-[430px] w-full bg-[radial-gradient(circle_at_top,#14203b_0%,#070c17_75%)]"
          />
        )}

        {inspected && (
          <div className="absolute bottom-3 right-3 z-[450] w-72 rounded-lg border border-sky-400/40 bg-panel/95 p-3 shadow-xl backdrop-blur">
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="text-[10px] font-bold uppercase tracking-wider text-sky-400">
                  {inspected.kind === "node" ? "Facility Node" : "Corridor Link"}
                </div>
                <div className="text-xs font-bold text-white">{inspected.title}</div>
                <div className="font-mono text-[10px] text-slate-400">{inspected.subtitle}</div>
              </div>
              <button
                type="button"
                onClick={() => setInspected(null)}
                className="rounded px-1.5 py-0.5 text-xs text-slate-400 hover:bg-panel2 hover:text-white"
              >
                x
              </button>
            </div>
            <div className="mt-2 space-y-1 border-t border-line pt-2">
              {inspected.details.map((row) => (
                <div key={row.label} className="flex justify-between gap-2 text-[11px]">
                  <span className="text-slate-400">{row.label}</span>
                  <span className="font-mono font-semibold text-slate-100">{row.value}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-line bg-[#0a1122] px-4 py-2 text-[11px] text-slate-300">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-sky-400" /> Port
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" /> Assembly Plant
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-purple-500" /> ICD / CFS
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-amber-500" /> Restricted (&lt;90%)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-red-500" /> Disrupted (&lt;50%)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-0.5 w-4 bg-sky-400" /> Road Flow
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-0.5 w-4 border-t-2 border-dashed border-purple-400" /> Intermodal Rail Flow
        </span>
        <span className="ml-auto text-[10px] text-slate-500">Click any marker or route to inspect</span>
      </div>
    </section>
  );
}
