import type { CSSProperties } from "react";
import { formatNumber } from "../utils/aqi";

interface MetricCardProps {
  label: string;
  value: number | null | undefined;
  unit?: string;
  digits?: number;
  hint?: string | null;
  accent?: string;
  loading?: boolean;
  emptyMessage?: string;
  displayValue?: string | null;
}

export function MetricCard({
  label,
  value,
  unit,
  digits = 0,
  hint,
  accent,
  loading,
  emptyMessage = "No observation in the latest feed",
  displayValue,
}: MetricCardProps) {
  const hasValue =
    displayValue != null || (value != null && !Number.isNaN(value));
  const style = accent
    ? ({ ["--metric-accent"]: accent } as CSSProperties)
    : undefined;

  return (
    <article className="metric-card panel rise" style={style}>
      <header className="metric-card__label">{label}</header>
      {loading ? (
        <div className="skeleton metric-card__skeleton" aria-hidden />
      ) : hasValue ? (
        <>
          <p className="metric-card__value">
            <span>{displayValue ?? formatNumber(value, digits)}</span>
            {unit ? <small>{unit}</small> : null}
          </p>
          {hint ? <p className="metric-card__hint">{hint}</p> : null}
        </>
      ) : (
        <p className="metric-card__empty">{emptyMessage}</p>
      )}
    </article>
  );
}
