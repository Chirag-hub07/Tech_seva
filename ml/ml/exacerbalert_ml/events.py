"""Documented events and post-event exclusion.

Post-event rows (the event day and the following washout days) describe a
participant who is already exacerbating or recovering. The primary pre-event
analysis excludes them; sensitivity analyses vary or disable the washout.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import Config
from .data import DataValidationError

EVENT_PID = "participant"
EVENT_DATE = "event_date"
EVENT_SEVERITY = "severity"


def events_from_labels(frame: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Unique (participant, event date) pairs referenced by the labels.

    This is a lower bound on the true event list: events that no feature row
    can predict (e.g. on/before the first feature date) are absent.
    """
    m = pd.to_datetime(frame[cfg.col("matched_event_date")], utc=True, errors="coerce")
    ev = pd.DataFrame({EVENT_PID: frame[cfg.pid].astype("string"), EVENT_DATE: m})
    return ev.dropna().drop_duplicates().sort_values([EVENT_PID, EVENT_DATE]).reset_index(drop=True)


def load_raw_events(cfg: Config, index_dir: str | Path | None = None) -> pd.DataFrame:
    """Read every exacerbations.csv under the raw TOLIFE index directory."""
    root = Path(index_dir) if index_dir is not None else cfg.path("raw_event_index_dir")
    if not root.is_dir():
        raise FileNotFoundError("raw event index directory not found")
    files = sorted(root.rglob("exacerbations.csv"))
    pcol, dcol, scol = (cfg.col("raw_event_participant"), cfg.col("raw_event_date"),
                        cfg.col("raw_event_severity"))
    frames = []
    for f in files:
        df = pd.read_csv(f)
        missing = [c for c in (pcol, dcol, scol) if c not in df.columns]
        if missing:
            raise DataValidationError(f"an event file is missing columns {missing}")
        frames.append(pd.DataFrame({
            EVENT_PID: df[pcol].astype("string").str.strip(),
            EVENT_DATE: pd.to_datetime(df[dcol], utc=True, errors="coerce"),
            EVENT_SEVERITY: df[scol].astype("string").str.strip(),
        }))
    if not frames:
        return pd.DataFrame({EVENT_PID: pd.Series(dtype="string"),
                             EVENT_DATE: pd.Series(dtype="datetime64[ns, UTC]"),
                             EVENT_SEVERITY: pd.Series(dtype="string")})
    out = pd.concat(frames, ignore_index=True)
    out.attrs["n_event_files"] = len(files)
    return out


def days_since_last_event(frame: pd.DataFrame, events: pd.DataFrame, cfg: Config) -> pd.Series:
    """Days from the most recent event on or before each row's date (NaN if none)."""
    result = pd.Series(np.nan, index=frame.index, dtype="float64")
    ev = events.dropna(subset=[EVENT_DATE])
    by_pid = {p: np.sort(g[EVENT_DATE].to_numpy()) for p, g in ev.groupby(EVENT_PID)}
    pid = frame[cfg.pid].astype("string")
    dates = frame[cfg.date]
    for p, idx in frame.groupby(pid, sort=False).groups.items():
        evs = by_pid.get(p)
        if evs is None or len(evs) == 0:
            continue
        d = dates.loc[idx].to_numpy()
        pos = np.searchsorted(evs, d, side="right") - 1
        valid = pos >= 0
        vals = np.full(len(d), np.nan)
        vals[valid] = (d[valid] - evs[pos[valid]]) / np.timedelta64(1, "D")
        result.loc[idx] = vals
    return result


def post_event_mask(frame: pd.DataFrame, events: pd.DataFrame, cfg: Config,
                    washout_days: int | None) -> pd.Series:
    """True for rows to EXCLUDE: event day through washout_days afterwards.

    washout_days=None disables the exclusion (all False).
    """
    if washout_days is None:
        return pd.Series(False, index=frame.index)
    if washout_days < 0:
        raise ValueError("washout_days must be >= 0 or None")
    ds = days_since_last_event(frame, events, cfg)
    return ds.between(0, washout_days, inclusive="both").fillna(False).astype(bool)
