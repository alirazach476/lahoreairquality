import type { CurrentAirQuality } from "../types/api";
import type { SliceError } from "../hooks/useDashboardData";
import { formatNumber, formatWind } from "../utils/aqi";
import { MetricCard } from "./MetricCard";

interface MetricGridProps {
  current: CurrentAirQuality | null;
  loading?: boolean;
  error?: SliceError;
}

export function MetricGrid({ current, loading, error }: MetricGridProps) {
  const weather = current?.weather;
  const pollutants = current?.pollutants;

  return (
    <section className="metric-grid" aria-label="Current conditions">
      {error && !current ? (
        <div className="metric-grid__banner panel">
          <strong>
            {error.kind === "network"
              ? "Network failure — current AQI"
              : "Current AQI API error"}
          </strong>
          <p>{error.message}</p>
        </div>
      ) : null}
      {!error && !loading && !current ? (
        <div className="metric-grid__banner panel metric-grid__banner--empty">
          <strong>No current observation</strong>
          <p>
            The current AQI endpoint returned no data (empty warehouse or 404).
          </p>
        </div>
      ) : null}
      <MetricCard
        label="PM2.5"
        value={pollutants?.pm25}
        unit="µg/m³"
        digits={1}
        accent="#0b6e6a"
        loading={loading && !current}
        emptyMessage="PM2.5 not in latest observation"
      />
      <MetricCard
        label="Temperature"
        value={weather?.temperature_c}
        unit="°C"
        digits={1}
        accent="#1d4ed8"
        loading={loading && !current}
        emptyMessage="Temperature not in latest feed"
      />
      <MetricCard
        label="Humidity"
        value={weather?.relative_humidity_pct}
        unit="%"
        digits={0}
        accent="#0e7490"
        loading={loading && !current}
        emptyMessage="Humidity not in latest feed"
      />
      <MetricCard
        label="Wind"
        value={weather?.wind_speed_ms}
        displayValue={
          weather?.wind_speed_ms != null
            ? formatWind(weather.wind_speed_ms, weather.wind_direction_deg)
            : null
        }
        hint={
          weather?.wind_direction_deg != null
            ? `${formatNumber(weather.wind_direction_deg, 0)}°`
            : null
        }
        accent="#b45309"
        loading={loading && !current}
        emptyMessage="Wind not in latest feed"
      />
    </section>
  );
}
