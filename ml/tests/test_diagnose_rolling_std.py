"""In-memory tests for ml/diagnose_rolling_std.py. Synthetic data only; no data-file reads.

Stored features are built with simple, independent loops (and, for the
"pandas noise" case, with pandas exactly as notebook 04 does). Deliberately
wrong features are planted next to correct ones.
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

import diagnose_rolling_std as dr
from exacerbalert_ml.config import DEFAULT_CONFIG_PATH, load_config

CFG = load_config(DEFAULT_CONFIG_PATH, project_root="/nonexistent/exacerbalert_test_root")
START = pd.Timestamp("2031-01-01", tz="UTC")
DISTINCT, DISTINCT_TEXT = 61.8273645, "61.827"


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


def loop(days, x, lo, hi, stat):
    """Independent window statistic over days lo..hi (inclusive) relative to each row."""
    out = []
    for d in days:
        v = [x[j] for j, dj in enumerate(days) if d + lo <= dj <= d + hi and not np.isnan(x[j])]
        if stat == "std":
            out.append(float(np.std(v, ddof=1)) if len(v) >= 2 else np.nan)
        elif stat == "mean":
            out.append(float(np.mean(v)) if v else np.nan)
    return out


def make_table(n_participants=4, n_days=45, seed=7):
    rng = np.random.default_rng(seed)
    parts = []
    for p in range(n_participants):
        dates = pd.date_range(START + pd.Timedelta(days=4 * p), periods=n_days, freq="D")
        days = list(range(n_days))
        x = [np.nan if rng.random() < 0.2 else float(rng.normal(30, 6)) for _ in days]
        x[10] = DISTINCT
        for k in range(20, 27):                      # a constant stretch -> zero-variance windows
            x[k] = 12.0
        prev = loop(days, x, -7, -1, "std")
        rec = {"Participant_ID": [f"SYN-Q{p:02d}"] * n_days, "Date": dates, "SRC": x,
               "SRC_rolling_7d_std": prev,                                         # correct
               "CUR_rolling_7d_std": loop(days, x, -6, 0, "std"),                  # includes day d
               "FUT_rolling_7d_std": loop(days, x, 1, 7, "std"),                   # future days
               "NOISE6_rolling_7d_std": [v + 1e-8 if np.isfinite(v) and v == 0 else v for v in prev],
               "NOISE3_rolling_7d_std": [v * (1 + 1e-4) + 1e-4 if np.isfinite(v) else v for v in prev],
               "RAND_rolling_7d_std": [np.nan if np.isnan(v) else float(rng.random()) for v in prev],
               "SRC_rolling_3d_mean": loop(days, x, -3, -1, "mean"),
               "CONST": [5.0] * n_days,
               "CONST_rolling_7d_std": loop(days, [5.0] * n_days, -7, -1, "std"),
               "SRC_baseline_mean": [np.mean([v for v in x[:i] if not np.isnan(v)])
                                     if sum(not np.isnan(v) for v in x[:i]) else np.nan for i in days],
               "WHOLE_baseline_mean": [float(np.nanmean(x))] * n_days,
               }
        nohist = list(prev)
        nohist[0] = 0.5                                                             # value without history
        rec["NOHIST_rolling_7d_std"] = nohist
        parts.append(pd.DataFrame(rec))
    f = pd.concat(parts, ignore_index=True)
    for alias in ("CUR", "FUT", "NOISE6", "NOISE3", "RAND", "WHOLE", "NOHIST"):
        f[alias] = f["SRC"]
    # Stored exactly as notebook 04 computes it (pandas streaming rolling std).
    pandas_std = []
    for _, g in f.groupby("Participant_ID", sort=False):
        s = g.set_index("Date")["SRC"].shift(1).rolling("7D", min_periods=1).std()
        pandas_std.extend(s.to_numpy())
    f["PANDAS"] = f["SRC"]
    f["PANDAS_rolling_7d_std"] = pandas_std
    f["SRC_availability"] = 1.0                      # present, but not a rolling/baseline feature
    return f


NAMES = ["SRC_rolling_7d_std", "CUR_rolling_7d_std", "FUT_rolling_7d_std", "NOISE6_rolling_7d_std",
         "NOISE3_rolling_7d_std", "RAND_rolling_7d_std", "SRC_rolling_3d_mean", "CONST_rolling_7d_std",
         "SRC_baseline_mean", "WHOLE_baseline_mean", "NOHIST_rolling_7d_std", "PANDAS_rolling_7d_std",
         "MISSING_rolling_7d_std", "SRC_availability"]


class TestDiagnosis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with no_file_reads():
            cls.t = dr.diagnose_frame(make_table(), NAMES, CFG)
        cls.r = cls.t.set_index("feature")

    def d(self, name):
        return self.r.loc[name, "diagnosis"]

    def test_backward_exact(self):
        self.assertEqual(self.d("SRC_rolling_7d_std"), dr.BACKWARD_EXACT)
        self.assertEqual(self.d("SRC_rolling_3d_mean"), dr.BACKWARD_EXACT)
        self.assertEqual(self.d("SRC_baseline_mean"), dr.BACKWARD_EXACT)
        self.assertEqual(self.r.loc["SRC_rolling_7d_std", "recommendation"], "retain")

    def test_pandas_computed_feature_is_backward(self):
        self.assertIn(self.d("PANDAS_rolling_7d_std"), (dr.BACKWARD_EXACT, dr.BACKWARD_NOISE))
        self.assertGreaterEqual(self.r.loc["PANDAS_rolling_7d_std", "agree_pandas_previous_1e-09"], 0.999)

    def test_current_day_inclusive_detected(self):
        self.assertEqual(self.d("CUR_rolling_7d_std"), dr.LOOKS_AHEAD)
        self.assertIn("includes_current_day", self.r.loc["CUR_rolling_7d_std", "detail"])
        self.assertTrue(self.r.loc["CUR_rolling_7d_std", "recommendation"].startswith("exclude"))

    def test_future_window_detected(self):
        self.assertEqual(self.d("FUT_rolling_7d_std"), dr.LOOKS_AHEAD)
        self.assertIn("future_days", self.r.loc["FUT_rolling_7d_std", "detail"])

    def test_whole_follow_up_baseline_detected(self):
        self.assertEqual(self.d("WHOLE_baseline_mean"), dr.LOOKS_AHEAD)
        self.assertIn("whole_follow_up", self.r.loc["WHOLE_baseline_mean", "detail"])

    def test_tolerance_levels(self):
        r6, r3 = self.r.loc["NOISE6_rolling_7d_std"], self.r.loc["NOISE3_rolling_7d_std"]
        self.assertEqual(r6["diagnosis"], dr.BACKWARD_NOISE)
        self.assertIn("1e-06", r6["detail"])
        self.assertLess(r6["agree_previous_days_1e-09"], 0.999)
        self.assertGreaterEqual(r6["agree_previous_days_1e-06"], 0.999)
        self.assertEqual(r6["share_disagreeing_in_constant_windows"], 1.0)     # noise only in flat windows
        self.assertEqual(r3["diagnosis"], dr.BACKWARD_NOISE)
        self.assertIn("0.001", r3["detail"])
        self.assertLess(r3["agree_previous_days_1e-06"], 0.999)
        for name in ("NOISE6_rolling_7d_std", "NOISE3_rolling_7d_std", "SRC_rolling_7d_std"):
            a = [self.r.loc[name, f"agree_previous_days_{t:g}"] for t in dr.TOLERANCES]
            self.assertEqual(a, sorted(a))                                     # monotone in tolerance

    def test_error_statistics_reported(self):
        r = self.r.loc["NOISE3_rolling_7d_std"]
        self.assertGreater(r["disagreeing_rows_at_1e-9"], 0)
        self.assertGreater(r["rel_error_median"], 0)
        self.assertLessEqual(r["rel_error_max"], 1e-3)
        self.assertTrue(pd.isna(self.r.loc["SRC_rolling_7d_std", "rel_error_median"]))

    def test_different_formula(self):
        self.assertEqual(self.d("RAND_rolling_7d_std"), dr.DIFFERENT)

    def test_constant_source_indistinguishable_and_uninformative(self):
        r = self.r.loc["CONST_rolling_7d_std"]
        self.assertEqual(r["diagnosis"], dr.INDISTINGUISHABLE)
        self.assertEqual(r["constant_source_share"], 1.0)
        self.assertIn("uninformative", r["recommendation"])

    def test_values_without_history_counted(self):
        self.assertGreaterEqual(self.r.loc["NOHIST_rolling_7d_std", "values_without_history"], 4)
        self.assertEqual(self.r.loc["SRC_rolling_7d_std", "values_without_history"], 0)

    def test_missing_and_unsupported(self):
        self.assertEqual(self.d("MISSING_rolling_7d_std"), dr.NOT_IN_TABLE)
        self.assertEqual(self.d("SRC_availability"), dr.NOT_SUPPORTED)

    def test_no_ids_dates_or_values_in_outputs(self):
        text = self.t.to_csv(index=False) + "\n".join(dr.summary_lines(self.t))
        for forbidden in ("SYN-", "2031-", DISTINCT_TEXT):
            self.assertNotIn(forbidden, text)

    def test_id_inside_name_redacted(self):
        f = make_table()
        f["SYN-Q00_x"] = f["SRC"]
        f["SYN-Q00_x_rolling_7d_std"] = f["SRC_rolling_7d_std"]
        t = dr.diagnose_frame(f, ["SYN-Q00_x_rolling_7d_std"], CFG)
        self.assertEqual(t.loc[0, "feature"], "<ID>_x_rolling_7d_std")
        self.assertEqual(t.loc[0, "source"], "<ID>_x")
        self.assertEqual(t.loc[0, "diagnosis"], dr.BACKWARD_EXACT)


class TestHelpers(unittest.TestCase):
    def test_exact_stat(self):
        v = np.array([1.0, np.nan, 3.0, 5.0])
        self.assertAlmostEqual(dr.exact_stat(v, "mean"), 3.0)
        self.assertAlmostEqual(dr.exact_stat(v, "std"), 2.0)
        self.assertEqual(dr.exact_stat(v, "count"), 3.0)
        self.assertTrue(np.isnan(dr.exact_stat(np.array([2.0]), "std")))
        self.assertEqual(dr.exact_stat(np.array([4.0, 4.0, 4.0]), "std"), 0.0)   # exact zero

    def test_agree_mask(self):
        # Tolerance is relative above 1: allowed |diff| = tol * max(1, |expected|).
        e = np.array([0.0, 100.0, np.nan])
        s = np.array([5e-10, 100.0 + 5e-7, 1.0])     # 5e-7 > 1e-9*100 but < 1e-6*100
        self.assertEqual(dr.agree_mask(s, e, 1e-9).tolist(), [True, False, False])
        self.assertEqual(dr.agree_mask(s, e, 1e-6).tolist(), [True, True, False])

    def test_classify(self):
        def fr(prev, cur, fut):
            return {("previous_days", t): prev[i] for i, t in enumerate(dr.TOLERANCES)} | \
                   {("includes_current_day", t): cur[i] for i, t in enumerate(dr.TOLERANCES)} | \
                   {("future_days", t): fut[i] for i, t in enumerate(dr.TOLERANCES)}
        self.assertEqual(dr.classify(fr([1, 1, 1], [0, 0, 0], [0, 0, 0]), 50)[0], dr.BACKWARD_EXACT)
        self.assertEqual(dr.classify(fr([0.5, 1, 1], [0, 0, 0], [0, 0, 0]), 50)[0], dr.BACKWARD_NOISE)
        self.assertEqual(dr.classify(fr([0, 0, 0], [1, 1, 1], [0, 0, 0]), 50)[0], dr.LOOKS_AHEAD)
        self.assertEqual(dr.classify(fr([0, 0, 0], [0, 0, 0], [0, 0, 0]), 50)[0], dr.DIFFERENT)
        self.assertEqual(dr.classify(fr([1, 1, 1], [1, 1, 1], [0, 0, 0]), 50)[0], dr.INDISTINGUISHABLE)
        self.assertEqual(dr.classify(fr([1, 1, 1], [0, 0, 0], [0, 0, 0]), 5)[0], dr.INSUFFICIENT)


class TestMain(unittest.TestCase):
    def _main(self, features=None, side_effect=None, extra=()):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            err, buf = io.StringIO(), io.StringIO()
            with mock.patch.object(dr, "load_features", side_effect=side_effect,
                                   return_value=features), \
                 contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
                rc = dr.main(["--project-dir", "/nonexistent/exacerbalert_test_root",
                              "--out-dir", str(out), *extra])
            files = sorted(p.name for p in out.iterdir()) if out.exists() else []
            texts = [buf.getvalue(), err.getvalue()] + [(out / n).read_text() for n in files]
        return rc, files, texts

    def test_default_feature_list_and_outputs(self):
        rc, files, texts = self._main(make_table())
        self.assertEqual(rc, 1)                          # default real names are absent here
        self.assertEqual(files, ["rolling_std_diagnosis.csv", "rolling_std_diagnosis_summary.txt"])
        self.assertIn("NOT_IN_FEATURE_TABLE", texts[0])
        for name in dr.DEFAULT_FEATURES:
            self.assertIn(name, texts[0])

    def test_explicit_features_exit_zero_when_backward(self):
        rc, _, texts = self._main(make_table(), extra=("--features", "SRC_rolling_7d_std", "SRC_baseline_mean"))
        self.assertEqual(rc, 0)
        for t in texts:
            for forbidden in ("SYN-", "2031-", DISTINCT_TEXT):
                self.assertNotIn(forbidden, t)

    def test_from_verification_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv = Path(tmp) / "temporal_verification.csv"
            pd.DataFrame({"feature": ["CUR_rolling_7d_std", "SRC_rolling_3d_mean", "<ID>_x_rolling_7d_std"],
                          "status": ["MISMATCH", "PASS", "INCONCLUSIVE"]}).to_csv(csv, index=False)
            rc, _, texts = self._main(make_table(), extra=("--from-verification", str(csv)))
        self.assertEqual(rc, 1)                          # CUR looks ahead
        self.assertIn("CUR_rolling_7d_std: LOOKS_AHEAD", texts[0])
        self.assertNotIn("SRC_rolling_3d_mean:", texts[0])   # PASS rows are not re-diagnosed

    def test_safe_error_handling(self):
        rc, _, texts = self._main(side_effect=FileNotFoundError(f"{Path.home()}/x/SYN-Q00.parquet"))
        self.assertEqual(rc, dr.vt.EXIT_ERROR)
        self.assertTrue(texts[1].startswith("ERROR [input_missing]:"))
        for forbidden in ("SYN-", str(Path.home()), "Traceback"):
            self.assertNotIn(forbidden, texts[1])


if __name__ == "__main__":
    unittest.main()
