#!/usr/bin/env python3
"""Read-only, aggregate-only pre-training data check (no model training).

Usage (from the project root or anywhere):
    python ml/check_data.py [--config ml/config.yaml] [--project-dir .]

Prints counts only: label totals under both label policies, post-event
exclusion counts, the event-file diagnostic, the predictor report and the
participant-grouped split summary. Never prints participant IDs, dates or rows,
and never writes files.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from exacerbalert_ml.config import DEFAULT_CONFIG_PATH, load_config  # noqa: E402
from exacerbalert_ml.data import load_merged  # noqa: E402
from exacerbalert_ml.dataset import build_modeling_data  # noqa: E402
from exacerbalert_ml.diagnostics import explain_event_participants_without_positives  # noqa: E402
from exacerbalert_ml.events import load_raw_events  # noqa: E402
from exacerbalert_ml.features import load_feature_dictionary, time_in_study_proxies  # noqa: E402
from exacerbalert_ml.labels import apply_label_policy, label_summary  # noqa: E402
from exacerbalert_ml.splits import split_summary, splits_from_config  # noqa: E402


def show(title, obj):
    print(f"\n=== {title}")
    print(obj if isinstance(obj, str) else json.dumps(obj, indent=2, default=str))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    ap.add_argument("--project-dir", default=None)
    args = ap.parse_args()
    cfg = load_config(args.config, project_root=args.project_dir)

    merged = load_merged(cfg)
    dictionary = load_feature_dictionary(cfg)
    show("Merged table", {"rows": len(merged), "columns": merged.shape[1]})

    for policy in ("original", "tolife_v1_absent_file_negative"):
        show(f"Labels - policy {policy}", label_summary(apply_label_policy(merged, cfg, policy), cfg))

    raw_events = None
    try:
        raw_events = load_raw_events(cfg)
        show("Event files", {"files": raw_events.attrs.get("n_event_files", 0), "events": len(raw_events)})
        show("Event-file participants without positive labels",
             explain_event_participants_without_positives(merged, raw_events, cfg))
    except FileNotFoundError:
        show("Event files", "raw event directory not found - diagnostic skipped")

    pe = cfg["post_event"]
    for w in [pe["primary_washout_days"]] + list(pe["sensitivity_washout_days"]):
        md = build_modeling_data(merged, dictionary, cfg, washout_days=w)
        show(f"Modelling data - washout {w}", {k: v for k, v in md.info.items() if k != "labels_before_exclusion"})

    md = build_modeling_data(merged, dictionary, cfg)
    show("Time-in-study proxy features (provisional)", {"count": len(time_in_study_proxies(md.predictors, cfg))})
    splits = splits_from_config(md.groups.to_numpy(), md.y.to_numpy(), cfg)
    show("Participant-grouped splits (primary analysis)", split_summary(md.groups.to_numpy(), md.y.to_numpy(),
                                                                        splits).to_string(index=False))
    print("\nCHECK COMPLETE (read-only; nothing was written; no model was trained)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
