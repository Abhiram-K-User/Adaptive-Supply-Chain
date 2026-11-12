import { useState } from "react";

// ---------------------------------------------------------------------------
// 1. Professional Business Intelligence Trend Chart (Demand vs Throughput)
// ---------------------------------------------------------------------------
export interface TrendDataPoint {
  label: string;
  seriesA: number; // e.g. Demand / Predicted Inflow
  seriesB: number; // e.g. Delivered / Historical Baseline
}

interface TrendAreaChartProps {
  data: TrendDataPoint[];
  seriesAName?: string;
  seriesBName?: string;
  height?: number;
  unit?: string;
}

export function TrendAreaChart({
  data,
  seriesAName = "Predicted Inflow",
  seriesBName = "Historical Baseline",
  height = 230,
  unit = "TEU",
}: TrendAreaChartProps) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  if (!data || data.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center text-xs text-light-text-muted dark:text-dark-text-muted">
        No analytical trend data available.
      </div>
    );
  }

  const allValues = data.flatMap((d) => [d.seriesA, d.seriesB]);
  const minVal = Math.min(...allValues) * 0.95;
  const maxVal = Math.max(...allValues) * 1.05;
  const valRange = maxVal - minVal || 1;

  const width = 640;
  const paddingLeft = 55;
  const paddingRight = 20;
  const paddingTop = 20;
  const paddingBottom = 30;
  const graphWidth = width - paddingLeft - paddingRight;
  const graphHeight = height - paddingTop - paddingBottom;

  const getX = (idx: number) =>
    paddingLeft + (idx / (data.length - 1)) * graphWidth;
  const getY = (val: number) =>
    paddingTop + graphHeight - ((val - minVal) / valRange) * graphHeight;

  const pointsA = data.map((d, i) => `${getX(i)},${getY(d.seriesA)}`).join(" ");
  const pointsB = data.map((d, i) => `${getX(i)},${getY(d.seriesB)}`).join(" ");

  const areaA = `${getX(0)},${paddingTop + graphHeight} ${pointsA} ${getX(
    data.length - 1
  )},${paddingTop + graphHeight}`;

  const hoveredPoint = hoverIndex !== null ? data[hoverIndex] : null;

  // Horizontal Gridline ticks
  const yTicks = [
    maxVal,
    minVal + valRange * 0.66,
    minVal + valRange * 0.33,
    minVal,
  ];

  return (
    <div className="relative w-full select-none">
      {/* Header Legend & Live Inspection */}
      <div className="flex items-center justify-between text-xs mb-3 border-b border-light-border/60 dark:border-dark-border/60 pb-2">
        <div className="flex items-center gap-5">
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-sm bg-google-blue" />
            <span className="font-semibold text-light-text-primary dark:text-dark-text-primary">
              {seriesAName}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-sm bg-slate-400 dark:bg-slate-500" />
            <span className="font-semibold text-light-text-secondary dark:text-dark-text-secondary">
              {seriesBName}
            </span>
          </div>
        </div>

        {hoveredPoint ? (
          <div className="flex items-center gap-3 text-xs">
            <span className="text-light-text-muted dark:text-dark-text-muted">
              {hoveredPoint.label}:
            </span>
            <span className="font-bold text-google-blue">
              {hoveredPoint.seriesA.toFixed(0)} {unit}
            </span>
            <span className="text-light-text-muted dark:text-dark-text-muted">/</span>
            <span className="font-bold text-light-text-secondary dark:text-dark-text-secondary">
              {hoveredPoint.seriesB.toFixed(0)} {unit}
            </span>
          </div>
        ) : (
          <span className="text-[11px] text-light-text-muted dark:text-dark-text-muted">
            Hover over nodes for interval inspection
          </span>
        )}
      </div>

      {/* SVG Responsive Surface */}
      <div className="w-full overflow-hidden">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full h-auto overflow-visible"
          onMouseLeave={() => setHoverIndex(null)}
        >
          <defs>
            <linearGradient id="areaGradientBlue" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#4285F4" stopOpacity="0.12" />
              <stop offset="100%" stopColor="#4285F4" stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Horizontal Gridlines & Y-Axis Labels */}
          {yTicks.map((tick, i) => {
            const y = getY(tick);
            return (
              <g key={i}>
                <line
                  x1={paddingLeft}
                  y1={y}
                  x2={width - paddingRight}
                  y2={y}
                  stroke="currentColor"
                  className="text-light-border dark:text-dark-border"
                  strokeWidth="1"
                  strokeDasharray="2 3"
                />
                <text
                  x={paddingLeft - 8}
                  y={y + 4}
                  textAnchor="end"
                  className="fill-light-text-muted dark:fill-dark-text-muted text-[11px]"
                >
                  {tick.toFixed(0)}
                </text>
              </g>
            );
          })}

          {/* Area Fill for Series A */}
          <polygon points={areaA} fill="url(#areaGradientBlue)" />

          {/* Series B Line (Baseline) */}
          <polyline
            fill="none"
            stroke="#94A3B8"
            strokeWidth="1.8"
            strokeDasharray="4 3"
            strokeLinecap="round"
            strokeLinejoin="round"
            points={pointsB}
          />

          {/* Series A Line (Google Blue) */}
          <polyline
            fill="none"
            stroke="#4285F4"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
            points={pointsA}
          />

          {/* Interactive Data Points */}
          {data.map((d, i) => {
            const cx = getX(i);
            const cyA = getY(d.seriesA);
            const cyB = getY(d.seriesB);
            const isHovered = hoverIndex === i;

            return (
              <g
                key={i}
                className="cursor-pointer"
                onMouseEnter={() => setHoverIndex(i)}
              >
                {/* Vertical hover crosshair */}
                {isHovered && (
                  <line
                    x1={cx}
                    y1={paddingTop}
                    x2={cx}
                    y2={paddingTop + graphHeight}
                    stroke="#4285F4"
                    strokeWidth="1"
                    strokeDasharray="3 3"
                    className="opacity-70"
                  />
                )}

                {/* Node Markers */}
                <circle
                  cx={cx}
                  cy={cyB}
                  r={isHovered ? 4 : 2.5}
                  fill="#94A3B8"
                />
                <circle
                  cx={cx}
                  cy={cyA}
                  r={isHovered ? 5 : 3.5}
                  fill="#4285F4"
                  stroke="#FFFFFF"
                  strokeWidth="1.5"
                />

                {/* Invisible hover hitbox */}
                <rect
                  x={cx - graphWidth / (data.length * 2)}
                  y={paddingTop}
                  width={graphWidth / data.length}
                  height={graphHeight}
                  fill="transparent"
                />
              </g>
            );
          })}

          {/* X-Axis Labels */}
          {data.map((d, i) => (
            <text
              key={i}
              x={getX(i)}
              y={height - 8}
              textAnchor="middle"
              className="fill-light-text-muted dark:fill-dark-text-muted text-[11px]"
            >
              {d.label}
            </text>
          ))}
        </svg>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 2. Structured Segmented Donut Chart (Mode Split & Commodity Distribution)
// ---------------------------------------------------------------------------
export interface DonutSegment {
  label: string;
  value: number;
  color: string;
}

interface DonutChartProps {
  segments: DonutSegment[];
  centerTitle?: string;
  centerSubtitle?: string;
  centerLabel?: string;
  centerValue?: string;
  size?: number;
}

export function DonutChart({
  segments,
  centerTitle,
  centerSubtitle,
  centerLabel,
  centerValue,
  size = 180,
}: DonutChartProps) {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  const displayTitle = centerValue ?? centerTitle ?? "Total";
  const displaySubtitle = centerLabel ?? centerSubtitle ?? "Throughput";

  const total = segments.reduce((sum, s) => sum + s.value, 0) || 1;

  const center = size / 2;
  const radius = size * 0.38;
  const strokeWidth = 16;
  const circumference = 2 * Math.PI * radius;

  let currentAngle = 0;
  const arcSegments = segments.map((seg, idx) => {
    const fraction = seg.value / total;
    const strokeDasharray = `${circumference * fraction} ${
      circumference * (1 - fraction)
    }`;
    const strokeDashoffset = -currentAngle * circumference;
    currentAngle += fraction;

    return {
      ...seg,
      strokeDasharray,
      strokeDashoffset,
      fraction,
      idx,
    };
  });

  return (
    <div className="flex flex-col sm:flex-row items-center gap-6 select-none">
      {/* Donut SVG Ring */}
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          className="transform -rotate-90"
        >
          {/* Base track ring */}
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="transparent"
            stroke="currentColor"
            className="text-light-border dark:text-dark-border"
            strokeWidth={strokeWidth}
          />

          {/* Segment Arcs */}
          {arcSegments.map((arc) => (
            <circle
              key={arc.idx}
              cx={center}
              cy={center}
              r={radius}
              fill="transparent"
              stroke={arc.color}
              strokeWidth={hoveredIdx === arc.idx ? strokeWidth + 3 : strokeWidth}
              strokeDasharray={arc.strokeDasharray}
              strokeDashoffset={arc.strokeDashoffset}
              strokeLinecap="butt"
              className="transition-all duration-150 cursor-pointer"
              onMouseEnter={() => setHoveredIdx(arc.idx)}
              onMouseLeave={() => setHoveredIdx(null)}
            />
          ))}
        </svg>

        {/* Center Label */}
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <span className="text-xl font-bold text-light-text-primary dark:text-dark-text-primary">
            {hoveredIdx !== null
              ? `${segments[hoveredIdx].value}%`
              : displayTitle}
          </span>
          <span className="text-[10px] text-light-text-muted dark:text-dark-text-muted uppercase tracking-wider">
            {hoveredIdx !== null
              ? segments[hoveredIdx].label
              : displaySubtitle}
          </span>
        </div>
      </div>

      {/* Legend Column */}
      <div className="flex flex-col gap-2 w-full text-xs">
        {segments.map((seg, idx) => {
          const pct = Math.round((seg.value / total) * 100);
          const isHovered = hoveredIdx === idx;
          return (
            <div
              key={idx}
              className={`flex items-center justify-between p-1.5 rounded transition-colors cursor-pointer ${
                isHovered
                  ? "bg-light-secondary dark:bg-dark-elevated"
                  : "hover:bg-light-hover dark:hover:bg-dark-hover"
              }`}
              onMouseEnter={() => setHoveredIdx(idx)}
              onMouseLeave={() => setHoveredIdx(null)}
            >
              <div className="flex items-center gap-2.5 truncate pr-2">
                <span
                  className="h-2.5 w-2.5 rounded-sm shrink-0"
                  style={{ backgroundColor: seg.color }}
                />
                <span className="text-light-text-secondary dark:text-dark-text-secondary truncate">
                  {seg.label}
                </span>
              </div>
              <span className="font-bold text-light-text-primary dark:text-dark-text-primary whitespace-nowrap">
                {seg.value}% ({pct}%)
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 3. Enterprise Horizontal Capacity Bar Chart
// ---------------------------------------------------------------------------
export interface CapacityBarItem {
  label: string;
  utilized?: number;
  value?: number;
  capacity?: number;
  max?: number;
  unit?: string;
  secondaryValue?: string;
  status?: "healthy" | "warning" | "critical";
  id?: string;
}

interface HorizontalBarChartProps {
  items: CapacityBarItem[];
  valueUnit?: string;
}

export function HorizontalBarChart({ items, valueUnit }: HorizontalBarChartProps) {
  return (
    <div className="space-y-3 select-none text-xs">
      {items.map((item, idx) => {
        const used = item.utilized ?? item.value ?? 0;
        const cap = item.capacity ?? item.max ?? 100;
        const unit = item.unit || valueUnit || "TEU/d";
        const pct = Math.min(
          100,
          Math.round((used / (cap || 1)) * 100)
        );
        const barColor =
          item.status === "critical" || pct > 90
            ? "bg-google-red"
            : item.status === "warning" || pct > 75
            ? "bg-google-yellow"
            : "bg-google-blue";

        return (
          <div key={item.id ?? idx} className="space-y-1">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-light-text-secondary dark:text-dark-text-secondary truncate pr-2">
                {item.label}
              </span>
              <span className="text-light-text-muted dark:text-dark-text-muted whitespace-nowrap">
                <strong className="text-light-text-primary dark:text-dark-text-primary">
                  {used}
                </strong>{" "}
                / {cap} {unit} ({pct}%)
              </span>
            </div>

            <div className="h-2 w-full rounded bg-light-border dark:bg-dark-border overflow-hidden">
              <div
                className={`h-full rounded transition-all duration-300 ${barColor}`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
