import type { CurrentAirQuality } from "../types/api";
import type { SliceError } from "../hooks/useDashboardData";
import { aqiBand, formatNumber } from "../utils/aqi";
import { formatLahoreParts } from "../utils/time";

interface AqiHeroProps {
  current: CurrentAirQuality | null;
  loading?: boolean;
  error?: SliceError;
}

/** Arc gauge: AQI 0–500 maps to 0–100% of the semicircle. */
function gaugeProgress(aqi: number): number {
  return Math.min(1, Math.max(0, aqi / 500));
}

export function AqiHero({ current, loading, error }: AqiHeroProps) {
  const band = aqiBand(current?.aqi);
  const observed = current ? formatLahoreParts(current.timestamp) : null;
  const progress = current ? gaugeProgress(current.aqi) : 0;

  const r = 92;
  const cx = 120;
  const cy = 118;
  const stroke = 14;
  const circ = Math.PI * r;
  const dash = circ * progress;

  return (
    <section
      className="aqi-hero panel rise"
      aria-label="Current AQI"
      style={{ ["--aqi-color" as string]: band.color }}
    >
      {error && !current ? (
        <div className="aqi-hero__error">
          <strong>
            {error.kind === "network"
              ? "Network failure — current AQI"
              : "Current AQI API error"}
          </strong>
          <p>{error.message}</p>
        </div>
      ) : null}

      {!error && !loading && !current ? (
        <div className="aqi-hero__error aqi-hero__error--muted">
          <strong>No current observation</strong>
          <p>The current AQI endpoint returned no data.</p>
        </div>
      ) : null}

      <div className="aqi-hero__gauge">
        <svg viewBox="0 0 240 140" className="aqi-hero__svg" role="img" aria-hidden>
          <defs>
            <linearGradient id="aqi-track" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#1a7f4b" />
              <stop offset="25%" stopColor="#b45309" />
              <stop offset="50%" stopColor="#c2410c" />
              <stop offset="75%" stopColor="#b91c1c" />
              <stop offset="100%" stopColor="#7f1d1d" />
            </linearGradient>
          </defs>
          <path
            d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
            fill="none"
            stroke="rgba(20,32,43,0.08)"
            strokeWidth={stroke}
            strokeLinecap="round"
          />
          <path
            d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
            fill="none"
            stroke="url(#aqi-track)"
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={`${dash} ${circ}`}
            className="aqi-hero__arc"
          />
        </svg>
        <div className="aqi-hero__readout">
          {loading && !current ? (
            <div className="skeleton aqi-hero__skeleton" />
          ) : current ? (
            <>
              <span className="aqi-hero__value">{formatNumber(current.aqi, 0)}</span>
              <span className="aqi-hero__unit">AQI</span>
            </>
          ) : (
            <span className="aqi-hero__value aqi-hero__value--empty">—</span>
          )}
        </div>
      </div>

      <div className="aqi-hero__meta">
        <p className="aqi-hero__band" style={{ color: band.color }}>
          {current ? (current.aqi_category ?? band.label) : band.label}
        </p>
        {current?.dominant_pollutant ? (
          <p className="aqi-hero__dominant">
            Dominant · {current.dominant_pollutant.toUpperCase()}
          </p>
        ) : null}
        {observed ? (
          <div className="aqi-hero__when" title={observed.title}>
            <span className="aqi-hero__when-label">Observed</span>
            <span className="aqi-hero__when-time">{observed.time}</span>
            <span className="aqi-hero__when-date">
              {observed.weekday} · {observed.date}
            </span>
            <span className="aqi-hero__when-place">Lahore · PKT</span>
          </div>
        ) : null}
        {current?.station_id ? (
          <p className="aqi-hero__station">{current.station_id}</p>
        ) : null}
      </div>
    </section>
  );
}
