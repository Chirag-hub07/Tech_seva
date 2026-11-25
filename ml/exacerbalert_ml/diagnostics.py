"""Aggregate-only diagnostics of label coverage.

Explains why participants that HAVE an event file receive no positive
seven-day label. Results are counts only - no identifiers or dates.

A feature row on date d is positive when an event e satisfies d < e <= d + H.
With a complete daily calendar from first to last feature date, an event can
produce a positive row only if first < e <= last + H.
"""

from __future__ import annotations

import pandas as pd

from .config import Config
from .events import EVENT_DATE, EVENT_PID, EVENT_SEVERITY

REASONS = (
    "participant_has_no_feature_rows",
    "event_date_missing_or_unparseable",
    "severity_not_counted_as_positive",
    "event_on_or_before_first_feature_date",
    "event_more_than_horizon_after_last_feature_date",
    "event_within_predictable_range",  # unexpected for a participant without positives
)


def classify_event(event_date, severity, first, last, cfg: Config) -> str:
    if pd.isna(first) or pd.isna(last):
        return "participant_has_no_feature_rows"
    if pd.isna(event_date):
        return "event_date_missing_or_unparseable"
    if severity not in set(cfg["target"]["positive_severities"]):
        return "severity_not_counted_as_positive"
    if event_date <= first:
        return "event_on_or_before_first_feature_date"
    if event_date > last + pd.Timedelta(days=cfg.horizon_days):
        return "event_more_than_horizon_after_last_feature_date"
    return "event_within_predictable_range"


def explain_event_participants_without_positives(frame: pd.DataFrame, raw_events: pd.DataFrame,
                                                 cfg: Config, target_col: str | None = None) -> dict:
    """Count, by reason, why event-file participants have no positive labels."""
    target_col = target_col or cfg.col("original_target")
    pid = frame[cfg.pid].astype("string")
    span = frame.groupby(pid)[cfg.date].agg(["min", "max"])
    positives = frame.loc[frame[target_col] == 1].groupby(pid[frame[target_col] == 1]).size()

    ev = raw_events.copy()
    ev[EVENT_PID] = ev[EVENT_PID].astype("string")
    event_pids = set(ev[EVENT_PID].dropna())
    without_pos = sorted(p for p in event_pids if positives.get(p, 0) == 0)

    event_reasons = {r: 0 for r in REASONS}
    participant_patterns: dict[str, int] = {}
    for p in without_pos:
        first = span["min"].get(p, pd.NaT)
        last = span["max"].get(p, pd.NaT)
        reasons = []
        for _, row in ev[ev[EVENT_PID] == p].iterrows():
            r = classify_event(row[EVENT_DATE], row.get(EVENT_SEVERITY), first, last, cfg)
            event_reasons[r] += 1
            reasons.append(r)
        key = " + ".join(sorted(set(reasons))) or "no_events_in_file"
        participant_patterns[key] = participant_patterns.get(key, 0) + 1

    return {
        "participants_with_event_files": len(event_pids),
        "participants_with_event_files_but_no_positive_labels": len(without_pos),
        "events_of_those_participants": int(sum(event_reasons.values())),
        "events_by_reason": event_reasons,
        "participants_by_reason_pattern": participant_patterns,
    }
