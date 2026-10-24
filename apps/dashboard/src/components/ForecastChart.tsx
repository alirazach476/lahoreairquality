import type { ForecastResponse } from "../types/api";
import type { SliceError } from "../hooks/useDashboardData";
import { LineChart } from "./LineChart";
import { StateBlock } from "./StateBlock";

interface ForecastChartProps {
  forecast: ForecastResponse | null;
  error?: SliceError;
  loading?: boolean;
}

export function ForecastChart({ forecast, error, loading }: ForecastChartProps) {
  const model =
    forecast && forecast.forecasts.length > 0
      ? `${forecast.forecasts[0].model_name} · ${forecast.forecasts[0].model_version}`
      : null;

  const points =
    forecast?.forecasts.map((f) => ({
      x: new Date(f.forecast_timestamp).getTime(),
      y: f.predicted_aqi,
      label: f.forecast_timestamp,
    })) ?? [];

  return (
    <section className="chart-panel panel rise rise-delay-2">
      <header className="chart-panel__head">
        <div>
          <h2>24–48h forecast</h2>
          <p>
            Predicted AQI from the serving model
            {model ? (
              <span className="chart-panel__model"> · {model}</span>
            ) : null}
            . Times in Lahore local.
          </p>
        </div>
      </header>
      {loading && !forecast ? (
        <div className="skeleton" style={{ height: 240 }} />
      ) : error && !forecast ? (
        <StateBlock
          title={
            error.kind === "network"
              ? "Network failure"
              : "Forecast API error"
          }
          message={error.message}
          tone="warning"
        />
      ) : !forecast || forecast.count === 0 ? (
        <StateBlock
          title="No forecast published"
          message="The forecast endpoint returned no rows (empty or 404)."
          tone="neutral"
        />
      ) : (
        <LineChart
          points={points}
          color="#0b6e6a"
          yLabel="Predicted AQI"
          showDots={points.length <= 36}
        />
      )}
    </section>
  );
}
