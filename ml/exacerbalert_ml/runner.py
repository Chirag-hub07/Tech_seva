"""Orchestration of a cross-validation run and of the final fit.

Writes AGGREGATE outputs only: no participant IDs, no dates, no row-level
predictions. Every run goes to a fresh timestamped folder and nothing is
overwritten.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from .config import Config
from .dataset import ModelingData, build_modeling_data, resolve_events
from .exclusions import (EXCLUDE, INCLUDE, build_register, load_feature_audit, load_temporal_verification,
                         register_summary)
from .labels import apply_label_policy
from .splits import SplitError, assert_group_separation
from .training import CVResult, fit_final, holdout_split, run_cv
from .utils import command_line, environment_info, new_run_dir, sha256_file, write_json

# Primary analysis and pre-specified sensitivity analyses. The primary design is
# never changed by a sensitivity analysis.
ANALYSES = {
    "primary": {"label_policy": "original", "washout_days": "primary",
                "description": "PRIMARY: original notebook-06 labels, primary post-event washout"},
    "washout_none": {"label_policy": "original", "washout_days": None,
                     "description": "Sensitivity: no post-event washout"},
    "washout_28": {"label_policy": "original", "washout_days": 28,
                   "description": "Sensitivity: 28-day post-event washout"},
    "tolife_absent_file_negative": {
        "label_policy": "tolife_v1_absent_file_negative", "washout_days": "primary",
        "description": ("ASSUMPTION-DEPENDENT sensitivity: participants WITHOUT an event file are treated "
                        "as having no exacerbations (full follow-up rows only). This assumption is NOT "
                        "verified; these results must not be reported as primary.")},
}
ALL_ANALYSES = tuple(ANALYSES)

NO_TEST_SET_STATEMENT = ("No independent final test set: all performance figures are participant-grouped "
                         "cross-validation estimates on the same participants used for development.")
CV_VS_ARTIFACT_STATEMENT = ("Cross-validation figures estimate the performance of the modelling PROCEDURE. "
                            "They are not measurements of any single fitted artifact.")
DISCLAIMER = "Research prototype only. Not a clinically validated prediction system."


class RunError(RuntimeError):
    """A deliberate refusal (e.g. incomplete prerequisites). Message contains no identifiers."""


@dataclass
class Inputs:
    merged: pd.DataFrame
    dictionary: pd.DataFrame
    events: pd.DataFrame
    audit: pd.DataFrame | None
    temporal: pd.DataFrame | None
    hashes: dict


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
def input_hashes(cfg: Config, audit_dir: Path | None, temporal_csv: Path | None) -> dict:
    """sha256 of every input file (file names only, never full paths)."""
    out = {}
    for key in ("features", "labels", "feature_dictionary"):
        p = cfg.path(key)
        if p.is_file():
            out[key] = {"file": p.name, "sha256": sha256_file(p)}
    if audit_dir is not None and (Path(audit_dir).expanduser() / "feature_audit.csv").is_file():
        out["feature_audit"] = {"file": "feature_audit.csv",
                                "sha256": sha256_file(Path(audit_dir).expanduser() / "feature_audit.csv")}
    if temporal_csv is not None and Path(temporal_csv).expanduser().is_file():
        out["temporal_verification"] = {"file": Path(temporal_csv).name,
                                        "sha256": sha256_file(Path(temporal_csv).expanduser())}
    if cfg.source is not None and Path(cfg.source).is_file():
        out["config"] = {"file": Path(cfg.source).name, "sha256": sha256_file(cfg.source)}
    return out


def audit_paths(cfg: Config, audit_dir=None, temporal_csv=None):
    fx = cfg["feature_exclusions"]
    a = Path(audit_dir or fx["feature_audit_dir"]).expanduser()
    t = Path(temporal_csv or fx["temporal_verification_csv"]).expanduser()
    return a, t


def load_inputs(cfg: Config, audit_dir=None, temporal_csv=None) -> Inputs:
    from .data import load_merged
    from .features import load_feature_dictionary

    a, t = audit_paths(cfg, audit_dir, temporal_csv)
    fx = cfg["feature_exclusions"]
    audit = load_feature_audit(a, cfg) if fx.get("require_feature_audit", True) or a.exists() else None
    temporal = (load_temporal_verification(t)
                if fx.get("require_temporal_verification", True) or t.exists() else None)
    merged = load_merged(cfg)
    dictionary = load_feature_dictionary(cfg)
    events = resolve_events(apply_label_policy(merged, cfg, None), cfg)
    return Inputs(merged, dictionary, events, audit, temporal, input_hashes(cfg, a, t))


# ---------------------------------------------------------------------------
# One analysis
# ---------------------------------------------------------------------------
def modelling_data(inputs: Inputs, cfg: Config, analysis: str) -> ModelingData:
    spec = ANALYSES[analysis]
    return build_modeling_data(inputs.merged, inputs.dictionary, cfg, washout_days=spec["washout_days"],
                               feature_set=cfg["training"].get("feature_set", "all"),
                               label_policy=spec["label_policy"], events=inputs.events)


def restrict(md: ModelingData, idx) -> ModelingData:
    idx = np.asarray(idx)
    return ModelingData(X=md.X.iloc[idx].reset_index(drop=True), y=md.y.iloc[idx].reset_index(drop=True),
                        groups=md.groups.iloc[idx].reset_index(drop=True),
                        dates=md.dates.iloc[idx].reset_index(drop=True), predictors=md.predictors,
                        info=dict(md.info))


def apply_holdout(md: ModelingData, cfg: Config):
    """Return (development data, holdout data or None, statement)."""
    if not cfg["holdout"].get("enabled", False):
        return md, None, NO_TEST_SET_STATEMENT
    try:
        dev, hold = holdout_split(md.groups, md.y, cfg)
    except SplitError as exc:
        raise RunError(f"holdout is enabled but infeasible ({exc}). Disable holdout in config.yaml to use "
                       "grouped cross-validation only; the design is never weakened automatically.") from exc
    return restrict(md, dev), restrict(md, hold), (
        "Held-out participants were set aside before cross-validation and are used only once, by fit_final.py.")


def cv_outputs(result: CVResult, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=False)
    result.split_summary.to_csv(out / "split_summary.csv", index=False)
    result.per_split.to_csv(out / "cv_metrics_by_split.csv", index=False)
    result.summary.to_csv(out / "model_comparison.csv", index=False)
    if result.by_repeat is not None:
        result.by_repeat.to_csv(out / "model_comparison_by_repeat.csv", index=False)
    pooled_rows, confusion_rows = [], []
    for model, res in result.pooled.items():
        m = res["metrics"]
        pooled_rows.append({"model": model, **{k: v for k, v in m.items() if k != "threshold"},
                            **res["event_level"], **res["bootstrap_ci"], **res["calibration_fit"]})
        confusion_rows.append({"model": model, "tp": m["tp"], "fp": m["fp"], "tn": m["tn"], "fn": m["fn"]})
        res["calibration"].assign(model=model).to_csv(out / f"calibration_{model}.csv", index=False)
    pd.DataFrame(pooled_rows).to_csv(out / "pooled_oof_metrics_repeat1.csv", index=False)
    pd.DataFrame(confusion_rows).to_csv(out / "confusion_matrix_pooled_repeat1.csv", index=False)


def run_analysis(inputs: Inputs, cfg: Config, analysis: str, predictors: list[str], out: Path,
                 models=None, n_repeats=None, progress=None) -> dict:
    md = modelling_data(inputs, cfg, analysis)
    md_dev, md_hold, statement = apply_holdout(md, cfg)
    X = md_dev.X[predictors]
    result = run_cv(X, md_dev.y, md_dev.groups, md_dev.dates, inputs.events, predictors, cfg,
                    models=models, n_repeats=n_repeats, progress=progress)
    cv_outputs(result, out)
    summary = {
        "analysis": analysis, "description": ANALYSES[analysis]["description"],
        "label_policy": ANALYSES[analysis]["label_policy"], "washout_days": md.info["washout_days"],
        "data": md.info, "development_rows": int(len(md_dev.y)),
        "development_participants": int(md_dev.groups.nunique()),
        "development_positive_rows": int(md_dev.y.sum()),
        "holdout_participants": None if md_hold is None else int(md_hold.groups.nunique()),
        "test_set_statement": statement,
        "outer_splits": int(len(result.split_summary)),
        "models": list(result.pooled),
    }
    write_json(out / "analysis_summary.json", summary)
    return {"summary": summary, "result": result}


# ---------------------------------------------------------------------------
# Full run
# ---------------------------------------------------------------------------
def select_features(inputs: Inputs, cfg: Config, strict: bool = True):
    md = modelling_data(inputs, cfg, "primary")
    register = build_register(md.predictors, cfg, inputs.audit, inputs.temporal, strict=strict)
    selected = register.loc[register["decision"] == INCLUDE, "feature"].tolist()
    if not selected:
        raise RunError("the feature register excluded every predictor; nothing to train on")
    return register, selected


def write_report(run_dir: Path, meta: dict, analyses: dict, reg_summary: dict) -> None:
    lines = [f"# ExacerbAlert cross-validation run", "", f"> {DISCLAIMER}", "",
             f"- {meta['test_set_statement']}", f"- {CV_VS_ARTIFACT_STATEMENT}",
             "- No final model was fitted in this run (use fit_final.py after reviewing these results).",
             f"- Repeats used: {meta['repeats_used']} of {meta['repeats_configured']} configured"
             + (" (REDUCED - development only, not the pre-specified design)" if meta["reduced_design"] else ""),
             "", "## Feature register", "",
             f"Candidates {reg_summary['candidates']}, included {reg_summary['included']}, "
             f"excluded {reg_summary['excluded']}.", ""]
    for reason, n in sorted(reg_summary["excluded_by_reason"].items(), key=lambda kv: -kv[1]):
        lines.append(f"- excluded `{reason}`: {n}")
    for name, a in analyses.items():
        s, res = a["summary"], a["result"]
        lines += ["", f"## {name}", "", s["description"], "",
                  f"Development rows {s['development_rows']} (positive {s['development_positive_rows']}), "
                  f"participants {s['development_participants']}, outer splits {s['outer_splits']}.", "",
                  "| model | PR-AUC mean (sd) | ROC-AUC mean (sd) | Brier | sensitivity | specificity | precision "
                  "| event sensitivity | false alerts / participant-week |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for _, r in res.summary.iterrows():
            lines.append(
                f"| {r['model']} | {r['pr_auc_average_precision_mean']:.3f} ({r['pr_auc_average_precision_std']:.3f}) "
                f"| {r['roc_auc_mean']:.3f} ({r['roc_auc_std']:.3f}) | {r['brier_mean']:.3f} "
                f"| {r['recall_sensitivity_mean']:.3f} | {r['specificity_mean']:.3f} | {r['precision_mean']:.3f} "
                f"| {r['event_sensitivity_mean']:.3f} | {r['false_alerts_per_participant_week_mean']:.3f} |")
        lines += ["", "Mean (sd) across outer test folds. Thresholds were chosen on inner (training-only) "
                  "out-of-fold predictions. dummy_prior is the no-information baseline."]
    lines += ["", "## Files", "", "- `feature_register.csv`, `selected_features.txt`: per-feature decisions",
              "- `<analysis>/model_comparison.csv`: per-model mean/sd across outer folds",
              "- `<analysis>/cv_metrics_by_split.csv`: per outer fold (aggregates only)",
              "- `<analysis>/model_comparison_by_repeat.csv`: per model and seed, mean over that seed's folds "
              "(`model_comparison.csv` also gives the between-seed SD)",
              "- `<analysis>/pooled_oof_metrics_repeat1.csv`: pooled out-of-fold metrics of repeat 1 with "
              "participant-bootstrap 95% intervals, event-level metrics and calibration slope/intercept",
              "- `<analysis>/calibration_<model>.csv`, `confusion_matrix_pooled_repeat1.csv`",
              "- `run_metadata.json`, `config_used.yaml`, `RUN_COMPLETE.json`"]
    (run_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_training(cfg: Config, analyses=("primary",), models=None, n_repeats=None, label="cv",
                 audit_dir=None, temporal_csv=None, outputs_dir=None, progress=None,
                 inputs: Inputs | None = None) -> Path:
    unknown = set(analyses) - set(ANALYSES)
    if unknown:
        raise RunError(f"unknown analyses: {sorted(unknown)}")
    if "primary" not in analyses:
        raise RunError("the primary analysis must be part of every run")
    inputs = inputs or load_inputs(cfg, audit_dir, temporal_csv)
    register, selected = select_features(inputs, cfg)
    reg_summary = register_summary(register)

    outputs = Path(outputs_dir) if outputs_dir else cfg.path("outputs")
    run_dir = new_run_dir(outputs, cfg["training"].get("outputs_subdir", "runs"), label)
    register.to_csv(run_dir / "feature_register.csv", index=False)
    (run_dir / "selected_features.txt").write_text("\n".join(selected) + "\n", encoding="utf-8")
    write_json(run_dir / "feature_register_summary.json", reg_summary)
    (run_dir / "config_used.yaml").write_text(yaml.safe_dump(cfg.raw, sort_keys=False), encoding="utf-8")

    n_conf = len(cfg["splits"]["outer_seeds"])
    meta = {
        "disclaimer": DISCLAIMER, "kind": "cross_validation",
        "analyses_requested": list(analyses), "models": models or "all enabled",
        "repeats_configured": n_conf, "repeats_used": int(n_repeats or n_conf),
        "reduced_design": bool(n_repeats and n_repeats < n_conf),
        "outer_n_splits": int(cfg["splits"]["outer_n_splits"]),
        "inner_n_splits": int(cfg["splits"]["inner_n_splits"]),
        "holdout_enabled": bool(cfg["holdout"].get("enabled", False)),
        "test_set_statement": NO_TEST_SET_STATEMENT if not cfg["holdout"].get("enabled", False)
        else "held-out participants reserved for fit_final.py",
        "cv_vs_artifact": CV_VS_ARTIFACT_STATEMENT,
        "inputs": inputs.hashes, "environment": environment_info(), "command": command_line(),
        "events_used_for_washout_and_event_metrics": int(len(inputs.events)),
        "event_source": cfg["post_event"].get("event_source", "labels"),
    }
    write_json(run_dir / "run_metadata.json", meta)

    done = {}
    for name in analyses:
        if progress:
            progress(f"analysis {name} started")
        done[name] = run_analysis(inputs, cfg, name, selected, run_dir / name, models, n_repeats, progress)
    write_report(run_dir, meta, done, reg_summary)
    write_json(run_dir / "RUN_COMPLETE.json", {
        "analyses_completed": list(done), "reduced_design": meta["reduced_design"],
        "models": sorted({m for a in done.values() for m in a["result"].pooled}),
        "inputs": inputs.hashes, "selected_features_sha256": sha256_file(run_dir / "selected_features.txt")})
    return run_dir


# ---------------------------------------------------------------------------
# Final model
# ---------------------------------------------------------------------------
def check_final_prerequisites(run_dir: Path, model: str, current_hashes: dict) -> dict:
    marker = Path(run_dir) / "RUN_COMPLETE.json"
    if not marker.is_file():
        raise RunError("the given run folder has no RUN_COMPLETE.json; cross-validation did not finish")
    done = json.loads(marker.read_text(encoding="utf-8"))
    missing = [a for a in ALL_ANALYSES if a not in done["analyses_completed"]]
    if missing:
        raise RunError(f"cross-validation run lacks analyses {missing}; run train.py --analyses all first")
    if done.get("reduced_design"):
        raise RunError("the cross-validation run used a reduced design (--repeats); re-run the full design")
    if model not in done["models"]:
        raise RunError(f"model {model} was not cross-validated in that run")
    changed = [k for k, v in done["inputs"].items() if current_hashes.get(k, {}).get("sha256") != v["sha256"]]
    if changed:
        raise RunError(f"inputs changed since cross-validation: {sorted(changed)}; re-run cross-validation")
    return done


def run_final_fit(cfg: Config, run_dir, model: str, audit_dir=None, temporal_csv=None,
                  inputs: Inputs | None = None) -> Path:
    run_dir = Path(run_dir)
    inputs = inputs or load_inputs(cfg, audit_dir, temporal_csv)
    check_final_prerequisites(run_dir, model, inputs.hashes)
    register, selected = select_features(inputs, cfg)
    saved = (run_dir / "selected_features.txt").read_text(encoding="utf-8").split()
    if saved != selected:
        raise RunError("the feature register differs from the cross-validated run; re-run cross-validation")

    md = modelling_data(inputs, cfg, "primary")
    md_dev, md_hold, statement = apply_holdout(md, cfg)
    pipe, params, thr, inner_score = fit_final(model, md_dev.X[selected], md_dev.y, md_dev.groups, selected, cfg)

    out = run_dir / f"final_model_{model}"
    out.mkdir(exist_ok=False)
    holdout = None
    if md_hold is not None:
        from .evaluate import event_level, row_metrics

        assert_group_separation(np.concatenate([md_dev.groups.to_numpy(), md_hold.groups.to_numpy()]),
                                np.arange(len(md_dev.y)), len(md_dev.y) + np.arange(len(md_hold.y)))
        p = pipe.predict_proba(md_hold.X[selected])[:, 1]
        holdout = {**row_metrics(md_hold.y, p, thr),
                   **event_level(md_hold.groups, md_hold.dates, p >= thr, inputs.events,
                                 int(cfg["evaluation"]["event_window_days"]))}
        write_json(out / "holdout_metrics.json", holdout)

    import joblib

    joblib.dump(pipe, out / "model.joblib")
    schema = {
        "disclaimer": DISCLAIMER, "model": model, "params": params, "alert_threshold": float(thr),
        "threshold_strategy": cfg["training"]["threshold_strategy"],
        "target_sensitivity": cfg["training"]["target_sensitivity"],
        "inner_tuning_score": inner_score, "predictors": selected,
        "label_policy": "original", "washout_days": md.info["washout_days"],
        "horizon_days": cfg.horizon_days, "prediction_time": cfg["prediction_time"]["assumption"],
        "training_rows": int(len(md_dev.y)), "training_participants": int(md_dev.groups.nunique()),
        "cross_validation_run": run_dir.name, "test_set_statement": statement,
        "performance_note": (CV_VS_ARTIFACT_STATEMENT + " This artifact was fitted on all development "
                             "participants; it has no performance estimate of its own"
                             + (" except the held-out evaluation in holdout_metrics.json." if holdout else ".")),
        "inputs": inputs.hashes, "environment": environment_info(),
    }
    write_json(out / "input_schema.json", schema)
    return out
