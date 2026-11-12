import { CloudRain, Radio, Wind } from "lucide-react";
import type { FeedsStatusResponse } from "../types/asci";

interface LiveFeedStripProps {
  feedsStatus: FeedsStatusResponse | null;
}

export function LiveFeedStrip({ feedsStatus }: LiveFeedStripProps) {
  const sources = feedsStatus?.source_statuses ?? [];
  const weather = feedsStatus?.weather_telemetry ?? [];

  if (sources.length === 0 && weather.length === 0) {
    return null;
  }

  return (
    <section className="rounded-xl border border-[#e2e8ed] bg-white px-4 py-2.5 shadow-subtle">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-[#101c2c]">
            <Radio className="h-3.5 w-3.5 text-teal-600 animate-pulse" />
            Live Ingestion Feeds:
          </span>
          {sources.map((src) => {
            const isLive = src.fetch_mode.startsWith("live");
            const badgeLabel =
              src.fetch_mode === "live_rss"
                ? "LIVE RSS"
                : src.fetch_mode === "live_gdelt"
                ? "LIVE GDELT"
                : isLive
                ? "LIVE"
                : "FALLBACK";
            return (
              <span
                key={src.source}
                title={
                  src.error ??
                  `Signals fetched: ${src.signals_fetched}, corridor events: ${src.corridor_events_grounded}`
                }
                className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[10px] font-semibold transition ${
                  isLive
                    ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                    : "border-amber-200 bg-amber-50 text-amber-800"
                }`}
              >
                <span>{src.source.split(" ")[0]}</span>
                <span className="font-mono text-[9px] opacity-90">
                  {badgeLabel}
                </span>
                <span className="text-[#64748b]">({src.signals_fetched})</span>
              </span>
            );
          })}
        </div>

        {feedsStatus?.last_polled_at && (
          <span className="font-mono text-[10px] text-[#64748b]">
            Mode: {feedsStatus.last_mode.toUpperCase()} ·{" "}
            {new Date(feedsStatus.last_polled_at).toLocaleTimeString()}
          </span>
        )}
      </div>

      {weather.length > 0 && (
        <div className="mt-2.5 grid grid-cols-2 gap-1.5 border-t border-[#f1f5f9] pt-2 sm:grid-cols-3 lg:grid-cols-6">
          {weather.map((row) => {
            const tone =
              row.alert_color === "RED"
                ? "border-rose-200 bg-rose-50/60 text-rose-900"
                : row.alert_color === "ORANGE"
                ? "border-amber-200 bg-amber-50/60 text-amber-900"
                : row.alert_color === "YELLOW"
                ? "border-yellow-200 bg-yellow-50/60 text-yellow-900"
                : "border-[#e2e8ed] bg-[#f8fafc] text-[#334155]";
            return (
              <div
                key={row.entity_id}
                className={`rounded-lg border px-2 py-1.5 text-[10px] ${tone}`}
              >
                <div className="flex items-center justify-between gap-1 font-semibold text-[#101c2c]">
                  <span className="truncate">{row.name.split(" ")[0]}</span>
                  <span className="font-mono text-[9px] font-bold">
                    {row.alert_color}
                  </span>
                </div>
                <div className="mt-0.5 flex items-center justify-between font-mono text-[10px] text-[#64748b]">
                  <span className="inline-flex items-center gap-0.5">
                    <Wind className="h-2.5 w-2.5 text-teal-600" />
                    {row.wind_kmh.toFixed(0)} km/h
                  </span>
                  <span className="inline-flex items-center gap-0.5">
                    <CloudRain className="h-2.5 w-2.5 text-sky-600" />
                    {row.rain_mm.toFixed(1)} mm
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
