"""Conservative feature-exclusion register.

Applied to the predictor allowlist BEFORE any fold is fitted. It only removes
features (never adds any) and records one decision and reason per feature.

Rules, in order:
  1. calendar/time name patterns              -> exclude
  2. time-in-study proxy patterns             -> exclude (if enabled)
  3. explicit config exclusions                -> exclude
  4. feature audit (audit_features.py output):
       not present in the audit                -> exclude ("not_in_feature_audit")
       audit decision 'exclude'                -> exclude
       a configured review reason              -> exclude
  5. temporal verification (verify_temporal.py --all):
       rolling/baseline feature not PASS       -> exclude (including never checked)
  6. cleared_after_review                      -> re-admitted with the documented reason
Everything else is included; data-driven filters (missingness, constant,
duplicate) still run inside each training fold.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from .config import Config

INCLUDE, EXCLUDE = "include", "exclude"


class AuditInputError(ValueError):
    """Raised when a required audit input is missing or was produced under the wrong policy."""


def _is_temporal(name: str) -> bool:
    return bool(re.search(r"_rolling_\d+d_[a-z_]+$|_baseline_[a-z_]+$", name))


def load_feature_audit(audit_dir: str | Path, cfg: Config) -> pd.DataFrame:
    """Read audit_features.py output and check it used the configured label policy."""
    d = Path(audit_dir).expanduser()
    csv, summary = d / "feature_audit.csv", d / "feature_audit_summary.txt"
    if not csv.is_file() or not summary.is_file():
        raise AuditInputError("feature audit output not found (feature_audit.csv and summary are required)")
    policy = cfg["target"]["label_policy"]
    head = summary.read_text(encoding="utf-8").splitlines()[:3]
    if not any(f"label_policy={policy}" in line for line in head):
        raise AuditInputError(f"feature audit was not produced under label_policy={policy}; re-run audit_features.py")
    t = pd.read_csv(csv)
    for col in ("feature", "decision", "review_reasons"):
        if col not in t.columns:
            raise AuditInputError(f"feature audit CSV lacks column '{col}'")
    return t


def load_temporal_verification(path: str | Path) -> pd.DataFrame:
    p = Path(path).expanduser()
    if not p.is_file():
        raise AuditInputError("temporal verification CSV not found (run verify_temporal.py --all)")
    t = pd.read_csv(p)
    if not {"feature", "status"} <= set(t.columns):
        raise AuditInputError("temporal verification CSV lacks 'feature'/'status' columns")
    return t


def build_register(predictors, cfg: Config, audit: pd.DataFrame | None = None,
                   temporal: pd.DataFrame | None = None, strict: bool = True) -> pd.DataFrame:
    """Return a register with columns feature, decision, reasons (one row per predictor)."""
    fx = cfg["feature_exclusions"]
    if strict and fx.get("require_feature_audit", True) and audit is None:
        raise AuditInputError("feature audit is required for this run (feature_exclusions.require_feature_audit)")
    if strict and fx.get("require_temporal_verification", True) and temporal is None:
        raise AuditInputError("temporal verification is required (feature_exclusions.require_temporal_verification)")

    cal = [re.compile(p) for p in fx.get("calendar_name_patterns", [])]
    proxy = [re.compile(p) for p in cfg.raw.get("time_in_study_proxy_patterns", [])] \
        if fx.get("exclude_time_in_study_proxies", True) else []
    explicit = dict(fx.get("explicit") or {})
    cleared = dict(fx.get("cleared_after_review") or {})
    review_block = set(fx.get("exclude_audit_review_reasons", []))

    audit_by = {} if audit is None else {
        str(r["feature"]): (str(r["decision"]), str(r.get("review_reasons", "") or ""))
        for _, r in audit.iterrows()}
    temporal_by = {} if temporal is None else dict(zip(temporal["feature"].astype(str),
                                                       temporal["status"].astype(str)))

    rows = []
    for f in predictors:
        reasons = []
        if any(p.search(f) for p in cal):
            reasons.append("calendar_or_time_name")
        if any(p.search(f) for p in proxy):
            reasons.append("time_in_study_proxy")
        if f in explicit:
            reasons.append(f"explicit: {explicit[f]}")
        if audit is not None:
            if f not in audit_by:
                reasons.append("not_in_feature_audit")
            else:
                decision, rr = audit_by[f]
                if decision == "exclude":
                    reasons.append("audit_exclude")
                hits = sorted(set(filter(None, rr.split(";"))) & review_block)
                reasons += [f"audit_review:{h}" for h in hits]
        if temporal is not None and _is_temporal(f):
            status = temporal_by.get(f)
            if status is None:
                reasons.append("temporal_not_verified")
            elif status != "PASS":
                reasons.append(f"temporal_{status}")
        if f in cleared:
            rows.append({"feature": f, "decision": INCLUDE,
                         "reasons": f"cleared_after_review: {cleared[f]}" + (
                             f" (would otherwise be: {'; '.join(reasons)})" if reasons else "")})
        else:
            rows.append({"feature": f, "decision": EXCLUDE if reasons else INCLUDE,
                         "reasons": "; ".join(reasons)})
    return pd.DataFrame(rows, columns=["feature", "decision", "reasons"])


def register_summary(register: pd.DataFrame) -> dict:
    excl = register[register["decision"] == EXCLUDE]
    # Group "explicit: <text>" as "explicit"; keep audit_review:<reason> and temporal_<status> specific.
    reasons = excl["reasons"].str.split("; ").explode().map(
        lambda r: "explicit" if str(r).startswith("explicit:") else str(r))
    return {"candidates": int(len(register)), "included": int((register["decision"] == INCLUDE).sum()),
            "excluded": int(len(excl)),
            "excluded_by_reason": {str(k): int(v) for k, v in reasons.value_counts().items()}}
