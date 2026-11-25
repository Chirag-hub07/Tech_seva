"""Model factories. Every model is ONE scikit-learn Pipeline, so all learned
preprocessing (feature filtering, imputation, scaling) is fitted on the
training rows passed to .fit() and nothing else.

Pipeline = leakage guard -> bool->float -> training-fold missingness filter ->
constant filter -> duplicate filter -> [imputer] -> [scaler] -> estimator.
"""

from __future__ import annotations

import itertools

from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .config import Config
from .features import make_feature_filter_steps

MODEL_NAMES = ("dummy_prior", "logistic_regression", "random_forest", "hist_gradient_boosting")


def _estimator(name: str, params: dict, seed: int):
    if name == "dummy_prior":
        return DummyClassifier(strategy="prior")
    if name == "logistic_regression":
        return LogisticRegression(random_state=seed, **params)
    if name == "random_forest":
        return RandomForestClassifier(random_state=seed, **params)
    if name == "hist_gradient_boosting":
        return HistGradientBoostingClassifier(random_state=seed, **params)
    raise KeyError(f"unknown model: {name}")


def build_pipeline(name: str, predictors, cfg: Config, params: dict | None = None,
                   seed: int | None = None) -> Pipeline:
    """Leakage-guarded pipeline for one model and one hyper-parameter setting."""
    seed = cfg["training"]["random_seed"] if seed is None else seed
    spec = cfg["models"].get(name, {})
    full = {**(spec.get("fixed") or {}), **(params or {})}
    steps = list(make_feature_filter_steps(list(predictors), cfg))
    if name in ("logistic_regression", "random_forest", "dummy_prior"):
        steps.append(("impute", SimpleImputer(strategy="median", keep_empty_features=False)))
    if name == "logistic_regression":
        steps.append(("scale", StandardScaler()))
    steps.append(("model", _estimator(name, full, seed)))
    return Pipeline(steps)


def param_grid(name: str, cfg: Config) -> list[dict]:
    grid = (cfg["models"].get(name, {}) or {}).get("grid") or {}
    if not grid:
        return [{}]
    keys = sorted(grid)
    return [dict(zip(keys, combo)) for combo in itertools.product(*(grid[k] for k in keys))]


def enabled_models(cfg: Config, only=None) -> list[str]:
    names = [n for n in MODEL_NAMES if (cfg["models"].get(n) or {}).get("enabled", False)]
    if only:
        unknown = set(only) - set(MODEL_NAMES)
        if unknown:
            raise KeyError(f"unknown model(s): {sorted(unknown)}")
        names = [n for n in names if n in set(only)]
    return names
