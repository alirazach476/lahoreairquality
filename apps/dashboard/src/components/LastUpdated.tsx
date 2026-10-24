import { formatLahoreParts } from "../utils/time";

interface LastUpdatedProps {
  /** When the dashboard last successfully fetched from the API. */
  fetchedAt: string | null | undefined;
  /** Observation timestamp from the current AQI payload (API original). */
  observationAt?: string | null;
  refreshing?: boolean;
}

export function LastUpdated({
  fetchedAt,
  observationAt,
  refreshing,
}: LastUpdatedProps) {
  const fetchParts = formatLahoreParts(fetchedAt);
  const obsParts = observationAt ? formatLahoreParts(observationAt) : null;

  return (
    <div className="timeplace panel" aria-live="polite">
      <div className="timeplace__place">
        <span className="timeplace__pin" aria-hidden>
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none">
            <path
              d="M12 21s7-5.4 7-11a7 7 0 1 0-14 0c0 5.6 7 11 7 11Z"
              stroke="currentColor"
              strokeWidth="1.8"
            />
            <circle cx="12" cy="10" r="2.4" fill="currentColor" />
          </svg>
        </span>
        <div className="timeplace__place-text">
          <strong>Lahore</strong>
          <span>Asia / Karachi · PKT</span>
        </div>
      </div>

      <div className="timeplace__clock" title={fetchParts.title}>
        <span className="timeplace__weekday">{fetchParts.weekday}</span>
        <span className="timeplace__time">
          {refreshing ? "···" : fetchParts.time}
        </span>
        <span className="timeplace__date">{fetchParts.date}</span>
      </div>

      <div className="timeplace__rows">
        <div className="timeplace__row">
          <span className="timeplace__label">Dashboard</span>
          <span className="timeplace__value" title={fetchParts.title}>
            {refreshing ? "Refreshing…" : fetchParts.display}
          </span>
        </div>
        {obsParts ? (
          <div className="timeplace__row">
            <span className="timeplace__label">Observation</span>
            <span className="timeplace__value" title={obsParts.title}>
              {obsParts.display}
            </span>
          </div>
        ) : null}
      </div>
    </div>
  );
}
