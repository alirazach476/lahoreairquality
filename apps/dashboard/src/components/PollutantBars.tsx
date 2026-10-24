import type { CurrentAirQuality } from "../types/api";
import type { SliceError } from "../hooks/useDashboardData";
import { formatNumber } from "../utils/aqi";
import { StateBlock } from "./StateBlock";

interface PollutantBarsProps {
  current: CurrentAirQuality | null;
  loading?: boolean;
  error?: SliceError;
}

/** Display pollutants excluding PM10 (removed from product UI). */
const POLLUTANTS: Array<{
  key: "pm25" | "o3" | "no2" | "so2" | "co";
  label: string;
  unit: string;
  /** Soft reference scale for bar width only — not a health threshold. */
  scale: number;
  color: string;
}> = [
  { key: "pm25", label: "PM2.5", unit: "µg/m³", scale: 250, color: "#0b6e6a" },
  { key: "o3", label: "O₃", unit: "ppb", scale: 200, color: "#1d4ed8" },
  { key: "no2", label: "NO₂", unit: "ppb", scale: 200, color: "#b45309" },
  { key: "so2", label: "SO₂", unit: "ppb", scale: 150, color: "#475569" },
  { key: "co", label: "CO", unit: "ppm", scale: 15, color: "#be123c" },
];

export function PollutantBars({ current, loading, error }: PollutantBarsProps) {
  const pollutants = current?.pollutants;

  return (
    <section className="chart-panel panel rise rise-delay-2">
      <header className="chart-panel__head">
        <div>
          <h2>Pollutant snapshot</h2>
          <p>Latest readings from the current observation (PM10 omitted).</p>
        </div>
      </header>

      {loading && !current ? (
        <div className="skeleton" style={{ height: 200 }} />
      ) : error && !current ? (
        <StateBlock
          title={
            error.kind === "network"
              ? "Network failure"
              : "Current AQI API error"
          }
          message={error.message}
          tone="danger"
        />
      ) : !current || !pollutants ? (
        <StateBlock
          title="No pollutant readings"
          message="The current observation has no pollutant payload."
          tone="neutral"
        />
      ) : (
        <ul className="pollutant-bars" aria-label="Pollutant levels">
          {POLLUTANTS.map((p) => {
            const raw = pollutants[p.key];
            const has = raw != null && !Number.isNaN(raw);
            const pct = has
              ? Math.min(100, Math.max(4, (raw / p.scale) * 100))
              : 0;
            return (
              <li key={p.key} className="pollutant-bars__row">
                <div className="pollutant-bars__label">
                  <span>{p.label}</span>
                  <strong>
                    {has ? formatNumber(raw, p.key === "co" ? 2 : 1) : "—"}
                    {has ? <small> {p.unit}</small> : null}
                  </strong>
                </div>
                <div className="pollutant-bars__track" aria-hidden>
                  {has ? (
                    <div
                      className="pollutant-bars__fill"
                      style={{
                        width: `${pct}%`,
                        background: p.color,
                      }}
                    />
                  ) : (
                    <div className="pollutant-bars__fill pollutant-bars__fill--empty" />
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
