"""Assemble the supervised modelling dataset.

Steps: one-to-one join -> label policy -> drop unknown targets -> optional
post-event exclusion -> predictor allowlist. Unknown targets are never kept.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .config import Config
from .data import LABEL_COLUMN_KEYS
from .events import events_from_labels, load_raw_events, post_event_mask
from .features import assert_no_banned, select_predictors
from .labels import apply_label_policy, label_summary


@dataclass
class ModelingData:
    X: pd.DataFrame          # predictors only
    y: pd.Series             # 0/1
    groups: pd.Series        # participant IDs - for splitting only, never a feature
    dates: pd.Series         # for event-level evaluation only, never a feature
    predictors: list[str]
    info: dict = field(default_factory=dict)


def resolve_events(labelled: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    source = cfg["post_event"].get("event_source", "labels")
    if source == "raw":
        return load_raw_events(cfg)
    if source == "labels":
        return events_from_labels(labelled, cfg)
    raise ValueError(f"unknown event_source: {source}")


def build_modeling_data(merged: pd.DataFrame, dictionary: pd.DataFrame, cfg: Config,
                        washout_days: int | None = "primary", feature_set: str = "all",
                        label_policy: str | None = None, events: pd.DataFrame | None = None) -> ModelingData:
    """washout_days="primary" uses post_event.primary_washout_days; None disables exclusion."""
    if washout_days == "primary":
        washout_days = cfg["post_event"]["primary_washout_days"]

    labelled = apply_label_policy(merged, cfg, label_policy)
    if events is None:
        events = resolve_events(labelled, cfg)

    known = labelled["target"].notna()
    excluded_post = post_event_mask(labelled, events, cfg, washout_days)
    keep = known & ~excluded_post
    data = labelled.loc[keep].reset_index(drop=True)

    label_cols = {cfg.col(k) for k in LABEL_COLUMN_KEYS}
    feature_table_columns = [c for c in merged.columns if c not in label_cols]
    predictors, feat_report = select_predictors(feature_table_columns, dictionary, cfg, feature_set)
    assert_no_banned(predictors, cfg)

    info = {
        "label_policy": label_policy or cfg["target"]["label_policy"],
        "washout_days": washout_days,
        "labels_before_exclusion": label_summary(labelled, cfg),
        "post_event_rows_excluded_known": int((known & excluded_post).sum()),
        "post_event_positive_rows_excluded": int((excluded_post & (labelled["target"] == 1)).sum()),
        "modelling_rows": int(len(data)),
        "modelling_positive_rows": int((data["target"] == 1).sum()),
        "modelling_participants": int(data[cfg.pid].nunique()),
        "features": feat_report,
    }
    return ModelingData(
        X=data[predictors], y=data["target"].astype("int64"),
        groups=data[cfg.pid].astype("string"), dates=data[cfg.date],
        predictors=predictors, info=info)
