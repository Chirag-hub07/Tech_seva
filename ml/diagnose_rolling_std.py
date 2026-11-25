#!/usr/bin/env python3
"""Read-only diagnosis of features flagged by verify_temporal.py (no training).

Usage (from the project root):
    python ml/diagnose_rolling_std.py                       # the 5 known rolling-std mismatches
    python ml/diagnose_rolling_std.py --features A_rolling_7d_std B_baseline_mean
    python ml/diagnose_rolling_std.py --from-verification ~/exacerbalert_tools/temporal_check/temporal_verification.csv
    (optional) --out-dir ~/exacerbalert_tools/rolling_std_diagnosis   # must be outside the project

For each feature it recomputes the statistic EXACTLY from the daily source
column (a direct two-pass calculation per window, not pandas' streaming
rolling algorithm), for each prediction date d, over:

  rolling features  <src>_rolling_<w>d_<stat>
    previous_days        days d-w ... d-1   (documented definition: notebook 04 cell 125)
    includes_current_day days d-w+1 ... d
    future_days          days d+1 ... d+w
    pandas_previous      days d-w ... d-1 via pandas rolling (the method notebook 04 used)
  baseline features <src>_baseline_<stat>
    previous_days        all days before d  (notebook 04 cells 60 and 129)
    includes_current_day all days up to and including d
    whole_follow_up      every day of the participant's follow-up (includes the future)

The stored feature is compared with each version only where the stored value is
non-missing, at tolerances 1e-9, 1e-6 and 1e-3: |stored - expected| <= tol * max(1, |expected|).
Disagreements with the documented definition are then described by aggregate
shares (constant windows, high mean-to-spread windows, values without history)
and error quantiles.

Privacy: reads only the feature table (and, optionally, the verification CSV,
which holds feature names and statuses). Prints and saves aggregate counts,
fractions and error statistics only - never participant IDs, dates or values.
IDs and dates inside column names are redacted; errors print a safe category.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import verify_temporal as vt  # noqa: E402  (reused, not modified)
from exacerbalert_ml.config import DEFAULT_CONFIG_PATH, load_config  # noqa: E402
from exacerbalert_ml.data import load_features  # noqa: E402

DEFAULT_FEATURES = (
    "EI_AQI_min_rolling_3d_std",
    "EI_AQI_min_rolling_7d_std",
    "EI_Lux_mean_rolling_7d_std",
    "MI_swm_std_mean_rolling_7d_std",
    "SII_min_rolling_7d_std",
)
TOLERANCES = (1e-9, 1e-6, 1e-3)
AGREE = 0.999                  # share of compared rows that must agree
MIN_COMPARED = 10
HIGH_RATIO = 1e4               # |window mean| / window std above this -> cancellation-prone
CONSTANT_SHARE_UNINFORMATIVE = 0.95

BACKWARD_EXACT = "BACKWARD_EXACT"
BACKWARD_NOISE = "BACKWARD_NUMERICAL_NOISE"
LOOKS_AHEAD = "LOOKS_AHEAD"
DIFFERENT = "DIFFERENT_FORMULA"
INDISTINGUISHABLE = "INDISTINGUISHABLE"
INSUFFICIENT = "INSUFFICIENT_DATA"
NOT_SUPPORTED = "NOT_A_ROLLING_OR_BASELINE_FEATURE"
NOT_IN_TABLE = "NOT_IN_FEATURE_TABLE"
NO_SOURCE = "SOURCE_NOT_AVAILABLE"

RECOMMENDATION = {
    BACKWARD_EXACT: "retain",
    BACKWARD_NOISE: "retain (backward-looking; differences are floating-point noise)",
    LOOKS_AHEAD: "exclude (uses the current day or future days)",
    DIFFERENT: "exclude pending manual review (matches no documented formula)",
    INDISTINGUISHABLE: "retain only if informative - see constant_source_share",
    INSUFFICIENT: "exclude pending review (too few comparable rows)",
    NOT_SUPPORTED: "review manually",
    NOT_IN_TABLE: "check the feature name",
    NO_SOURCE: "exclude pending review (daily source column missing)",
}


# ---------------------------------------------------------------------------
# Exact statistics (two-pass, per window)
# ---------------------------------------------------------------------------
def exact_stat(values: np.ndarray, stat: str) -> float:
    v = values[np.isfinite(values)]
    n = len(v)
    if stat == "count":
        return float(n)
    if n == 0:
        return np.nan
    if stat == "mean":
        return float(v.mean())
    if stat == "std":
        if n < 2:
            return np.nan
        m = v.mean()
        return float(np.sqrt(((v - m) ** 2).sum() / (n - 1)))
    if stat == "min":
        return float(v.min())
    if stat == "max":
        return float(v.max())
    if stat == "median":
        return float(np.median(v))
    if stat in ("change", "pct_change"):
        if n < 2:
            return np.nan
        if stat == "change":
            return float(v[-1] - v[-2])
        return np.nan if v[-2] == 0 else float((v[-1] - v[-2]) / v[-2] * 100)
    raise ValueError(f"unsupported statistic: {stat}")


def _baseline_value(window: np.ndarray, current: float, stat: str) -> float:
    if stat in ("mean", "std", "count", "median"):
        return exact_stat(window, stat)
    mean, std = exact_stat(window, "mean"), exact_stat(window, "std")
    dev = current - mean
    if stat == "deviation":
        return dev
    return np.nan if (np.isnan(std) or std == 0) else dev / std


def windows_for_participant(days: np.ndarray, x: np.ndarray, family: str, stat: str, w: int | None):
    """Exact values for every version of the feature, plus window descriptors."""
    n = len(days)
    out = {k: np.full(n, np.nan) for k in (
        ("previous_days", "includes_current_day", "future_days") if family == "rolling"
        else ("previous_days", "includes_current_day", "whole_follow_up"))}
    prev_count = np.zeros(n)
    prev_constant = np.zeros(n, dtype=bool)
    prev_ratio = np.full(n, np.nan)
    for i, d in enumerate(days):
        if family == "rolling":
            masks = {"previous_days": (days >= d - w) & (days <= d - 1),
                     "includes_current_day": (days >= d - w + 1) & (days <= d),
                     "future_days": (days >= d + 1) & (days <= d + w)}
            for k, m in masks.items():
                out[k][i] = exact_stat(x[m], stat)
            prev = x[masks["previous_days"]]
        else:
            masks = {"previous_days": days < d, "includes_current_day": days <= d,
                     "whole_follow_up": np.ones(n, dtype=bool)}
            for k, m in masks.items():
                out[k][i] = _baseline_value(x[m], x[i], stat)
            prev = x[masks["previous_days"]]
        pv = prev[np.isfinite(prev)]
        prev_count[i] = len(pv)
        if len(pv) >= 2:
            sd = float(np.std(pv, ddof=1))
            prev_constant[i] = bool(np.all(pv == pv[0]))
            prev_ratio[i] = np.inf if sd == 0 else abs(float(pv.mean())) / sd
    return out, prev_count, prev_constant, prev_ratio


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------
def agree_mask(stored: np.ndarray, expected: np.ndarray, tol: float) -> np.ndarray:
    """Element-wise agreement; NaN expected never agrees with a stored value."""
    with np.errstate(invalid="ignore"):
        return np.abs(stored - expected) <= tol * np.maximum(1.0, np.abs(expected))


def agreement(stored: np.ndarray, expected: np.ndarray, tol: float, count_stat: bool) -> tuple[float, int]:
    if count_stat:
        s, e = np.nan_to_num(stored, nan=0.0), np.nan_to_num(expected, nan=0.0)
        rows = np.ones(len(s), dtype=bool)
    else:
        s, e = stored, expected
        rows = ~np.isnan(stored)
    n = int(rows.sum())
    if n == 0:
        return float("nan"), 0
    return float(agree_mask(s[rows], e[rows], tol).mean()), n


def quantiles(a: np.ndarray) -> dict:
    a = a[np.isfinite(a)]
    if len(a) == 0:
        return {"median": None, "p95": None, "p99": None, "max": None}
    q = np.quantile(a, [0.5, 0.95, 0.99])
    return {"median": float(q[0]), "p95": float(q[1]), "p99": float(q[2]), "max": float(a.max())}


def classify(frac: dict, n: int) -> tuple[str, str]:
    """frac[(variant, tol)] -> agreement share. Returns (diagnosis, detail)."""
    if n < MIN_COMPARED:
        return INSUFFICIENT, ""
    variants = sorted({v for v, _ in frac})
    alts = [v for v in variants if v not in ("previous_days", "pandas_previous")]

    def best_tol(v):
        for t in TOLERANCES:
            if frac.get((v, t), 0.0) >= AGREE:
                return t
        return None

    prev_t = best_tol("previous_days")
    alt_t = {v: best_tol(v) for v in alts}
    if prev_t is not None and any(t is not None and t <= prev_t for t in alt_t.values()):
        same = [v for v, t in alt_t.items() if t is not None and t <= prev_t]
        return INDISTINGUISHABLE, "also matches: " + ", ".join(same)
    if prev_t == TOLERANCES[0]:
        return BACKWARD_EXACT, "agrees at 1e-9"
    if prev_t is not None:
        return BACKWARD_NOISE, f"agrees at {prev_t:g}"
    ahead = [(t, v) for v, t in alt_t.items() if t is not None]
    if ahead:
        t, v = min(ahead)
        return LOOKS_AHEAD, f"matches {v} at {t:g}"
    return DIFFERENT, ""


# ---------------------------------------------------------------------------
# Diagnosis on an in-memory feature table
# ---------------------------------------------------------------------------
def diagnose_feature(df: pd.DataFrame, name: str, cfg) -> dict:
    parsed = vt.parse_feature(name)
    if name not in df.columns:
        return {"feature": name, "diagnosis": NOT_IN_TABLE}
    if parsed is None:
        return {"feature": name, "diagnosis": NOT_SUPPORTED}
    family, stat, src, w = parsed
    rec = {"feature": name, "source": src, "family": family, "statistic": stat, "window_days": w}
    if src not in df.columns:
        rec["diagnosis"] = NO_SOURCE
        return rec

    pid, date = cfg.pid, cfg.date
    stored_all = pd.to_numeric(df[name], errors="coerce").to_numpy("float64")
    source_all = pd.to_numeric(df[src], errors="coerce").to_numpy("float64")
    n_rows = len(df)
    exp = {}
    prev_count = np.zeros(n_rows)
    prev_constant = np.zeros(n_rows, dtype=bool)
    prev_ratio = np.full(n_rows, np.nan)
    constant_participants = participants = 0
    for _, idx in df.groupby(pid, sort=False).groups.items():
        idx = np.asarray(idx)
        order = np.argsort(df[date].to_numpy()[idx], kind="mergesort")
        idx = idx[order]
        t = pd.DatetimeIndex(df[date].to_numpy()[idx])
        days = ((t - t[0]) // pd.Timedelta(days=1)).to_numpy().astype(np.int64)
        x = source_all[idx]
        vals, pc, pk, pr = windows_for_participant(days, x, family, stat, w)
        for k, v in vals.items():
            exp.setdefault(k, np.full(n_rows, np.nan))[idx] = v
        if family == "rolling":
            pandas_prev = vt.rolling_variants(pd.Series(x, index=t), w, stat)["historical"].to_numpy(float)
            exp.setdefault("pandas_previous", np.full(n_rows, np.nan))[idx] = pandas_prev
        prev_count[idx], prev_constant[idx], prev_ratio[idx] = pc, pk, pr
        finite = x[np.isfinite(x)]
        participants += 1
        constant_participants += int(len(finite) > 0 and np.all(finite == finite[0]))

    count_stat = stat == "count"
    frac, n = {}, 0
    for k, e in exp.items():
        for tol in TOLERANCES:
            f, n_k = agreement(stored_all, e, tol, count_stat)
            frac[(k, tol)] = f
            if k == "previous_days":
                n = n_k
    diagnosis, detail = classify(frac, n)

    rows = ~np.isnan(stored_all) if not count_stat else np.ones(n_rows, dtype=bool)
    prev = exp["previous_days"]
    dis = rows & ~agree_mask(np.nan_to_num(stored_all) if count_stat else stored_all,
                             np.nan_to_num(prev) if count_stat else prev, TOLERANCES[0])
    with np.errstate(invalid="ignore", divide="ignore"):
        abs_err = np.abs(stored_all - prev)
        rel_err = abs_err / np.maximum(1.0, np.abs(prev))
    min_obs = 2 if stat in ("std", "change", "pct_change") else 1
    n_dis = int(dis.sum())
    rec.update(
        diagnosis=diagnosis, detail=detail, recommendation=RECOMMENDATION[diagnosis],
        compared_rows=n, **{"disagreeing_rows_at_1e-9": n_dis},
        values_without_history=(0 if count_stat else int((rows & (prev_count < min_obs)).sum())),
        share_disagreeing_in_constant_windows=(None if n_dis == 0 else round(float(prev_constant[dis].mean()), 4)),
        share_disagreeing_in_high_mean_to_spread_windows=(
            None if n_dis == 0 else round(float((prev_ratio[dis] >= HIGH_RATIO).mean()), 4)),
        constant_source_share=round(constant_participants / participants, 4) if participants else None,
        **{f"abs_error_{k}": v for k, v in quantiles(abs_err[dis]).items()},
        **{f"rel_error_{k}": v for k, v in quantiles(rel_err[dis]).items()},
        **{f"agree_{k}_{t:g}": (None if np.isnan(f) else round(f, 4)) for (k, t), f in sorted(frac.items())},
    )
    if diagnosis == INDISTINGUISHABLE and rec["constant_source_share"] is not None \
            and rec["constant_source_share"] >= CONSTANT_SHARE_UNINFORMATIVE:
        rec["recommendation"] = "exclude (source is constant for nearly all participants - uninformative)"
    return rec


def diagnose_frame(features: pd.DataFrame, names, cfg) -> pd.DataFrame:
    """Diagnose the named features of an in-memory table. No file I/O."""
    redact = vt.make_redactor(features[cfg.pid].dropna().unique())
    table = pd.DataFrame([diagnose_feature(features, n, cfg) for n in names])
    for col in ("feature", "source"):
        if col in table.columns:
            table[col] = table[col].map(lambda v: v if pd.isna(v) else redact(v))
    return table


def summary_lines(table: pd.DataFrame) -> list[str]:
    def fmt(v):
        return "n/a" if v is None or (isinstance(v, float) and np.isnan(v)) else (
            f"{v:.3g}" if isinstance(v, float) else str(v))
    lines = ["ROLLING / BASELINE FEATURE DIAGNOSIS (read-only; aggregates only)", ""]
    for _, r in table.iterrows():
        lines.append(f"{r['feature']}: {r['diagnosis']}" + (f" ({r['detail']})" if r.get("detail") else ""))
        if "compared_rows" in r and pd.notna(r.get("compared_rows")):
            lines.append(f"  window: {r['family']}, statistic={r['statistic']}, days={fmt(r['window_days'])}; "
                         f"compared rows={int(r['compared_rows'])}; disagreeing at 1e-9={int(r['disagreeing_rows_at_1e-9'])}")
            ag = [c for c in table.columns if c.startswith("agree_") and pd.notna(r.get(c))]
            for variant in dict.fromkeys(c.rsplit("_", 1)[0][len("agree_"):] for c in ag):
                vals = [f"{t:g}={fmt(r.get(f'agree_{variant}_{t:g}'))}" for t in TOLERANCES]
                lines.append(f"  agreement with {variant}: " + ", ".join(vals))
            lines.append(f"  disagreements: in constant windows={fmt(r['share_disagreeing_in_constant_windows'])}, "
                         f"in high mean-to-spread windows={fmt(r['share_disagreeing_in_high_mean_to_spread_windows'])}; "
                         f"values without history={int(r['values_without_history'])}")
            lines.append(f"  relative error (disagreeing rows): median={fmt(r['rel_error_median'])}, "
                         f"p95={fmt(r['rel_error_p95'])}, max={fmt(r['rel_error_max'])}; "
                         f"constant-source participants share={fmt(r['constant_source_share'])}")
        lines.append(f"  recommendation: {r['recommendation'] if 'recommendation' in r and pd.notna(r.get('recommendation')) else RECOMMENDATION.get(r['diagnosis'], 'review')}")
        lines.append("")
    lines.append("Diagnoses: " + ", ".join(f"{k}={v}" for k, v in table["diagnosis"].value_counts().items()))
    lines.append("DIAGNOSIS COMPLETE - dataset not modified; no model trained")
    return lines


def features_from_verification(path: Path) -> list[str]:
    t = pd.read_csv(path)
    keep = t["status"].isin([vt.MISMATCH, vt.INCONCLUSIVE, vt.FAIL_AHEAD, vt.FAIL_NO_HISTORY])
    return [f for f in t.loc[keep, "feature"].astype(str) if "<ID>" not in f and "<DATE>" not in f]


def run(args) -> int:
    cfg = load_config(args.config, project_root=args.project_dir)
    out_dir = vt.safe_out_dir(Path(args.out_dir), cfg.project_root) if args.out_dir else None
    names = list(args.features) if args.features else []
    if args.from_verification:
        names += features_from_verification(Path(args.from_verification).expanduser())
    names = list(dict.fromkeys(names or DEFAULT_FEATURES))
    features = load_features(cfg)                       # read-only; labels never read
    run.ids = features[cfg.pid].dropna().unique()
    table = diagnose_frame(features, names, cfg)
    lines = summary_lines(table)
    print("\n".join(lines))
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        table.to_csv(out_dir / "rolling_std_diagnosis.csv", index=False)
        (out_dir / "rolling_std_diagnosis_summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    bad = table["diagnosis"].isin([LOOKS_AHEAD, DIFFERENT, NO_SOURCE, NOT_IN_TABLE, INSUFFICIENT])
    return 1 if bad.any() else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    ap.add_argument("--project-dir", default=None)
    ap.add_argument("--features", nargs="*", default=None, help="feature names to diagnose")
    ap.add_argument("--from-verification", default=None,
                    help="temporal_verification.csv: diagnose its MISMATCH/INCONCLUSIVE/FAIL features")
    ap.add_argument("--out-dir", default=None, help="optional; must be outside the project")
    args = ap.parse_args(argv)
    run.ids = ()
    try:
        return run(args)
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print("ERROR [interrupted]: diagnosis stopped by the user.", file=sys.stderr)
        return vt.EXIT_ERROR
    except BaseException as exc:                        # noqa: BLE001
        category, message = vt.error_report(exc, run.ids)
        print(f"ERROR [{category}]: {message}", file=sys.stderr)
        return vt.EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
