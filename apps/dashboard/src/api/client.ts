import type {
  AirQualityHistory,
  ApiErrorBody,
  CurrentAirQuality,
  DataQualityResponse,
  ForecastResponse,
  HealthResponse,
  SensorsResponse,
  WeatherReadings,
} from "../types/api";
import { ApiError } from "../types/api";

const EMPTY_WEATHER: WeatherReadings = {
  temperature_c: null,
  relative_humidity_pct: null,
  wind_speed_ms: null,
  wind_direction_deg: null,
};

function apiBaseUrl(): string {
  const raw = import.meta.env.VITE_API_BASE_URL?.trim();
  if (!raw) {
    throw new ApiError(
      0,
      "VITE_API_BASE_URL is not set. Copy .env.example to .env and point it at the FastAPI service.",
      "config_error",
    );
  }
  return raw.replace(/\/$/, "");
}

export function getConfiguredApiBaseUrl(): string | null {
  const raw = import.meta.env.VITE_API_BASE_URL?.trim();
  return raw ? raw.replace(/\/$/, "") : null;
}

async function request<T>(
  path: string,
  init?: RequestInit & { allowNotFound?: boolean },
): Promise<T | null> {
  const { allowNotFound = false, ...fetchInit } = init ?? {};
  const base = apiBaseUrl();
  const url = `${base}${path}`;

  let response: Response;
  try {
    response = await fetch(url, {
      ...fetchInit,
      headers: {
        Accept: "application/json",
        ...(fetchInit.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError(
      0,
      `Network failure: unable to reach ${base}. Check that the FastAPI backend is running and CORS allows this origin.`,
      "network_error",
    );
  }

  if (response.status === 404 && allowNotFound) {
    return null;
  }

  if (!response.ok) {
    let message = `API error (${response.status})`;
    let code = "http_error";
    try {
      const body = (await response.json()) as ApiErrorBody;
      if (body.error?.message) message = body.error.message;
      if (body.error?.code) code = body.error.code;
    } catch {
      /* non-JSON body */
    }
    throw new ApiError(response.status, message, code);
  }

  return (await response.json()) as T;
}

function normalizeCurrent(raw: CurrentAirQuality): CurrentAirQuality {
  return {
    ...raw,
    weather: raw.weather ?? { ...EMPTY_WEATHER },
    pollutants: raw.pollutants ?? {
      pm25: null,
      pm10: null,
      o3: null,
      no2: null,
      so2: null,
      co: null,
    },
  };
}

/** Live FastAPI endpoints — no mock / synthetic production payloads. */
export const api = {
  health: () => request<HealthResponse>("/health"),

  currentAirQuality: async (stationId?: string) => {
    const q = stationId ? `?station_id=${encodeURIComponent(stationId)}` : "";
    const raw = await request<CurrentAirQuality>(`/api/air-quality/current${q}`, {
      allowNotFound: true,
    });
    return raw ? normalizeCurrent(raw) : null;
  },

  history: async (hours = 48, stationId?: string) => {
    const params = new URLSearchParams({ hours: String(hours) });
    if (stationId) params.set("station_id", stationId);
    return request<AirQualityHistory>(`/api/air-quality/history?${params}`);
  },

  forecast: async (limit = 48, stationId?: string) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (stationId) params.set("station_id", stationId);
    return request<ForecastResponse>(`/api/forecast?${params}`, {
      allowNotFound: true,
    });
  },

  sensors: () => request<SensorsResponse>("/api/sensors"),

  dataQuality: () => request<DataQualityResponse>("/api/data-quality"),
};
