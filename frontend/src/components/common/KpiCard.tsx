import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

export type KpiStatus = "healthy" | "warning" | "critical" | "info" | "neutral";

export interface KpiCardProps {
  title: string;
  value: string | number;
  unit?: string;
  comparison?: string;
  trend?: "up" | "down" | "neutral";
  status?: KpiStatus;
  trendTone?: "positive" | "negative" | "neutral" | "cyan" | "purple" | "coral" | "amber" | "teal";
  subtitle?: string;
  sparklineData?: number[];
  variant?: "default" | "capsule" | "featured" | "accent" | "bordered";
  capsuleColor?: "cyan" | "purple" | "coral" | "amber";
  accent?: "cyan" | "purple" | "coral" | "amber";
}

export function KpiCard({
  title,
  value,
  unit,
  comparison,
  trend = "neutral",
  status,
  trendTone,
  subtitle,
  sparklineData = [35, 42, 38, 55, 48, 62, 58, 70],
}: KpiCardProps) {
  // Resolve semantic status cleanly using Google Color System
  const resolvedStatus: KpiStatus =
    status ??
    (trendTone === "positive" || trendTone === "teal" || trendTone === "cyan"
      ? "healthy"
      : trendTone === "negative" || trendTone === "coral"
      ? "critical"
      : trendTone === "amber"
      ? "warning"
      : trendTone === "purple"
      ? "info"
      : trend === "up"
      ? "healthy"
      : trend === "down"
      ? "critical"
      : "neutral");

  // Semantic accent indicator and sparkline stroke
  const indicatorColor = {
    healthy: "bg-google-green",
    warning: "bg-google-yellow",
    critical: "bg-google-red",
    info: "bg-google-blue",
    neutral: "bg-slate-400 dark:bg-slate-500",
  }[resolvedStatus];

  const strokeColor = {
    healthy: "#34A853",
    warning: "#FBBC04",
    critical: "#EA4335",
    info: "#4285F4",
    neutral: "#7C8997",
  }[resolvedStatus];

  const textColor = {
    healthy: "text-google-green",
    warning: "text-amber-600 dark:text-google-yellow",
    critical: "text-google-red",
    info: "text-google-blue",
    neutral: "text-light-text-secondary dark:text-dark-text-secondary",
  }[resolvedStatus];

  // SVG Sparkline calculation
  const min = Math.min(...sparklineData);
  const max = Math.max(...sparklineData);
  const range = max - min || 1;
  const width = 64;
  const height = 22;

  const points = sparklineData
    .map((val, idx) => {
      const x = (idx / (sparklineData.length - 1)) * width;
      const y = height - ((val - min) / range) * (height - 4) - 2;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <div className="relative flex flex-col justify-between h-[132px] rounded-md border border-light-border bg-light-surface p-3.5 shadow-card transition-colors hover:border-google-blue/40 dark:border-dark-border dark:bg-dark-surface dark:hover:border-google-blue/50">
      {/* Top Accent Indicator Line (Restrained) */}
      <div
        className={`absolute top-0 left-0 right-0 h-[3px] rounded-t-md ${indicatorColor}`}
      />

      {/* Header: Title and Comparison Label */}
      <div className="flex items-center justify-between gap-2 pt-0.5">
        <span className="text-xs font-semibold uppercase tracking-wider text-light-text-secondary dark:text-dark-text-secondary truncate">
          {title}
        </span>
        {comparison && (
          <span className={`text-[11px] font-semibold ${textColor} whitespace-nowrap`}>
            {comparison}
          </span>
        )}
      </div>

      {/* Metric Value */}
      <div className="flex items-baseline gap-1.5 my-1">
        <span className="text-2xl font-bold tracking-tight text-light-text-primary dark:text-dark-text-primary">
          {value}
        </span>
        {unit && (
          <span className="text-xs font-normal text-light-text-muted dark:text-dark-text-muted">
            {unit}
          </span>
        )}
      </div>

      {/* Footer: Trend, Subtitle & Clean Sparkline */}
      <div className="flex items-center justify-between border-t border-light-border/60 dark:border-dark-border/60 pt-2 mt-auto">
        <div className="flex items-center gap-1.5 text-xs text-light-text-muted dark:text-dark-text-muted truncate min-w-0 pr-2">
          {trend === "up" && (
            <ArrowUpRight className="h-3.5 w-3.5 text-google-green shrink-0" />
          )}
          {trend === "down" && (
            <ArrowDownRight className="h-3.5 w-3.5 text-google-red shrink-0" />
          )}
          {trend === "neutral" && (
            <Minus className="h-3.5 w-3.5 text-slate-400 shrink-0" />
          )}
          <span className="truncate">{subtitle || comparison || "Operational Baseline"}</span>
        </div>

        {sparklineData && sparklineData.length > 1 && (
          <svg
            width={width}
            height={height}
            className="shrink-0 opacity-80"
            aria-hidden="true"
          >
            <polyline
              fill="none"
              stroke={strokeColor}
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              points={points}
            />
          </svg>
        )}
      </div>
    </div>
  );
}

export default KpiCard;
