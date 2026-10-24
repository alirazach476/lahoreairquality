/** EPA-style AQI band helpers for display (labels only — values come from API). */

export interface AqiBand {
  label: string;
  color: string;
  track: string;
}

export function aqiBand(aqi: number | null | undefined): AqiBand {
  if (aqi == null || Number.isNaN(aqi)) {
    return { label: "Unavailable", color: "#64748b", track: "rgba(100,116,139,0.2)" };
  }
  if (aqi <= 50) {
    return { label: "Good", color: "#1a7f4b", track: "rgba(26,127,75,0.18)" };
  }
  if (aqi <= 100) {
    return { label: "Moderate", color: "#b45309", track: "rgba(180,83,9,0.18)" };
  }
  if (aqi <= 150) {
    return {
      label: "Unhealthy for Sensitive Groups",
      color: "#c2410c",
      track: "rgba(194,65,12,0.18)",
    };
  }
  if (aqi <= 200) {
    return { label: "Unhealthy", color: "#b91c1c", track: "rgba(185,28,28,0.18)" };
  }
  if (aqi <= 300) {
    return { label: "Very Unhealthy", color: "#6b21a8", track: "rgba(107,33,168,0.18)" };
  }
  return { label: "Hazardous", color: "#7f1d1d", track: "rgba(127,29,29,0.22)" };
}

export function formatNumber(
  value: number | null | undefined,
  digits = 0,
): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

export function formatWind(
  speedMs: number | null | undefined,
  directionDeg: number | null | undefined,
): string {
  if (speedMs == null) return "—";
  const speed = `${formatNumber(speedMs, 1)} m/s`;
  if (directionDeg == null) return speed;
  const dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
  const idx = Math.round((((directionDeg % 360) + 360) % 360) / 45) % 8;
  return `${speed} ${dirs[idx]}`;
}

/** @deprecated Prefer formatLahoreWithOriginal from utils/time */
export { formatAge, formatLahoreTime as formatTimestamp } from "./time";
