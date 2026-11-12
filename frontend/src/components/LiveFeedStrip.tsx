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
    <section className="rounded-xl border border-line bg-panel px-3.5 py-2.5 shadow-lg shadow-black/20">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-sky-300">
            <Radio className="h-3 w-3 text-emerald-400" />
            Feed Sources:
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
                title={src.error ?? `Signals fetched: ${src.signals_fetched}, corridor events: ${src.corridor_events_grounded}`}
                className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
                  isLive
                    ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                    : "border-amber-500/40 bg-amber-500/10 text-amber-200"
                }`}
              >
                <span>{src.source.split(" ")[0]}</span>
                <span className="font-mono text-[9px] opacity-90">{badgeLabel}</span>
                <span className="text-slate-400">({src.signals_fetched})</span>
              </span>
            );
          })}
        </div>

        {feedsStatus?.last_polled_at && (
          <span className="font-mono text-[10px] text-slate-400">
            Mode: {feedsStatus.last_mode.toUpperCase()} ·{" "}
            {new Date(feedsStatus.last_polled_at).toLocaleTimeString()}
          </span>
        )}
      </div>

      {weather.length > 0 && (
        <div className="mt-2 grid grid-cols-2 gap-1.5 border-t border-line/70 pt-2 sm:grid-cols-3 lg:grid-cols-6">
          {weather.map((row) => {
            const tone =
              row.alert_color === "RED"
                ? "border-red-500/40 bg-red-500/10 text-red-200"
                : row.alert_color === "ORANGE"
                ? "border-amber-500/40 bg-amber-500/10 text-amber-200"
                : row.alert_color === "YELLOW"
                ? "border-yellow-500/40 bg-yellow-500/10 text-yellow-200"
                : "border-line bg-[#0a1122] text-slate-300";
            return (
              <div
                key={row.entity_id}
                className={`rounded-lg border px-2 py-1.5 text-[10px] ${tone}`}
              >
                <div className="flex items-center justify-between gap-1 font-semibold text-slate-100">
                  <span className="truncate">{row.name.split(" ")[0]}</span>
                  <span className="font-mono text-[9px]">{row.alert_color}</span>
                </div>
                <div className="mt-0.5 flex items-center justify-between font-mono text-[10px] text-slate-300">
                  <span className="inline-flex items-center gap-0.5">
                    <Wind className="h-2.5 w-2.5 text-sky-400" />
                    {row.wind_kmh.toFixed(0)} km/h
                  </span>
                  <span className="inline-flex items-center gap-0.5">
                    <CloudRain className="h-2.5 w-2.5 text-cyan-400" />
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

