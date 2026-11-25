"""Fully synthetic test data. No real participant data is used anywhere in the tests.

Labels are produced by an independent re-implementation of the notebook-06
rules so the package code is checked against a separate reference.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

HORIZON = 7
START = pd.Timestamp("2031-01-01", tz="UTC")


def _participants():
    # (participant id, number of days, event day offsets relative to first date, has event file)
    return [
        ("SYN-E01", 70, [20, 45], True),
        ("SYN-E02", 60, [30], True),
        ("SYN-E03", 80, [15, 60], True),
        ("SYN-E04", 50, [25], True),
        ("SYN-E05", 65, [40], True),
        ("SYN-E06", 55, [10], True),
        ("SYN-E07", 75, [35], True),
        # Event-file participants whose events cannot produce positives:
        ("SYN-X01", 40, [0], True),        # event on the first feature date
        ("SYN-X02", 45, [44 + 20], True),  # event > 7 days after the last feature date
        # Participants without an event file (no recorded exacerbations):
        ("SYN-N01", 60, [], False),
        ("SYN-N02", 30, [], False),
        ("SYN-N03", 50, [], False),
        ("SYN-N04", 6, [], False),         # too short: never a full 7-day window
    ]


def reference_labels(features: pd.DataFrame, events: pd.DataFrame, file_pids: set) -> pd.DataFrame:
    rows = []
    last = features.groupby("Participant_ID")["Date"].max()
    for pid, d in zip(features["Participant_ID"], features["Date"]):
        evs = events.loc[(events["participant"] == pid), "event_date"].sort_values()
        hit = evs[(evs > d) & (evs <= d + pd.Timedelta(days=HORIZON))]
        if len(hit):
            rows.append((pid, d, 1.0, "positive_documented_event", hit.iloc[0], "Moderate"))
        elif pid not in file_pids:
            rows.append((pid, d, np.nan, "unknown_no_event_file", pd.NaT, None))
        elif d + pd.Timedelta(days=HORIZON) > last[pid]:
            rows.append((pid, d, np.nan, "unknown_incomplete_followup", pd.NaT, None))
        else:
            rows.append((pid, d, 0.0, "negative_full_followup", pd.NaT, None))
    out = pd.DataFrame(rows, columns=["Participant_ID", "Date", "exacerbation_within_7d", "label_status",
                                      "matched_event_date", "matched_event_severity"])
    out["matched_event_date"] = pd.to_datetime(out["matched_event_date"], utc=True)
    return out


def make_synthetic(seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    feat_rows, ev_rows, file_pids = [], [], set()
    for i, (pid, n_days, offsets, has_file) in enumerate(_participants()):
        first = START + pd.Timedelta(days=3 * i)
        dates = pd.date_range(first, periods=n_days, freq="D")
        for d in dates:
            feat_rows.append((pid, d))
        if has_file:
            file_pids.add(pid)
            for o in offsets:
                ev_rows.append((pid, first + pd.Timedelta(days=o), "Moderate" if o % 2 else "Severe"))

    f = pd.DataFrame(feat_rows, columns=["Participant_ID", "Date"])
    n = len(f)
    base = rng.normal(size=n)
    f["BRI_mean"] = np.where(rng.random(n) < 0.3, np.nan, base)
    f["BRI_mean_rolling_7d_mean"] = rng.normal(size=n)
    f["BRI_mean_rolling_14d_mean"] = rng.normal(size=n)
    f["BRI_mean_baseline_count"] = f.groupby("Participant_ID").cumcount().astype("int64")
    f["BRI_mean_baseline_deviation"] = rng.normal(size=n)
    f["MI_flag"] = pd.Series(rng.random(n) < 0.5, dtype="object")
    f.loc[rng.random(n) < 0.1, "MI_flag"] = None
    f["SQI_copy_of_BRI_mean"] = f["BRI_mean"]                 # exact duplicate
    f["EI_constant"] = 1.0                                   # constant
    f["PRVI_sparse"] = np.where(rng.random(n) < 0.99, np.nan, rng.normal(size=n))
    f["SII_availability"] = (rng.random(n) < 0.7).astype("int64")
    f["UNDOCUMENTED_extra"] = rng.normal(size=n)             # not in the dictionary

    events = pd.DataFrame(ev_rows, columns=["participant", "event_date", "severity"])
    events["participant"] = events["participant"].astype("string")
    labels = reference_labels(f, events, file_pids)

    dictionary = pd.DataFrame({
        "Feature": ["BRI_mean", "BRI_mean_rolling_7d_mean", "BRI_mean_rolling_14d_mean",
                    "BRI_mean_baseline_count", "BRI_mean_baseline_deviation", "MI_flag",
                    "SQI_copy_of_BRI_mean", "EI_constant", "PRVI_sparse", "SII_availability"],
        "Feature_Group": ["Daily", "Rolling", "Rolling", "Baseline", "Baseline", "Daily",
                          "Daily", "Daily", "Daily", "Data Quality"],
        "Time_Window": ["Current calendar day", "Previous 7 calendar days", "Previous 14 calendar days",
                        "All previous calendar days", "Current calendar day", "Current calendar day",
                        "Current calendar day", "Current calendar day", "Current calendar day",
                        "Current calendar day"],
    })
    return {"features": f, "labels": labels, "events": events, "dictionary": dictionary,
            "file_pids": file_pids}


def write_synthetic_project(root, data: dict) -> None:
    """Write the synthetic tables to the configured locations under root."""
    from pathlib import Path

    root = Path(root)
    (root / "data/processed/features").mkdir(parents=True, exist_ok=True)
    (root / "data/processed/labels").mkdir(parents=True, exist_ok=True)
    f = data["features"].copy()
    f["MI_flag"] = f["MI_flag"].astype("boolean")
    f.to_parquet(root / "data/processed/features/final_feature_dataset.parquet", index=False)
    data["labels"].to_parquet(root / "data/processed/labels/exacerbation_labels_7d.parquet", index=False)
    data["dictionary"].to_csv(root / "data/processed/features/feature_dictionary.csv", index=False)
    idx = root / "data/raw/TOLIFE_COPD_Dataset/index"
    for pid, g in data["events"].groupby("participant"):
        d = idx / str(pid)
        d.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"Date": g["event_date"].dt.strftime("%Y-%m-%d"), "PatientId": 0,
                      "Kit-id": g["participant"], "Type": g["severity"]}).to_csv(d / "exacerbations.csv", index=False)
