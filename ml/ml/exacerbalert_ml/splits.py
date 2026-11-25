"""Participant-grouped cross-validation splits.

Every participant's rows stay together: a participant is either entirely in
training or entirely in validation. There is deliberately no row-level random
split function in this module.

Strategy: participants are stratified by whether they have at least one
positive row and assigned to K folds (scikit-learn StratifiedKFold applied to
the participant table). The outer loop is repeated with several seeds because
the number of participants with positive rows is small. Inner splits for
tuning and threshold selection use the same procedure on training
participants only.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold


class SplitError(ValueError):
    pass


@dataclass(frozen=True)
class GroupedSplit:
    repeat: int
    seed: int
    fold: int
    train_idx: np.ndarray
    test_idx: np.ndarray


def participant_table(groups, y) -> pd.DataFrame:
    """One row per participant: row count, positive count, has_positive."""
    g = pd.Series(np.asarray(groups)).astype("string")
    yy = pd.Series(np.asarray(y, dtype="float64"))
    if yy.isna().any():
        raise SplitError("targets contain unknown values; drop unknown rows before splitting")
    if not yy.isin([0.0, 1.0]).all():
        raise SplitError("targets must be binary 0/1")
    t = pd.DataFrame({"pid": g, "pos": yy}).groupby("pid", sort=True).agg(
        n_rows=("pos", "size"), n_pos=("pos", "sum"))
    t["has_positive"] = t["n_pos"] > 0
    return t


def assign_participant_folds(groups, y, n_splits: int, seed: int,
                             min_positive_participants_per_fold: int = 1) -> pd.Series:
    """Map each participant to a fold number in 1..n_splits."""
    t = participant_table(groups, y)
    n_pos_p = int(t["has_positive"].sum())
    if len(t) < n_splits:
        raise SplitError(f"{len(t)} participants cannot form {n_splits} folds")
    if n_pos_p < n_splits * min_positive_participants_per_fold:
        raise SplitError(
            f"{n_pos_p} positive-bearing participants are too few for {n_splits} folds "
            f"with at least {min_positive_participants_per_fold} each")
    strata = t["has_positive"].astype(int).to_numpy()
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    folds = pd.Series(0, index=t.index, dtype="int64")
    with warnings.catch_warnings():
        # A small negative-only stratum may hold fewer members than n_splits.
        warnings.simplefilter("ignore", UserWarning)
        for k, (_, test) in enumerate(skf.split(np.zeros(len(t)), strata), start=1):
            folds.iloc[test] = k
    pos_per_fold = t.assign(fold=folds).groupby("fold")["has_positive"].sum()
    if (pos_per_fold < min_positive_participants_per_fold).any():
        raise SplitError("a fold received too few positive-bearing participants")
    return folds


def _rows_for_folds(groups, folds: pd.Series):
    g = pd.Series(np.asarray(groups)).astype("string")
    row_fold = g.map(folds).to_numpy()
    if np.isnan(row_fold.astype("float64")).any():
        raise SplitError("some rows have no fold assignment")
    return row_fold.astype(int)


def assert_group_separation(groups, train_idx, test_idx) -> None:
    g = np.asarray(pd.Series(np.asarray(groups)).astype("string"))
    overlap = set(g[train_idx]) & set(g[test_idx])
    if overlap:
        raise SplitError(f"{len(overlap)} participant(s) appear in both training and validation")
    if len(np.intersect1d(train_idx, test_idx)):
        raise SplitError("a row appears in both training and validation")


def grouped_kfold(groups, y, n_splits: int, seed: int, repeat: int = 0,
                  min_positive_participants_per_fold: int = 1) -> list[GroupedSplit]:
    folds = assign_participant_folds(groups, y, n_splits, seed, min_positive_participants_per_fold)
    row_fold = _rows_for_folds(groups, folds)
    out = []
    for k in range(1, n_splits + 1):
        test_idx = np.flatnonzero(row_fold == k)
        train_idx = np.flatnonzero(row_fold != k)
        assert_group_separation(groups, train_idx, test_idx)
        out.append(GroupedSplit(repeat=repeat, seed=seed, fold=k, train_idx=train_idx, test_idx=test_idx))
    return out


def outer_splits(groups, y, n_splits: int, seeds, min_positive_participants_per_fold: int = 1):
    """Repeated participant-grouped K-fold: len(seeds) * n_splits splits."""
    splits = []
    for r, seed in enumerate(seeds):
        splits.extend(grouped_kfold(groups, y, n_splits, int(seed), repeat=r,
                                    min_positive_participants_per_fold=min_positive_participants_per_fold))
    return splits


def inner_splits(groups, y, train_idx, n_splits: int, seed: int,
                 min_positive_participants_per_fold: int = 1) -> list[GroupedSplit]:
    """Grouped K-fold over TRAINING rows only; indices refer to the full arrays."""
    train_idx = np.asarray(train_idx)
    g_tr = np.asarray(groups)[train_idx]
    y_tr = np.asarray(y)[train_idx]
    local = grouped_kfold(g_tr, y_tr, n_splits, seed, repeat=0,
                          min_positive_participants_per_fold=min_positive_participants_per_fold)
    return [GroupedSplit(repeat=s.repeat, seed=s.seed, fold=s.fold,
                         train_idx=train_idx[s.train_idx], test_idx=train_idx[s.test_idx]) for s in local]


def splits_from_config(groups, y, cfg) -> list[GroupedSplit]:
    sc = cfg["splits"]
    return outer_splits(groups, y, int(sc["outer_n_splits"]), sc["outer_seeds"],
                        int(sc.get("min_positive_participants_per_test_fold", 1)))


def split_summary(groups, y, splits) -> pd.DataFrame:
    """Aggregate per-split counts (no identifiers)."""
    g = pd.Series(np.asarray(groups)).astype("string").to_numpy()
    yy = np.asarray(y, dtype="float64")
    rows = []
    for s in splits:
        te = s.test_idx
        pos_p = len(set(g[te][yy[te] == 1]))
        rows.append({"repeat": s.repeat, "fold": s.fold,
                     "train_participants": len(set(g[s.train_idx])), "test_participants": len(set(g[te])),
                     "test_positive_participants": pos_p, "test_rows": len(te),
                     "test_positive_rows": int((yy[te] == 1).sum())})
    return pd.DataFrame(rows)
