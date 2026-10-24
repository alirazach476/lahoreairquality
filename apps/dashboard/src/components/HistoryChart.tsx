import { useMemo, useState } from "react";
import type { AirQualityHistory } from "../types/api";
import type { SliceError } from "../hooks/useDashboardData";
import { LineChart } from "./LineChart";
import { StateBlock } from "./StateBlock";

interface HistoryChartProps {
  history: AirQualityHistory | null;
  error?: SliceError;
  loading?: boolean;
}

type SeriesKey = "aqi" | "pm25";

const SERIES_META: Record<
  SeriesKey,
  { label: string; yLabel: string; color: string }
> = {
  aqi: { label: "AQI", yLabel: "AQI", color: "#1d4ed8" },
  pm25: { label: "PM2.5", yLabel: "PM2.5 µg/m³", color: "#0b6e6a" },
};

export function HistoryChart({ history, error, loading }: HistoryChartProps) {
  const [active, setActive] = useState<SeriesKey>("aqi");

  const points = useMemo(() => {
    if (!history?.points) return [];
    return history.points
      .map((p) => {
        const y =
          active === "aqi" ? p.aqi : (p.pollutants?.pm25 ?? null);
        if (y == null) return null;
        return {
          x: new Date(p.timestamp).getTime(),
          y,
          label: p.timestamp,
        };
      })
      .filter((p): p is { x: number; y: number; label: string } => p != null);
  }, [history, active]);

  const meta = SERIES_META[active];

  return (
    <section className="chart-panel panel rise rise-delay-1">
      <header className="chart-panel__head chart-panel__head--split">
        <div>
          <h2>Historical trend</h2>
          <p>Observed values from the API · Lahore local time.</p>
        </div>
        <div className="chart-toggle" role="tablist" aria-label="History series">
          {(Object.keys(SERIES_META) as SeriesKey[]).map((key) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={active === key}
              className={
                active === key
                  ? "chart-toggle__btn chart-toggle__btn--active"
                  : "chart-toggle__btn"
              }
              onClick={() => setActive(key)}
            >
              {SERIES_META[key].label}
            </button>
          ))}
        </div>
      </header>
      {loading && !history ? (
        <div className="skeleton" style={{ height: 240 }} />
      ) : error && !history ? (
        <StateBlock
          title={
            error.kind === "network"
              ? "Network failure"
              : "History API error"
          }
          message={error.message}
          tone="danger"
        />
      ) : !history || history.count === 0 || points.length === 0 ? (
        <StateBlock
          title="No history yet"
          message={
            active === "pm25"
              ? "No PM2.5 points in this history window."
              : "The history endpoint returned no points for this window."
          }
          tone="neutral"
        />
      ) : (
        <LineChart
          points={points}
          color={meta.color}
          yLabel={meta.yLabel}
          showDots={points.length <= 48}
        />
      )}
    </section>
  );
}
