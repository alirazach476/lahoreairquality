#!/usr/bin/env python3
"""Run chronological baseline evaluation and print a comparison table.

Baselines are the reference for future SARIMA / XGBoost models.
Does **not** train those models.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from lahore_aqi_ml.evaluation import (
    ChronologicalSplitSpec,
    format_evaluation_table,
    run_baseline_evaluation,
)
from lahore_aqi_ml.features import make_synthetic_mart_frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-parquet", type=Path, default=None)
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Use synthetic mart-shaped demo data (not production observations)",
    )
    parser.add_argument("--value-col", default="pm25")
    parser.add_argument("--horizon", type=int, default=1)
    parser.add_argument("--season", type=int, default=24)
    parser.add_argument("--train-fraction", type=float, default=0.70)
    parser.add_argument("--validation-fraction", type=float, default=0.15)
    parser.add_argument("--test-fraction", type=float, default=0.15)
    parser.add_argument("--n-hours", type=int, default=240)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("ml/evaluation/reports"),
        help="Write markdown + JSON table (default: ml/evaluation/reports)",
    )
    parser.add_argument("--name", default="baseline_evaluation")
    args = parser.parse_args()

    if args.from_parquet is not None:
        frame = pd.read_parquet(args.from_parquet)
        source = str(args.from_parquet)
    elif args.synthetic:
        frame = make_synthetic_mart_frame(n_hours=args.n_hours, stations=("S1", "S2"))
        source = "synthetic:make_synthetic_mart_frame"
    else:
        raise SystemExit("Pass --from-parquet <file> or --synthetic for a local demo run.")

    if args.value_col not in frame.columns:
        raise SystemExit(
            f"value column {args.value_col!r} not in frame columns: {list(frame.columns)}"
        )

    spec = ChronologicalSplitSpec(
        train_fraction=args.train_fraction,
        validation_fraction=args.validation_fraction,
        test_fraction=args.test_fraction,
    )
    table = run_baseline_evaluation(
        frame,
        value_col=args.value_col,
        split_spec=spec,
        horizon=args.horizon,
        season=args.season,
    )

    md = format_evaluation_table(table)
    print(f"source: {source}")
    print(f"value_col: {args.value_col}  horizon: {args.horizon}  season: {args.season}")
    print()
    print(md)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    md_path = out / f"{args.name}.md"
    json_path = out / f"{args.name}.json"
    csv_path = out / f"{args.name}.csv"
    md_path.write_text(
        f"# Baseline evaluation\n\nSource: `{source}`\n\n{md}\n",
        encoding="utf-8",
    )
    json_path.write_text(
        json.dumps(
            {
                "source": source,
                "value_col": args.value_col,
                "horizon": args.horizon,
                "season": args.season,
                "split": {
                    "train_fraction": args.train_fraction,
                    "validation_fraction": args.validation_fraction,
                    "test_fraction": args.test_fraction,
                },
                "rows": table.to_dicts(),
            },
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    table.to_dataframe().to_csv(csv_path, index=False)
    print()
    print(f"wrote: {md_path}")
    print(f"wrote: {json_path}")
    print(f"wrote: {csv_path}")


if __name__ == "__main__":
    main()
