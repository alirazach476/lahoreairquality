import type { DataFreshness } from "../types/api";
import { formatAge, formatLahoreWithOriginal } from "../utils/time";

interface FreshnessBadgeProps {
  freshness: DataFreshness | null | undefined;
  loading?: boolean;
}

export function FreshnessBadge({ freshness, loading }: FreshnessBadgeProps) {
  if (loading) {
    return (
      <span className="freshness skeleton" style={{ width: 120, height: 28 }} />
    );
  }
  if (!freshness) {
    return (
      <span className="freshness freshness--unknown" title="Freshness unknown">
        Freshness unavailable
      </span>
    );
  }
  const observed = formatLahoreWithOriginal(freshness.observed_at);
  const tone = freshness.is_fresh ? "fresh" : "stale";
  return (
    <span
      className={`freshness freshness--${tone}`}
      title={`${observed.title}\nAge ${Math.round(freshness.age_seconds)}s · threshold ${freshness.freshness_threshold_seconds}s`}
    >
      <span className="freshness__dot" aria-hidden />
      {freshness.is_fresh ? "Fresh" : "Stale"} · {formatAge(freshness.age_seconds)}
    </span>
  );
}
