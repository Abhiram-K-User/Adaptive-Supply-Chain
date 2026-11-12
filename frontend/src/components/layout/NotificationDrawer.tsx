import {
  AlertCircle,
  AlertTriangle,
  CloudRain,
  Radio,
  Wind,
  X,
} from "lucide-react";
import type { DisruptionEvent, FeedsStatusResponse } from "../../types/asci";

interface NotificationDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  events: DisruptionEvent[];
  feedsStatus: FeedsStatusResponse | null;
  onSelectEvent?: (eventId: string) => void;
}

export function NotificationDrawer({
  isOpen,
  onClose,
  events,
  feedsStatus,
  onSelectEvent,
}: NotificationDrawerProps) {
  if (!isOpen) return null;

  const weather = feedsStatus?.weather_telemetry ?? [];
  const sources = feedsStatus?.source_statuses ?? [];

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-black/60 backdrop-blur-xs transition-opacity animate-fade-in">
      <div className="fixed inset-y-0 right-0 flex max-w-full pl-10">
        <div className="w-screen max-w-md bg-white border-l border-light-border dark:bg-dark-surface dark:border-dark-border shadow-2xl flex flex-col">
          {/* Drawer Header */}
          <div className="flex items-center justify-between border-b border-light-border px-5 py-4 bg-light-elevated dark:border-dark-border dark:bg-dark-card">
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-md bg-blue-50 text-google-blue border border-blue-200 dark:bg-blue-950/40 dark:border-blue-900/60 dark:text-google-blue">
                <AlertCircle className="h-4 w-4" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-light-text-primary dark:text-dark-text-primary">
                  Operational Telemetry Feed
                </h3>
                <p className="text-[11px] text-light-text-muted dark:text-dark-text-muted">
                  Live meteorological alerts &amp; incident signals
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-1.5 text-light-text-muted hover:bg-light-hover hover:text-light-text-primary dark:text-dark-text-muted dark:hover:bg-dark-elevated dark:hover:text-dark-text-primary transition"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Active Feed Adapters */}
          <div className="border-b border-light-border bg-white px-5 py-3 dark:border-dark-border dark:bg-dark-surface">
            <div className="flex items-center justify-between text-xs font-semibold mb-2">
              <span className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-light-text-muted dark:text-dark-text-muted">
                <Radio className="h-3 w-3 text-teal-600 dark:text-accent-cyan animate-pulse" />
                Ingestion Feed Adapters
              </span>
              <span className="text-[10px] font-mono text-light-text-muted dark:text-dark-text-muted">
                {feedsStatus?.last_polled_at
                  ? `Synced: ${new Date(feedsStatus.last_polled_at).toLocaleTimeString()}`
                  : "Syncing..."}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2">
              {sources.map((src) => {
                const isLive = src.fetch_mode.startsWith("live");
                return (
                  <div
                    key={src.source}
                    className="flex flex-col rounded-xl border border-light-border bg-light-elevated p-2 text-[11px] dark:border-dark-border dark:bg-dark-card"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-light-text-primary dark:text-dark-text-primary truncate">
                        {src.source.split(" ")[0]}
                      </span>
                      <span
                        className={`rounded px-1.5 py-0.2 font-mono text-[9px] font-bold ${
                          isLive
                            ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300"
                            : "bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300"
                        }`}
                      >
                        {isLive ? "LIVE" : "FALLBACK"}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center justify-between text-[10px] text-light-text-muted dark:text-dark-text-muted">
                      <span>{src.signals_fetched} signals</span>
                      <span>{src.corridor_events_grounded} grounded</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Drawer Scrollable Content */}
          <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
            {/* Weather Radar Telemetry */}
            {weather.length > 0 && (
              <div>
                <h4 className="text-[10px] font-bold uppercase tracking-wider text-light-text-muted dark:text-dark-text-muted mb-2">
                  Corridor Weather Radar (Open-Meteo / IMD)
                </h4>
                <div className="space-y-1.5">
                  {weather.map((row) => {
                    const isSevere =
                      row.alert_color === "RED" || row.alert_color === "ORANGE";
                    return (
                      <div
                        key={row.entity_id}
                        className={`flex items-center justify-between rounded-xl border p-2.5 text-xs ${
                          isSevere
                            ? "border-rose-200 bg-rose-50/50 dark:border-rose-900/60 dark:bg-rose-950/30"
                            : "border-light-border bg-light-elevated dark:border-dark-border dark:bg-dark-card"
                        }`}
                      >
                        <div>
                          <div className="font-semibold text-light-text-primary dark:text-dark-text-primary">
                            {row.name}
                          </div>
                          <div className="text-[10px] text-light-text-muted dark:text-dark-text-muted">
                            {row.region} • Alert: {row.alert_color}
                          </div>
                        </div>
                        <div className="flex items-center gap-2.5 font-mono text-[11px]">
                          <span className="flex items-center gap-1 text-light-text-secondary dark:text-dark-text-secondary">
                            <Wind className="h-3 w-3 text-teal-600 dark:text-accent-cyan" />
                            {row.wind_kmh.toFixed(0)} km/h
                          </span>
                          <span className="flex items-center gap-1 text-light-text-secondary dark:text-dark-text-secondary">
                            <CloudRain className="h-3 w-3 text-sky-600 dark:text-accent-blue" />
                            {row.rain_mm.toFixed(1)} mm
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Corroborated Disruption Incidents */}
            <div>
              <h4 className="text-[10px] font-bold uppercase tracking-wider text-light-text-muted dark:text-dark-text-muted mb-2">
                Active Incidents ({events.length})
              </h4>
              <div className="space-y-2">
                {events.map((ev) => {
                  const isHigh = ev.severity >= 0.6;
                  return (
                    <div
                      key={ev.event_id}
                      onClick={() => {
                        if (onSelectEvent) onSelectEvent(ev.event_id);
                        onClose();
                      }}
                      className={`cursor-pointer rounded-xl border p-3 transition hover:shadow-xs ${
                        isHigh
                          ? "border-rose-200 bg-rose-50/40 hover:border-rose-300 dark:border-rose-900/60 dark:bg-rose-950/20"
                          : "border-light-border bg-white hover:border-teal-400 dark:border-dark-border dark:bg-dark-card dark:hover:border-accent-cyan/60"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-1.5">
                          <AlertTriangle
                            className={`h-4 w-4 shrink-0 ${
                              isHigh
                                ? "text-rose-600 dark:text-rose-400"
                                : "text-amber-500 dark:text-amber-400"
                            }`}
                          />
                          <span className="font-semibold text-xs text-light-text-primary dark:text-dark-text-primary">
                            {ev.event_type}
                          </span>
                        </div>
                        <span
                          className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-bold ${
                            isHigh
                              ? "bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-300"
                              : "bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300"
                          }`}
                        >
                          {Math.round(ev.severity * 100)}%
                        </span>
                      </div>
                      <p className="mt-1.5 text-xs text-light-text-secondary dark:text-dark-text-secondary leading-relaxed line-clamp-2">
                        {ev.raw_headline}
                      </p>
                      <div className="mt-2 flex items-center justify-between text-[10px] text-light-text-muted dark:text-dark-text-muted font-mono">
                        <span>Target: {ev.primary_entity_id}</span>
                        <span>Confidence: {Math.round(ev.confidence * 100)}%</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Drawer Footer */}
          <div className="border-t border-light-border bg-light-elevated p-3 text-center text-xs text-light-text-muted dark:border-dark-border dark:bg-dark-card dark:text-dark-text-muted">
            All telemetry validated against SQLite EventStore
          </div>
        </div>
      </div>
    </div>
  );
}

