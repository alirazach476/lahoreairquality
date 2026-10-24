#!/usr/bin/env python3
"""Build and save a documented ML feature dataset.

Production path: ``--from-parquet`` extract of ``marts.mart_air_quality_features``.
Synthetic frames require an explicit ``--synthetic`` flag (tests/demos only).

Usage (from repo root, with ``ml`` package installed)::

    python ml/features/generate_feature_dataset.py --from-parquet path/to/mart.parquet
    python ml/features/generate_feature_dataset.py --synthetic
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from lahore_aqi_ml.features import (
    build_feature_dataset,
    make_synthetic_mart_frame,
    save_feature_dataset,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from-parquet",
        type=Path,
        default=None,
        help="Parquet extract of mart_air_quality_features",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Explicitly allow synthetic demo data (tests/demos only; not production)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("ml/features/datasets"),
        help="Directory for parquet + docs (default: ml/features/datasets)",
    )
    parser.add_argument("--name", default="lahore_aqi_features")
    parser.add_argument("--n-hours", type=int, default=168, help="Synthetic hours")
    args = parser.parse_args()

    if args.from_parquet is not None:
        frame = pd.read_parquet(args.from_parquet)
        source = str(args.from_parquet)
    elif args.synthetic:
        frame = make_synthetic_mart_frame(n_hours=args.n_hours)
        source = "synthetic:make_synthetic_mart_frame"
    else:
        raise SystemExit(
            "Refusing to invent feature rows. Pass --from-parquet <mart extract> "
            "or --synthetic for local demos/tests only."
        )

    dataset = build_feature_dataset(frame)
    paths = save_feature_dataset(
        dataset,
        args.output_dir,
        name=args.name,
        extra_metadata={"input_source": source},
    )
    print(f"rows={len(dataset.frame)} features={len(dataset.feature_columns)}")
    for kind, path in paths.items():
        print(f"{kind}: {path}")


if __name__ == "__main__":
    main()
