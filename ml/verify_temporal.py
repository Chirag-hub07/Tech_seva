#!/usr/bin/env python3
"""Read-only verification that engineered features look only BACKWARDS in time.

Usage (from the project root):
    python ml/verify_temporal.py [--sample-per-family 30 | --all] [--seed 0]
                                 [--out-dir ~/exacerbalert_tools/temporal_check]

What it checks (re-implementing notebook 04's formulas independently):
  1. Calendar completeness: each participant's rows form a gap-free daily
     calendar, which the rolling and expanding formulas rely on.
  2. Rolling features  <src>_rolling_<w>d_<stat>  (stat = mean, std, min, max,
     count, change, pct_change): recomputed from the daily source column using
     ONLY the previous w calendar days (shift by one day, window "<w>D").
  3. Baseline features <src>_baseline_<stat>  (stat = mean, std, count, median,
     deviation, standardized_deviation): recomputed from ALL previous days only
     (shift by one day, expanding window). Deviation features use the current
     day minus the historical mean, as designed for end-of-day prediction.
  4. Look-ahead alternatives: the same statistics computed WITH the current day,
     over FUTURE days, over a centred window, or over the participant's whole
     follow-up. A feature that matches one of these but not the historical
     version is reported as FAIL_LOOKS_AHEAD.
  5. Values without history: a stored value on a row where no past observation
     exists cannot have come from the past -> FAIL_VALUES_WITHOUT_HISTORY.
  6. No label, event or identifier columns inside the feature table.

Values are compared only where the stored feature is non-missing, so the
notebook's minimum-observation thresholds do not affect the result.

Privacy: reads ONLY the feature table (no labels, no events). Prints and saves
feature names, statuses, counts and match fractions only - never participant
IDs, dates or feature values. An optional CSV is written only outside the project.
  * Participant IDs and ISO dates found INSIDE column names are replaced by
    <ID> and <DATE> before anything is printed or saved; ordinary names are kept.
  * Errors are reported as "ERROR [category]: safe message" on stderr, with no
    traceback, so local paths, usernames, IDs, dates and values never appear.
"""

from __future__ import annotations

import argparse
import getpass
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from exacerbalert_ml.config import DEFAULT_CONFIG_PATH, load_config  # noqa: E402
from exacerbalert_ml.data import LABEL_COLUMN_KEYS, DataValidationError, load_features  # noqa: E402
from exacerbalert_ml.features import is_banned  # noqa: E402

EXIT_ERROR = 2

ROLLING_RX = re.compile(r"^(?P<src>.+)_rolling_(?P<w>\d+)d_(?P<stat>mean|std|min|max|count|pct_change|change)$")
BASELINE_RX = re.compile(
    r"^(?P<src>.+)_baseline_(?P<stat>standardized_deviation|deviation|mean|std|count|median)$")
MATCH_OK = 0.999          # fraction of compared rows that must agree
MIN_COMPARED = 10         # fewer compared rows -> INSUFFICIENT_DATA
RTOL, ATOL = 1e-6, 1e-9

PASS = "PASS"
INCONCLUSIVE = "INCONCLUSIVE"            # historical and look-ahead versions identical
FAIL_AHEAD = "FAIL_LOOKS_AHEAD"
FAIL_NO_HISTORY = "FAIL_VALUES_WITHOUT_HISTORY"
MISMATCH = "MISMATCH"                    # matches no known formula - needs review
INSUFFICIENT = "INSUFFICIENT_DATA"
NO_SOURCE = "SOURCE_NOT_AVAILABLE"
FAIL_STATUSES = (FAIL_AHEAD, FAIL_NO_HISTORY, MISMATCH)


# ---------------------------------------------------------------------------
# Privacy helpers
# ---------------------------------------------------------------------------
ISO_DATE_RX = re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?")
# A path starts a token: "/x", "~/x", "C:\x" or "\\server" - not "feature/label" inside a word.
PATH_RX = re.compile(r"(?<![\w.])(?:[A-Za-z]:[\\/]|\\\\|~[\\/]|/)[^\s'\"<>|,;)]*")
# Conservative scrub for ERROR TEXT only (used before participant IDs are known):
# letters followed by 2+ digits, optionally joined by - or _, e.g. "ABC-001", "kit_0042".
ID_LIKE_RX = re.compile(r"(?<![\w-])[A-Za-z]{2,}[-_]?[A-Za-z]{0,3}\d{2,}(?![\w-])")


def make_redactor(ids):
    """Return a function replacing participant IDs and ISO dates inside names.

    IDs shorter than 3 characters are ignored, and an ID is replaced only as a
    whole token, so ordinary feature names stay readable.
    """
    clean = sorted({str(i).strip() for i in ids if pd.notna(i) and len(str(i).strip()) >= 3},
                   key=len, reverse=True)
    id_rx = (re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(map(re.escape, clean)) + r")(?![A-Za-z0-9])")
             if clean else None)

    def redact(name) -> str:
        text = str(name)
        if id_rx is not None:
            text = id_rx.sub("<ID>", text)
        return ISO_DATE_RX.sub("<DATE>", text)
    return redact


def sanitize(text: str, ids=()) -> str:
    """Remove paths, home directory, username, participant IDs and dates from text."""
    out = str(text)
    for secret, tag in ((str(Path.home()), "<HOME>"), (_safe_username(), "<USER>")):
        if secret and len(secret) >= 2:
            out = out.replace(secret, tag)
    out = PATH_RX.sub("<PATH>", out)
    out = make_redactor(ids)(out)                       # known IDs and ISO dates
    out = ID_LIKE_RX.sub("<ID>", out)                   # unknown ID-like tokens
    return out


def _safe_username() -> str:
    try:
        return getpass.getuser()
    except Exception:  # pragma: no cover - platform dependent
        return ""


def error_report(exc: BaseException, ids=()) -> tuple[str, str]:
    """Map an exception to (category, safe message). Never echoes raw values."""
    if isinstance(exc, FileNotFoundError):
        return "input_missing", ("A required input file was not found. Check the paths in "
                                 "ml/config.yaml and run from the project root.")
    if isinstance(exc, PermissionError):
        return "permission_denied", "A file or folder could not be read or written (permission denied)."
    if isinstance(exc, DataValidationError):
        return "data_validation", sanitize(exc, ids)      # pipeline messages contain counts only
    if isinstance(exc, ModuleNotFoundError):
        mod = exc.name if exc.name and re.fullmatch(r"[A-Za-z0-9_.]+", exc.name) else "a required package"
        return "environment", f"Python package not available: {mod}. Activate the exacerbalert environment."
    if isinstance(exc, ImportError):
        return "environment", "A required Python package could not be imported. Check the environment."
    if isinstance(exc, MemoryError):
        return "resource", "Not enough memory. Try a smaller --sample-per-family."
    if isinstance(exc, (KeyError, ValueError, TypeError)):
        return "unexpected_data", ("The feature table has an unexpected structure or value type. "
                                   f"Error type: {type(exc).__name__}.")
    if isinstance(exc, OSError):
        return "file_system", f"A file-system error occurred. Error type: {type(exc).__name__}."
    return "internal", f"An unexpected error occurred. Error type: {type(exc).__name__}."


# ---------------------------------------------------------------------------
# Feature name parsing
# ---------------------------------------------------------------------------
def parse_feature(name: str):
    """Return (family, stat, source, window) or None for non-temporal names."""
    m = ROLLING_RX.match(name)
    if m:
        return "rolling", m["stat"], m["src"], int(m["w"])
    m = BASELINE_RX.match(name)
    if m:
        return "baseline", m["stat"], m["src"], None
    return None


# ---------------------------------------------------------------------------
# Per-participant reference calculations (one participant's daily series,
# indexed by a sorted DatetimeIndex)
# ---------------------------------------------------------------------------
def _last_change(v: np.ndarray, pct: bool) -> float:
    v = v[np.isfinite(v)]
    if len(v) < 2:
        return np.nan
    if pct:
        return np.nan if v[-2] == 0 else (v[-1] - v[-2]) / v[-2] * 100
    return v[-1] - v[-2]


def _rolling_stat(s: pd.Series, w: int, stat: str, center: bool = False) -> pd.Series:
    if center:
        r = s.rolling(w, center=True, min_periods=1)        # row-based centred window
    else:
        r = s.rolling(f"{w}D", min_periods=1)                # calendar window ending today
    if stat == "count":
        return r.count()
    if stat in ("change", "pct_change"):
        return r.apply(lambda v: _last_change(v, stat == "pct_change"), raw=True)
    if stat == "std":
        return r.std(ddof=1)
    return getattr(r, stat)()


def rolling_variants(s: pd.Series, w: int, stat: str) -> dict[str, pd.Series]:
    """Historical reference plus look-ahead alternatives for a rolling feature."""
    hist = _rolling_stat(s.shift(1), w, stat)
    current = _rolling_stat(s, w, stat)                      # includes the current day
    rev = pd.Series(s.to_numpy()[::-1], index=s.index)
    fut = _rolling_stat(rev.shift(1), w, stat)               # next w days (computed in reverse)
    future = pd.Series(fut.to_numpy()[::-1], index=s.index)
    centred = _rolling_stat(s, 2 * w + 1, stat, center=True)  # w days either side
    return {"historical": hist, "includes_current_day": current,
            "future_window": future, "centred_window": centred}


def _expanding(s: pd.Series, stat: str, min_periods: int) -> pd.Series:
    e = s.expanding(min_periods=min_periods)
    if stat == "count":
        return e.count()
    if stat == "std":
        return e.std(ddof=1)
    return getattr(e, stat)()


def _whole(s: pd.Series, stat: str) -> pd.Series:
    val = {"mean": s.mean(), "std": s.std(ddof=1), "median": s.median(), "count": float(s.count())}[stat]
    return pd.Series(val, index=s.index, dtype="float64")


def baseline_variants(s: pd.Series, stat: str) -> dict[str, pd.Series]:
    """Historical reference plus look-ahead alternatives for a baseline feature."""
    def build(base_stat_fn):
        if stat in ("mean", "std", "count", "median"):
            return base_stat_fn(stat)
        mean, std = base_stat_fn("mean"), base_stat_fn("std")
        dev = s - mean
        return dev if stat == "deviation" else dev / std.replace(0, np.nan)

    hist = build(lambda st: _expanding(s.shift(1), st, 1))
    current = build(lambda st: _expanding(s, st, 1))
    whole = build(lambda st: _whole(s, st))
    return {"historical": hist, "includes_current_day": current, "whole_follow_up": whole}


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------
def match_fraction(stored: pd.Series, ref: pd.Series, count_stat: bool = False) -> tuple[float, int]:
    """Share of rows (where stored is non-missing) on which ref agrees."""
    if count_stat:
        a, b = stored.fillna(0).to_numpy(float), ref.fillna(0).to_numpy(float)
        mask = np.ones(len(a), dtype=bool)
    else:
        a, b = stored.to_numpy(float), ref.to_numpy(float)
        mask = ~np.isnan(a)
    n = int(mask.sum())
    if n == 0:
        return float("nan"), 0
    ok = np.isclose(a[mask], b[mask], rtol=RTOL, atol=ATOL, equal_nan=False)
    return float(ok.mean()), n


def classify(fracs: dict[str, float], n: int, n_no_history: int) -> tuple[str, str]:
    """Return (status, best look-ahead variant).

    Order: a matching look-ahead version is the most specific diagnosis, so it
    is reported before 'values without history' (which such features often
    also have); a feature matching no formula is a MISMATCH.
    """
    if n < MIN_COMPARED:
        return INSUFFICIENT, ""
    hist = fracs.get("historical", 0.0)
    ahead = {k: v for k, v in fracs.items() if k != "historical" and not np.isnan(v)}
    best = max(ahead, key=ahead.get) if ahead else ""
    if hist >= MATCH_OK and n_no_history == 0:
        return (INCONCLUSIVE, best) if best and ahead[best] >= MATCH_OK else (PASS, "")
    if best and ahead[best] >= MATCH_OK:
        return FAIL_AHEAD, best
    if n_no_history > 0:
        return FAIL_NO_HISTORY, ""
    return MISMATCH, best


# ---------------------------------------------------------------------------
# Main verification on an in-memory feature table
# ---------------------------------------------------------------------------
def calendar_report(features: pd.DataFrame, pid: str, date: str) -> dict:
    gaps = dups = 0
    for _, g in features.groupby(pid, sort=False):
        d = g[date].sort_values()
        dups += int(d.duplicated().sum())
        diffs = d.drop_duplicates().diff().dropna().dt.days
        gaps += int((diffs != 1).any())
    return {"participants": int(features[pid].nunique()),
            "participants_with_gaps": gaps, "duplicate_participant_dates": dups}


def select_features(columns, sample_per_family: int | None, seed: int) -> list[tuple]:
    parsed = [(c, *p) for c in columns if (p := parse_feature(c))]
    if sample_per_family is None:
        return parsed
    rng = np.random.default_rng(seed)
    out = []
    for fam_stat in sorted({(p[1], p[2]) for p in parsed}):
        group = [p for p in parsed if (p[1], p[2]) == fam_stat]
        idx = rng.choice(len(group), size=min(sample_per_family, len(group)), replace=False)
        out.extend(group[i] for i in sorted(idx))
    return out


def verify_frame(features: pd.DataFrame, cfg, sample_per_family: int | None = 30,
                 seed: int = 0) -> tuple[pd.DataFrame, dict]:
    """Verify temporal features of an in-memory feature table. No file I/O."""
    pid, date = cfg.pid, cfg.date
    df = features.sort_values([pid, date], kind="mergesort").reset_index(drop=True)
    label_cols = {cfg.col(k) for k in LABEL_COLUMN_KEYS}
    forbidden = [c for c in df.columns if c in label_cols
                 or (c not in (pid, date) and is_banned(c, cfg))]

    groups = {p: g.index.to_numpy() for p, g in df.groupby(pid, sort=False)}
    dates = df[date]
    records = []
    for name, family, stat, src, w in select_features(df.columns, sample_per_family, seed):
        rec = {"feature": name, "family": family, "statistic": stat, "window_days": w, "source": src}
        if src not in df.columns:
            rec.update(status=NO_SOURCE)
            records.append(rec)
            continue
        stored = pd.to_numeric(df[name], errors="coerce").astype("float64")
        source = pd.to_numeric(df[src], errors="coerce").astype("float64")
        variants: dict[str, list[pd.Series]] = {}
        no_hist = 0
        for _, idx in groups.items():
            s = pd.Series(source.to_numpy()[idx], index=pd.DatetimeIndex(dates.to_numpy()[idx]))
            v = rolling_variants(s, w, stat) if family == "rolling" else baseline_variants(s, stat)
            past_count = (_rolling_stat(s.shift(1), w, "count") if family == "rolling"
                          else _expanding(s.shift(1), "count", 1))
            st = stored.to_numpy()[idx]
            if stat != "count":
                no_hist += int((~np.isnan(st) & (past_count.fillna(0).to_numpy() == 0)).sum())
            for k, series in v.items():
                variants.setdefault(k, []).append(pd.Series(series.to_numpy(float), index=idx))
        fracs, n = {}, 0
        for k, parts in variants.items():
            ref = pd.concat(parts).sort_index()
            f, n_k = match_fraction(stored, ref, count_stat=(stat == "count"))
            fracs[k] = f
            if k == "historical":
                n = n_k
        status, best = classify(fracs, n, no_hist)
        rec.update(status=status, compared_rows=n, values_without_history=no_hist,
                   best_lookahead_variant=best,
                   **{f"match_{k}": (None if np.isnan(v) else round(v, 4)) for k, v in fracs.items()})
        records.append(rec)

    table = pd.DataFrame(records)
    # Redact participant IDs / dates inside names before anything leaves this function.
    redact = make_redactor(df[pid].dropna().unique())
    for col in ("feature", "source"):
        if col in table.columns:
            table[col] = table[col].map(redact)
    summary = {
        "calendar": calendar_report(df, pid, date),
        "forbidden_columns_in_feature_table": [redact(c) for c in forbidden],
        "temporal_features_in_table": sum(1 for c in df.columns if parse_feature(c)),
        "features_checked": len(table),
        "status_counts": table["status"].value_counts().to_dict() if len(table) else {},
    }
    return table, summary


def summary_lines(table: pd.DataFrame, summary: dict, sample_per_family) -> list[str]:
    cal = summary["calendar"]
    lines = [
        "TEMPORAL VERIFICATION (read-only; feature table only; no values printed)",
        f"Participants: {cal['participants']}; with calendar gaps: {cal['participants_with_gaps']}; "
        f"duplicate participant-dates: {cal['duplicate_participant_dates']}",
        f"Label/event/identifier columns inside the feature table: "
        f"{len(summary['forbidden_columns_in_feature_table'])}"
        + (": " + ", ".join(summary["forbidden_columns_in_feature_table"][:20])
           if summary["forbidden_columns_in_feature_table"] else ""),
        f"Temporal features in table: {summary['temporal_features_in_table']}; checked: "
        f"{summary['features_checked']} ({'all' if sample_per_family is None else f'up to {sample_per_family} per family'})",
        "",
        "Status counts: " + ", ".join(f"{k}={v}" for k, v in summary["status_counts"].items()),
    ]
    if len(table):
        lines += ["", "By family and statistic:",
                  pd.crosstab([table["family"], table["statistic"]], table["status"]).to_string()]
        bad = table[table["status"].isin(FAIL_STATUSES)]
        lines += ["", f"Features needing attention: {len(bad)}"]
        for _, r in bad.head(50).iterrows():
            lines.append(f"  {r['status']}: {r['feature']}"
                         + (f" (matches {r['best_lookahead_variant']})" if r.get("best_lookahead_variant") else ""))
    ok = (not summary["forbidden_columns_in_feature_table"] and cal["participants_with_gaps"] == 0
          and cal["duplicate_participant_dates"] == 0
          and not (len(table) and table["status"].isin(FAIL_STATUSES).any()))
    lines += ["", "RESULT: " + ("PASS - no look-ahead detected in the checked features" if ok
                                else "ATTENTION - review the items above before training")]
    return lines


def safe_out_dir(out_dir: Path, project_root: Path) -> Path:
    out, root = out_dir.expanduser().resolve(), project_root.resolve()
    if out == root or root in out.parents:
        raise SystemExit("ERROR [output_location]: --out-dir must be outside the project directory")
    return out


def run(args) -> int:
    """The verification itself; may raise. main() turns exceptions into safe messages."""
    cfg = load_config(args.config, project_root=args.project_dir)
    out_dir = safe_out_dir(Path(args.out_dir), cfg.project_root) if args.out_dir else None
    sample = None if args.all else args.sample_per_family

    features = load_features(cfg)                      # read-only; labels are never read
    run.ids = features[cfg.pid].dropna().unique()      # remembered for error sanitising
    table, summary = verify_frame(features, cfg, sample, args.seed)
    lines = summary_lines(table, summary, sample)
    print("\n".join(lines))
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        table.to_csv(out_dir / "temporal_verification.csv", index=False)
        (out_dir / "temporal_verification_summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if lines[-1].startswith("RESULT: PASS") else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    ap.add_argument("--project-dir", default=None)
    ap.add_argument("--sample-per-family", type=int, default=30)
    ap.add_argument("--all", action="store_true", help="check every temporal feature (slow)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out-dir", default=None, help="optional; must be outside the project")
    args = ap.parse_args(argv)

    run.ids = ()
    try:
        return run(args)
    except SystemExit:
        raise                                          # deliberate exits (e.g. --out-dir refusal)
    except KeyboardInterrupt:
        print("ERROR [interrupted]: verification stopped by the user.", file=sys.stderr)
        return EXIT_ERROR
    except BaseException as exc:                       # noqa: BLE001 - report every failure safely
        category, message = error_report(exc, run.ids)
        print(f"ERROR [{category}]: {message}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
