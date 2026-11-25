"""Training engine (in memory; no file I/O).

Nested, participant-grouped cross-validation:
  outer: repeated participant-stratified K-fold (splits.outer_splits)
    inner: participant-grouped K-fold on the OUTER-TRAINING participants only
      -> choose hyper-parameters by the tuning metric on inner out-of-fold predictions
      -> choose the alert threshold on the same inner out-of-fold predictions
    refit on all outer-training rows, score the outer-test participants once.
Every learned step is inside the model Pipeline, so it is fitted on training
rows only. Outer-test participants never influence tuning, thresholds or fitting.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from .config import Config
from .evaluate import (bootstrap_ci, calibration_slope_intercept, calibration_table, event_level,
                       row_metrics, select_threshold)
from .models import build_pipeline, enabled_models, param_grid
from .splits import SplitError, assert_group_separation, assign_participant_folds, inner_splits, outer_splits

TUNING_METRICS = {"average_precision": average_precision_score, "roc_auc": roc_auc_score}


@dataclass
class CVResult:
    per_split: pd.DataFrame                       # one row per (model, repeat, fold): aggregates only
    summary: pd.DataFrame                         # one row per model: mean/std across splits
    pooled: dict = field(default_factory=dict)    # model -> pooled repeat-0 metrics, CIs, calibration
    split_summary: pd.DataFrame | None = None
    by_repeat: pd.DataFrame | None = None         # one row per (model, repeat): mean over that repeat's folds


def _proba(pipe, X):
    p = pipe.predict_proba(X)
    return p[:, 1] if p.shape[1] == 2 else np.zeros(len(X))


def _inner(groups, y, train_idx, cfg: Config):
    sc = cfg["splits"]
    return inner_splits(groups, y, train_idx, int(sc["inner_n_splits"]), int(sc["inner_seed"]),
                        int(sc.get("min_positive_participants_per_test_fold", 1)))


def plan_splits(groups, y, cfg: Config, n_repeats: int | None = None):
    """Build every outer AND inner split before any model is fitted.

    Raises SplitError if the configured design is infeasible; the design is
    never weakened automatically.
    """
    sc = cfg["splits"]
    seeds = list(sc["outer_seeds"])[: (n_repeats or len(sc["outer_seeds"]))]
    outer = outer_splits(groups, y, int(sc["outer_n_splits"]), seeds,
                         int(sc.get("min_positive_participants_per_test_fold", 1)))
    plan = []
    for s in outer:
        assert_group_separation(groups, s.train_idx, s.test_idx)
        try:
            inner = _inner(groups, y, s.train_idx, cfg)
        except SplitError as exc:
            raise SplitError(f"inner split infeasible in repeat {s.repeat + 1} fold {s.fold}: {exc}") from exc
        for i in inner:
            assert_group_separation(groups, i.train_idx, i.test_idx)
            if len(np.setdiff1d(np.concatenate([i.train_idx, i.test_idx]), s.train_idx)):
                raise SplitError("an inner split uses rows outside the outer training set")
        plan.append((s, inner))
    return seeds, plan


def tune_on_inner(name, X, y, groups, train_idx, predictors, cfg: Config, seed: int, inner=None):
    """Choose params and threshold using inner grouped folds of train_idx only."""
    tr = cfg["training"]
    if inner is None:
        inner = _inner(groups, y, train_idx, cfg)
    metric = TUNING_METRICS[tr["tuning_metric"]]
    best = None
    for params in param_grid(name, cfg):
        oof = pd.Series(np.nan, index=train_idx)
        for s in inner:
            assert_group_separation(groups, s.train_idx, s.test_idx)
            pipe = build_pipeline(name, predictors, cfg, params, seed)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                pipe.fit(X.iloc[s.train_idx], y[s.train_idx])
            oof.loc[s.test_idx] = _proba(pipe, X.iloc[s.test_idx])
        yo = y[oof.index.to_numpy()]
        try:
            score = float(metric(yo, oof.to_numpy()))
        except ValueError:
            score = float("nan")
        if best is None or (np.isfinite(score) and (not np.isfinite(best[0]) or score > best[0])):
            best = (score, params, oof)
    score, params, oof = best
    thr = select_threshold(y[oof.index.to_numpy()], oof.to_numpy(), tr["threshold_strategy"],
                           float(tr["target_sensitivity"]))
    return params, thr, score


def run_cv(X: pd.DataFrame, y, groups, dates, events: pd.DataFrame, predictors, cfg: Config,
           models=None, n_repeats: int | None = None, progress=None) -> CVResult:
    """Nested grouped CV for each enabled model. Returns aggregates only."""
    y = np.asarray(y, int)
    groups = np.asarray(pd.Series(groups).astype("string"))
    tr, ev_cfg = cfg["training"], cfg["evaluation"]
    seeds, plan = plan_splits(groups, y, cfg, n_repeats)
    splits = [s for s, _ in plan]
    seed = int(tr["random_seed"])
    dates = pd.Series(pd.to_datetime(pd.Series(dates).reset_index(drop=True), utc=True))
    records, pooled = [], {}
    for name in enabled_models(cfg, models):
        pooled_p = {r: np.full(len(y), np.nan) for r in range(len(seeds))}
        pooled_a = {r: np.zeros(len(y), bool) for r in range(len(seeds))}
        for s, inner in plan:
            assert_group_separation(groups, s.train_idx, s.test_idx)
            params, thr, inner_score = tune_on_inner(name, X, y, groups, s.train_idx, predictors, cfg,
                                                     seed, inner)
            pipe = build_pipeline(name, predictors, cfg, params, seed)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                pipe.fit(X.iloc[s.train_idx], y[s.train_idx])
            p_test = _proba(pipe, X.iloc[s.test_idx])
            alerts = p_test >= thr
            pooled_p[s.repeat][s.test_idx] = p_test
            pooled_a[s.repeat][s.test_idx] = alerts
            rm = row_metrics(y[s.test_idx], p_test, thr)
            em = event_level(groups[s.test_idx], dates.iloc[s.test_idx], alerts, events,
                             int(ev_cfg["event_window_days"]))
            records.append({"model": name, "repeat": s.repeat, "seed": s.seed, "fold": s.fold,
                            "train_participants": len(set(groups[s.train_idx])),
                            "test_participants": len(set(groups[s.test_idx])),
                            "params": repr(params), "inner_tuning_score": inner_score, **rm, **em})
            if progress:
                progress(f"{name}: repeat {s.repeat + 1}/{len(seeds)} fold {s.fold} done")
        # Pooled out-of-fold predictions of repeat 0 (one prediction per participant-day).
        p0, a0 = pooled_p[0], pooled_a[0]
        ok = np.isfinite(p0)
        pooled[name] = {
            # Fold-specific thresholds: the pooled alerts are used as given.
            "metrics": row_metrics(y[ok], p0[ok], float("nan"), alerts=a0[ok]),
            "event_level": event_level(groups[ok], dates[ok], a0[ok], events, int(ev_cfg["event_window_days"])),
            "bootstrap_ci": _pooled_bootstrap(y[ok], p0[ok], a0[ok], groups[ok], ev_cfg, seed),
            "calibration": calibration_table(y[ok], p0[ok], int(ev_cfg["calibration_bins"])),
            "calibration_fit": calibration_slope_intercept(y[ok], p0[ok]),
        }
    per_split = pd.DataFrame(records)
    return CVResult(per_split=per_split, summary=summarise(per_split), pooled=pooled,
                    split_summary=split_table(groups, y, splits), by_repeat=summarise_by_repeat(per_split))


def _pooled_bootstrap(y, p, alerts, groups, ev_cfg, seed):
    # Threshold-dependent metrics use the fold-specific alerts; encode them as p' so
    # that p' >= 0.5 <=> alert, while ROC/PR/Brier use the original probabilities.
    ci = bootstrap_ci(y, p, groups, threshold=0.5, n_resamples=int(ev_cfg["bootstrap_resamples"]), seed=seed,
                      metrics=("roc_auc", "pr_auc_average_precision", "brier"))
    ci_thr = bootstrap_ci(y, alerts.astype(float), groups, threshold=0.5,
                          n_resamples=int(ev_cfg["bootstrap_resamples"]), seed=seed,
                          metrics=("recall_sensitivity", "specificity", "precision"))
    return {**ci, **ci_thr}


METRIC_COLUMNS = ["roc_auc", "pr_auc_average_precision", "brier", "precision", "recall_sensitivity",
                  "specificity", "f1", "event_sensitivity", "false_alerts_per_participant_week"]


def summarise(per_split: pd.DataFrame) -> pd.DataFrame:
    if per_split.empty:
        return pd.DataFrame()
    rows = []
    for name, g in per_split.groupby("model", sort=False):
        row = {"model": name, "splits": len(g)}
        for m in METRIC_COLUMNS:
            v = g[m].astype(float)
            row[f"{m}_mean"], row[f"{m}_std"] = float(v.mean()), float(v.std(ddof=1)) if len(v) > 1 else float("nan")
        per_repeat = g.groupby("repeat")[METRIC_COLUMNS].mean()
        row["repeats"] = int(len(per_repeat))
        for m in METRIC_COLUMNS:
            # SD of the per-repeat means: variation due to the participant-fold assignment (seed).
            row[f"{m}_between_repeat_sd"] = (float(per_repeat[m].std(ddof=1)) if len(per_repeat) > 1
                                             else float("nan"))
        for c in ("tp", "fp", "tn", "fn"):
            row[f"{c}_total_all_repeats"] = int(g[c].sum())
        rows.append(row)
    return pd.DataFrame(rows)


def summarise_by_repeat(per_split: pd.DataFrame) -> pd.DataFrame:
    """One row per (model, repeat/seed): mean of each metric over that repeat's outer folds."""
    if per_split.empty:
        return pd.DataFrame()
    out = (per_split.groupby(["model", "repeat", "seed"], sort=False)[METRIC_COLUMNS].mean()
           .add_suffix("_mean").reset_index())
    out.insert(3, "folds", per_split.groupby(["model", "repeat", "seed"], sort=False).size().to_numpy())
    return out


def split_table(groups, y, splits) -> pd.DataFrame:
    rows = []
    for s in splits:
        te, tr = s.test_idx, s.train_idx
        rows.append({"repeat": s.repeat, "seed": s.seed, "fold": s.fold,
                     "train_participants": len(set(groups[tr])), "test_participants": len(set(groups[te])),
                     "test_positive_participants": len(set(groups[te][y[te] == 1])),
                     "train_rows": len(tr), "train_positive_rows": int(y[tr].sum()),
                     "test_rows": len(te), "test_positive_rows": int(y[te].sum())})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Optional held-out participants (disabled in the default configuration)
# ---------------------------------------------------------------------------
def holdout_split(groups, y, cfg: Config):
    """Return (development_idx, holdout_idx) or raise SplitError if infeasible."""
    h = cfg["holdout"]
    k = max(2, int(round(1 / float(h["test_fraction"]))))
    folds = assign_participant_folds(groups, y, k, int(h["seed"]), 1)
    g = np.asarray(pd.Series(groups).astype("string"))
    hold_pids = set(folds.index[folds == 1])
    hold = np.flatnonzero(np.isin(g, list(hold_pids)))
    dev = np.flatnonzero(~np.isin(g, list(hold_pids)))
    n_pos = len(set(g[hold][np.asarray(y)[hold] == 1]))
    if n_pos < int(h["min_positive_participants"]):
        raise SplitError(f"holdout would contain {n_pos} positive-bearing participants; "
                         f"at least {h['min_positive_participants']} required")
    assert_group_separation(g, dev, hold)
    return dev, hold


# ---------------------------------------------------------------------------
# Final model (only on explicit request, after cross-validation)
# ---------------------------------------------------------------------------
def fit_final(name, X, y, groups, predictors, cfg: Config):
    """Tune on grouped inner folds of ALL given rows, set the threshold on their
    out-of-fold predictions, then refit on all rows.
    Returns (pipeline, params, threshold, inner_tuning_score)."""
    y = np.asarray(y, int)
    groups = np.asarray(pd.Series(groups).astype("string"))
    seed = int(cfg["training"]["random_seed"])
    params, thr, score = tune_on_inner(name, X, y, groups, np.arange(len(y)), predictors, cfg, seed)
    pipe = build_pipeline(name, predictors, cfg, params, seed)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pipe.fit(X, y)
    return pipe, params, thr, score

