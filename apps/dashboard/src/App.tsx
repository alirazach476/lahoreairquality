import { AqiHero } from "./components/AqiHero";
import { ForecastChart } from "./components/ForecastChart";
import { HeaderBar } from "./components/HeaderBar";
import { HistoryChart } from "./components/HistoryChart";
import { MetricGrid } from "./components/MetricGrid";
import { PollutantBars } from "./components/PollutantBars";
import { SensorsPanel } from "./components/SensorsPanel";
import { StateBlock } from "./components/StateBlock";
import { StaleBanner } from "./components/StaleBanner";
import { useDashboardData } from "./hooks/useDashboardData";
import { getConfiguredApiBaseUrl } from "./api/client";

export default function App() {
  const { data, fatalError, isInitialLoading, isRefreshing, reload } =
    useDashboardData(60_000);
  const apiConfigured = Boolean(getConfiguredApiBaseUrl());
  const loading = isInitialLoading;

  return (
    <div className="app-shell">
      <div className="app-atmosphere" aria-hidden />

      <HeaderBar
        freshness={data.current?.freshness}
        fetchedAt={data.fetchedAt}
        observationAt={data.current?.timestamp}
        loading={loading}
        refreshing={isRefreshing}
        onRefresh={() => void reload()}
      />

      {!apiConfigured ? (
        <StateBlock
          title="API URL not configured"
          message="Create apps/dashboard/.env from .env.example and set VITE_API_BASE_URL to your FastAPI base URL (for example http://localhost:8000). No secrets belong in the frontend — only the public API origin."
          tone="danger"
        />
      ) : null}

      {fatalError ? (
        <StateBlock
          title={
            fatalError.kind === "network"
              ? "Network failure"
              : fatalError.kind === "config"
                ? "Configuration error"
                : "Unable to load dashboard"
          }
          message={fatalError.message}
          tone="danger"
          actionLabel="Retry"
          onAction={() => void reload()}
        />
      ) : null}

      <StaleBanner freshness={data.current?.freshness} />

      <div className="hero-row">
        <AqiHero
          current={data.current}
          loading={loading}
          error={data.errors.current}
        />
        <div className="hero-row__metrics">
          <MetricGrid
            current={data.current}
            loading={loading}
            error={undefined}
          />
        </div>
      </div>

      <div className="charts-row">
        <HistoryChart
          history={data.history}
          error={data.errors.history}
          loading={loading}
        />
        <ForecastChart
          forecast={data.forecast}
          error={data.errors.forecast}
          loading={loading}
        />
      </div>

      <div className="charts-row charts-row--secondary">
        <PollutantBars
          current={data.current}
          loading={loading}
          error={data.errors.current}
        />
        <SensorsPanel
          sensors={data.sensors}
          quality={data.quality}
          sensorsError={data.errors.sensors}
          qualityError={data.errors.quality}
          loading={loading}
        />
      </div>

      <footer className="app-footer">
        <span>Lahore Air Quality Intelligence Platform</span>
        <span>Live FastAPI data · Lahore local times · no fabricated values</span>
      </footer>
    </div>
  );
}
