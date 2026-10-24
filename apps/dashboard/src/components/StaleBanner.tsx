import type { DataFreshness } from "../types/api";
import { formatAge, formatLahoreWithOriginal } from "../utils/time";

interface StaleBannerProps {
  freshness: DataFreshness | null | undefined;
}

export function StaleBanner({ freshness }: StaleBannerProps) {
  if (!freshness || freshness.is_fresh) return null;
  const observed = formatLahoreWithOriginal(freshness.observed_at);

  return (
    <aside className="stale-banner panel" role="status">
      <strong>Stale data</strong>
      <p>
        Latest observation is {formatAge(freshness.age_seconds)} old (threshold{" "}
        {Math.round(freshness.freshness_threshold_seconds / 60)}m). Observed{" "}
        <span title={observed.title}>{observed.display} Lahore time</span>.
        Values may not reflect current conditions.
      </p>
    </aside>
  );
}
