"""Label policy: derive the modelling target from the notebook-06 labels.

The original label file is never modified. A new `target` column (1 / 0 / NaN)
and a `target_status` column are added to a copy of the merged table.

Rules
- Unknown is never silently converted to negative.
- "original" policy: target == exacerbation_within_7d.
- "tolife_v1_absent_file_negative" policy (TOLIFE V1.0 README: an absent
  exacerbations.csv means no exacerbations were recorded): rows with status
  `unknown_no_event_file` become 0 only when the whole window
  (Date, Date + horizon] lies on or before the participant's last available
  feature date; otherwise they remain NaN. All other rows keep their original
  value, including `unknown_incomplete_followup` rows (NaN).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Config
from .data import DataValidationError

POSITIVE = "positive_documented_event"
NEGATIVE = "negative_full_followup"
UNKNOWN_NO_FILE = "unknown_no_event_file"
UNKNOWN_INCOMPLETE = "unknown_incomplete_followup"
ORIGINAL_STATUSES = {POSITIVE, NEGATIVE, UNKNOWN_NO_FILE, UNKNOWN_INCOMPLETE}

# Statuses produced by the TOLIFE policy for no-event-file participants.
NEGATIVE_NO_RECORDED_EVENTS = "negative_no_recorded_events_full_followup"
UNKNOWN_NO_FILE_INCOMPLETE = "unknown_no_event_file_incomplete_followup"

POLICIES = ("original", "tolife_v1_absent_file_negative")


def validate_original_labels(frame: pd.DataFrame, cfg: Config) -> None:
    """Check that the notebook-06 status and target columns agree."""
    y = frame[cfg.col("original_target")]
    status = frame[cfg.col("label_status")].astype("string")
    unexpected = set(status.dropna().unique()) - ORIGINAL_STATUSES
    if unexpected or status.isna().any():
        raise DataValidationError(
            f"unexpected label_status values ({len(unexpected)} kinds) or missing statuses")
    bad_values = ~(y.isna() | y.isin([0, 1]))
    if bad_values.any():
        raise DataValidationError(f"{int(bad_values.sum())} target values are not 0, 1 or NaN")
    expected = {POSITIVE: 1, NEGATIVE: 0}
    for st, val in expected.items():
        n_bad = int(((status == st) & (y != val)).sum())
        if n_bad:
            raise DataValidationError(f"{n_bad} rows with status {st} do not have target {val}")
    for st in (UNKNOWN_NO_FILE, UNKNOWN_INCOMPLETE):
        n_bad = int(((status == st) & y.notna()).sum())
        if n_bad:
            raise DataValidationError(f"{n_bad} rows with status {st} have a non-missing target")


def participant_last_dates(frame: pd.DataFrame, cfg: Config) -> pd.Series:
    return frame.groupby(cfg.pid)[cfg.date].transform("max")


def apply_label_policy(frame: pd.DataFrame, cfg: Config, policy: str | None = None) -> pd.DataFrame:
    """Return a copy with `target` and `target_status` columns added."""
    policy = policy or cfg["target"]["label_policy"]
    if policy not in POLICIES:
        raise ValueError(f"unknown label policy: {policy}")
    validate_original_labels(frame, cfg)

    out = frame.copy()
    y = out[cfg.col("original_target")].astype("float64")
    status = out[cfg.col("label_status")].astype("string")
    out["target"] = y
    out["target_status"] = status

    if policy == "tolife_v1_absent_file_negative":
        no_file = status == UNKNOWN_NO_FILE
        # A participant without an event file must have no positive rows.
        pid = out[cfg.pid]
        no_file_pids = set(pid[no_file])
        n_conflict = int((pid.isin(no_file_pids) & (status == POSITIVE)).sum())
        if n_conflict:
            raise DataValidationError(
                f"{n_conflict} positive rows belong to participants marked as having no event file")
        window_end = out[cfg.date] + pd.Timedelta(days=cfg.horizon_days)
        covered = window_end <= participant_last_dates(out, cfg)
        to_negative = no_file & covered
        out.loc[to_negative, "target"] = 0.0
        out.loc[to_negative, "target_status"] = NEGATIVE_NO_RECORDED_EVENTS
        out.loc[no_file & ~covered, "target_status"] = UNKNOWN_NO_FILE_INCOMPLETE

    # Safety: positives and unknown-incomplete rows are never altered.
    assert (out.loc[status == POSITIVE, "target"] == 1).all()
    assert out.loc[status == UNKNOWN_INCOMPLETE, "target"].isna().all()
    return out


def label_summary(frame: pd.DataFrame, cfg: Config, target_col: str = "target") -> dict:
    """Aggregate label counts. Contains no identifiers."""
    y = frame[target_col]
    pid = frame[cfg.pid]
    known = y.notna()
    per_pid = pd.DataFrame({"pid": pid, "known": known, "pos": y == 1}).groupby("pid").agg(
        known=("known", "sum"), pos=("pos", "sum"))
    status_col = "target_status" if "target_status" in frame.columns else cfg.col("label_status")
    return {
        "rows": int(len(frame)),
        "known": int(known.sum()),
        "positive": int((y == 1).sum()),
        "negative": int((y == 0).sum()),
        "unknown": int(y.isna().sum()),
        "positive_rate_known": float((y == 1).sum() / known.sum()) if known.any() else float("nan"),
        "participants": int(per_pid.shape[0]),
        "participants_with_known": int((per_pid["known"] > 0).sum()),
        "participants_with_positive": int((per_pid["pos"] > 0).sum()),
        "status_counts": {str(k): int(v) for k, v in
                          frame[status_col].astype("string").value_counts(dropna=False).items()},
    }
