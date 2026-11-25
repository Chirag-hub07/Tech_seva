"""In-memory tests for ml/verify_temporal.py. Synthetic data only; no file reads.

Correct (backward-looking) features are built with explicit day-by-day loops
that mirror notebook 04's definitions, independently of the pandas code in
verify_temporal.py. Deliberately wrong features are planted alongside them.
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

import verify_temporal as vt
from exacerbalert_ml.config import DEFAULT_CONFIG_PATH, load_config

CFG = load_config(DEFAULT_CONFIG_PATH, project_root="/nonexistent/exacerbalert_test_root")
START = pd.Timestamp("2031-01-01", tz="UTC")
# Planted raw value that must never be printed. Ordinary magnitude on purpose: a huge
# value makes pandas' streaming rolling std lose precision versus the exact loop reference.
DISTINCT = 73.9182736
DISTINCT_TEXT = "73.918"
THRESH = {3: {"mean": 1, "std": 2, "min": 1, "max": 1},   # notebook 04 cell 125 thresholds
          7: {"mean": 2, "std": 2, "min": 2, "max": 2}}


class FileAccessError(AssertionError):
    pass


@contextlib.contextmanager
def no_file_reads():
    def deny(*a, **k):
        raise FileAccessError("file access attempted")
    with contextlib.ExitStack() as st:
        for obj, name in [(builtins, "open"), (io, "open"), (Path, "open"), (Path, "read_text"),
                          (pd, "read_parquet"), (pd, "read_csv")]:
            st.enter_context(mock.patch.object(obj, name, deny))
        yield


# ---------------------------------------------------------------------------
# Independent reference implementation (explicit loops)
# ---------------------------------------------------------------------------
def _stat(vals, stat):
    v = [x for x in vals if not np.isnan(x)]
    if stat == "count":
        return float(len(v))
    if not v:
        return np.nan
    if stat == "mean":
        return float(np.mean(v))
    if stat == "std":
        return float(np.std(v, ddof=1)) if len(v) >= 2 else np.nan
    if stat == "min":
        return float(min(v))
    if stat == "max":
        return float(max(v))
    if stat == "median":
        return float(np.median(v))
    if stat in ("change", "pct_change"):
        if len(v) < 2:
            return np.nan
        if stat == "change":
            return v[-1] - v[-2]
        return np.nan if v[-2] == 0 else (v[-1] - v[-2]) / v[-2] * 100
    raise ValueError(stat)


def loop_rolling(dates, x, w, stat, mode="historical"):
    out = []
    for i, d in enumerate(dates):
        if mode == "historical":
            sel = [x[j] for j, dj in enumerate(dates) if d - pd.Timedelta(days=w) <= dj < d]
        elif mode == "current":
            sel = [x[j] for j, dj in enumerate(dates) if d - pd.Timedelta(days=w) < dj <= d]
        elif mode == "future":
            sel = [x[j] for j, dj in enumerate(dates) if d < dj <= d + pd.Timedelta(days=w)]
        val = _stat(sel, stat)
        if stat in THRESH.get(w, {}):
            if _stat(sel, "count") < THRESH[w][stat]:
                val = np.nan
        out.append(val)
    return out


def loop_baseline(x, stat, mode="historical"):
    out = []
    for i in range(len(x)):
        past = x[:i] if mode == "historical" else x            # "whole": entire follow-up
        n = _stat(past, "count")
        if stat == "count":
            out.append(n)
            continue
        if n < 3:
            out.append(np.nan)
            continue
        if stat in ("mean", "std", "median"):
            out.append(_stat(past, stat))
        else:
            dev = x[i] - _stat(past, "mean")
            if stat == "deviation":
                out.append(dev)
            else:
                sd = _stat(past, "std")
                out.append(np.nan if (np.isnan(sd) or sd == 0) else dev / sd)
    return out


def make_features(n_participants=4, n_days=40, seed=3, with_bad=True):
    rng = np.random.default_rng(seed)
    rows = []
    for p in range(n_participants):
        dates = list(pd.date_range(START + pd.Timedelta(days=5 * p), periods=n_days, freq="D"))
        x = [np.nan if rng.random() < 0.25 else float(rng.normal(50, 10)) for _ in dates]
        x[5] = DISTINCT
        const = [7.0] * n_days
        rec = {"Participant_ID": [f"SYN-P{p:02d}"] * n_days, "Date": dates, "SRC": x, "CONST": const}
        for w in (3, 7):
            for st in ("mean", "std", "min", "max", "count", "change", "pct_change"):
                rec[f"SRC_rolling_{w}d_{st}"] = loop_rolling(dates, x, w, st)
        for st in ("mean", "std", "count", "median", "deviation", "standardized_deviation"):
            rec[f"SRC_baseline_{st}"] = loop_baseline(x, st)
        rec["CONST_rolling_7d_mean"] = loop_rolling(dates, const, 7, "mean")
        if with_bad:
            rec["BADCUR_rolling_7d_mean"] = loop_rolling(dates, x, 7, "mean", mode="current")
            rec["BADFUT_rolling_3d_max"] = loop_rolling(dates, x, 3, "max", mode="future")
            rec["BADWHOLE_baseline_mean"] = loop_baseline(x, "mean", mode="whole")
            rec["BADWHOLE_baseline_deviation"] = loop_baseline(x, "deviation", mode="whole")
            # Unrelated values, present only where a genuine 7-day std exists (pure MISMATCH).
            genuine = loop_rolling(dates, x, 7, "std")
            rec["BADNOISE_rolling_7d_std"] = [np.nan if np.isnan(g) else float(rng.normal())
                                              for g in genuine]
            nohist = loop_rolling(dates, x, 3, "mean")
            nohist[0] = 1.0                                         # value with no past data
            rec["BADNOHIST_rolling_3d_mean"] = nohist
            rec["MISSINGSRC_rolling_7d_mean"] = list(rng.normal(size=n_days))
        rows.append(pd.DataFrame(rec))
    f = pd.concat(rows, ignore_index=True)
    if with_bad:
        for bad in ("BADCUR", "BADFUT", "BADWHOLE", "BADNOISE", "BADNOHIST"):
            f[bad] = f["SRC"]                                       # sources for the bad features
    return f


def run(features, sample=None):
    with no_file_reads():
        return vt.verify_frame(features, CFG, sample_per_family=sample)


class TestVerifyTemporal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table, cls.summary = run(make_features())
        cls.status = dict(zip(cls.table["feature"], cls.table["status"]))

    def test_all_correct_backward_features_pass(self):
        good = [f for f in self.status if f.startswith("SRC_")]
        self.assertEqual(len(good), 2 * 7 + 6)
        failing = {f: s for f, s in self.status.items() if f.startswith("SRC_") and s != vt.PASS}
        self.assertEqual(failing, {})

    def test_feature_including_current_day_fails(self):
        self.assertEqual(self.status["BADCUR_rolling_7d_mean"], vt.FAIL_AHEAD)
        row = self.table.set_index("feature").loc["BADCUR_rolling_7d_mean"]
        self.assertEqual(row["best_lookahead_variant"], "includes_current_day")

    def test_future_window_feature_fails(self):
        self.assertEqual(self.status["BADFUT_rolling_3d_max"], vt.FAIL_AHEAD)
        row = self.table.set_index("feature").loc["BADFUT_rolling_3d_max"]
        self.assertEqual(row["best_lookahead_variant"], "future_window")

    def test_whole_follow_up_baselines_fail(self):
        for f in ("BADWHOLE_baseline_mean", "BADWHOLE_baseline_deviation"):
            self.assertEqual(self.status[f], vt.FAIL_AHEAD, f)
            self.assertEqual(self.table.set_index("feature").loc[f, "best_lookahead_variant"], "whole_follow_up")

    def test_values_without_history_fail(self):
        self.assertEqual(self.status["BADNOHIST_rolling_3d_mean"], vt.FAIL_NO_HISTORY)

    def test_unrelated_values_are_mismatch(self):
        self.assertEqual(self.status["BADNOISE_rolling_7d_std"], vt.MISMATCH)

    def test_constant_source_is_inconclusive(self):
        self.assertEqual(self.status["CONST_rolling_7d_mean"], vt.INCONCLUSIVE)

    def test_missing_source_reported(self):
        self.assertEqual(self.status["MISSINGSRC_rolling_7d_mean"], vt.NO_SOURCE)

    def test_overall_result_flags_attention(self):
        lines = vt.summary_lines(self.table, self.summary, None)
        self.assertTrue(lines[-1].startswith("RESULT: ATTENTION"))

    def test_clean_table_passes_overall(self):
        table, summary = run(make_features(with_bad=False))
        lines = vt.summary_lines(table, summary, None)
        self.assertTrue(lines[-1].startswith("RESULT: PASS"), lines[-1])
        self.assertEqual(set(table["status"]) - {vt.PASS, vt.INCONCLUSIVE}, set())

    def test_calendar_gap_detected(self):
        f = make_features(with_bad=False)
        f = f.drop(index=f.index[10])                       # remove one day of one participant
        _, summary = run(f)
        self.assertEqual(summary["calendar"]["participants_with_gaps"], 1)
        self.assertTrue(vt.summary_lines(*run(f), None)[-1].startswith("RESULT: ATTENTION"))

    def test_label_columns_in_feature_table_reported(self):
        f = make_features(with_bad=False)
        f["label_status"] = "x"
        f["matched_event_date"] = pd.NaT
        _, summary = run(f)
        self.assertEqual(set(summary["forbidden_columns_in_feature_table"]), {"label_status", "matched_event_date"})

    def test_no_identifiers_dates_or_values_in_outputs(self):
        text = self.table.to_csv(index=False) + "\n".join(vt.summary_lines(self.table, self.summary, None))
        for forbidden in ("SYN-", "2031-", DISTINCT_TEXT):
            self.assertNotIn(forbidden, text)

    def test_row_order_does_not_matter(self):
        f = make_features().sample(frac=1.0, random_state=1)
        table, _ = run(f)
        self.assertEqual(dict(zip(table["feature"], table["status"])), self.status)

    def test_sampling_is_deterministic_and_bounded(self):
        f = make_features()
        a, _ = run(f, sample=2)
        b, _ = run(f, sample=2)
        self.assertEqual(list(a["feature"]), list(b["feature"]))
        self.assertTrue((a.groupby(["family", "statistic"]).size() <= 2).all())


class TestHelpers(unittest.TestCase):
    def test_parse_feature(self):
        self.assertEqual(vt.parse_feature("A_rolling_7d_pct_change"), ("rolling", "pct_change", "A", 7))
        self.assertEqual(vt.parse_feature("A_rolling_14d_change"), ("rolling", "change", "A", 14))
        self.assertEqual(vt.parse_feature("A_x_baseline_standardized_deviation"),
                         ("baseline", "standardized_deviation", "A_x", None))
        self.assertIsNone(vt.parse_feature("A_availability"))

    def test_match_fraction(self):
        a = pd.Series([1.0, np.nan, 3.0])
        self.assertEqual(vt.match_fraction(a, pd.Series([1.0, 5.0, 3.0])), (1.0, 2))
        self.assertEqual(vt.match_fraction(a, pd.Series([1.0, 5.0, 4.0])), (0.5, 2))
        self.assertEqual(vt.match_fraction(pd.Series([np.nan, 2.0]), pd.Series([0.0, 2.0]), count_stat=True), (1.0, 2))

    def test_classify(self):
        self.assertEqual(vt.classify({"historical": 1.0, "x": 0.2}, 50, 0), (vt.PASS, ""))
        self.assertEqual(vt.classify({"historical": 1.0, "x": 1.0}, 50, 0), (vt.INCONCLUSIVE, "x"))
        self.assertEqual(vt.classify({"historical": 0.3, "x": 1.0}, 50, 0), (vt.FAIL_AHEAD, "x"))
        self.assertEqual(vt.classify({"historical": 0.3, "x": 0.4}, 50, 0), (vt.MISMATCH, "x"))
        self.assertEqual(vt.classify({"historical": 1.0}, 5, 0), (vt.INSUFFICIENT, ""))
        self.assertEqual(vt.classify({"historical": 1.0}, 50, 3), (vt.FAIL_NO_HISTORY, ""))
        # Order: look-ahead diagnosis beats values-without-history, which beats mismatch.
        self.assertEqual(vt.classify({"historical": 0.3, "x": 1.0}, 50, 3), (vt.FAIL_AHEAD, "x"))
        self.assertEqual(vt.classify({"historical": 0.3, "x": 0.2}, 50, 3), (vt.FAIL_NO_HISTORY, ""))

    def test_safe_out_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            root.mkdir()
            with self.assertRaises(SystemExit):
                vt.safe_out_dir(root / "out", root)
            self.assertEqual(vt.safe_out_dir(Path(tmp) / "o", root), (Path(tmp) / "o").resolve())


class TestMain(unittest.TestCase):
    def _main(self, features, extra=()):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            with mock.patch.object(vt, "load_features", return_value=features), \
                 mock.patch.object(vt.pd, "read_parquet", side_effect=FileAccessError), \
                 mock.patch.object(vt.pd, "read_csv", side_effect=FileAccessError), \
                 contextlib.redirect_stdout(io.StringIO()) as buf:
                rc = vt.main(["--project-dir", "/nonexistent/exacerbalert_test_root", "--all",
                              "--out-dir", str(out), *extra])
            files = sorted(p.name for p in out.iterdir())
            texts = [buf.getvalue()] + [(out / n).read_text() for n in files]
        return rc, files, texts

    def test_main_exit_codes_and_outputs(self):
        rc_ok, files, texts = self._main(make_features(with_bad=False))
        self.assertEqual(rc_ok, 0)
        self.assertEqual(files, ["temporal_verification.csv", "temporal_verification_summary.txt"])
        rc_bad, _, texts_bad = self._main(make_features())
        self.assertEqual(rc_bad, 1)
        for t in texts + texts_bad:
            for forbidden in ("SYN-", "2031-", DISTINCT_TEXT):
                self.assertNotIn(forbidden, t)


# ---------------------------------------------------------------------------
# Privacy protections: redaction of names and safe error handling
# ---------------------------------------------------------------------------
PLANTED_ID = "SYN-P00"                                     # a participant ID in the synthetic data
FAKE_HOME = str(Path.home())
FAKE_USER = vt._safe_username()
FAKE_PATHS = (f"{FAKE_HOME}/Tech_seva/data/processed/final_feature_dataset.parquet",
              "/Users/someone/Tech_seva/data/x.parquet",
              "C:\\Users\\someone\\Tech_seva\\data\\x.parquet",
              "~/Tech_seva/data/x.parquet")


def features_with_sensitive_names():
    """Synthetic table whose COLUMN NAMES contain a participant ID and a date."""
    f = make_features(with_bad=False)
    f[f"{PLANTED_ID}_custom"] = f["SRC"]                                   # source named with an ID
    f[f"{PLANTED_ID}_custom_rolling_7d_mean"] = f["SRC_rolling_7d_mean"]   # correct backward feature
    f["metric_2031-02-03"] = f["SRC"]                                      # source named with a date
    f["metric_2031-02-03_rolling_3d_mean"] = f["SRC_rolling_3d_mean"]
    f[f"patient_id_{PLANTED_ID}"] = 1.0                                    # banned column with an ID
    return f


def assert_clean(test, text, extra=()):
    for forbidden in ("SYN-", "2031-", DISTINCT_TEXT, "/Users/", "C:\\Users", "someone",
                      "Traceback", *extra):
        test.assertNotIn(forbidden, text, f"leaked {forbidden!r}")
    if len(FAKE_HOME) > 1:
        test.assertNotIn(FAKE_HOME, text)


class TestNameRedaction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table, cls.summary = run(features_with_sensitive_names())
        cls.lines = vt.summary_lines(cls.table, cls.summary, None)

    def test_id_inside_feature_and_source_names_redacted(self):
        row = self.table.set_index("feature").loc["<ID>_custom_rolling_7d_mean"]
        self.assertEqual(row["source"], "<ID>_custom")
        self.assertEqual(row["status"], vt.PASS)          # still verified correctly

    def test_date_inside_names_redacted(self):
        row = self.table.set_index("feature").loc["metric_<DATE>_rolling_3d_mean"]
        self.assertEqual(row["source"], "metric_<DATE>")
        self.assertEqual(row["status"], vt.PASS)

    def test_forbidden_column_listed_but_redacted(self):
        self.assertIn("patient_id_<ID>", self.summary["forbidden_columns_in_feature_table"])

    def test_ordinary_names_preserved(self):
        self.assertIn("SRC_rolling_7d_mean", set(self.table["feature"]))
        self.assertIn("SRC", set(self.table["source"]))

    def test_nothing_sensitive_in_table_or_summary(self):
        assert_clean(self, self.table.to_csv(index=False) + "\n".join(self.lines))

    def test_make_redactor_rules(self):
        red = vt.make_redactor(["SYN-P00", "AB"])         # IDs under 3 characters are ignored
        self.assertEqual(red("SYN-P00_x"), "<ID>_x")
        self.assertEqual(red("XSYN-P00"), "XSYN-P00")     # not a whole token
        self.assertEqual(red("AB_mean"), "AB_mean")
        self.assertEqual(red("f_2031-01-02T10:00:00Z"), "f_<DATE>")
        self.assertEqual(vt.make_redactor([])("BRI_rolling_7d_mean"), "BRI_rolling_7d_mean")


class TestSanitize(unittest.TestCase):
    def test_paths_home_and_username_removed(self):
        for p in FAKE_PATHS:
            out = vt.sanitize(f"cannot open {p}")
            assert_clean(self, out)
            self.assertIn("<", out)
        if FAKE_USER:
            self.assertNotIn(FAKE_USER, vt.sanitize(f"user {FAKE_USER} failed"))

    def test_ids_and_dates_removed_even_when_ids_unknown(self):
        out = vt.sanitize("3 duplicate keys for SYN-P00 and GER-003 on 2031-01-01 and kit_0042")
        assert_clean(self, out, extra=("GER-003", "kit_0042"))
        self.assertIn("3 duplicate keys", out)

    def test_ordinary_text_preserved(self):
        msg = "feature/label keys differ: 4 feature-only rows, 0 label-only rows"
        self.assertEqual(vt.sanitize(msg), msg)


class TestSafeErrors(unittest.TestCase):
    def _main(self, load_side_effect=None, verify_side_effect=None, write_error=None, extra=()):
        patches = [mock.patch.object(vt, "load_features",
                                     side_effect=load_side_effect,
                                     return_value=features_with_sensitive_names())]
        if verify_side_effect is not None:
            patches.append(mock.patch.object(vt, "verify_frame", side_effect=verify_side_effect))
        if write_error is not None:
            patches.append(mock.patch.object(vt.pd.DataFrame, "to_csv", side_effect=write_error))
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as st:
            for p in patches:
                st.enter_context(p)
            err, out = io.StringIO(), io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
                rc = vt.main(["--project-dir", "/nonexistent/exacerbalert_test_root",
                              "--out-dir", str(Path(tmp) / "out"), *extra])
        return rc, err.getvalue(), out.getvalue()

    def assert_safe_error(self, rc, err, category):
        self.assertEqual(rc, vt.EXIT_ERROR)
        self.assertTrue(err.startswith(f"ERROR [{category}]:"), err)
        assert_clean(self, err)
        self.assertNotIn(DISTINCT_TEXT, err)

    def test_missing_input_file(self):
        rc, err, _ = self._main(load_side_effect=FileNotFoundError(
            f"No such file: {FAKE_PATHS[0]} for {PLANTED_ID}"))
        self.assert_safe_error(rc, err, "input_missing")

    def test_data_validation_message_sanitised(self):
        msg = f"features: 3 duplicate keys in {FAKE_PATHS[1]} for {PLANTED_ID} on 2031-01-01"
        rc, err, _ = self._main(load_side_effect=vt.DataValidationError(msg))
        self.assert_safe_error(rc, err, "data_validation")
        self.assertIn("3 duplicate keys", err)            # the useful, safe part is kept

    def test_value_error_never_echoes_values(self):
        rc, err, _ = self._main(verify_side_effect=ValueError(
            f"could not convert {DISTINCT} for {PLANTED_ID} on 2031-01-01 at {FAKE_PATHS[2]}"))
        self.assert_safe_error(rc, err, "unexpected_data")
        self.assertIn("ValueError", err)

    def test_key_and_type_errors(self):
        for exc in (KeyError(f"{PLANTED_ID}"), TypeError(f"bad value {DISTINCT}")):
            rc, err, _ = self._main(verify_side_effect=exc)
            self.assert_safe_error(rc, err, "unexpected_data")

    def test_missing_package(self):
        rc, err, _ = self._main(load_side_effect=ModuleNotFoundError("No module", name="pyarrow"))
        self.assert_safe_error(rc, err, "environment")
        self.assertIn("pyarrow", err)

    def test_permission_error_on_write(self):
        rc, err, _ = self._main(write_error=PermissionError(13, "Permission denied", FAKE_PATHS[0]))
        self.assert_safe_error(rc, err, "permission_denied")

    def test_memory_and_unexpected_errors(self):
        rc, err, _ = self._main(verify_side_effect=MemoryError())
        self.assert_safe_error(rc, err, "resource")
        rc, err, _ = self._main(verify_side_effect=RuntimeError(f"boom at {FAKE_PATHS[3]} {PLANTED_ID}"))
        self.assert_safe_error(rc, err, "internal")
        self.assertIn("RuntimeError", err)

    def test_successful_run_still_redacts_and_returns_normally(self):
        rc, err, out = self._main()
        self.assertIn(rc, (0, 1))                          # 1 here: a banned column was planted
        self.assertEqual(err, "")
        assert_clean(self, out)
        self.assertIn("patient_id_<ID>", out)              # reported, but redacted

    def test_out_dir_inside_project_refused_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            root.mkdir()
            err = io.StringIO()
            with mock.patch.object(vt, "load_features") as lf, contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as ctx:
                    vt.main(["--project-dir", str(root), "--out-dir", str(root / "out")])
            lf.assert_not_called()                         # refused before reading any data
            self.assertIn("output_location", str(ctx.exception.code))
            self.assertNotIn(tmp, str(ctx.exception.code))


if __name__ == "__main__":
    unittest.main()
