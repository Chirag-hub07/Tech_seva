#!/usr/bin/env python3
"""Read-only, aggregate-only audit of every candidate feature (no model training).

Usage (from the project root):
    python ml/audit_features.py [--out-dir ~/exacerbalert_tools/feature_audit]
                                [--washout primary|none|<days>] [--config ml/config.yaml]

For every column of the feature table it reports, per FEATURE (never per row):
  * dictionary mapping (group, time window, other dictionary fields)
  * leakage screens: banned names, undocumented columns, future time windows
  * time-in-study proxies: name patterns and |Spearman r| with days-in-study
  * missingness on all rows and on the primary modelling rows, by class
  * participant coverage, constant and exact-duplicate columns
  * Pearson r with the target (leakage SCREEN ONLY - see below)
  * a proposed decision (exclude / review / include_candidate) with reasons

Target correlation is used only to flag features for manual leakage review.
It never includes or excludes a feature, because selecting features on the
outcome using all participants would itself leak information. Data-driven
filtering (missingness, constant, duplicate) is repeated inside each training
fold by the pipeline; the flags here describe the whole labelled dataset.

Privacy and safety
  * Reads the dataset only; never writes to the project directory.
  * Prints and saves feature names, dictionary text and aggregates only - no
    participant IDs, dates, rows or raw clinical values (no min/max).
  * Any participant ID appearing inside a feature name is replaced by <ID>.
  * The report is written only to --out-dir, which must be OUTSIDE the project.
"""

from __future__ import annotations

import argparse
import re
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from exacerbalert_ml.config import DEFAULT_CONFIG_PATH, load_config  # noqa: E402
from exacerbalert_ml.data import LABEL_COLUMN_KEYS, load_merged  # noqa: E402
from exacerbalert_ml.dataset import resolve_events  # noqa: E402
from exacerbalert_ml.events import post_event_mask  # noqa: E402
from exacerbalert_ml.features import is_banned, load_feature_dictionary  # noqa: E402
from exacerbalert_ml.labels import apply_label_policy  # noqa: E402

MIN_PAIRS = 100              # minimum non-missing rows for a correlation
TIME_CORR_REVIEW = 0.80      # |Spearman r| with days-in-study
TARGET_CORR_REVIEW = 0.30    # |Pearson r| with the target (leakage screen)
MISSING_REVIEW = 0.95        # missing fraction on primary modelling rows
CLASS_MISSING_DIFF = 0.20    # absolute difference in missing fraction, pos vs neg
COVERAGE_REVIEW = 0.50       # share of modelling participants with any value
NAME_REVIEW_PATTERNS = {     # name-based flags for manual review (not banned)
    "possible_event_or_outcome_name": r"(?i)exacerb|event|outcome|hospital|admission|recover|post_",
    "possible_calendar_or_time_name": r"(?i)days_since|day_of|week|month|year|calendar|elapsed|study_day",
}


def redactor(ids):
    ids = sorted({str(i).strip() for i in ids if len(str(i).strip()) >= 3}, key=len, reverse=True)
    if not ids:
        return lambda s: str(s)
    rx = re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(map(re.escape, ids)) + r")(?![A-Za-z0-9])")
    return lambda s: rx.sub("<ID>", str(s))


def safe_out_dir(out_dir: Path, project_root: Path) -> Path:
    out = out_dir.expanduser().resolve()
    root = project_root.resolve()
    if out == root or root in out.parents:
        raise SystemExit("ERROR: --out-dir must be outside the project directory")
    return out


def to_numeric_frame(X: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    """Float copy of X plus the value kind of every column.

    Kinds: numeric, boolean, boolean_like (object column holding booleans),
    datetime and text. Datetime and text columns are NOT converted - their
    float column is all-NaN, so no statistic is computed on their values.
    """
    cols, kinds = {}, {}
    for c in X.columns:
        s = X[c]
        if pd.api.types.is_datetime64_any_dtype(s):
            kinds[c] = "datetime"
            cols[c] = pd.Series(np.nan, index=X.index)
        elif pd.api.types.is_bool_dtype(s):
            kinds[c] = "boolean"
            cols[c] = s.astype("boolean").astype("float64")
        elif pd.api.types.is_numeric_dtype(s):
            kinds[c] = "numeric"
            cols[c] = s.astype("float64")
        else:
            try:
                cols[c] = s.astype("boolean").astype("float64")
                kinds[c] = "boolean_like"
            except (TypeError, ValueError):
                kinds[c] = "text"
                cols[c] = pd.Series(np.nan, index=X.index)
    return pd.DataFrame(cols, index=X.index), kinds


def column_hash(s: pd.Series) -> int:
    return int(pd.util.hash_pandas_object(s, index=False).sum())


def audit_frames(merged: pd.DataFrame, dictionary: pd.DataFrame, cfg, washout,
                 events: pd.DataFrame | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Audit every feature column of an in-memory merged table.

    merged     : joined feature + label table (as returned by data.load_merged)
    dictionary : feature dictionary (must contain a 'Feature' column)
    washout    : post-event washout in days, or None for no exclusion
    events     : event table; if None it is resolved from the config
                 (event_source), which may read the raw event files.
    Returns (per-feature table, summary lines). Performs no file I/O itself.
    """
    if "Feature" not in dictionary.columns:
        raise ValueError("feature dictionary has no 'Feature' column")
    red = redactor(merged[cfg.pid].unique())
    labelled = apply_label_policy(merged, cfg)          # policy from config (original)
    if events is None:
        events = resolve_events(labelled, cfg)          # event source from config (raw)
    post = post_event_mask(labelled, events, cfg, washout)
    rows = labelled["target"].notna() & ~post           # primary modelling rows
    y = labelled.loc[rows, "target"]
    pid = labelled.loc[rows, cfg.pid].astype("string")
    first_date = labelled.groupby(cfg.pid)[cfg.date].transform("min")
    days_in_study = ((labelled[cfg.date] - first_date).dt.days).loc[rows].astype("float64")

    label_cols = {cfg.col(k) for k in LABEL_COLUMN_KEYS}
    feature_cols = [c for c in merged.columns if c not in label_cols and c not in (cfg.pid, cfg.date)]
    dictionary = dictionary.copy()
    dictionary["Feature"] = dictionary["Feature"].astype("string").str.strip()
    dictionary = dictionary.drop_duplicates("Feature")
    dict_by_name = dictionary.set_index("Feature")
    documented = set(dictionary["Feature"].dropna())
    tw_pats = [re.compile(p) for p in cfg["prediction_time"].get("forbidden_time_window_patterns", [])]
    proxy_pats = [re.compile(p) for p in cfg.raw.get("time_in_study_proxy_patterns", [])]
    name_pats = {k: re.compile(v) for k, v in NAME_REVIEW_PATTERNS.items()}

    X_all, kinds = to_numeric_frame(merged[feature_cols])
    X = X_all.loc[rows]
    pos, neg = (y == 1), (y == 0)
    n_participants = int(pid.nunique())

    # ---- vectorised aggregates --------------------------------------------
    miss_all = X_all.isna().mean()
    miss = X.isna().mean()
    miss_pos = X.loc[pos].isna().mean()
    miss_neg = X.loc[neg].isna().mean()
    nunique = X.nunique(dropna=True)
    coverage = X.notna().groupby(pid.to_numpy()).any().mean()
    n_pairs = X.notna().sum()
    with warnings.catch_warnings(), np.errstate(all="ignore"):
        warnings.simplefilter("ignore")
        r_target = X.corrwith(y.astype("float64"))
        r_time = X.corrwith(days_in_study, method="spearman")
    r_target[n_pairs < MIN_PAIRS] = np.nan
    r_time[n_pairs < MIN_PAIRS] = np.nan

    first_of_hash: dict[int, str] = {}
    duplicate_of: dict[str, str] = {}
    for c in feature_cols:
        if kinds[c] in ("datetime", "text"):
            continue
        h = column_hash(X[c])
        if h in first_of_hash and X[c].equals(X[first_of_hash[h]]):
            duplicate_of[c] = first_of_hash[h]
        else:
            first_of_hash.setdefault(h, c)

    # ---- per-feature table ------------------------------------------------
    extra_dict_cols = [c for c in dictionary.columns if c != "Feature"]
    records = []
    for c in feature_cols:
        d = dict_by_name.loc[c] if c in dict_by_name.index else None
        tw = "" if d is None or "Time_Window" not in d.index or pd.isna(d["Time_Window"]) else str(d["Time_Window"])
        exclude, review = [], []
        if is_banned(c, cfg):
            exclude.append("banned_name")
        if c not in documented:
            exclude.append("undocumented")
        if any(p.search(tw) for p in tw_pats):
            exclude.append("future_time_window")
        if kinds[c] in ("datetime", "text"):
            exclude.append("non_numeric_column")
        elif miss[c] == 1.0:
            exclude.append("all_missing_in_modelling_rows")
        elif nunique[c] <= 1:
            exclude.append("constant_in_modelling_rows")
        if any(p.search(c) for p in proxy_pats):
            review.append("time_in_study_proxy_name")
        if pd.notna(r_time[c]) and abs(r_time[c]) >= TIME_CORR_REVIEW:
            review.append("high_correlation_with_days_in_study")
        for k, p in name_pats.items():
            if p.search(c):
                review.append(k)
        if pd.notna(r_target[c]) and abs(r_target[c]) >= TARGET_CORR_REVIEW:
            review.append("high_target_correlation_check_for_leakage")
        if (miss[c] > MISSING_REVIEW and "all_missing_in_modelling_rows" not in exclude
                and "non_numeric_column" not in exclude):
            review.append("missing_over_95pct")
        if kinds[c] not in ("datetime", "text") and abs(miss_pos[c] - miss_neg[c]) >= CLASS_MISSING_DIFF:
            review.append("missingness_differs_by_class")
        if kinds[c] not in ("datetime", "text") and coverage[c] < COVERAGE_REVIEW:
            review.append("low_participant_coverage")
        if c in duplicate_of:
            review.append("exact_duplicate")
        decision = "exclude" if exclude else ("review" if review else "include_candidate")
        rec = {
            "feature": red(c),
            "documented": c in documented,
            "dtype": str(merged[c].dtype),
            "value_kind": kinds[c],
            "missing_all_rows": round(float(miss_all[c]), 4),
            "missing_modelling_rows": round(float(miss[c]), 4),
            "missing_positive_rows": round(float(miss_pos[c]), 4),
            "missing_negative_rows": round(float(miss_neg[c]), 4),
            "participant_coverage": round(float(coverage[c]), 4),
            "distinct_values_bucket": "0-1" if nunique[c] <= 1 else ("2" if nunique[c] == 2 else
                                      ("3-10" if nunique[c] <= 10 else ">10")),
            "pearson_r_target": None if pd.isna(r_target[c]) else round(float(r_target[c]), 4),
            "spearman_r_days_in_study": None if pd.isna(r_time[c]) else round(float(r_time[c]), 4),
            "duplicate_of": red(duplicate_of[c]) if c in duplicate_of else "",
            "decision": decision,
            "exclude_reasons": ";".join(exclude),
            "review_reasons": ";".join(review),
        }
        for dc in extra_dict_cols:
            rec[f"dict_{dc}"] = "" if d is None or pd.isna(d.get(dc)) else red(d.get(dc))
        records.append(rec)
    table = pd.DataFrame(records)

    meta = {
        "label_policy": cfg["target"]["label_policy"],
        "event_source": cfg["post_event"]["event_source"],
        "washout": washout,
        "n_features": len(feature_cols),
        "n_documented": int(table["documented"].sum()) if len(table) else 0,
        "n_dictionary_without_column": len(documented - set(feature_cols)),
        "n_rows": int(rows.sum()), "n_pos": int(pos.sum()), "n_neg": int(neg.sum()),
        "n_participants": n_participants,
    }
    return table, summarise(table, meta)


def summarise(table: pd.DataFrame, meta: dict) -> list[str]:
    """Aggregate-only summary lines (counts and feature names)."""
    lines = [
        "FEATURE AUDIT (read-only; aggregates only; no model trained)",
        f"label_policy={meta['label_policy']}, event_source={meta['event_source']}, "
        f"washout_days={meta['washout']}",
        f"Candidate columns: {meta['n_features']}; documented in dictionary: {meta['n_documented']}; "
        f"dictionary entries without column: {meta['n_dictionary_without_column']}",
        f"Primary modelling rows: {meta['n_rows']} (positive {meta['n_pos']}, negative {meta['n_neg']}) "
        f"from {meta['n_participants']} participants",
        "",
        "Decisions: " + ", ".join(f"{k}={v}" for k, v in table["decision"].value_counts().items()),
    ]
    for col, title in (("exclude_reasons", "Exclude reasons"), ("review_reasons", "Review reasons")):
        counts = table[col].str.split(";").explode().replace("", np.nan).dropna().value_counts()
        lines += ["", f"{title} (features may have several):"] + [f"  {k}: {v}" for k, v in counts.items()]
    if "dict_Feature_Group" in table.columns:
        lines += ["", "Decision by feature group:",
                  pd.crosstab(table["dict_Feature_Group"].replace("", "<none>"), table["decision"]).to_string()]
    for col, title in (("pearson_r_target", f"Top 20 |Pearson r| with target (leakage screen only, >= {MIN_PAIRS} rows):"),
                       ("spearman_r_days_in_study", "Top 20 |Spearman r| with days-in-study (time-in-study proxy screen):")):
        lines += ["", title]
        top = table.dropna(subset=[col]).assign(a=lambda t: t[col].abs()).sort_values("a", ascending=False).head(20)
        lines += [f"  {r['feature']}: {r[col]:+.3f}" for _, r in top.iterrows()]
    for reason in ("banned_name", "undocumented", "future_time_window", "non_numeric_column"):
        names = table.loc[table["exclude_reasons"].str.contains(reason), "feature"].tolist()
        lines += ["", f"{reason}: {len(names)}" + (": " + ", ".join(names[:30]) + (" ..." if len(names) > 30 else "")
                                                   if names else "")]
    lines += ["", f"Full per-feature table: feature_audit.csv ({len(table)} rows) in the output directory",
              "AUDIT COMPLETE - dataset not modified; no model trained"]
    return lines


def write_report(table: pd.DataFrame, lines: list[str], out_dir: Path) -> None:
    """Write the CSV and summary to out_dir (which must already be validated)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(out_dir / "feature_audit.csv", index=False)
    (out_dir / "feature_audit_summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_washout(value: str, cfg):
    if value == "primary":
        return cfg["post_event"]["primary_washout_days"]
    if value == "none":
        return None
    days = int(value)
    if days < 0:
        raise ValueError("washout must be >= 0, 'none' or 'primary'")
    return days


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    ap.add_argument("--project-dir", default=None)
    ap.add_argument("--out-dir", default="~/exacerbalert_tools/feature_audit")
    ap.add_argument("--washout", default="primary", help="primary | none | integer days")
    args = ap.parse_args(argv)

    cfg = load_config(args.config, project_root=args.project_dir)
    out_dir = safe_out_dir(Path(args.out_dir), cfg.project_root)
    washout = parse_washout(args.washout, cfg)

    merged = load_merged(cfg)                       # read-only
    dictionary = load_feature_dictionary(cfg)       # read-only
    table, lines = audit_frames(merged, dictionary, cfg, washout)
    write_report(table, lines, out_dir)
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
