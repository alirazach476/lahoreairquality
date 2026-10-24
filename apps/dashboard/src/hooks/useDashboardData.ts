import { useCallback, useEffect, useRef, useState } from "react";
import { api, getConfiguredApiBaseUrl } from "../api/client";
import type {
  AirQualityHistory,
  CurrentAirQuality,
  DataQualityResponse,
  ForecastResponse,
  SensorsResponse,
} from "../types/api";
import { ApiError } from "../types/api";

export type DataSlice =
  | "current"
  | "history"
  | "forecast"
  | "sensors"
  | "quality";

export interface SliceError {
  message: string;
  kind: "network" | "api" | "config" | "unknown";
  status?: number;
}

export interface DashboardData {
  current: CurrentAirQuality | null;
  history: AirQualityHistory | null;
  forecast: ForecastResponse | null;
  sensors: SensorsResponse | null;
  quality: DataQualityResponse | null;
  errors: Partial<Record<DataSlice, SliceError>>;
  /** Client clock when this payload was fetched (ISO). */
  fetchedAt: string | null;
  /** True when API reports observation age beyond freshness threshold. */
  isStale: boolean;
}

const empty: DashboardData = {
  current: null,
  history: null,
  forecast: null,
  sensors: null,
  quality: null,
  errors: {},
  fetchedAt: null,
  isStale: false,
};

function classifyError(err: unknown): SliceError {
  if (err instanceof ApiError) {
    if (err.code === "config_error") {
      return { message: err.message, kind: "config", status: err.status };
    }
    if (err.code === "network_error" || err.status === 0) {
      return { message: err.message, kind: "network", status: err.status };
    }
    return { message: err.message, kind: "api", status: err.status };
  }
  if (err instanceof Error) {
    return { message: err.message, kind: "unknown" };
  }
  return { message: "Unexpected error", kind: "unknown" };
}

export function useDashboardData(refreshMs = 60_000) {
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const hasLoadedOnce = useRef(false);
  const [data, setData] = useState<DashboardData>(empty);
  const [fatalError, setFatalError] = useState<SliceError | null>(null);

  const load = useCallback(async () => {
    if (!getConfiguredApiBaseUrl()) {
      setFatalError({
        kind: "config",
        message:
          "VITE_API_BASE_URL is not set. Copy apps/dashboard/.env.example to .env.",
      });
      setIsInitialLoading(false);
      setIsRefreshing(false);
      return;
    }

    setFatalError(null);
    if (hasLoadedOnce.current) {
      setIsRefreshing(true);
    } else {
      setIsInitialLoading(true);
    }

    const errors: DashboardData["errors"] = {};

    const settled = await Promise.allSettled([
      api.currentAirQuality(),
      api.history(48),
      api.forecast(48),
      api.sensors(),
      api.dataQuality(),
    ]);

    const next: DashboardData = {
      ...empty,
      fetchedAt: new Date().toISOString(),
      errors,
    };

    const assign = <T,>(
      key: DataSlice,
      result: PromiseSettledResult<T | null>,
      apply: (value: T | null) => void,
    ) => {
      if (result.status === "fulfilled") {
        apply(result.value);
      } else {
        errors[key] = classifyError(result.reason);
      }
    };

    assign("current", settled[0], (v) => {
      next.current = v;
    });
    assign("history", settled[1], (v) => {
      next.history = v;
    });
    assign("forecast", settled[2], (v) => {
      next.forecast =
        v ??
        ({
          generated_at: next.fetchedAt!,
          forecasts: [],
          count: 0,
        } satisfies ForecastResponse);
    });
    assign("sensors", settled[3], (v) => {
      next.sensors = v;
    });
    assign("quality", settled[4], (v) => {
      next.quality = v;
    });

    next.errors = errors;
    next.isStale = Boolean(
      next.current?.freshness && !next.current.freshness.is_fresh,
    );

    setData(next);
    hasLoadedOnce.current = true;
    setIsInitialLoading(false);
    setIsRefreshing(false);

    const networkHits = Object.values(errors).filter((e) => e?.kind === "network");
    if (networkHits.length === 5) {
      setFatalError(networkHits[0] ?? null);
    }
  }, []);

  useEffect(() => {
    void load();
    if (refreshMs <= 0) return;
    const id = window.setInterval(() => {
      void load();
    }, refreshMs);
    return () => window.clearInterval(id);
  }, [load, refreshMs]);

  return {
    data,
    fatalError,
    isInitialLoading,
    isRefreshing,
    reload: load,
  };
}
