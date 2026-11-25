"""Evaluation: row-level metrics, threshold selection, calibration,
event-level performance and participant-level bootstrap intervals.

All functions take arrays/frames in memory and return aggregates only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import (average_precision_score, brier_score_loss, confusion_matrix,
                             roc_auc_score)


# ---------------------------------------------------------------------------
# Threshold selection (on training-side out-of-fold predictions only)
# ---------------------------------------------------------------------------
def select_threshold(y, p, strategy: str = "target_sensitivity", target_sensitivity: float = 0.8) -> float:
    y, p = np.asarray(y, int), np.asarray(p, float)
    if y.sum() == 0:
        return 0.5
    cands = np.unique(p)[::-1]                          # high -> low
    if strategy == "target_sensitivity":
        pos = p[y == 1]
        for t in cands:                                  # highest threshold meeting the target
            if (pos >= t).mean() >= target_sensitivity:
                return float(t)
        return float(cands[-1])
    if strategy == "max_f1":
        best_t, best_f1 = 0.5, -1.0
        for t in cands:
            pred = p >= t
            tp = int((pred & (y == 1)).sum())
            fp, fn = int((pred & (y == 0)).sum()), int((~pred & (y == 1)).sum())
            f1 = 0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn)
            if f1 > best_f1:
                best_t, best_f1 = float(t), f1
        return best_t
    raise ValueError(f"unknown threshold strategy: {strategy}")


# ---------------------------------------------------------------------------
# Row-level metrics
# ---------------------------------------------------------------------------
def _safe(fn, *a):
    try:
        return float(fn(*a))
    except ValueError:
        return float("nan")


def row_metrics(y, p, threshold: float, alerts=None) -> dict:
    """Metrics at a threshold. `alerts` overrides p >= threshold (used when pooled
    folds were scored with different fold-specific thresholds)."""
    y, p = np.asarray(y, int), np.asarray(p, float)
    pred = (p >= threshold).astype(int) if alerts is None else np.asarray(alerts, int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    precision = tp / (tp + fp) if tp + fp else float("nan")
    recall = tp / (tp + fn) if tp + fn else float("nan")
    specificity = tn / (tn + fp) if tn + fp else float("nan")
    f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
    single = len(np.unique(y)) < 2
    return {
        "n_rows": int(len(y)), "n_positive": int(y.sum()), "prevalence": float(y.mean()) if len(y) else float("nan"),
        "threshold": float(threshold),
        "tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn),
        "precision": float(precision), "recall_sensitivity": float(recall),
        "specificity": float(specificity), "f1": float(f1),
        "roc_auc": float("nan") if single else _safe(roc_auc_score, y, p),
        "pr_auc_average_precision": float("nan") if single else _safe(average_precision_score, y, p),
        "brier": _safe(brier_score_loss, y, p),
    }


def calibration_table(y, p, n_bins: int = 10) -> pd.DataFrame:
    """Quantile-binned reliability table (aggregates per bin)."""
    y, p = np.asarray(y, int), np.asarray(p, float)
    if len(y) == 0:
        return pd.DataFrame(columns=["bin", "n", "mean_predicted", "observed_rate"])
    edges = np.unique(np.quantile(p, np.linspace(0, 1, n_bins + 1)))
    bins = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, max(len(edges) - 2, 0))
    df = pd.DataFrame({"bin": bins, "y": y, "p": p})
    return (df.groupby("bin").agg(n=("y", "size"), mean_predicted=("p", "mean"), observed_rate=("y", "mean"))
            .reset_index())


def calibration_slope_intercept(y, p) -> dict:
    """Logistic recalibration of y on logit(p). Slope 1 / intercept 0 = well calibrated."""
    from sklearn.linear_model import LogisticRegression

    y, p = np.asarray(y, int), np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    if len(np.unique(y)) < 2:
        return {"calibration_slope": float("nan"), "calibration_intercept": float("nan")}
    logit = np.log(p / (1 - p)).reshape(-1, 1)
    m = LogisticRegression(C=1e6, max_iter=1000).fit(logit, y)
    return {"calibration_slope": float(m.coef_[0, 0]), "calibration_intercept": float(m.intercept_[0])}


# ---------------------------------------------------------------------------
# Event-level performance
# ---------------------------------------------------------------------------
def event_level(groups, dates, alerts, events: pd.DataFrame, window_days: int = 7) -> dict:
    """An event is DETECTED if any modelled prediction day in [e - window, e - 1] raised an alert.

    Only events with at least one modelled prediction day in that window are
    "evaluable". False alerts are alerts on days with no event in the next
    window_days; reported per participant-week of modelled days.
    events: columns participant, event_date (raw event list).
    """
    g = pd.Series(np.asarray(groups)).astype("string").to_numpy()
    d = pd.to_datetime(pd.Series(dates), utc=True).to_numpy()
    a = np.asarray(alerts, bool)
    window = np.timedelta64(window_days, "D")
    day = np.timedelta64(1, "D")
    evaluable = detected = 0
    lead_days = []
    covered_by_event = np.zeros(len(g), dtype=bool)
    ev = events.dropna(subset=["event_date"]).copy()
    ev["participant"] = ev["participant"].astype("string")
    for p_id, e_dates in ev.groupby("participant")["event_date"]:
        rows = np.flatnonzero(g == p_id)
        if len(rows) == 0:
            continue
        for e in pd.to_datetime(e_dates, utc=True).to_numpy():
            in_win = rows[(d[rows] >= e - window) & (d[rows] <= e - day)]
            covered_by_event[in_win] = True
            if len(in_win) == 0:
                continue
            evaluable += 1
            hit = in_win[a[in_win]]
            if len(hit):
                detected += 1
                lead_days.append(float((e - d[hit].min()) / day))
    false_alerts = int((a & ~covered_by_event).sum())
    weeks = len(g) / 7.0
    return {
        "events_evaluable": int(evaluable), "events_detected": int(detected),
        "event_sensitivity": float(detected / evaluable) if evaluable else float("nan"),
        "median_lead_days": float(np.median(lead_days)) if lead_days else float("nan"),
        "false_alerts": false_alerts,
        "false_alerts_per_participant_week": float(false_alerts / weeks) if weeks else float("nan"),
    }


# ---------------------------------------------------------------------------
# Participant-level bootstrap
# ---------------------------------------------------------------------------
def bootstrap_ci(y, p, groups, threshold: float, n_resamples: int = 200, seed: int = 0,
                 metrics=("roc_auc", "pr_auc_average_precision", "recall_sensitivity", "specificity", "brier"),
                 alpha: float = 0.05) -> dict:
    """Resample PARTICIPANTS with replacement; percentile intervals for the given metrics."""
    y, p = np.asarray(y, int), np.asarray(p, float)
    g = pd.Series(np.asarray(groups)).astype("string").to_numpy()
    ids = np.unique(g)
    rows_of = {i: np.flatnonzero(g == i) for i in ids}
    rng = np.random.default_rng(seed)
    draws = {m: [] for m in metrics}
    for _ in range(n_resamples):
        pick = rng.choice(ids, size=len(ids), replace=True)
        idx = np.concatenate([rows_of[i] for i in pick])
        res = row_metrics(y[idx], p[idx], threshold)
        for m in metrics:
            draws[m].append(res[m])
    out = {}
    for m, v in draws.items():
        v = np.asarray(v, float)
        v = v[np.isfinite(v)]
        out[f"{m}_ci_low"] = float(np.quantile(v, alpha / 2)) if len(v) else float("nan")
        out[f"{m}_ci_high"] = float(np.quantile(v, 1 - alpha / 2)) if len(v) else float("nan")
    return out
