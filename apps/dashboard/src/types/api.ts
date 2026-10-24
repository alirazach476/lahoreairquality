/** Types aligned with the FastAPI response models. */

export interface DataFreshness {
  observed_at: string;
  age_seconds: number;
  is_fresh: boolean;
  freshness_threshold_seconds: number;
}

export interface PollutantReadings {
  pm25: number | null;
  pm10: number | null;
  o3: number | null;
  no2: number | null;
  so2: number | null;
  co: number | null;
}

export interface WeatherReadings {
  temperature_c: number | null;
  relative_humidity_pct: number | null;
  wind_speed_ms: number | null;
  wind_direction_deg: number | null;
}

export interface CurrentAirQuality {
  timestamp: string;
  aqi: number;
  aqi_category: string | null;
  dominant_pollutant: string | null;
  pollutants: PollutantReadings;
  weather?: WeatherReadings;
  station_id: string | null;
  scope: string;
  freshness: DataFreshness;
}

export interface HistoryPoint {
  timestamp: string;
  aqi: number | null;
  dominant_pollutant: string | null;
  pollutants: PollutantReadings;
  station_id: string | null;
}

export interface AirQualityHistory {
  start: string;
  end: string;
  station_id: string | null;
  points: HistoryPoint[];
  count: number;
}

export interface ForecastPoint {
  forecast_timestamp: string;
  predicted_aqi: number;
  model_name: string;
  model_version: string;
  forecast_horizon: number;
  station_id: string | null;
  origin_timestamp: string | null;
}

export interface ForecastResponse {
  generated_at: string;
  forecasts: ForecastPoint[];
  count: number;
}

export interface SensorInfo {
  station_id: string;
  location_name: string | null;
  latitude: number | null;
  longitude: number | null;
  source_name: string | null;
  last_observed_at: string | null;
  observation_count: number | null;
}

export interface SensorsResponse {
  sensors: SensorInfo[];
  count: number;
}

export interface DataQualityResponse {
  evaluated_at: string;
  database_healthy: boolean;
  air_quality_rows_evaluated: number;
  weather_rows_evaluated: number;
  class_counts: { valid: number; suspect: number; invalid: number };
  inactive_stations: string[];
  notes: string[];
  rules_doc?: string;
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  database: string;
  database_message: string | null;
}

export interface ApiErrorBody {
  error?: {
    code?: string;
    message?: string;
    details?: unknown;
  };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, message: string, code = "api_error") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}
