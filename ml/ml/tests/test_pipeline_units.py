"""Unit tests on synthetic data only. Run from ml/:  python -m unittest discover -s tests -v"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from exacerbalert_ml import data as data_mod
from exacerbalert_ml import labels as labels_mod
from exacerbalert_ml.config import DEFAULT_CONFIG_PATH, load_config
from exacerbalert_ml.dataset import build_modeling_data
from exacerbalert_ml.diagnostics import explain_event_participants_without_positives
from exacerbalert_ml.events import days_since_last_event, events_from_labels, load_raw_events, post_event_mask
from exacerbalert_ml.features import (ConstantColumnDropper, DuplicateColumnDropper, LeakageError,
                                      LeakageGuard, MissingnessFilter, BooleanToFloat, assert_no_banned,
                                      make_feature_filter_steps, select_predictors, time_in_study_proxies)
from exacerbalert_ml.splits import (SplitError, assert_group_separation, assign_participant_folds,
                                    inner_splits, outer_splits, split_summary)

try:
    import pyarrow  # noqa: F401
    HAVE_PYARROW = True
except ImportError:  # pragma: no cover
    HAVE_PYARROW = False

from synthetic import make_synthetic, write_synthetic_project

CFG = load_config(DEFAULT_CONFIG_PATH, project_root=".")


def merged_synthetic(seed=0):
    d = make_synthetic(seed)
    f = data_mod.normalize_keys(d["features"], CFG, "features")
    lab = data_mod.normalize_keys(d["labels"], CFG, "labels")
    return d, data_mod.join_features_labels(f, lab, CFG)


# ---------------------------------------------------------------------------
class TestDataJoin(unittest.TestCase):
    def test_one_to_one_join_keeps_all_rows(self):
        d, merged = merged_synthetic()
        self.assertEqual(len(merged), len(d["features"]))
        self.assertEqual(merged.shape[1], d["features"].shape[1] + 4)

    def test_duplicate_key_rejected(self):
        d = make_synthetic()
        f = pd.concat([d["features"], d["features"].iloc[[3]]], ignore_index=True)
        with self.assertRaises(data_mod.DataValidationError):
            data_mod.normalize_keys(f, CFG, "features")

    def test_mismatched_keys_rejected_without_ids_in_message(self):
        d = make_synthetic()
        f = data_mod.normalize_keys(d["features"], CFG, "features")
        lab = data_mod.normalize_keys(d["labels"].iloc[:-5], CFG, "labels")
        with self.assertRaises(data_mod.DataValidationError) as ctx:
            data_mod.join_features_labels(f, lab, CFG)
        self.assertNotIn("SYN-", str(ctx.exception))

    def test_time_of_day_rejected(self):
        d = make_synthetic()
        f = d["features"].copy()
        f.loc[0, "Date"] = f.loc[0, "Date"] + pd.Timedelta(hours=5)
        with self.assertRaises(data_mod.DataValidationError):
            data_mod.normalize_keys(f, CFG, "features")

    def test_label_columns_inside_features_rejected(self):
        d = make_synthetic()
        f = d["features"].copy()
        f["label_status"] = "x"
        f = data_mod.normalize_keys(f, CFG, "features")
        lab = data_mod.normalize_keys(d["labels"], CFG, "labels")
        with self.assertRaises(data_mod.DataValidationError):
            data_mod.join_features_labels(f, lab, CFG)

    @unittest.skipUnless(HAVE_PYARROW, "pyarrow not installed")
    def test_parquet_round_trip_from_config_paths(self):
        d = make_synthetic()
        with tempfile.TemporaryDirectory() as tmp:
            write_synthetic_project(tmp, d)
            cfg = load_config(DEFAULT_CONFIG_PATH, project_root=tmp)
            merged = data_mod.load_merged(cfg)
            self.assertEqual(len(merged), len(d["features"]))
            self.assertEqual(str(merged["Date"].dt.tz), "UTC")


# ---------------------------------------------------------------------------
class TestLabelPolicy(unittest.TestCase):
    def setUp(self):
        self.d, self.merged = merged_synthetic()

    def test_original_policy_keeps_unknowns_unknown(self):
        out = labels_mod.apply_label_policy(self.merged, CFG, "original")
        unknown = self.merged["label_status"].str.startswith("unknown")
        self.assertTrue(out.loc[unknown, "target"].isna().all())
        pd.testing.assert_series_equal(out["target"], self.merged["exacerbation_within_7d"].astype("float64"),
                                       check_names=False)

    def test_tolife_policy_negative_only_with_full_followup(self):
        out = labels_mod.apply_label_policy(self.merged, CFG, "tolife_v1_absent_file_negative")
        no_file = self.merged["label_status"] == labels_mod.UNKNOWN_NO_FILE
        last = self.merged.groupby("Participant_ID")["Date"].transform("max")
        covered = self.merged["Date"] + pd.Timedelta(days=7) <= last
        self.assertTrue((out.loc[no_file & covered, "target"] == 0).all())
        self.assertTrue(out.loc[no_file & ~covered, "target"].isna().all())
        self.assertGreater(int((no_file & ~covered).sum()), 0)
        # Short participant never has a full window -> all unknown.
        self.assertTrue(out.loc[self.merged["Participant_ID"] == "SYN-N04", "target"].isna().all())

    def test_tolife_policy_never_touches_other_rows(self):
        out = labels_mod.apply_label_policy(self.merged, CFG, "tolife_v1_absent_file_negative")
        other = self.merged["label_status"] != labels_mod.UNKNOWN_NO_FILE
        pd.testing.assert_series_equal(out.loc[other, "target"],
                                       self.merged.loc[other, "exacerbation_within_7d"].astype("float64"),
                                       check_names=False)
        inc = self.merged["label_status"] == labels_mod.UNKNOWN_INCOMPLETE
        self.assertGreater(int(inc.sum()), 0)
        self.assertTrue(out.loc[inc, "target"].isna().all())

    def test_conflicting_positive_for_no_file_participant_rejected(self):
        m = self.merged.copy()
        i = m.index[m["Participant_ID"] == "SYN-N01"][0]
        m.loc[i, ["exacerbation_within_7d", "label_status"]] = [1.0, labels_mod.POSITIVE]
        with self.assertRaises(data_mod.DataValidationError):
            labels_mod.apply_label_policy(m, CFG, "tolife_v1_absent_file_negative")

    def test_inconsistent_original_labels_rejected(self):
        m = self.merged.copy()
        i = m.index[m["label_status"] == labels_mod.UNKNOWN_INCOMPLETE][0]
        m.loc[i, "exacerbation_within_7d"] = 0.0
        with self.assertRaises(data_mod.DataValidationError):
            labels_mod.apply_label_policy(m, CFG, "original")

    def test_summary_has_no_identifiers(self):
        out = labels_mod.apply_label_policy(self.merged, CFG)
        s = labels_mod.label_summary(out, CFG)
        self.assertNotIn("SYN-", repr(s))
        self.assertEqual(s["known"] + s["unknown"], s["rows"])


# ---------------------------------------------------------------------------
class TestPostEvent(unittest.TestCase):
    def setUp(self):
        self.d, self.merged = merged_synthetic()

    def test_days_since_and_washout_window(self):
        ev = self.d["events"]
        ds = days_since_last_event(self.merged, ev, CFG)
        mask = post_event_mask(self.merged, ev, CFG, 14)
        self.assertTrue((mask == ds.between(0, 14)).all())
        # Rows strictly before any event are never excluded.
        first_ev = ev.groupby("participant")["event_date"].min()
        before = self.merged["Date"] < self.merged["Participant_ID"].map(first_ev)
        self.assertFalse(mask[before.fillna(True)].any())
        # The event day itself is excluded.
        e = ev.iloc[0]
        row = (self.merged["Participant_ID"] == e["participant"]) & (self.merged["Date"] == e["event_date"])
        self.assertTrue(mask[row].all())

    def test_disabled_washout_excludes_nothing(self):
        self.assertFalse(post_event_mask(self.merged, self.d["events"], CFG, None).any())

    def test_label_events_are_lower_bound(self):
        from_labels = events_from_labels(self.merged, CFG)
        self.assertLess(len(from_labels), len(self.d["events"]))  # first-date / late events missing

    @unittest.skipUnless(HAVE_PYARROW, "pyarrow not installed")
    def test_raw_event_loader(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_synthetic_project(tmp, self.d)
            cfg = load_config(DEFAULT_CONFIG_PATH, project_root=tmp)
            raw = load_raw_events(cfg)
            self.assertEqual(len(raw), len(self.d["events"]))
            self.assertEqual(raw.attrs["n_event_files"], len({p for p in self.d["events"]["participant"]}))


# ---------------------------------------------------------------------------
class TestDiagnostics(unittest.TestCase):
    def test_explains_event_participants_without_positives(self):
        d, merged = merged_synthetic()
        rep = explain_event_participants_without_positives(merged, d["events"], CFG)
        self.assertEqual(rep["participants_with_event_files_but_no_positive_labels"], 2)
        self.assertEqual(rep["events_by_reason"]["event_on_or_before_first_feature_date"], 1)
        self.assertEqual(rep["events_by_reason"]["event_more_than_horizon_after_last_feature_date"], 1)
        self.assertEqual(rep["events_by_reason"]["event_within_predictable_range"], 0)
        self.assertNotIn("SYN-", repr(rep))


# ---------------------------------------------------------------------------
class TestFeatureSelection(unittest.TestCase):
    def setUp(self):
        self.d, self.merged = merged_synthetic()
        self.dic = self.d["dictionary"].copy()

    def test_banned_and_undocumented_columns_never_selected(self):
        dic = pd.concat([self.dic, pd.DataFrame({"Feature": ["label_status", "Participant_ID", "Date"],
                                                 "Feature_Group": "x", "Time_Window": "Current calendar day"})])
        preds, rep = select_predictors(list(self.merged.columns), dic, CFG)
        for bad in ["Participant_ID", "Date", "exacerbation_within_7d", "label_status",
                    "matched_event_date", "matched_event_severity", "UNDOCUMENTED_extra"]:
            self.assertNotIn(bad, preds)
        self.assertEqual(rep["excluded_undocumented"], 1)

    def test_assert_no_banned_catches_patterns(self):
        for col in ["participant_id_hash", "days_to_next_exacerbation", "fold", "target_lag"]:
            with self.assertRaises(LeakageError):
                assert_no_banned([col], CFG)

    def test_future_time_window_rejected(self):
        dic = self.dic.copy()
        dic.loc[0, "Time_Window"] = "Next 7 calendar days"
        with self.assertRaises(LeakageError):
            select_predictors(list(self.merged.columns), dic, CFG)

    def test_feature_sets(self):
        compact, _ = select_predictors(list(self.merged.columns), self.dic, CFG, "compact")
        no_proxy, _ = select_predictors(list(self.merged.columns), self.dic, CFG, "compact_no_time_proxies")
        all_preds, _ = select_predictors(list(self.merged.columns), self.dic, CFG, "all")
        self.assertIn("BRI_mean_rolling_7d_mean", compact)
        self.assertIn("BRI_mean_baseline_deviation", compact)
        self.assertIn("BRI_mean", compact)                       # Daily group
        self.assertNotIn("BRI_mean_rolling_14d_mean", compact)
        self.assertEqual(time_in_study_proxies(all_preds, CFG), ["BRI_mean_baseline_count"])
        self.assertIn("BRI_mean_baseline_count", all_preds)
        self.assertNotIn("BRI_mean_baseline_count", no_proxy)
        self.assertTrue(set(no_proxy) <= set(compact))

    def test_leakage_guard_rejects_banned_allowlist(self):
        X = pd.DataFrame({"a": [1.0], "label_status": ["x"]})
        with self.assertRaises(LeakageError):
            LeakageGuard.from_config(["a", "label_status"], CFG).fit(X)


class TestFitOnTrainOnly(unittest.TestCase):
    """Filters learn from training rows only and are then applied unchanged."""

    def test_missingness_filter_uses_training_rows(self):
        Xtr = pd.DataFrame({"a": [np.nan] * 9 + [1.0], "b": np.arange(10.0)})
        Xva = pd.DataFrame({"a": np.arange(5.0), "b": np.arange(5.0)})  # 'a' complete in validation
        mf = MissingnessFilter(0.5).fit(Xtr)
        self.assertEqual(list(mf.transform(Xva).columns), ["b"])

    def test_constant_and_duplicate_learned_on_train(self):
        Xtr = pd.DataFrame({"c": [1.0, 1, 1, 1], "x": [1.0, 2, 3, 4], "x_dup": [1.0, 2, 3, 4]})
        Xva = pd.DataFrame({"c": [5.0, 6], "x": [1.0, 2], "x_dup": [9.0, 9]})
        self.assertEqual(list(ConstantColumnDropper().fit(Xtr).transform(Xva).columns), ["x", "x_dup"])
        self.assertEqual(list(DuplicateColumnDropper().fit(Xtr).transform(Xva).columns), ["c", "x"])

    def test_boolean_to_float_preserves_missing(self):
        X = pd.DataFrame({"f": pd.Series([True, None, False], dtype="object")})
        out = BooleanToFloat().fit_transform(X)
        self.assertTrue(np.isnan(out.loc[1, "f"]))
        self.assertEqual(out["f"].dtype, np.float64)

    def test_full_filter_chain_on_synthetic(self):
        from sklearn.pipeline import Pipeline

        d, merged = merged_synthetic()
        preds, _ = select_predictors(list(merged.columns), d["dictionary"], CFG)
        pipe = Pipeline(make_feature_filter_steps(preds, CFG))
        Xt = pipe.fit_transform(merged[preds])
        for dropped in ["EI_constant", "PRVI_sparse", "SQI_copy_of_BRI_mean"]:
            self.assertNotIn(dropped, Xt.columns)
        self.assertTrue(all(Xt.dtypes == np.float64))


# ---------------------------------------------------------------------------
class TestSplits(unittest.TestCase):
    def setUp(self):
        d, merged = merged_synthetic()
        md = build_modeling_data(merged, d["dictionary"], CFG, washout_days=None, events=d["events"])
        self.groups, self.y = md.groups.to_numpy(), md.y.to_numpy()

    def test_no_participant_in_train_and_test(self):
        for s in outer_splits(self.groups, self.y, 3, [1, 2, 3]):
            assert_group_separation(self.groups, s.train_idx, s.test_idx)
            self.assertEqual(len(s.train_idx) + len(s.test_idx), len(self.y))

    def test_every_participant_tested_exactly_once_per_repeat(self):
        splits = outer_splits(self.groups, self.y, 3, [7])
        tested = np.concatenate([self.groups[s.test_idx] for s in splits])
        self.assertEqual(len(tested), len(self.y))
        self.assertEqual(sorted(set(tested)), sorted(set(self.groups)))

    def test_each_test_fold_has_positive_participant(self):
        summ = split_summary(self.groups, self.y, outer_splits(self.groups, self.y, 3, [1, 2]))
        self.assertTrue((summ["test_positive_participants"] >= 1).all())
        self.assertNotIn("SYN-", summ.to_string())

    def test_deterministic_and_seed_dependent(self):
        a = assign_participant_folds(self.groups, self.y, 3, 5)
        b = assign_participant_folds(self.groups, self.y, 3, 5)
        pd.testing.assert_series_equal(a, b)
        others = [assign_participant_folds(self.groups, self.y, 3, s) for s in range(20)]
        self.assertTrue(any(not a.equals(o) for o in others))

    def test_inner_splits_stay_inside_training(self):
        outer = outer_splits(self.groups, self.y, 3, [3])[0]
        for s in inner_splits(self.groups, self.y, outer.train_idx, 2, 11):
            self.assertTrue(set(s.train_idx) | set(s.test_idx) <= set(outer.train_idx))
            assert_group_separation(self.groups, s.train_idx, s.test_idx)

    def test_unknown_targets_refused(self):
        y = self.y.astype("float64").copy()
        y[0] = np.nan
        with self.assertRaises(SplitError):
            outer_splits(self.groups, y, 3, [1])

    def test_too_few_positive_participants_refused(self):
        with self.assertRaises(SplitError):
            outer_splits(self.groups, self.y, 20, [1])


# ---------------------------------------------------------------------------
class TestModelingDataset(unittest.TestCase):
    def test_unknowns_dropped_and_no_banned_columns(self):
        d, merged = merged_synthetic()
        md = build_modeling_data(merged, d["dictionary"], CFG, events=d["events"])
        self.assertTrue(set(md.y.unique()) <= {0, 1})
        assert_no_banned(md.X.columns, CFG)
        self.assertNotIn("Participant_ID", md.X.columns)
        self.assertNotIn("Date", md.X.columns)
        self.assertEqual(len(md.X), len(md.y))

    def test_primary_washout_excludes_post_event_rows(self):
        d, merged = merged_synthetic()
        ev = d["events"]
        none = build_modeling_data(merged, d["dictionary"], CFG, washout_days=None, events=ev)
        prim = build_modeling_data(merged, d["dictionary"], CFG, events=ev)          # 14 days
        longer = build_modeling_data(merged, d["dictionary"], CFG, washout_days=28, events=ev)
        self.assertGreater(len(none.y), len(prim.y))
        self.assertGreater(len(prim.y), len(longer.y))
        self.assertGreater(prim.info["post_event_rows_excluded_known"], 0)
        self.assertNotIn("SYN-", repr(prim.info))

    def test_raw_event_source_extends_exclusion(self):
        d, merged = merged_synthetic()
        from_labels = build_modeling_data(merged, d["dictionary"], CFG, washout_days=14,
                                          events=events_from_labels(merged, CFG))
        from_raw = build_modeling_data(merged, d["dictionary"], CFG, washout_days=14, events=d["events"])
        # The first-date event of SYN-X01 is only known from the raw event files.
        self.assertLess(len(from_raw.y), len(from_labels.y))

    def test_configured_sources_match_config(self):
        # The approved configuration: conservative labels and raw event files.
        self.assertEqual(CFG["target"]["label_policy"], "original")
        self.assertEqual(CFG["post_event"]["event_source"], "raw")

    @unittest.skipUnless(HAVE_PYARROW, "pyarrow not installed")
    def test_configured_raw_event_source_reads_event_files_from_disk(self):
        # Real-data path: with no events passed, build_modeling_data must read the
        # raw exacerbations.csv files from the configured directory (synthetic here).
        d = make_synthetic()
        with tempfile.TemporaryDirectory() as tmp:
            write_synthetic_project(tmp, d)
            cfg = load_config(DEFAULT_CONFIG_PATH, project_root=tmp)
            merged = data_mod.load_merged(cfg)
            from_disk = build_modeling_data(merged, d["dictionary"], cfg)
            passed = build_modeling_data(merged, d["dictionary"], cfg, events=d["events"])
            self.assertEqual(len(from_disk.y), len(passed.y))
            self.assertEqual(from_disk.info, passed.info)

    def test_configured_raw_event_source_fails_loudly_when_directory_missing(self):
        # No silent fallback to the incomplete label-derived event list.
        d, merged = merged_synthetic()
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config(DEFAULT_CONFIG_PATH, project_root=tmp)
            with self.assertRaises(FileNotFoundError):
                build_modeling_data(merged, d["dictionary"], cfg)


if __name__ == "__main__":
    unittest.main()
