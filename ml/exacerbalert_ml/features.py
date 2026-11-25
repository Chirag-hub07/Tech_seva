"""Predictor selection, leakage guards and fit-on-train feature filters.

Predictors come from an allowlist: columns documented in the feature
dictionary, minus every banned column. All data-dependent filtering
(missingness, constant and duplicate columns) is implemented as scikit-learn
transformers so that it is fitted on training folds only.
"""

from __future__ import annotations

import hashlib
import re

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

from .config import Config


class LeakageError(ValueError):
    """Raised when a banned or future-information column reaches the predictors."""


# ---------------------------------------------------------------------------
# Banned columns
# ---------------------------------------------------------------------------
def _patterns(cfg: Config, key: str) -> list[re.Pattern]:
    return [re.compile(p) for p in cfg.raw.get(key, []) or []]


def is_banned(column: str, cfg: Config) -> bool:
    if column in set(cfg["never_predictors"]):
        return True
    return any(p.search(str(column)) for p in _patterns(cfg, "never_predictor_patterns"))


def assert_no_banned(columns, cfg: Config) -> None:
    banned = [c for c in columns if is_banned(c, cfg)]
    if banned:
        raise LeakageError(f"{len(banned)} banned column(s) among predictors: {banned[:10]}")


# ---------------------------------------------------------------------------
# Feature dictionary and predictor allowlist
# ---------------------------------------------------------------------------
def load_feature_dictionary(cfg: Config) -> pd.DataFrame:
    from .data import read_table

    fd = read_table(cfg.path("feature_dictionary"))
    if "Feature" not in fd.columns:
        raise ValueError("feature dictionary has no 'Feature' column")
    fd = fd.copy()
    fd["Feature"] = fd["Feature"].astype("string").str.strip()
    if fd["Feature"].duplicated().any():
        raise ValueError(f"feature dictionary has {int(fd['Feature'].duplicated().sum())} duplicate entries")
    return fd


def check_time_windows(dictionary: pd.DataFrame, cfg: Config) -> None:
    """Reject features whose documented time window implies future data."""
    if "Time_Window" not in dictionary.columns:
        return
    pats = [re.compile(p) for p in cfg["prediction_time"].get("forbidden_time_window_patterns", [])]
    tw = dictionary["Time_Window"].astype("string").fillna("")
    bad = dictionary.loc[tw.apply(lambda v: any(p.search(v) for p in pats)), "Feature"]
    if len(bad):
        raise LeakageError(
            f"{len(bad)} feature(s) documented with a future time window: {list(bad)[:10]}")


def _feature_set_spec(cfg: Config, name: str) -> dict:
    sets = cfg["feature_sets"]
    if name not in sets:
        raise KeyError(f"unknown feature set: {name}")
    spec = dict(sets[name] or {})
    if "base" in spec:
        base = _feature_set_spec(cfg, spec.pop("base"))
        for key in ("include_groups", "include_patterns", "exclude_patterns"):
            spec[key] = list(base.get(key, [])) + list(spec.get(key, []))
    return spec


def apply_feature_set(columns: list[str], dictionary: pd.DataFrame, cfg: Config, name: str) -> list[str]:
    spec = _feature_set_spec(cfg, name)
    groups = {g.lower() for g in spec.get("include_groups", [])}
    inc = [re.compile(p) for p in spec.get("include_patterns", [])]
    exc = [re.compile(p) for p in spec.get("exclude_patterns", [])]
    group_of = {}
    if "Feature_Group" in dictionary.columns:
        group_of = dict(zip(dictionary["Feature"], dictionary["Feature_Group"].astype("string").str.lower()))
    selected = []
    for c in columns:
        keep = True
        if groups or inc:
            keep = (group_of.get(c) in groups) or any(p.search(c) for p in inc)
        if keep and any(p.search(c) for p in exc):
            keep = False
        if keep:
            selected.append(c)
    return selected


def select_predictors(feature_columns, dictionary: pd.DataFrame, cfg: Config,
                      feature_set: str = "all") -> tuple[list[str], dict]:
    """Return (predictor list, aggregate report).

    Order follows the feature table. Raises LeakageError if anything banned or
    future-looking would be selected.
    """
    check_time_windows(dictionary, cfg)
    documented = set(dictionary["Feature"].dropna())
    cols = [c for c in feature_columns if c not in (cfg.pid, cfg.date)]
    banned = [c for c in cols if is_banned(c, cfg)]
    undocumented = [c for c in cols if c not in documented and c not in banned]
    allowed = [c for c in cols if c in documented and c not in banned]
    selected = apply_feature_set(allowed, dictionary, cfg, feature_set)
    assert_no_banned(selected, cfg)
    report = {
        "feature_set": feature_set,
        "candidate_columns": len(cols),
        "excluded_banned": len(banned),
        "excluded_undocumented": len(undocumented),
        "dictionary_entries_without_column": len(documented - set(cols)),
        "selected": len(selected),
    }
    return selected, report


def time_in_study_proxies(columns, cfg: Config) -> list[str]:
    pats = [re.compile(p) for p in cfg.raw.get("time_in_study_proxy_patterns", [])]
    return [c for c in columns if any(p.search(c) for p in pats)]


# ---------------------------------------------------------------------------
# Fit-on-train transformers (pandas in, pandas out)
# ---------------------------------------------------------------------------
class _FrameTransformer(BaseEstimator, TransformerMixin):
    def _check_frame(self, X):
        if not isinstance(X, pd.DataFrame):
            raise TypeError(f"{type(self).__name__} expects a pandas DataFrame")

    def get_feature_names_out(self, input_features=None):
        return np.asarray(self.columns_, dtype=object)


class LeakageGuard(_FrameTransformer):
    """Keeps exactly the allowlisted predictors; fails on banned columns."""

    def __init__(self, predictors, never_predictors=(), never_predictor_patterns=()):
        self.predictors = predictors
        self.never_predictors = never_predictors
        self.never_predictor_patterns = never_predictor_patterns

    def _banned(self, c):
        return c in set(self.never_predictors) or any(
            re.search(p, str(c)) for p in self.never_predictor_patterns)

    def fit(self, X, y=None):
        self._check_frame(X)
        bad = [c for c in self.predictors if self._banned(c)]
        if bad:
            raise LeakageError(f"{len(bad)} banned column(s) in the predictor allowlist")
        missing = [c for c in self.predictors if c not in X.columns]
        if missing:
            raise KeyError(f"{len(missing)} allowlisted predictor(s) missing from the input")
        self.columns_ = list(self.predictors)
        return self

    def transform(self, X):
        self._check_frame(X)
        missing = [c for c in self.columns_ if c not in X.columns]
        if missing:
            raise KeyError(f"{len(missing)} expected predictor(s) missing from the input")
        return X[self.columns_]

    @classmethod
    def from_config(cls, predictors, cfg: Config):
        return cls(predictors, tuple(cfg["never_predictors"]), tuple(cfg.raw.get("never_predictor_patterns", [])))


class BooleanToFloat(_FrameTransformer):
    """Casts every column to float64 (booleans -> 0/1, missing preserved)."""

    def fit(self, X, y=None):
        self._check_frame(X)
        self.columns_ = list(X.columns)
        return self

    def transform(self, X):
        self._check_frame(X)
        out = {}
        for c in self.columns_:
            s = X[c]
            if s.dtype == object or str(s.dtype) in ("bool", "boolean"):
                s = s.astype("boolean")
            out[c] = pd.to_numeric(s, errors="raise").astype("float64")
        return pd.DataFrame(out, index=X.index)


class MissingnessFilter(_FrameTransformer):
    """Drops columns whose TRAINING missing fraction exceeds the threshold."""

    def __init__(self, max_missing_fraction: float = 0.95):
        self.max_missing_fraction = max_missing_fraction

    def fit(self, X, y=None):
        self._check_frame(X)
        frac = X.isna().mean()
        self.missing_fraction_ = frac
        self.columns_ = [c for c in X.columns if frac[c] <= self.max_missing_fraction]
        self.dropped_ = [c for c in X.columns if c not in set(self.columns_)]
        return self

    def transform(self, X):
        self._check_frame(X)
        return X[self.columns_]


class ConstantColumnDropper(_FrameTransformer):
    """Drops columns with at most one distinct non-missing TRAINING value."""

    def fit(self, X, y=None):
        self._check_frame(X)
        nunique = X.nunique(dropna=True)
        self.columns_ = [c for c in X.columns if nunique[c] > 1]
        self.dropped_ = [c for c in X.columns if nunique[c] <= 1]
        return self

    def transform(self, X):
        self._check_frame(X)
        return X[self.columns_]


class DuplicateColumnDropper(_FrameTransformer):
    """Drops columns identical (values and missingness) to an earlier column in TRAINING data."""

    def fit(self, X, y=None):
        self._check_frame(X)
        seen: dict[str, str] = {}
        keep, self.duplicate_of_ = [], {}
        for c in X.columns:
            h = hashlib.sha1(pd.util.hash_pandas_object(X[c], index=False).to_numpy().tobytes()).hexdigest()
            if h in seen and X[c].equals(X[seen[h]]):
                self.duplicate_of_[c] = seen[h]
            else:
                seen.setdefault(h, c)
                keep.append(c)
        self.columns_ = keep
        self.dropped_ = list(self.duplicate_of_)
        return self

    def transform(self, X):
        self._check_frame(X)
        return X[self.columns_]


def make_feature_filter_steps(predictors, cfg: Config) -> list[tuple[str, BaseEstimator]]:
    """Ordered (name, transformer) steps for use at the start of a model Pipeline."""
    ff = cfg["feature_filters"]
    steps: list[tuple[str, BaseEstimator]] = [
        ("leakage_guard", LeakageGuard.from_config(predictors, cfg)),
        ("to_float", BooleanToFloat()),
        ("missingness_filter", MissingnessFilter(ff["max_train_missing_fraction"])),
    ]
    if ff.get("drop_constant", True):
        steps.append(("constant_filter", ConstantColumnDropper()))
    if ff.get("drop_exact_duplicates", True):
        steps.append(("duplicate_filter", DuplicateColumnDropper()))
    return steps
