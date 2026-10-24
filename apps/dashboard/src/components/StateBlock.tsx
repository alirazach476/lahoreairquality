interface StateBlockProps {
  title: string;
  message: string;
  tone?: "neutral" | "danger" | "warning";
  actionLabel?: string;
  onAction?: () => void;
}

export function StateBlock({
  title,
  message,
  tone = "neutral",
  actionLabel,
  onAction,
}: StateBlockProps) {
  return (
    <div className={`state-block state-block--${tone}`} role="status">
      <h3>{title}</h3>
      <p>{message}</p>
      {actionLabel && onAction ? (
        <button type="button" className="btn" onClick={onAction}>
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}
