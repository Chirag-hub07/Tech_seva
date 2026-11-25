"""Training/evaluation tests on fully synthetic data. Run from ml/:
    python -m unittest discover -s tests -v     (or: PYTHONPATH=. python -m pytest tests -q)
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import re
import tempfile
import unittest
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from exacerbalert_ml import data as data_mod
from exacerbalert_ml import training as training_mod
from exacerbalert_ml.config import DEFAULT_CONFIG_PATH, config_from_dict, load_config
from exacerbalert_ml.evaluate import (bootstrap_ci, calibration_table, event_level, row_metrics,
                                      select_threshold)
from exacerbalert_ml.exclusions import (EXCLUDE, INCLUDE, AuditInputError, build_register, load_feature_audit,
                                        register_summary)
from exacerbalert_ml.models import build_pipeline, enabled_models, param_grid
from exacerbalert_ml.runner import (ALL_ANALYSES, Inputs, RunError, modelling_data, run_final_fit,
                                    run_training)
from exacerbalert_ml.splits import SplitError
from exacerbalert_ml.training import plan_splits, run_cv

from synthetic import EXPECTED_INCLUDED, make_training_synthetic, write_audit_inputs, write_synthetic_project

BASE = load_config(DEFAULT_CONFIG_PATH, project_root=".")


def small_raw():
    raw = copy.deepcopy(BASE.raw)
    raw["splits"].update(outer_n_splits=3, outer_seeds=[42, 43], inner_n_splits=2)
    raw["models"]["logistic_regression"]["grid"] = {"C": [0.1, 1.0], "l1_ratio": [0.5]}
    raw["models"]["random_forest"]["fixed"].update(n_estimators=15, n_jobs=1)
    raw["models"]["random_forest"]["grid"] = {"min_samples_leaf": [10]}
    raw["models"]["hist_gradient_boosting"]["fixed"].update(max_iter=25)
    raw["models"]["hist_gradient_boosting"]["grid"] = {"max_depth": [2]}
    raw["evaluation"]["bootstrap_resamples"] = 20
    raw["paths"]["feature_dictionary"] = "data/processed/features/feature_dictionary.csv"
    return raw


def small_cfg(root="."):
    return config_from_dict(small_raw(), project_root=root)


SYN = make_training_synthetic()


def inputs_from(syn, cfg):
    f = data_mod.normalize_keys(syn["features"], cfg, "features")
    lab = data_mod.normalize_keys(syn["labels"], cfg, "labels")
    merged = data_mod.join_features_labels(f, lab, cfg)
    ev = syn["events"].copy()
    ev["event_date"] = pd.to_datetime(ev["event_date"], utc=True)
    return Inputs(merged, syn["dictionary"], ev, syn["audit"], syn["temporal"], {})


ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def scan_for_identifiers(folder: Path, ids) -> list[str]:
    hits = []
    for p in folder.rglob("*"):
        if p.is_file() and p.suffix in {".csv", ".json", ".txt", ".md", ".yaml"}:
            text = p.read_text(encoding="utf-8")
            if any(str(i) in text for i in ids) or ISO_DATE.search(text):
                hits.append(p.name)
    return hits


# ---------------------------------------------------------------------------
class TestExclusions(unittest.TestCase):
    def setUp(self):
        self.cfg = small_cfg()
        self.preds = list(SYN["dictionary"]["Feature"])

    def test_register_conservative_defaults(self):
        reg = build_register(self.preds, self.cfg, SYN["audit"], SYN["temporal"]).set_index("feature")
        self.assertEqual(set(reg.index[reg["decision"] == INCLUDE]), EXPECTED_INCLUDED)
        r = reg["reasons"]
        self.assertIn("calendar_or_time_name", r["MI_days_since_start"])
        self.assertIn("time_in_study_proxy", r["BRI_mean_baseline_count"])
        self.assertIn("explicit:", r["EI_AQI_min_rolling_7d_std"])
        self.assertIn("temporal_MISMATCH", r["EI_AQI_min_rolling_7d_std"])
        self.assertIn("temporal_not_verified", r["BRI_mean_rolling_7d_std"])
        self.assertIn("audit_review:high_target_correlation_check_for_leakage", r["SII_hi_corr"])
        self.assertIn("not_in_feature_audit", r["EI_unaudited"])

    def test_real_config_excludes_the_mismatch_features(self):
        names = ["EI_AQI_min_rolling_3d_std", "EI_AQI_min_rolling_7d_std", "EI_Lux_mean_rolling_7d_std",
                 "SII_min_rolling_7d_std"]
        reg = build_register(names, BASE, strict=False)
        self.assertTrue((reg["decision"] == EXCLUDE).all())
        # The stale name (not in the feature table) is no longer listed.
        self.assertNotIn("MI_swm_std_mean_rolling_7d_std", BASE["feature_exclusions"]["explicit"])

    def test_strict_requires_audit_inputs(self):
        with self.assertRaises(AuditInputError):
            build_register(self.preds, self.cfg, None, SYN["temporal"])
        with self.assertRaises(AuditInputError):
            build_register(self.preds, self.cfg, SYN["audit"], None)

    def test_cleared_after_review_is_documented(self):
        raw = small_raw()
        raw["feature_exclusions"]["cleared_after_review"] = {"SII_hi_corr": "verified backward-looking"}
        reg = build_register(self.preds, config_from_dict(raw), SYN["audit"], SYN["temporal"]).set_index("feature")
        self.assertEqual(reg.loc["SII_hi_corr", "decision"], INCLUDE)
        self.assertIn("cleared_after_review", reg.loc["SII_hi_corr", "reasons"])
        self.assertIn("would otherwise be", reg.loc["SII_hi_corr", "reasons"])

    def test_summary_counts(self):
        s = register_summary(build_register(self.preds, self.cfg, SYN["audit"], SYN["temporal"]))
        self.assertEqual(s["candidates"], len(self.preds))
        self.assertEqual(s["included"] + s["excluded"], s["candidates"])
        self.assertEqual(s["excluded_by_reason"]["explicit"], 1)

    def test_audit_under_wrong_policy_is_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            a, _ = write_audit_inputs(t, SYN, policy="tolife_v1_absent_file_negative")
            with self.assertRaises(AuditInputError):
                load_feature_audit(a, self.cfg)
            a, _ = write_audit_inputs(Path(t) / "ok", SYN, policy="original")
            self.assertEqual(len(load_feature_audit(a, self.cfg)), len(SYN["audit"]))


# ---------------------------------------------------------------------------
class TestModels(unittest.TestCase):
    def test_every_model_fits_with_missing_values(self):
        cfg = small_cfg()
        md = modelling_data(inputs_from(SYN, cfg), cfg, "primary")
        preds = sorted(EXPECTED_INCLUDED)
        for name in enabled_models(cfg):
            for params in param_grid(name, cfg):
                with warnings.catch_warnings():
                    warnings.simplefilter("error", FutureWarning)     # no deprecated API use
                    pipe = build_pipeline(name, preds, cfg, params).fit(md.X[preds], md.y)
                p = pipe.predict_proba(md.X[preds])[:, 1]
                self.assertTrue(np.isfinite(p).all() and ((p >= 0) & (p <= 1)).all(), name)

    def test_grid_and_names(self):
        cfg = small_cfg()
        self.assertEqual(param_grid("dummy_prior", cfg), [{}])
        self.assertEqual(len(param_grid("logistic_regression", cfg)), 2)
        self.assertEqual(enabled_models(cfg), ["dummy_prior", "logistic_regression", "random_forest",
                                               "hist_gradient_boosting"])
        with self.assertRaises(KeyError):
            enabled_models(cfg, ["xgboost"])

    def test_pipeline_refuses_banned_predictor(self):
        cfg = small_cfg()
        X = pd.DataFrame({"Participant_ID": ["a", "b"], "x": [1.0, 2.0]})
        with self.assertRaises(Exception):
            build_pipeline("logistic_regression", ["Participant_ID", "x"], cfg).fit(X, [0, 1])


# ---------------------------------------------------------------------------
class TestEvaluate(unittest.TestCase):
    def test_threshold_target_sensitivity(self):
        y = np.array([0, 0, 0, 1, 1, 1, 1, 1])
        p = np.array([.1, .2, .6, .3, .5, .7, .8, .9])
        t = select_threshold(y, p, "target_sensitivity", 0.8)
        self.assertEqual(t, 0.5)                                  # highest threshold with 4/5 recall
        self.assertGreaterEqual((p[y == 1] >= t).mean(), 0.8)
        self.assertEqual(select_threshold(np.zeros(3), np.ones(3)), 0.5)

    def test_row_metrics_values(self):
        m = row_metrics([1, 1, 0, 0], [.9, .2, .8, .1], 0.5)
        self.assertEqual((m["tp"], m["fn"], m["fp"], m["tn"]), (1, 1, 1, 1))
        self.assertAlmostEqual(m["precision"], .5)
        self.assertAlmostEqual(m["specificity"], .5)
        self.assertAlmostEqual(m["roc_auc"], .75)
        m2 = row_metrics([1, 0], [.1, .9], 0.5, alerts=[1, 0])     # alerts override the threshold
        self.assertEqual(m2["tp"], 1)

    def test_event_level(self):
        d = pd.date_range("2031-01-01", periods=20, freq="D", tz="UTC")
        g = ["A"] * 20
        alerts = np.zeros(20, bool)
        alerts[[7, 15]] = True                                   # day 7 precedes event on day 10
        events = pd.DataFrame({"participant": ["A", "A"],
                               "event_date": [d[10], pd.Timestamp("2031-03-01", tz="UTC")]})
        r = event_level(g, d, alerts, events, 7)
        self.assertEqual(r["events_evaluable"], 1)                # second event has no modelled days
        self.assertEqual(r["events_detected"], 1)
        self.assertEqual(r["median_lead_days"], 3.0)
        self.assertEqual(r["false_alerts"], 1)                    # day 15 not in any event window

    def test_bootstrap_and_calibration(self):
        rng = np.random.default_rng(0)
        y = rng.integers(0, 2, 300)
        p = np.clip(y * .3 + rng.random(300) * .7, 0, 1)
        g = np.repeat(np.arange(30), 10)
        ci = bootstrap_ci(y, p, g, 0.5, n_resamples=30, seed=1)
        self.assertLessEqual(ci["roc_auc_ci_low"], ci["roc_auc_ci_high"])
        self.assertEqual(int(calibration_table(y, p, 10)["n"].sum()), 300)


# ---------------------------------------------------------------------------
class TestTraining(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = small_cfg()
        cls.inputs = inputs_from(SYN, cls.cfg)
        cls.md = modelling_data(cls.inputs, cls.cfg, "primary")
        cls.preds = sorted(EXPECTED_INCLUDED)

    def test_infeasible_design_is_refused_not_weakened(self):
        raw = small_raw()
        raw["splits"]["outer_n_splits"] = 40
        with self.assertRaises(SplitError):
            plan_splits(self.md.groups, self.md.y, config_from_dict(raw))

    def test_outer_test_participants_never_used_for_fitting(self):
        log = []
        real_build = training_mod.build_pipeline

        def spy_build(*a, **k):
            pipe = real_build(*a, **k)
            fit, proba = pipe.fit, pipe.predict_proba

            def fit_spy(X, y=None, **kw):
                log.append(("fit", set(self.md.groups.iloc[X.index])))
                return fit(X, y, **kw)

            def proba_spy(X):
                log.append(("predict", frozenset(X.index)))
                return proba(X)
            pipe.fit, pipe.predict_proba = fit_spy, proba_spy
            return pipe

        training_mod.build_pipeline = spy_build
        try:
            res = run_cv(self.md.X[self.preds], self.md.y, self.md.groups, self.md.dates, self.inputs.events,
                         self.preds, self.cfg, models=["logistic_regression"])
        finally:
            training_mod.build_pipeline = real_build
        _, plan = plan_splits(self.md.groups.to_numpy(), self.md.y.to_numpy(), self.cfg)
        outer_tests = {frozenset(s.test_idx.tolist()): set(self.md.groups.iloc[s.test_idx]) for s, _ in plan}
        fits_since, checked = [], 0
        for kind, val in log:
            if kind == "fit":
                fits_since.append(val)
                continue
            if val in outer_tests:
                test_pids = outer_tests[val]
                self.assertTrue(fits_since)
                for fitted in fits_since:                   # inner fits, final refit of this outer split
                    self.assertFalse(fitted & test_pids)
                checked += 1
                fits_since = []
            else:                                           # inner validation scoring
                self.assertFalse(fits_since[-1] & set(self.md.groups.iloc[list(val)]))
        self.assertEqual(checked, len(plan))
        self.assertEqual(len(res.per_split), len(plan))

    def test_aggregation_by_repeat(self):
        res = run_cv(self.md.X[self.preds], self.md.y, self.md.groups, self.md.dates, self.inputs.events,
                     self.preds, self.cfg, models=["dummy_prior", "logistic_regression"])
        n_rep, n_fold = len(self.cfg["splits"]["outer_seeds"]), int(self.cfg["splits"]["outer_n_splits"])
        br = res.by_repeat
        self.assertEqual(len(br), 2 * n_rep)
        self.assertTrue((br["folds"] == n_fold).all())
        self.assertEqual(sorted(br["seed"].unique()), sorted(self.cfg["splits"]["outer_seeds"]))
        ps = res.per_split
        for _, r in br.iterrows():
            sub = ps[(ps["model"] == r["model"]) & (ps["repeat"] == r["repeat"])]
            self.assertAlmostEqual(r["roc_auc_mean"], sub["roc_auc"].mean())
        s = res.summary.set_index("model")
        lr = br[br["model"] == "logistic_regression"]["pr_auc_average_precision_mean"]
        self.assertEqual(s.loc["logistic_regression", "repeats"], n_rep)
        self.assertAlmostEqual(s.loc["logistic_regression", "pr_auc_average_precision_between_repeat_sd"],
                               lr.std(ddof=1))
        # Overall mean over all folds of all seeds equals the mean of the per-seed means (equal fold counts).
        self.assertAlmostEqual(s.loc["logistic_regression", "pr_auc_average_precision_mean"], lr.mean())

    def test_signal_beats_baseline(self):
        res = run_cv(self.md.X[self.preds], self.md.y, self.md.groups, self.md.dates, self.inputs.events,
                     self.preds, self.cfg, models=["dummy_prior", "logistic_regression"]).summary.set_index("model")
        self.assertGreater(res.loc["logistic_regression", "pr_auc_average_precision_mean"],
                           res.loc["dummy_prior", "pr_auc_average_precision_mean"] + 0.05)
        self.assertAlmostEqual(res.loc["dummy_prior", "roc_auc_mean"], 0.5, places=6)


# ---------------------------------------------------------------------------
class TestRunAndFinalFit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.cfg = small_cfg(cls.tmp.name)
        cls.inputs = inputs_from(SYN, cls.cfg)
        cls.out = Path(cls.tmp.name) / "outputs"
        cls.run_all = run_training(cls.cfg, analyses=ALL_ANALYSES, models=["dummy_prior", "logistic_regression"],
                                   outputs_dir=cls.out, inputs=cls.inputs, label="all")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_outputs_written_and_aggregate_only(self):
        r = self.run_all
        for f in ("report.md", "run_metadata.json", "config_used.yaml", "feature_register.csv",
                  "selected_features.txt", "RUN_COMPLETE.json"):
            self.assertTrue((r / f).is_file(), f)
        for a in ALL_ANALYSES:
            for f in ("model_comparison.csv", "model_comparison_by_repeat.csv", "cv_metrics_by_split.csv", "split_summary.csv",
                      "pooled_oof_metrics_repeat1.csv", "confusion_matrix_pooled_repeat1.csv",
                      "calibration_logistic_regression.csv", "analysis_summary.json"):
                self.assertTrue((r / a / f).is_file(), f"{a}/{f}")
        self.assertEqual(scan_for_identifiers(r, SYN["features"]["Participant_ID"].unique()), [])
        # Cross-validation itself never saves a model (final_model_* folders come only from fit_final).
        self.assertFalse([p for p in r.rglob("*.joblib") if not p.parent.name.startswith("final_model_")])
        report = (r / "report.md").read_text()
        self.assertIn("No independent final test set", report)
        self.assertIn("ASSUMPTION-DEPENDENT", report)
        self.assertEqual(set((r / "selected_features.txt").read_text().split()), EXPECTED_INCLUDED)

    def test_primary_required(self):
        with self.assertRaises(RunError):
            run_training(self.cfg, analyses=["washout_28"], outputs_dir=self.out, inputs=self.inputs)

    def test_final_fit_refused_without_sensitivity_analyses(self):
        r = run_training(self.cfg, analyses=["primary"], models=["logistic_regression"],
                         outputs_dir=self.out, inputs=self.inputs, label="primary_only")
        with self.assertRaises(RunError):
            run_final_fit(self.cfg, r, "logistic_regression", inputs=self.inputs)

    def test_final_fit_refused_for_reduced_design(self):
        r = run_training(self.cfg, analyses=ALL_ANALYSES, models=["logistic_regression"], n_repeats=1,
                         outputs_dir=self.out, inputs=self.inputs, label="reduced")
        self.assertIn("REDUCED", (r / "report.md").read_text())
        with self.assertRaises(RunError):
            run_final_fit(self.cfg, r, "logistic_regression", inputs=self.inputs)

    def test_final_fit_refused_for_model_not_validated(self):
        with self.assertRaises(RunError):
            run_final_fit(self.cfg, self.run_all, "random_forest", inputs=self.inputs)

    def test_final_fit_and_predict(self):
        import predict

        out = run_final_fit(self.cfg, self.run_all, "logistic_regression", inputs=self.inputs)
        schema = json.loads((out / "input_schema.json").read_text())
        self.assertEqual(set(schema["predictors"]), EXPECTED_INCLUDED)
        self.assertIn("no performance estimate of its own", schema["performance_note"])
        pipe, schema2 = predict.load_artifact(out)
        frame = SYN["features"].head(50)
        pred = predict.predict_frame(pipe, schema2, frame, self.cfg)
        self.assertEqual(len(pred), 50)
        self.assertTrue(pred["probability_7d"].between(0, 1).all())
        self.assertTrue(set(pred["alert"]) <= {0, 1})
        with self.assertRaises(data_mod.DataValidationError):
            predict.predict_frame(pipe, schema2, frame.drop(columns=["BRI_mean"]), self.cfg)
        with self.assertRaises(FileExistsError):
            out.mkdir(exist_ok=False)                               # artifact folder is never overwritten


class TestHoldout(unittest.TestCase):
    def test_infeasible_holdout_is_refused(self):
        from exacerbalert_ml.runner import apply_holdout

        raw = small_raw()
        raw["holdout"].update(enabled=True, min_positive_participants=50)
        cfg = config_from_dict(raw)
        md = modelling_data(inputs_from(SYN, cfg), cfg, "primary")
        with self.assertRaises(RunError):
            apply_holdout(md, cfg)

    def test_feasible_holdout_separates_participants(self):
        from exacerbalert_ml.runner import apply_holdout

        raw = small_raw()
        raw["holdout"].update(enabled=True, min_positive_participants=2)
        cfg = config_from_dict(raw)
        md = modelling_data(inputs_from(SYN, cfg), cfg, "primary")
        dev, hold, _ = apply_holdout(md, cfg)
        self.assertFalse(set(dev.groups) & set(hold.groups))
        self.assertEqual(len(dev.y) + len(hold.y), len(md.y))


# ---------------------------------------------------------------------------
class TestCommandLine(unittest.TestCase):
    """train.py -> fit_final.py -> predict.py on a synthetic project written to a temp folder."""

    def test_end_to_end(self):
        import fit_final
        import predict
        import train

        with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as outside:
            write_synthetic_project(proj, SYN)
            audit_dir, temporal_csv = write_audit_inputs(outside, SYN)
            raw = small_raw()
            raw["feature_exclusions"].update(feature_audit_dir=str(audit_dir),
                                             temporal_verification_csv=str(temporal_csv))
            cfg_path = Path(outside) / "config.yaml"
            cfg_path.write_text(yaml.safe_dump(raw))
            common = ["--config", str(cfg_path), "--project-dir", proj]
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = train.main(common + ["--analyses", "all", "--models", "logistic_regression", "--quiet"])
            self.assertEqual(rc, 0, buf.getvalue())
            runs = list((Path(proj) / "ml/outputs/runs").iterdir())
            self.assertEqual(len(runs), 1)
            ids = SYN["features"]["Participant_ID"].unique()
            self.assertFalse(any(i in buf.getvalue() for i in ids))
            self.assertEqual(scan_for_identifiers(runs[0], ids), [])
            meta = json.loads((runs[0] / "run_metadata.json").read_text())
            self.assertEqual(set(meta["inputs"]), {"features", "labels", "feature_dictionary", "feature_audit",
                                                   "temporal_verification", "config"})
            self.assertNotIn(proj, json.dumps(meta))

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(fit_final.main(common + ["--run-dir", str(runs[0]),
                                                          "--model", "logistic_regression"]), 0)
            model_dir = runs[0] / "final_model_logistic_regression"
            feats = Path(proj) / "data/processed/features/final_feature_dataset.parquet"

            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                rc = predict.main(common + ["--model-dir", str(model_dir), "--input", str(feats),
                                            "--output", str(Path(proj) / "preds.csv")])
            self.assertEqual(rc, 2)
            self.assertIn("outside the project", err.getvalue())

            target = Path(outside) / "preds" / "predictions.csv"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = predict.main(common + ["--model-dir", str(model_dir), "--input", str(feats),
                                            "--output", str(target)])
            self.assertEqual(rc, 0)
            self.assertTrue(target.is_file())
            self.assertFalse(any(i in buf.getvalue() for i in ids))

            # Changed inputs after cross-validation -> final fit refused.
            (audit_dir / "feature_audit.csv").write_text(
                (audit_dir / "feature_audit.csv").read_text() + "EXTRA_feature,include,\n")
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                rc = fit_final.main(common + ["--run-dir", str(runs[0]), "--model", "logistic_regression"])
            self.assertEqual(rc, 2)
            self.assertIn("inputs changed", err.getvalue())

    def test_missing_audit_gives_safe_error(self):
        import train

        with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as outside:
            write_synthetic_project(proj, SYN)
            raw = small_raw()
            raw["feature_exclusions"].update(feature_audit_dir=str(Path(outside) / "none"),
                                             temporal_verification_csv=str(Path(outside) / "none.csv"))
            cfg_path = Path(outside) / "config.yaml"
            cfg_path.write_text(yaml.safe_dump(raw))
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                rc = train.main(["--config", str(cfg_path), "--project-dir", proj, "--quiet"])
            self.assertEqual(rc, 2)
            self.assertIn("ERROR [audit_inputs]", err.getvalue())
            self.assertNotIn("Traceback", err.getvalue())
            self.assertFalse((Path(proj) / "ml/outputs").exists())

    def test_outputs_inside_project_refused(self):
        import train

        with tempfile.TemporaryDirectory() as proj:
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                rc = train.main(["--project-dir", proj, "--outputs", str(Path(proj) / "data"), "--quiet"])
            self.assertEqual(rc, 2)
            self.assertIn("ml/outputs", err.getvalue())


if __name__ == "__main__":
    unittest.main()
