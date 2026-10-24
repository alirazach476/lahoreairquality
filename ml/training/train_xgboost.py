#!/usr/bin/env python3
"""CLI: train / evaluate XGBoost on the causal feature dataset.

Named ``train_xgboost.py`` (not ``xgboost.py``) so running the script does not
shadow the installed ``xgboost`` package on ``sys.path``.

Reproducible commands::

    # From the previously saved feature dataset (preferred)
    python ml/training/train_xgboost.py \\
      --from-features ml/features/datasets/lahore_aqi_features.parquet \\
      -v

    # Synthetic feature matrix demo (not production observations)
    python ml/training/train_xgboost.py --synthetic -v

Does not claim XGBoost accuracy or superiority unless measured metrics say so.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from lahore_aqi_ml.evaluation import ChronologicalSplitSpec, format_evaluation_table
from lahore_aqi_ml.features import build_feature_dataset, make_synthetic_mart_frame
from lahore_aqi_ml.training.xgboost_model import (
    DEFAULT_TARGET,
    XgbConfig,
    load_feature_frame,
    run_xgboost_experiment,
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
    parser.add_argument(
        "--from-features",
        type=Path,
        default=None,
        help="Path to feature parquet (e.g. ml/features/datasets/lahore_aqi_features.parquet)",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=None,
        help="Optional feature metadata JSON (defaults to <stem>.metadata.json)",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Build features from synthetic mart (demo only)",
    )
    parser.add_argument("--n-hours", type=int, default=240)
    parser.add_argument("--target-col", default=DEFAULT_TARGET)
    parser.add_argument("--value-col", default="pm25")
    parser.add_argument("--horizon", type=int, default=1)
    parser.add_argument("--early-stopping-rounds", type=int, default=30)
    parser.add_argument("--train-fraction", type=float, default=0.70)
    parser.add_argument("--validation-fraction", type=float, default=0.15)
    parser.add_argument("--test-fraction", type=float, default=0.15)
    parser.add_argument(
        "--no-sarima-comparison",
        action="store_true",
        help="Skip SARIMA reference (faster)",
    )
    parser.add_argument(
        "--sarima-order",
        type=_parse_order,
        default=(1, 0, 1),
    )
    parser.add_argument(
        "--sarima-seasonal-order",
        type=_parse_seasonal,
        default=(1, 0, 1, 24),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("ml/training/artifacts/xgboost"),
    )
    parser.add_argument("--run-name", default="xgboost")
    parser.add_argument("--random-state", type=int, default=42)
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

    feature_columns = None
    if args.from_features is not None:
        frame, feature_columns = load_feature_frame(args.from_features, metadata_path=args.metadata)
        source = str(args.from_features)
    elif args.synthetic:
        mart = make_synthetic_mart_frame(n_hours=args.n_hours, stations=("S1",), seed=7)
        dataset = build_feature_dataset(mart)
        frame = dataset.frame
        feature_columns = dataset.feature_columns
        source = "synthetic:build_feature_dataset"
    else:
        default_features = Path("ml/features/datasets/lahore_aqi_features.parquet")
        if default_features.exists():
            frame, feature_columns = load_feature_frame(default_features)
            source = str(default_features)
        else:
            print(
                "Pass --from-features <feature.parquet> or --synthetic for a demo.",
                file=sys.stderr,
            )
            return 2

    config = XgbConfig(
        target_col=args.target_col,
        value_col=args.value_col,
        horizon=args.horizon,
        early_stopping_rounds=args.early_stopping_rounds,
        random_state=args.random_state,
        include_sarima_comparison=not args.no_sarima_comparison,
        sarima_order=args.sarima_order,
        sarima_seasonal_order=args.sarima_seasonal_order,
    )
    split_spec = ChronologicalSplitSpec(
        train_fraction=args.train_fraction,
        validation_fraction=args.validation_fraction,
        test_fraction=args.test_fraction,
    )

    result = run_xgboost_experiment(
        frame,
        config=config,
        feature_columns=feature_columns,
        split_spec=split_spec,
        output_dir=args.output_dir,
        run_name=args.run_name,
        log_mlflow=not args.no_mlflow,
        mlflow_tracking_uri=args.mlflow_tracking_uri,
    )

    print(f"source={source}")
    print(f"model={result.model_name}")
    print(f"best_params={result.best_params}")
    print(f"best_iteration={result.best_iteration}")
    print(f"n_features={len(result.feature_columns)}")
    print(f"artifacts={args.output_dir.resolve()}")
    print()
    print(format_evaluation_table(result.metrics_table))
    print()
    print(f"mae_comparison={result.metadata.get('mae_comparison')}")
    print(f"lowest_mae_among_measured={result.metadata.get('lowest_mae_among_measured')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
