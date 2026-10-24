#!/usr/bin/env python3
"""CLI: train / evaluate SARIMA and compare to the naive baseline.

Usage::

    python ml/training/sarima.py --synthetic
    python ml/training/sarima.py --from-parquet path/to/mart.parquet --station-id S1

Does not implement XGBoost. Does not claim SARIMA superiority unless metrics say so.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from lahore_aqi_ml.evaluation import ChronologicalSplitSpec, format_evaluation_table
from lahore_aqi_ml.features import make_synthetic_mart_frame
from lahore_aqi_ml.training.sarima import (
    DEFAULT_SEASONAL_PERIOD,
    SarimaConfig,
    run_sarima_experiment,
)


def _parse_order(text: str) -> tuple[int, int, int]:
    parts = [int(x.strip()) for x in text.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("order must be p,d,q")
    return parts[0], parts[1], parts[2]


def _parse_seasonal(text: str) -> tuple[int, int, int, int]:
    parts = [int(x.strip()) for x in text.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("seasonal-order must be P,D,Q,s")
    return parts[0], parts[1], parts[2], parts[3]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-parquet", type=Path, default=None)
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Demo series only (not production observations)",
    )
    parser.add_argument("--n-hours", type=int, default=240)
    parser.add_argument("--station-id", default=None)
    parser.add_argument("--target-col", default="pm25")
    parser.add_argument("--horizon", type=int, default=1)
    parser.add_argument(
        "--order",
        type=_parse_order,
        default=(1, 0, 1),
        help="Non-seasonal order p,d,q (default: 1,0,1)",
    )
    parser.add_argument(
        "--seasonal-order",
        type=_parse_seasonal,
        default=(1, 0, 1, DEFAULT_SEASONAL_PERIOD),
        help="Seasonal order P,D,Q,s (default: 1,0,1,24 for hourly)",
    )
    parser.add_argument(
        "--select-from-candidates",
        action="store_true",
        help="Pick among a small built-in candidate list via validation MAE",
    )
    parser.add_argument("--train-fraction", type=float, default=0.70)
    parser.add_argument("--validation-fraction", type=float, default=0.15)
    parser.add_argument("--test-fraction", type=float, default=0.15)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("ml/training/artifacts/sarima"),
    )
    parser.add_argument("--run-name", default="sarima")
    parser.add_argument(
        "--mlflow-tracking-uri",
        default=None,
        help=(
            "MLflow tracking URI (overrides MLFLOW_TRACKING_URI). "
            "Omit both to use MLflow's local ./mlruns store."
        ),
    )
    parser.add_argument(
        "--no-mlflow",
        action="store_true",
        help="Disable MLflow logging for this run",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s %(message)s",
    )

    if args.from_parquet is not None:
        frame = pd.read_parquet(args.from_parquet)
        source = str(args.from_parquet)
    elif args.synthetic:
        frame = make_synthetic_mart_frame(n_hours=args.n_hours, stations=("S1",), seed=7)
        source = "synthetic:make_synthetic_mart_frame"
    else:
        print(
            "Pass --from-parquet <mart extract> or --synthetic for a demo.",
            file=sys.stderr,
        )
        return 2

    config = SarimaConfig(
        order=args.order,
        seasonal_order=args.seasonal_order,
        select_from_candidates=args.select_from_candidates,
        horizon=args.horizon,
        target_col=args.target_col,
    )
    split_spec = ChronologicalSplitSpec(
        train_fraction=args.train_fraction,
        validation_fraction=args.validation_fraction,
        test_fraction=args.test_fraction,
    )

    result = run_sarima_experiment(
        frame,
        config=config,
        station_id=args.station_id,
        split_spec=split_spec,
        output_dir=args.output_dir,
        run_name=args.run_name,
        log_mlflow=not args.no_mlflow,
        mlflow_tracking_uri=args.mlflow_tracking_uri,
    )

    print(f"source: {source}")
    print(f"station_id: {result.station_id}")
    print(f"model: {result.model_name}")
    print(f"order: {result.config.order}  seasonal_order: {result.config.seasonal_order}")
    print(f"train_aic: {result.train_aic}")
    print(f"comparison_vs_naive_mae: {result.metadata.get('comparison_vs_naive_mae')}")
    print()
    print(format_evaluation_table(result.metrics_table))
    print()
    print(f"predictions: {args.output_dir / (args.run_name + '_predictions.parquet')}")
    print(f"metadata: {args.output_dir / (args.run_name + '_metadata.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
