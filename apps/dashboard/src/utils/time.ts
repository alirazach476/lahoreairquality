/** Timestamp display helpers — Lahore local time, originals preserved. */

/** IANA zone for Lahore (Pakistan Standard Time, UTC+5, no DST). */
export const LAHORE_TIME_ZONE = "Asia/Karachi";

export function parseApiTimestamp(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** Human-readable Lahore local time from an API ISO timestamp. */
export function formatLahoreTime(
  iso: string | null | undefined,
  options?: Intl.DateTimeFormatOptions,
): string {
  const d = parseApiTimestamp(iso);
  if (!d) return "—";
  return d.toLocaleString("en-PK", {
    timeZone: LAHORE_TIME_ZONE,
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    ...options,
  });
}

/** Compact Lahore local for chart axis ticks. */
export function formatLahoreTick(isoOrMs: string | number): string {
  const d =
    typeof isoOrMs === "number" ? new Date(isoOrMs) : parseApiTimestamp(isoOrMs);
  if (!d || Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("en-PK", {
    timeZone: LAHORE_TIME_ZONE,
    month: "short",
    day: "numeric",
    hour: "2-digit",
    hour12: false,
  });
}

/**
 * Accessible label: Lahore local primary, original API timestamp preserved.
 * Example: "24 Oct 2026, 14:30 PKT (API: 2026-10-24T09:30:00+00:00)"
 */
export function formatLahoreWithOriginal(
  iso: string | null | undefined,
): { display: string; title: string; original: string | null } {
  if (!iso) {
    return { display: "—", title: "No timestamp", original: null };
  }
  const display = formatLahoreTime(iso);
  const title = `Lahore local (${LAHORE_TIME_ZONE}): ${display}\nOriginal from API: ${iso}`;
  return { display, title, original: iso };
}

/** Structured Lahore parts for rich UI (date / clock / place). */
export interface LahoreTimeParts {
  weekday: string;
  date: string;
  time: string;
  display: string;
  title: string;
  original: string | null;
}

export function formatLahoreParts(
  iso: string | null | undefined,
): LahoreTimeParts {
  const empty: LahoreTimeParts = {
    weekday: "—",
    date: "—",
    time: "—",
    display: "—",
    title: "No timestamp",
    original: null,
  };
  const d = parseApiTimestamp(iso);
  if (!d || !iso) return empty;

  const weekday = d.toLocaleString("en-PK", {
    timeZone: LAHORE_TIME_ZONE,
    weekday: "long",
  });
  const date = d.toLocaleString("en-PK", {
    timeZone: LAHORE_TIME_ZONE,
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  const time = d.toLocaleString("en-PK", {
    timeZone: LAHORE_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
  const display = formatLahoreTime(iso);
  return {
    weekday,
    date,
    time,
    display,
    title: `Lahore local (${LAHORE_TIME_ZONE}): ${display}\nOriginal from API: ${iso}`,
    original: iso,
  };
}

export function formatAge(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h ago`;
  return `${(seconds / 86400).toFixed(1)}d ago`;
}
