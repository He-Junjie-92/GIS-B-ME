# -*- coding: utf-8 -*-
"""Utilities for reading and writing GIS road-matrix files.

The original GIS prototype stored OD matrices only as Parquet. In practice,
some environments can run the GIS pipeline but do not have a Parquet engine
available. This helper keeps Parquet as the preferred format, but falls back to
compressed CSV when needed.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ROAD_MATRIX_CANDIDATES = (
    "road_matrix.parquet",
    "road_matrix.csv.gz",
    "road_matrix.csv",
)


def resolve_road_matrix_path(path_or_dir: str | Path) -> Path:
    path = Path(path_or_dir)
    if path.is_file():
        return path
    for name in ROAD_MATRIX_CANDIDATES:
        candidate = path / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"cannot find road matrix under {path}")


def load_road_matrix(path_or_dir: str | Path) -> pd.DataFrame:
    path = resolve_road_matrix_path(path_or_dir)
    suffixes = [s.lower() for s in path.suffixes]
    if suffixes[-2:] == [".csv", ".gz"] or suffixes[-1:] == [".csv"]:
        return pd.read_csv(path)
    return pd.read_parquet(path)


def write_road_matrix(df: pd.DataFrame, out_dir: str | Path) -> Path:
    out_path = Path(out_dir)
    parquet_path = out_path / "road_matrix.parquet"
    try:
        df.to_parquet(parquet_path, index=False)
        return parquet_path
    except Exception:
        csv_gz_path = out_path / "road_matrix.csv.gz"
        df.to_csv(csv_gz_path, index=False, encoding="utf-8-sig", compression="gzip")
        return csv_gz_path
