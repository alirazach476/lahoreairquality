import { FreshnessBadge } from "./FreshnessBadge";
import { LastUpdated } from "./LastUpdated";
import type { DataFreshness } from "../types/api";
import { getConfiguredApiBaseUrl } from "../api/client";

interface HeaderBarProps {
  freshness?: DataFreshness | null;
  fetchedAt?: string | null;
  observationAt?: string | null;
  loading?: boolean;
  refreshing?: boolean;
  onRefresh: () => void;
}

export function HeaderBar({
  freshness,
  fetchedAt,
  observationAt,
  loading,
  refreshing,
  onRefresh,
}: HeaderBarProps) {
  const apiBase = getConfiguredApiBaseUrl();

  return (
    <header className="header-bar rise">
      <div className="header-bar__brand">
        <p className="header-bar__kicker">Live air · Pakistan</p>
        <h1>Air Quality Intelligence</h1>
        <p className="header-bar__sub">
          Readings and forecasts for Lahore, shown in local time
          (Asia/Karachi · PKT).
        </p>
      </div>
      <div className="header-bar__meta">
        <FreshnessBadge
          freshness={freshness}
          loading={Boolean(loading) && !freshness}
        />
        <LastUpdated
          fetchedAt={fetchedAt}
          observationAt={observationAt}
          refreshing={refreshing}
        />
        <button
          type="button"
          className="btn"
          onClick={onRefresh}
          disabled={loading || refreshing}
        >
          {refreshing || loading ? "Refreshing…" : "Refresh"}
        </button>
        {apiBase ? (
          <p className="header-bar__api" title={apiBase}>
            API {apiBase.replace(/^https?:\/\//, "")}
          </p>
        ) : (
          <p className="header-bar__api header-bar__api--warn">
            Set VITE_API_BASE_URL
          </p>
        )}
      </div>
    </header>
  );
}
