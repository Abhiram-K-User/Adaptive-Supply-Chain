import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Boxes,
  Building2,
  Cpu,
  FileText,
  LayoutDashboard,
  MapPin,
  Network,
  Search,
  TrendingUp,
  X,
} from "lucide-react";
import type {
  ActiveWorkspaceTab,
  CanonicalEntity,
  DisruptionEvent,
} from "../../types/asci";

interface GlobalSearchModalProps {
  isOpen: boolean;
  onClose: () => void;
  entities: CanonicalEntity[];
  events: DisruptionEvent[];
  onSelectTab: (tab: ActiveWorkspaceTab) => void;
  onSelectEntity?: (entity: CanonicalEntity) => void;
  onSelectEvent?: (eventId: string) => void;
}

export function GlobalSearchModal({
  isOpen,
  onClose,
  entities,
  events,
  onSelectTab,
  onSelectEntity,
  onSelectEvent,
}: GlobalSearchModalProps) {
  const [searchTerm, setSearchTerm] = useState("");

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        onClose();
      }
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  const filteredEntities = useMemo(() => {
    if (!searchTerm.trim()) return entities.slice(0, 6);
    const q = searchTerm.toLowerCase();
    return entities
      .filter(
        (e) =>
          e.name.toLowerCase().includes(q) ||
          e.id.toLowerCase().includes(q) ||
          e.region.toLowerCase().includes(q) ||
          e.entity_type.toLowerCase().includes(q)
      )
      .slice(0, 8);
  }, [entities, searchTerm]);

  const filteredEvents = useMemo(() => {
    if (!searchTerm.trim()) return events.slice(0, 4);
    const q = searchTerm.toLowerCase();
    return events
      .filter(
        (ev) =>
          ev.raw_headline.toLowerCase().includes(q) ||
          ev.event_id.toLowerCase().includes(q) ||
          ev.event_type.toLowerCase().includes(q) ||
          ev.primary_entity_id.toLowerCase().includes(q)
      )
      .slice(0, 6);
  }, [events, searchTerm]);

  const navPages: Array<{
    id: ActiveWorkspaceTab;
    name: string;
    category: string;
    icon: typeof LayoutDashboard;
  }> = [
    { id: "overview", name: "Overview Command Center", category: "Operations", icon: LayoutDashboard },
    { id: "network", name: "Supply Chain Network", category: "Operations", icon: Network },
    { id: "inventory", name: "Inventory Management", category: "Operations", icon: Boxes },
    { id: "forecasting", name: "Demand Forecasting", category: "Intelligence", icon: TrendingUp },
    { id: "suppliers", name: "Supplier & Port Intelligence", category: "Intelligence", icon: Building2 },
    { id: "risk", name: "Risk & Disruptions", category: "Intelligence", icon: AlertTriangle },
    { id: "optimization", name: "Optimization Engine", category: "Decision Engine", icon: Cpu },
    { id: "analytics", name: "Analytics & Reports", category: "Decision Engine", icon: FileText },
  ];

  const filteredPages = useMemo(() => {
    if (!searchTerm.trim()) return navPages.slice(0, 4);
    const q = searchTerm.toLowerCase();
    return navPages.filter(
      (p) =>
        p.name.toLowerCase().includes(q) || p.category.toLowerCase().includes(q)
    );
  }, [searchTerm]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4 pt-20 backdrop-blur-sm animate-fade-in">
      <div
        className="w-full max-w-2xl overflow-hidden rounded-md border border-light-border bg-white dark:border-dark-border dark:bg-dark-card shadow-2xl transition-all"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search Input Bar */}
        <div className="flex items-center border-b border-light-border dark:border-dark-border px-4 py-3 bg-light-elevated dark:bg-dark-surface">
          <Search className="h-4 w-4 text-light-text-muted dark:text-dark-text-muted shrink-0" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search ports, plants, active events, navigation..."
            autoFocus
            className="flex-1 border-0 bg-transparent px-3 text-sm text-light-text-primary dark:text-dark-text-primary placeholder-light-text-muted dark:placeholder-dark-text-muted focus:outline-none"
          />
          {searchTerm && (
            <button
              type="button"
              onClick={() => setSearchTerm("")}
              className="mr-2 text-xs text-light-text-muted hover:text-light-text-primary dark:text-dark-text-muted dark:hover:text-dark-text-primary"
            >
              Clear
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-light-text-muted hover:bg-light-hover hover:text-light-text-primary dark:text-dark-text-muted dark:hover:bg-dark-elevated dark:hover:text-dark-text-primary"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Results Container */}
        <div className="max-h-[460px] overflow-y-auto p-3.5 space-y-4">
          {/* Navigation Pages */}
          {filteredPages.length > 0 && (
            <div>
              <div className="px-2 pb-1.5 text-[10px] font-bold uppercase tracking-wider text-light-text-muted dark:text-dark-text-muted">
                Application Modules
              </div>
              <div className="space-y-1">
                {filteredPages.map((page) => {
                  const Icon = page.icon;
                  return (
                    <button
                      key={page.id}
                      type="button"
                      onClick={() => {
                        onSelectTab(page.id);
                        onClose();
                      }}
                      className="flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-xs hover:bg-light-hover dark:hover:bg-dark-elevated transition group"
                    >
                      <div className="flex items-center gap-2.5">
                        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-light-elevated border border-light-border text-light-text-secondary dark:bg-dark-surface dark:border-dark-border dark:text-dark-text-secondary group-hover:text-teal-600 dark:group-hover:text-accent-cyan">
                          <Icon className="h-3.5 w-3.5" />
                        </div>
                        <div>
                          <div className="font-semibold text-light-text-primary dark:text-dark-text-primary">
                            {page.name}
                          </div>
                          <div className="text-[10px] text-light-text-muted dark:text-dark-text-muted">
                            {page.category}
                          </div>
                        </div>
                      </div>
                      <span className="text-[10px] font-medium text-teal-600 dark:text-accent-cyan opacity-0 group-hover:opacity-100 transition">
                        Jump &rarr;
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Canonical Entities */}
          {filteredEntities.length > 0 && (
            <div>
              <div className="px-2 pb-1.5 text-[10px] font-bold uppercase tracking-wider text-light-text-muted dark:text-dark-text-muted">
                Supply Chain Facilities ({entities.length} total)
              </div>
              <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                {filteredEntities.map((ent) => (
                  <button
                    key={ent.id}
                    type="button"
                    onClick={() => {
                      if (onSelectEntity) onSelectEntity(ent);
                      onSelectTab("network");
                      onClose();
                    }}
                    className="flex items-start gap-2.5 rounded-xl border border-light-border bg-light-elevated p-2.5 text-left hover:border-teal-400 hover:bg-white dark:border-dark-border dark:bg-dark-surface dark:hover:border-accent-cyan/60 dark:hover:bg-dark-elevated transition"
                  >
                    <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-teal-50 text-teal-700 dark:bg-accent-cyan/20 dark:text-accent-cyan">
                      <MapPin className="h-3.5 w-3.5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-xs font-semibold text-light-text-primary dark:text-dark-text-primary">
                        {ent.name}
                      </div>
                      <div className="flex items-center gap-2 font-mono text-[10px] text-light-text-muted dark:text-dark-text-muted">
                        <span className="rounded bg-light-border dark:bg-dark-border px-1 text-[9px] font-bold text-light-text-secondary dark:text-dark-text-secondary">
                          {ent.entity_type}
                        </span>
                        <span className="truncate">{ent.region}</span>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Disruption Events */}
          {filteredEvents.length > 0 && (
            <div>
              <div className="px-2 pb-1.5 text-[10px] font-bold uppercase tracking-wider text-light-text-muted dark:text-dark-text-muted">
                Active Incidents ({events.length})
              </div>
              <div className="space-y-1.5">
                {filteredEvents.map((ev) => (
                  <button
                    key={ev.event_id}
                    type="button"
                    onClick={() => {
                      if (onSelectEvent) onSelectEvent(ev.event_id);
                      onSelectTab("risk");
                      onClose();
                    }}
                    className="flex w-full items-start justify-between rounded-xl border border-light-border bg-white p-2.5 text-left hover:border-amber-400 dark:border-dark-border dark:bg-dark-surface dark:hover:border-amber-500/60 transition"
                  >
                    <div className="flex items-start gap-2.5">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
                      <div>
                        <div className="text-xs font-semibold text-light-text-primary dark:text-dark-text-primary line-clamp-1">
                          {ev.raw_headline}
                        </div>
                        <div className="mt-0.5 flex items-center gap-2 text-[10px] text-light-text-muted dark:text-dark-text-muted font-mono">
                          <span>{ev.event_id}</span>
                          <span>•</span>
                          <span>Target: {ev.primary_entity_id}</span>
                          <span>•</span>
                          <span className="font-semibold text-amber-600 dark:text-amber-400">
                            Severity {Math.round(ev.severity * 100)}%
                          </span>
                        </div>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-between border-t border-light-border bg-light-elevated px-4 py-2 text-[11px] text-light-text-muted dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-muted">
          <span>Press ESC to exit</span>
          <span className="font-mono text-[10px]">ASCI Knowledge Index</span>
        </div>
      </div>
    </div>
  );
}

