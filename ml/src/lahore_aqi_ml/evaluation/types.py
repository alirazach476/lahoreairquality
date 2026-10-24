"""Shared types for chronological forecast evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

SplitName = Literal["train", "validation", "test"]


@dataclass(frozen=True, slots=True)
class ChronologicalSplitSpec:
    """Fractions for a time-ordered train / validation / test partition.

    Fractions must sum to 1.0. Cuts are applied on sorted unique timestamps —
    rows are never shuffled.
    """

    train_fraction: float = 0.70
    validation_fraction: float = 0.15
    test_fraction: float = 0.15

    def __post_init__(self) -> None:
        total = self.train_fraction + self.validation_fraction + self.test_fraction
        if abs(total - 1.0) > 1e-9:
            raise ValueError(
                f"split fractions must sum to 1.0, got {total} "
                f"(train={self.train_fraction}, validation={self.validation_fraction}, "
                f"test={self.test_fraction})"
            )
        for name, value in (
            ("train_fraction", self.train_fraction),
            ("validation_fraction", self.validation_fraction),
            ("test_fraction", self.test_fraction),
        ):
            if value < 0:
                raise ValueError(f"{name} must be >= 0, got {value}")


@dataclass(frozen=True, slots=True)
class MetricScores:
    """Point-forecast metrics for one (model, split, series) evaluation."""

    mae: float
    rmse: float
    mape: float | None
    n_obs: int
    n_mape: int
    mape_skipped_near_zero: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EvaluationRow:
    """One row of the baseline / model comparison table."""

    model: str
    split: SplitName
    target: str
    horizon: int
    mae: float
    rmse: float
    mape: float | None
    n_obs: int
    n_mape: int
    mape_skipped_near_zero: int = 0
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvaluationTable:
    """Collection of evaluation rows with DataFrame / markdown helpers."""

    rows: list[EvaluationRow] = field(default_factory=list)

    def to_dicts(self) -> list[dict[str, Any]]:
        return [r.as_dict() for r in self.rows]

    def to_dataframe(self):  # type: ignore[no-untyped-def]
        import pandas as pd

        if not self.rows:
            return pd.DataFrame(
                columns=[
                    "model",
                    "split",
                    "target",
                    "horizon",
                    "mae",
                    "rmse",
                    "mape",
                    "n_obs",
                    "n_mape",
                    "mape_skipped_near_zero",
                    "notes",
                ]
            )
        return pd.DataFrame(self.to_dicts())

    def to_markdown(self, *, float_digits: int = 4) -> str:
        """Render a GitHub-flavored markdown table (no extra dependencies)."""
        frame = self.to_dataframe()
        if frame.empty:
            return "_No evaluation rows._"

        def _fmt(col: str, value: object) -> str:
            if value is None:
                return ""
            if isinstance(value, float):
                if value != value:  # NaN
                    return ""
                if col in {"mae", "rmse", "mape"}:
                    return f"{value:.{float_digits}f}"
            return str(value)

        columns = list(frame.columns)
        header = "| " + " | ".join(columns) + " |"
        sep = "| " + " | ".join("---" for _ in columns) + " |"
        lines = [header, sep]
        for _, row in frame.iterrows():
            cells = [_fmt(c, row[c]) for c in columns]
            lines.append("| " + " | ".join(cells) + " |")
        return "\n".join(lines)
