"""Loading and joining the feature and label tables.

All error messages report counts only - never participant IDs or dates.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import Config

LABEL_COLUMN_KEYS = ("original_target", "label_status", "matched_event_date", "matched_event_severity")


class DataValidationError(ValueError):
    """Raised when an input table violates an expected structural property."""


def read_table(path: str | Path, columns: list[str] | None = None) -> pd.DataFrame:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Required input file is missing: {path.name}")
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path, columns=columns)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, usecols=columns, low_memory=False)
    raise DataValidationError(f"Unsupported file type: {path.suffix}")


def normalize_keys(df: pd.DataFrame, cfg: Config, name: str) -> pd.DataFrame:
    """Return a copy with string participant IDs and UTC calendar-day dates."""
    pid, date = cfg.pid, cfg.date
    missing = [c for c in (pid, date) if c not in df.columns]
    if missing:
        raise DataValidationError(f"{name}: missing key columns {missing}")
    out = df.copy()
    out[pid] = out[pid].astype("string").str.strip()
    out[date] = pd.to_datetime(out[date], utc=True, errors="coerce")
    n_bad_pid = int(out[pid].isna().sum() + (out[pid] == "").sum())
    n_bad_date = int(out[date].isna().sum())
    if n_bad_pid or n_bad_date:
        raise DataValidationError(
            f"{name}: {n_bad_pid} missing participant IDs and {n_bad_date} missing/unparseable dates")
    n_time = int((out[date] != out[date].dt.normalize()).sum())
    if n_time:
        raise DataValidationError(
            f"{name}: {n_time} dates carry a time-of-day component; expected UTC calendar days")
    n_dup = int(out.duplicated([pid, date]).sum())
    if n_dup:
        raise DataValidationError(f"{name}: {n_dup} duplicate participant-date keys")
    return out


def load_features(cfg: Config) -> pd.DataFrame:
    return normalize_keys(read_table(cfg.path("features")), cfg, "features")


def load_labels(cfg: Config) -> pd.DataFrame:
    labels = normalize_keys(read_table(cfg.path("labels")), cfg, "labels")
    required = [cfg.col(k) for k in LABEL_COLUMN_KEYS]
    missing = [c for c in required if c not in labels.columns]
    if missing:
        raise DataValidationError(f"labels: missing columns {missing}")
    labels[cfg.col("matched_event_date")] = pd.to_datetime(
        labels[cfg.col("matched_event_date")], utc=True, errors="coerce")
    return labels


def join_features_labels(features: pd.DataFrame, labels: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """One-to-one join on (participant, date); key sets must be identical."""
    pid, date = cfg.pid, cfg.date
    label_cols = [cfg.col(k) for k in LABEL_COLUMN_KEYS]
    clash = [c for c in label_cols if c in features.columns]
    if clash:
        raise DataValidationError(f"features already contain label columns: {clash}")

    f_keys = pd.MultiIndex.from_frame(features[[pid, date]])
    l_keys = pd.MultiIndex.from_frame(labels[[pid, date]])
    only_f = len(f_keys.difference(l_keys))
    only_l = len(l_keys.difference(f_keys))
    if only_f or only_l:
        raise DataValidationError(
            f"feature/label keys differ: {only_f} feature-only rows, {only_l} label-only rows")

    merged = features.merge(labels[[pid, date] + label_cols], on=[pid, date],
                            how="inner", validate="one_to_one")
    if len(merged) != len(features):
        raise DataValidationError("join changed the number of rows")
    return merged.sort_values([pid, date], kind="mergesort").reset_index(drop=True)


def load_merged(cfg: Config) -> pd.DataFrame:
    return join_features_labels(load_features(cfg), load_labels(cfg), cfg)
