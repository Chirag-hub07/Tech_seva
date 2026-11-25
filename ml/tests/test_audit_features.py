"""In-memory tests for ml/audit_features.py. Synthetic data only.

Every dataset here is built in memory. While the audit runs, all file-reading
entry points (builtins.open, io.open, pandas readers) are patched to raise,
so any attempt to read a dataset file makes the test fail.
Run from ml/:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import builtins
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import audit_features as af
from exacerbalert_ml import data as data_mod
from exacerbalert_ml.config import DEFAULT_CONFIG_PATH, load_config
from synthetic import make_synthetic

# A project root that does not exist: nothing can be resolved from it.
CFG = load_config(DEFAULT_CONFIG_PATH, project_root="/nonexistent/exacerbalert_test_root")
EXTREME = 987654.321


class FileAccessError(AssertionError):
    pass


@contextlib.contextmanager
def no_file_reads():
    """Fail loudly if anything tries to open or read a file."""
    def deny(*args, **kwargs):
        raise FileAccessError(f"file access attempted: {args[:1]}")
    patches = [mock.patch.object(builtins, "open", deny), mock.patch.object(io, "open", deny),
               mock.patch.object(Path, "open", deny), mock.patch.object(Path, "read_text", deny),
               mock.patch.object(Path, "read_bytes", deny)]
    for name in ("read_parquet", "read_csv", "read_excel", "read_json", "read_table", "read_pickle"):
        patches.append(mock.patch.object(pd, name, deny))
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        yield


def synthetic_inputs(variant: str = "full", seed: int = 1):
    """Merged table, dictionary and events - all in memory."""
    d = make_synthetic(seed)
    f = d["features"].copy()
    n = len(f)
    rng = np.random.default_rng(5)
    f["leaky_signal"] = d["labels"]["exacerbation_within_7d"].fillna(0).to_numpy() + rng.normal(0, 0.05, n)
    f["days_to_next_exacerbation"] = rng.normal(size=n)                    # banned name
    f["SII_future_window_feature"] = rng.normal(size=n)                    # future time window
    f["SYN-E01_custom_metric"] = rng.normal(size=n)                        # ID inside a name
    f["MI_quarter_missing"] = np.where(np.arange(n) % 4 == 0, np.nan, rng.normal(size=n))
    f["PEI_all_missing"] = np.nan
    f.loc[3, "BRI_mean_rolling_7d_mean"] = EXTREME                         # raw value that must not leak
    f["free_text_note"] = pd.Series(np.where(rng.random(n) < 0.5, "abc", "xyz"), dtype="object")
    f["sync_time"] = pd.Timestamp("2031-06-01", tz="UTC")                  # datetime column
    f["doc_text_column"] = pd.Series(["lorem"] * n, dtype="object")        # documented but text

    dic = pd.concat([d["dictionary"], pd.DataFrame({
        "Feature": ["leaky_signal", "days_to_next_exacerbation", "SII_future_window_feature",
                    "SYN-E01_custom_metric", "MI_quarter_missing", "PEI_all_missing", "doc_text_column",
                    "ghost_feature"],
        "Feature_Group": ["Daily", "Daily", "Rolling", "Daily", "Daily", "Daily", "Daily", "Daily"],
        "Time_Window": ["Current calendar day", "Current calendar day", "Next 7 calendar days",
                        "Current calendar day", "Current calendar day", "Current calendar day",
                        "Current calendar day", "Current calendar day"],
    })], ignore_index=True)
    dic["Description"] = "synthetic description"
    dic.loc[dic["Feature"] == "BRI_mean", "Description"] = "mentions SYN-E02 inside text"
    if variant == "minimal_dictionary":
        dic = dic[["Feature"]]
    if variant == "duplicate_dictionary_entry":
        dic = pd.concat([dic, dic.iloc[[0]]], ignore_index=True)

    feats = data_mod.normalize_keys(f, CFG, "features")
    labs = data_mod.normalize_keys(d["labels"], CFG, "labels")
    merged = data_mod.join_features_labels(feats, labs, CFG)
    return d, merged, dic


def run_audit(variant="full", washout=14):
    d, merged, dic = synthetic_inputs(variant)
    with no_file_reads():
        table, lines = af.audit_frames(merged, dic, CFG, washout, events=d["events"])
    return d, merged, dic, table, lines


def reference_rows(merged, events, washout=14):
    """Independent reference for the primary modelling rows, aligned with `merged` (join order)."""
    lab, ev = merged, events
    keep = lab["exacerbation_within_7d"].notna().to_numpy().copy()
    for i, (p, dt) in enumerate(zip(lab["Participant_ID"], lab["Date"])):
        e = ev.loc[(ev["participant"] == p) & (ev["event_date"] <= dt), "event_date"]
        if washout is not None and len(e) and (dt - e.max()).days <= washout:
            keep[i] = False
    return keep


class TestAuditFramesInMemory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d, cls.merged, cls.dic, cls.t, cls.lines = run_audit()
        cls.row = staticmethod(lambda name: cls.t.loc[cls.t["feature"] == name].iloc[0])
        cls.keep = reference_rows(cls.merged, cls.d["events"])

    def test_no_file_access_guard_is_active(self):
        with no_file_reads():
            with self.assertRaises(FileAccessError):
                pd.read_parquet("anything.parquet")
            with self.assertRaises(FileAccessError):
                open("anything.csv")

    def test_audit_needs_events_or_reads_from_disk_which_is_blocked(self):
        # Without in-memory events the audit would resolve raw event files; the guard must catch it.
        d, merged, dic = synthetic_inputs()
        with no_file_reads(), self.assertRaises((FileAccessError, FileNotFoundError)):
            af.audit_frames(merged, dic, CFG, 14)

    def test_one_row_per_candidate_column(self):
        expected = [c for c in self.merged.columns if c not in
                    {"Participant_ID", "Date", "exacerbation_within_7d", "label_status",
                     "matched_event_date", "matched_event_severity"}]
        self.assertEqual(len(self.t), len(expected))

    # ---- missingness ---------------------------------------------------
    def test_missing_fractions_match_reference(self):
        merged = self.merged
        q = merged.loc[self.keep, "MI_quarter_missing"]
        y = merged.loc[self.keep, "exacerbation_within_7d"]
        r = self.row("MI_quarter_missing")
        self.assertEqual(r["missing_modelling_rows"], round(float(q.isna().mean()), 4))
        self.assertEqual(r["missing_all_rows"], round(float(merged["MI_quarter_missing"].isna().mean()), 4))
        self.assertEqual(r["missing_positive_rows"], round(float(q[y == 1].isna().mean()), 4))
        self.assertEqual(r["missing_negative_rows"], round(float(q[y == 0].isna().mean()), 4))

    def test_missingness_flags(self):
        self.assertIn("all_missing_in_modelling_rows", self.row("PEI_all_missing")["exclude_reasons"])
        sparse = self.t[(self.t["missing_modelling_rows"] > 0.95) & (self.t["missing_modelling_rows"] < 1)]
        self.assertGreaterEqual(len(sparse), 1)
        self.assertTrue(sparse["review_reasons"].str.contains("missing_over_95pct").all())
        low = self.t[self.t["missing_modelling_rows"] <= 0.95]
        self.assertFalse(low["review_reasons"].str.contains("missing_over_95pct").any())

    def test_modelling_row_count_matches_reference(self):
        self.assertIn(f"Primary modelling rows: {int(self.keep.sum())} ", "\n".join(self.lines))

    # ---- dictionary ----------------------------------------------------
    def test_dictionary_mapping(self):
        r = self.row("BRI_mean_rolling_7d_mean")
        self.assertEqual(r["dict_Feature_Group"], "Rolling")
        self.assertEqual(r["dict_Time_Window"], "Previous 7 calendar days")
        self.assertIn("dictionary entries without column: 1", "\n".join(self.lines))  # ghost_feature

    def test_missing_dictionary_entry_is_undocumented(self):
        r = self.row("UNDOCUMENTED_extra")
        self.assertFalse(r["documented"])
        self.assertIn("undocumented", r["exclude_reasons"])
        self.assertEqual(r["dict_Feature_Group"], "")

    def test_minimal_dictionary(self):
        _, _, _, t, _ = run_audit("minimal_dictionary")
        self.assertFalse(t["exclude_reasons"].str.contains("future_time_window").any())
        self.assertFalse(any(c.startswith("dict_") for c in t.columns))

    def test_duplicate_dictionary_entry_tolerated(self):
        _, _, _, t, _ = run_audit("duplicate_dictionary_entry")
        self.assertEqual(len(t), len(self.t))

    def test_dictionary_without_feature_column_rejected(self):
        d, merged, dic = synthetic_inputs()
        with self.assertRaises(ValueError):
            af.audit_frames(merged, dic.rename(columns={"Feature": "Name"}), CFG, 14, events=d["events"])

    # ---- leakage screens -----------------------------------------------
    def test_banned_undocumented_future(self):
        self.assertIn("banned_name", self.row("days_to_next_exacerbation")["exclude_reasons"])
        self.assertIn("future_time_window", self.row("SII_future_window_feature")["exclude_reasons"])
        self.assertEqual(self.row("SII_future_window_feature")["decision"], "exclude")

    def test_leaky_feature_flagged_not_removed(self):
        r = self.row("leaky_signal")
        self.assertIn("high_target_correlation_check_for_leakage", r["review_reasons"])
        self.assertEqual(r["decision"], "review")

    def test_time_in_study_proxy(self):
        r = self.row("BRI_mean_baseline_count")
        self.assertIn("time_in_study_proxy_name", r["review_reasons"])
        self.assertIn("high_correlation_with_days_in_study", r["review_reasons"])

    def test_duplicate_and_constant(self):
        self.assertEqual(self.row("SQI_copy_of_BRI_mean")["duplicate_of"], "BRI_mean")
        self.assertIn("constant_in_modelling_rows", self.row("EI_constant")["exclude_reasons"])

    # ---- non-numeric columns -------------------------------------------
    def test_non_numeric_columns(self):
        for col, kind, documented in (("free_text_note", "text", False), ("sync_time", "datetime", False),
                                      ("doc_text_column", "text", True)):
            r = self.row(col)
            self.assertEqual(r["value_kind"], kind)
            self.assertIn("non_numeric_column", r["exclude_reasons"])
            self.assertEqual(r["documented"], documented)
            self.assertTrue(pd.isna(r["pearson_r_target"]))
            self.assertNotIn("missing_over_95pct", r["review_reasons"])
        # In memory MI_flag is an object column holding booleans (it becomes "boolean" after Parquet).
        self.assertEqual(self.row("MI_flag")["value_kind"], "boolean_like")

    # ---- correlations --------------------------------------------------
    def test_correlations_match_numpy_and_scipy(self):
        merged = self.merged
        y = merged.loc[self.keep, "exacerbation_within_7d"].to_numpy()
        first = merged.groupby("Participant_ID")["Date"].transform("min")
        days = (merged["Date"] - first).dt.days.to_numpy()[self.keep]
        for feat in ("leaky_signal", "BRI_mean", "BRI_mean_baseline_count", "MI_quarter_missing"):
            x = merged.loc[self.keep, feat].astype("float64").to_numpy()
            m = ~np.isnan(x)
            self.assertAlmostEqual(self.row(feat)["pearson_r_target"], np.corrcoef(x[m], y[m])[0, 1], places=3)
            self.assertAlmostEqual(self.row(feat)["spearman_r_days_in_study"],
                                   spearmanr(x[m], days[m]).statistic, places=3)

    def test_too_few_pairs_gives_no_correlation(self):
        self.assertTrue(pd.isna(self.row("PRVI_sparse")["pearson_r_target"]))

    # ---- privacy -------------------------------------------------------
    def test_no_identifiers_dates_or_raw_values_in_outputs(self):
        text = self.t.to_csv(index=False) + "\n".join(self.lines)
        for forbidden in ("SYN-", "2031-", "987654", "abc", "xyz", "lorem"):
            self.assertNotIn(forbidden, text)
        self.assertIn("<ID>_custom_metric", set(self.t["feature"]))
        self.assertEqual(self.row("BRI_mean")["dict_Description"], "mentions <ID> inside text")
        self.assertFalse({"min", "max"} & {c.lower() for c in self.t.columns})

    def test_washout_changes_row_counts(self):
        counts = []
        for w in (None, 14, 28):
            _, _, _, _, lines = run_audit(washout=w)
            counts.append(int("\n".join(lines).split("Primary modelling rows: ")[1].split(" ")[0]))
            self.assertIn(f"Primary modelling rows: {int(reference_rows(self.merged, self.d['events'], w).sum())} ",
                          "\n".join(lines))
        self.assertGreater(counts[0], counts[1])
        self.assertGreater(counts[1], counts[2])


class TestHelpers(unittest.TestCase):
    def test_to_numeric_frame_kinds(self):
        cases = {
            "obj_bool": (pd.Series([True, None, False], dtype="object"), "boolean_like", [1.0, None, 0.0]),
            "obj_text": (pd.Series(["abc", "xyz", None], dtype="object"), "text", [None] * 3),
            "obj_mixed": (pd.Series([1, "2", "n/a"], dtype="object"), "text", [None] * 3),
            "string": (pd.Series(["a", "b", None], dtype="string"), "text", [None] * 3),
            "tz_datetime": (pd.Series(pd.to_datetime(["2031-01-01"] * 3, utc=True)), "datetime", [None] * 3),
            "naive_datetime": (pd.Series(pd.to_datetime(["2031-01-01"] * 3)), "datetime", [None] * 3),
            "pd_boolean": (pd.Series([True, pd.NA, False], dtype="boolean"), "boolean", [1.0, None, 0.0]),
            "np_bool": (pd.Series([True, False, True]), "boolean", [1.0, 0.0, 1.0]),
            "int": (pd.Series([1, 2, 3]), "numeric", [1.0, 2.0, 3.0]),
            "float_nan": (pd.Series([1.5, np.nan, 2.5]), "numeric", [1.5, None, 2.5]),
        }
        frame, kinds = af.to_numeric_frame(pd.DataFrame({k: v[0] for k, v in cases.items()}))
        for k, (_, kind, expected) in cases.items():
            self.assertEqual(kinds[k], kind, k)
            self.assertEqual([None if pd.isna(v) else float(v) for v in frame[k]], expected, k)
            self.assertEqual(frame[k].dtype, np.float64, k)

    def test_redactor(self):
        red = af.redactor(["SYN-E01", "AB"])            # IDs shorter than 3 chars are ignored
        self.assertEqual(red("SYN-E01_x"), "<ID>_x")
        self.assertEqual(red("XSYN-E01"), "XSYN-E01")   # not a whole-token match
        self.assertEqual(red("AB_feature"), "AB_feature")
        self.assertEqual(af.redactor([])("SYN-E01"), "SYN-E01")

    def test_safe_out_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            root.mkdir()
            with self.assertRaises(SystemExit):
                af.safe_out_dir(root / "reports", root)
            with self.assertRaises(SystemExit):
                af.safe_out_dir(root, root)
            self.assertEqual(af.safe_out_dir(Path(tmp) / "outside", root), (Path(tmp) / "outside").resolve())

    def test_parse_washout(self):
        self.assertEqual(af.parse_washout("primary", CFG), 14)
        self.assertIsNone(af.parse_washout("none", CFG))
        self.assertEqual(af.parse_washout("28", CFG), 28)
        with self.assertRaises(ValueError):
            af.parse_washout("-1", CFG)

    def test_column_hash_stable_and_sensitive(self):
        a = pd.Series([1.0, np.nan, 3.0])
        self.assertEqual(af.column_hash(a), af.column_hash(a.copy()))
        self.assertNotEqual(af.column_hash(a), af.column_hash(pd.Series([1.0, np.nan, 4.0])))


class TestMainEndToEnd(unittest.TestCase):
    def test_main_reads_nothing_itself_and_writes_only_to_out_dir(self):
        d, merged, dic = synthetic_inputs()
        real_audit = af.audit_frames
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "audit_out"
            with mock.patch.object(af, "load_merged", return_value=merged), \
                 mock.patch.object(af, "load_feature_dictionary", return_value=dic), \
                 mock.patch.object(af, "audit_frames",
                                   side_effect=lambda m, di, c, w: real_audit(m, di, c, w, events=d["events"])), \
                 mock.patch.object(af.pd, "read_parquet", side_effect=FileAccessError), \
                 mock.patch.object(af.pd, "read_csv", side_effect=FileAccessError), \
                 contextlib.redirect_stdout(io.StringIO()) as buf:
                rc = af.main(["--project-dir", "/nonexistent/exacerbalert_test_root", "--out-dir", str(out)])
            self.assertEqual(rc, 0)
            self.assertEqual(sorted(p.name for p in out.iterdir()), ["feature_audit.csv", "feature_audit_summary.txt"])
            for text in (buf.getvalue(), (out / "feature_audit.csv").read_text(),
                         (out / "feature_audit_summary.txt").read_text()):
                self.assertNotIn("SYN-", text)
                self.assertNotIn("2031-", text)
                self.assertNotIn("987654", text)


if __name__ == "__main__":
    unittest.main()
