import { useMemo } from "react";
import { formatLahoreTick } from "../utils/time";

export interface ChartPoint {
  x: number; // epoch ms
  y: number;
  label?: string;
}

export interface ChartSeries {
  id: string;
  points: ChartPoint[];
  color: string;
  dashed?: boolean;
}

interface LineChartProps {
  /** Single series (legacy) or multi-series. */
  points?: ChartPoint[];
  series?: ChartSeries[];
  color?: string;
  height?: number;
  yLabel?: string;
  emptyMessage?: string;
  showDots?: boolean;
}

export function LineChart({
  points,
  series: seriesProp,
  color = "#0b6e6a",
  height = 240,
  yLabel = "AQI",
  emptyMessage = "No series available",
  showDots = false,
}: LineChartProps) {
  const series: ChartSeries[] = useMemo(() => {
    if (seriesProp && seriesProp.length > 0) return seriesProp;
    if (points && points.length > 0) {
      return [{ id: "primary", points, color }];
    }
    return [];
  }, [seriesProp, points, color]);

  const geometry = useMemo(() => {
    const allPoints = series.flatMap((s) => s.points);
    if (allPoints.length === 0) return null;

    const pad = { top: 18, right: 14, bottom: 32, left: 42 };
    const width = 640;
    const innerW = width - pad.left - pad.right;
    const innerH = height - pad.top - pad.bottom;
    const xs = allPoints.map((p) => p.x);
    const ys = allPoints.map((p) => p.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const spanX = Math.max(maxX - minX, 1);
    const spanY = Math.max(maxY - minY, 1);
    const yPad = spanY * 0.1 || 5;
    const y0 = Math.max(0, minY - yPad);
    const y1 = maxY + yPad;

    const mapX = (x: number) => pad.left + ((x - minX) / spanX) * innerW;
    const mapY = (y: number) => pad.top + (1 - (y - y0) / (y1 - y0)) * innerH;

    const built = series.map((s) => {
      if (s.points.length === 0) {
        return { ...s, path: "", area: "", mapped: [] as Array<{ x: number; y: number }> };
      }
      const mapped = s.points.map((p) => ({
        x: mapX(p.x),
        y: mapY(p.y),
      }));
      const path = mapped
        .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`)
        .join(" ");
      const area = `${path} L ${mapped[mapped.length - 1].x.toFixed(2)} ${
        pad.top + innerH
      } L ${mapped[0].x.toFixed(2)} ${pad.top + innerH} Z`;
      return { ...s, path, area, mapped };
    });

    const ticks = 4;
    const yTicks = Array.from({ length: ticks + 1 }, (_, i) => {
      const v = y0 + ((y1 - y0) * i) / ticks;
      return { v, y: mapY(v) };
    });

    const timeAnchors = [
      allPoints[0],
      allPoints[Math.floor(allPoints.length / 2)],
      allPoints[allPoints.length - 1],
    ].filter(Boolean);

    const xLabels = timeAnchors.map((p) => ({
      x: mapX(p.x),
      text: formatLahoreTick(p.x),
    }));

    return { width, height, built, yTicks, xLabels, pad, yLabel, gradientId: `fill-${yLabel.replace(/\s+/g, "")}` };
  }, [series, height, yLabel]);

  if (!geometry) {
    return <div className="chart-empty">{emptyMessage}</div>;
  }

  const primary = geometry.built[0];

  return (
    <div className="chart-wrap">
      <svg
        viewBox={`0 0 ${geometry.width} ${geometry.height}`}
        role="img"
        aria-label={`${yLabel} time series`}
        className="chart-svg"
      >
        <defs>
          {geometry.built.map((s) => (
            <linearGradient
              key={`g-${s.id}`}
              id={`${geometry.gradientId}-${s.id}`}
              x1="0"
              y1="0"
              x2="0"
              y2="1"
            >
              <stop offset="0%" stopColor={s.color} stopOpacity={0.28} />
              <stop offset="100%" stopColor={s.color} stopOpacity={0} />
            </linearGradient>
          ))}
        </defs>
        {geometry.yTicks.map((t) => (
          <g key={t.v}>
            <line
              x1={geometry.pad.left}
              x2={geometry.width - geometry.pad.right}
              y1={t.y}
              y2={t.y}
              className="chart-grid"
            />
            <text
              x={geometry.pad.left - 8}
              y={t.y + 4}
              className="chart-tick"
              textAnchor="end"
            >
              {Math.round(t.v)}
            </text>
          </g>
        ))}
        {primary?.area ? (
          <path
            d={primary.area}
            fill={`url(#${geometry.gradientId}-${primary.id})`}
          />
        ) : null}
        {geometry.built.map((s) =>
          s.path ? (
            <path
              key={s.id}
              d={s.path}
              fill="none"
              stroke={s.color}
              strokeWidth={2.6}
              strokeLinejoin="round"
              strokeLinecap="round"
              strokeDasharray={s.dashed ? "6 5" : undefined}
              className="chart-line"
            />
          ) : null,
        )}
        {showDots
          ? geometry.built.flatMap((s) =>
              s.mapped.map((p, i) => (
                <circle
                  key={`${s.id}-${i}`}
                  cx={p.x}
                  cy={p.y}
                  r={3}
                  fill="#fff"
                  stroke={s.color}
                  strokeWidth={2}
                  className="chart-dot"
                />
              )),
            )
          : null}
        {geometry.xLabels.map((l) => (
          <text
            key={`${l.x}-${l.text}`}
            x={l.x}
            y={geometry.height - 8}
            className="chart-tick"
            textAnchor="middle"
          >
            {l.text}
          </text>
        ))}
      </svg>
    </div>
  );
}
