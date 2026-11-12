import {
  Boxes,
  Building2,
  ChevronLeft,
  ChevronRight,
  LayoutDashboard,
  Network,
  ShieldAlert,
  SlidersHorizontal,
  TrendingUp,
  BarChart3,
} from "lucide-react";
import { BrandLogo } from "../common/BrandLogo";
import type { ActiveWorkspaceTab, HealthResponse } from "../../types/asci";

interface SidebarProps {
  activeTab: ActiveWorkspaceTab;
  onSelectTab: (tab: ActiveWorkspaceTab) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
  health: HealthResponse | null;
  nodeCount: number;
  edgeCount: number;
  disruptionCount: number;
}

interface NavItem {
  id: ActiveWorkspaceTab;
  label: string;
  icon: typeof LayoutDashboard;
  badge?: string | number;
  badgeTone?: "green" | "yellow" | "red" | "blue" | "neutral";
}

interface NavGroup {
  group: string;
  items: NavItem[];
}

export function Sidebar({
  activeTab,
  onSelectTab,
  collapsed,
  onToggleCollapse,
  health,
  nodeCount,
  edgeCount,
  disruptionCount,
}: SidebarProps) {
  const normalizedActive =
    activeTab === "command"
      ? "overview"
      : activeTab === "evidence" || activeTab === "trace"
      ? "analytics"
      : activeTab === "whatif"
      ? "optimization"
      : activeTab === "outcomes"
      ? "forecasting"
      : activeTab;

  const navGroups: NavGroup[] = [
    {
      group: "Operations",
      items: [
        { id: "overview", label: "Overview", icon: LayoutDashboard },
        {
          id: "network",
          label: "Supply Chain Network",
          icon: Network,
          badge: nodeCount > 0 ? `${nodeCount}n` : undefined,
          badgeTone: "neutral",
        },
        {
          id: "inventory",
          label: "Inventory Management",
          icon: Boxes,
        },
      ],
    },
    {
      group: "Intelligence",
      items: [
        {
          id: "forecasting",
          label: "Demand Forecasting",
          icon: TrendingUp,
        },
        {
          id: "suppliers",
          label: "Supplier Intelligence",
          icon: Building2,
        },
        {
          id: "risk",
          label: "Risk & Disruptions",
          icon: ShieldAlert,
          badge: disruptionCount > 0 ? disruptionCount : undefined,
          badgeTone: disruptionCount > 0 ? "red" : "neutral",
        },
      ],
    },
    {
      group: "Decision & Reports",
      items: [
        {
          id: "optimization",
          label: "Optimization Engine",
          icon: SlidersHorizontal,
        },
        {
          id: "analytics",
          label: "Analytics & Reports",
          icon: BarChart3,
        },
      ],
    },
  ];

  return (
    <aside
      className={`h-screen sticky top-0 flex flex-col border-r select-none border-light-border bg-light-sidebar dark:border-dark-border dark:bg-dark-sidebar transition-[width] duration-200 z-30 ${
        collapsed ? "w-[76px]" : "w-[260px]"
      }`}
    >
      {/* 1. Header with Unified ASCI Brand Identity */}
      <div className="flex h-16 items-center justify-between border-b border-light-border px-3.5 dark:border-dark-border">
        <BrandLogo collapsed={collapsed} />

        <button
          type="button"
          onClick={onToggleCollapse}
          className="flex h-7 w-7 items-center justify-center rounded border border-light-border bg-light-secondary text-light-text-muted hover:text-light-text-primary dark:border-dark-border dark:bg-dark-elevated dark:text-dark-text-muted dark:hover:text-dark-text-primary transition"
          title={collapsed ? "Expand sidebar (260px)" : "Collapse sidebar (76px)"}
        >
          {collapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronLeft className="h-4 w-4" />
          )}
        </button>
      </div>

      {/* 2. Topology Status Indicator */}
      {!collapsed && (
        <div className="mx-3 mt-3 overflow-hidden rounded-lg border border-light-border bg-light-secondary/70 p-2.5 dark:border-dark-border dark:bg-dark-elevated/70">
          <div className="flex min-w-0 items-center justify-between text-xs">
            <span className="flex min-w-0 items-center gap-1.5 font-semibold text-light-text-secondary dark:text-dark-text-secondary">
              <span className="h-2 w-2 shrink-0 rounded-full bg-google-green" />
              <span className="truncate">Corridor Network</span>
            </span>
            <span className="ml-1 shrink-0 rounded bg-blue-50 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-google-blue dark:bg-blue-950/40 dark:text-blue-300">
              {health?.network_scale ?? "v1_corridor"}
            </span>
          </div>
          <div className="mt-1.5 flex min-w-0 items-center justify-between text-[11px] text-light-text-muted dark:text-dark-text-muted">
            <span className="truncate">Calibrated Topology</span>
            <span className="ml-1 shrink-0 font-medium text-light-text-primary dark:text-dark-text-primary">
              {nodeCount > 0 ? `${nodeCount} nodes • ${edgeCount} links` : "118 nodes • 364 links"}
            </span>
          </div>
        </div>
      )}

      {/* 3. Navigation Groups */}
      <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-4">
        {navGroups.map((grp) => (
          <div key={grp.group} className="space-y-1">
            {!collapsed && (
              <div className="px-2 pb-1 text-[10px] font-bold tracking-wider uppercase text-light-text-muted dark:text-dark-text-muted">
                {grp.group}
              </div>
            )}
            {grp.items.map((item) => {
              const isActive = normalizedActive === item.id;
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onSelectTab(item.id)}
                  title={collapsed ? item.label : undefined}
                  className={`group relative flex w-full items-center gap-3 rounded px-2.5 py-2 text-xs transition-colors ${
                    isActive
                      ? "bg-blue-50 text-google-blue font-bold border-l-4 border-google-blue dark:bg-[#1A2838] dark:text-[#6BA5FF] dark:border-google-blue"
                      : "text-light-text-secondary hover:bg-light-hover hover:text-light-text-primary dark:text-dark-text-secondary dark:hover:bg-dark-hover dark:hover:text-dark-text-primary"
                  }`}
                >
                  <Icon
                    className={`h-4 w-4 shrink-0 transition-colors ${
                      isActive
                        ? "text-google-blue dark:text-[#6BA5FF]"
                        : "text-light-text-muted dark:text-dark-text-muted group-hover:text-light-text-primary dark:group-hover:text-dark-text-primary"
                    }`}
                  />

                  {!collapsed && (
                    <span className="truncate flex-1 text-left">
                      {item.label}
                    </span>
                  )}

                  {!collapsed && item.badge !== undefined && (
                    <span
                      className={`ml-auto rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                        item.badgeTone === "red"
                          ? "bg-red-50 text-google-red border border-red-200 dark:bg-red-950/40 dark:border-red-900/60 dark:text-red-300"
                          : "bg-light-secondary text-light-text-secondary border border-light-border dark:bg-dark-surface dark:border-dark-border dark:text-dark-text-secondary"
                      }`}
                    >
                      {item.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        ))}
      </nav>

      {/* 4. Operator Console Status Footer */}
      <div className="border-t border-light-border p-3 dark:border-dark-border">
        <div
          className={`flex items-center gap-2 rounded-lg border border-light-border bg-light-secondary/70 p-2 dark:border-dark-border dark:bg-dark-elevated/70 ${
            collapsed ? "justify-center" : ""
          }`}
        >
          <div className="relative flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-google-blue text-white font-bold text-xs">
            CT
            <span className="absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full border-2 border-white bg-google-green dark:border-dark-elevated" />
          </div>

          {!collapsed && (
            <div className="min-w-0 flex-1 leading-tight">
              <div className="flex items-center justify-between gap-1">
                <span className="truncate text-xs font-semibold text-light-text-primary dark:text-dark-text-primary">
                  Control Tower
                </span>
                <span className="shrink-0 rounded bg-green-50 text-google-green border border-green-200 px-1 py-0.2 text-[9px] font-bold dark:bg-green-950/40 dark:border-green-900/60 dark:text-green-300">
                  ONLINE
                </span>
              </div>
              <p className="truncate text-[10px] text-light-text-muted dark:text-dark-text-muted mt-0.5">
                South India Logistics Hub
              </p>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}

export default Sidebar;
