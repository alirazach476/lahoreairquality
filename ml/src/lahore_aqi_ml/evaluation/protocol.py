"""Forecast model protocol — baselines and future SARIMA / XGBoost adapters."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class PointForecaster(Protocol):
    """Minimal interface every future model should satisfy for evaluation.

    Implementations return a prediction series aligned to ``frame.index`` for
    forecasting ``value_col`` (point forecasts at each row's timestamp).
    """

    @property
    def name(self) -> str: ...

    def predict(
        self,
        frame: pd.DataFrame,
        *,
        value_col: str,
        group_col: str = "station_id",
        time_col: str = "observed_hour",
    ) -> pd.Series: ...
