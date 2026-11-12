import {
  Bell,
  Cpu,
  FileText,
  Play,
  Radio,
  RefreshCw,
  Search,
} from "lucide-react";
import { ThemeToggle } from "../common/ThemeToggle";
import type {
  ActiveWorkspaceTab,
  FeedsStatusResponse,
  HealthResponse,
  LLMStatusResponse,
} from "../../types/asci";

interface TopNavbarProps {
  activeTab: ActiveWorkspaceTab;
  health?: HealthResponse | null;
  llmStatus: LLMStatusResponse | null;
  feedsStatus: FeedsStatusResponse | null;
  nodeCount?: number;
  edgeCount?: number;
  alertCount: number;
  onOpenSearch: () => void;
  onOpenNotifications: () => void;
  onPollLive: () => void;
  onRunMichaungDemo: () => void;
  onRunOptimization: () => void;
  autoPollEnabled: boolean;
  onToggleAutoPoll: () => void;
  busy: boolean;
  collapsedSidebar?: boolean;
}

const PAGE_METADATA: Record<
  string,
  { title: string; category: string; description: string }
> = {
  overview: {
    title: "Executive Operational Overview",
    category: "Operations",
    description: "Real-time corridor visibility, key performance metrics & multi-tier logistics movement",
  },
  network: {
    title: "Supply Chain Network",
    category: "Operations",
    description: "Multimodal corridor topology, port-to-plant connections & active transit routes",
  },
  inventory: {
    title: "Inventory Management",
    category: "Operations",
    description: "Warehouse stock levels, days-of-cover analysis & multi-commodity buffer health",
  },
  forecasting: {
    title: "Demand Forecasting",
    category: "Intelligence",
    description: "Predictive plant demand, time-to-line-stop (TTLS) & confidence intervals",
  },
  suppliers: {
    title: "Supplier & Port Intelligence",
    category: "Intelligence",
    description: "Maritime gateway ports, vendor reliability & PortWatch anomaly indexes",
  },
  risk: {
    title: "Risk & Disruptions",
    category: "Intelligence",
    description: "Live weather radar, multi-feed corroboration & cascading corridor vulnerability",
  },
  optimization: {
    title: "Optimization Engine",
    category: "Decision Engine",
    description: "Google OR-Tools & HiGHS dual-solver, CVaR risk hedging & route diversion",
  },
  analytics: {
    title: "Analytics & Reports",
    category: "Decision Engine",
    description: "Decision audit traces, semantic SOP playbooks & exportable executive briefs",
  },
};

export function TopNavbar({
  activeTab,
  llmStatus,
  alertCount,
  onOpenSearch,
  onOpenNotifications,
  onPollLive,
  onRunMichaungDemo,
  onRunOptimization,
  autoPollEnabled,
  onToggleAutoPoll,
  busy,
}: TopNavbarProps) {
  const normTab =
    activeTab === "command"
      ? "overview"
      : activeTab === "evidence" || activeTab === "trace"
      ? "analytics"
      : activeTab === "whatif"
      ? "optimization"
      : activeTab === "outcomes"
      ? "forecasting"
      : activeTab;

  const meta = PAGE_METADATA[normTab] ?? PAGE_METADATA.overview;
  const isLiveLlm = Boolean(llmStatus?.configured);

  return (
    <header className="sticky top-0 z-20 flex h-16 w-full items-center justify-between border-b border-light-border bg-light-surface px-6 dark:border-dark-border dark:bg-dark-surface shadow-subtle select-none">
      {/* 1. Contextual Title & Breadcrumbs */}
      <div className="flex flex-col min-w-0 pr-4">
        <div className="flex items-center gap-1.5 text-xs text-light-text-muted dark:text-dark-text-muted">
          <span>{meta.category}</span>
          <span className="opacity-40">/</span>
          <span className="font-semibold text-light-text-primary dark:text-dark-text-primary truncate">
            {meta.title}
          </span>
        </div>
        <p className="hidden md:block truncate text-[11px] text-light-text-secondary dark:text-dark-text-secondary mt-0.5">
          {meta.description}
        </p>
      </div>

      {/* 2. Global Search Input Trigger */}
      <div className="hidden lg:flex items-center px-2">
        <button
          type="button"
          onClick={onOpenSearch}
          className="flex h-9 w-64 items-center justify-between rounded-md border border-light-border bg-light-secondary px-3 text-xs text-light-text-muted hover:border-google-blue hover:text-light-text-primary dark:border-dark-border dark:bg-dark-elevated dark:text-dark-text-muted dark:hover:border-google-blue transition"
        >
          <div className="flex items-center gap-2 truncate">
            <Search className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">Search corridor nodes, events...</span>
          </div>
          <kbd className="shrink-0 rounded border border-light-border bg-light-surface px-1.5 py-0.5 text-[10px] text-light-text-muted dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-secondary">
            Ctrl K
          </kbd>
        </button>
      </div>

      {/* 3. Controls & Action Cluster */}
      <div className="flex items-center gap-2.5">
        {/* Status Badges */}
        <div className="hidden xl:flex items-center gap-2 text-xs">
          {/* LLM Status Badge */}
          <span className="inline-flex items-center gap-1.5 rounded-md border border-light-border bg-light-secondary px-2.5 py-1 text-light-text-secondary dark:border-dark-border dark:bg-dark-elevated dark:text-dark-text-secondary">
            <Cpu className="h-3 w-3 text-google-blue" />
            <span>
              {isLiveLlm ? `${llmStatus?.active_provider}` : "Deterministic Solver"}
            </span>
          </span>

          {/* Auto-Poll Toggle */}
          <button
            type="button"
            onClick={onToggleAutoPoll}
            className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 transition ${
              autoPollEnabled
                ? "border-google-blue bg-blue-50 text-google-blue dark:border-google-blue dark:bg-blue-950/30"
                : "border-light-border bg-light-secondary text-light-text-secondary dark:border-dark-border dark:bg-dark-elevated dark:text-dark-text-secondary"
            }`}
            title="Toggle Live Background Polling"
          >
            <Radio
              className={`h-3 w-3 ${
                autoPollEnabled ? "text-google-blue animate-pulse" : "text-slate-400"
              }`}
            />
            <span>{autoPollEnabled ? "Live Polling" : "Sync: Manual"}</span>
          </button>
        </div>

        {/* Sync Feeds Action */}
        <button
          type="button"
          onClick={onPollLive}
          disabled={busy}
          className="hidden sm:inline-flex items-center gap-1.5 rounded-md border border-light-border bg-light-surface px-3 py-1.5 text-xs font-semibold text-light-text-primary hover:bg-light-hover dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-primary dark:hover:bg-dark-elevated transition shadow-subtle disabled:opacity-50"
          title="Poll GDACS, GDELT & Open-Meteo feeds"
        >
          <RefreshCw
            className={`h-3.5 w-3.5 text-google-blue ${busy ? "animate-spin" : ""}`}
          />
          <span className="hidden md:inline">Sync Feeds</span>
        </button>

        {/* Cyclone Michaung Preset (Functional FileText icon - NO Sparkles) */}
        <button
          type="button"
          onClick={onRunMichaungDemo}
          disabled={busy}
          className="hidden md:inline-flex items-center gap-1.5 rounded-md border border-light-border bg-light-surface px-3 py-1.5 text-xs font-semibold text-light-text-primary hover:border-google-yellow hover:bg-amber-50/20 dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-primary dark:hover:border-google-yellow dark:hover:bg-dark-elevated transition shadow-subtle disabled:opacity-50"
          title="Load and optimize Cyclone Michaung scenario"
        >
          <FileText className="h-3.5 w-3.5 text-amber-600 dark:text-google-yellow" />
          <span>Cyclone Preset</span>
        </button>

        {/* Primary Action Button: Solid Google Blue */}
        <button
          type="button"
          onClick={onRunOptimization}
          disabled={busy}
          className="inline-flex items-center gap-2 rounded-md bg-google-blue px-4 py-1.5 text-xs font-bold text-white shadow-sm hover:bg-[#3367D6] active:bg-[#2A56C6] transition disabled:opacity-50"
        >
          <Play className="h-3.5 w-3.5 fill-current" />
          <span>Run Optimization</span>
        </button>

        {/* Notifications Icon */}
        <button
          type="button"
          onClick={onOpenNotifications}
          className="relative flex h-8 w-8 items-center justify-center rounded-md border border-light-border bg-light-surface text-light-text-secondary hover:bg-light-hover hover:text-light-text-primary dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-secondary dark:hover:bg-dark-elevated dark:hover:text-dark-text-primary transition shadow-subtle"
          title="Telemetry and disruption alerts"
        >
          <Bell className="h-4 w-4" />
          {alertCount > 0 && (
            <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-google-red text-[9px] font-bold text-white shadow-xs">
              {alertCount > 9 ? "9+" : alertCount}
            </span>
          )}
        </button>

        {/* Theme Switcher Toggle */}
        <ThemeToggle />
      </div>
    </header>
  );
}

export default TopNavbar;
