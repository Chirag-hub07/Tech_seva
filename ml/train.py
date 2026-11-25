#!/usr/bin/env python3
"""Nested participant-grouped cross-validation of the ExacerbAlert models (no final model).

Research prototype only - not a clinically validated prediction system.

Usage (from the project root):
    python ml/train.py                           # primary analysis, full configured design
    python ml/train.py --analyses all            # primary + all pre-specified sensitivity analyses
    python ml/train.py --models logistic_regression dummy_prior --repeats 1   # quick, flagged REDUCED

Requires the feature audit (audit_features.py, label_policy=original) and the
full temporal verification (verify_temporal.py --all); see config.yaml
feature_exclusions. Outputs (aggregates only) go to a new folder under
ml/outputs/runs/. No final model is fitted: use fit_final.py afterwards.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _cli import run_safely  # noqa: E402
from exacerbalert_ml.config import DEFAULT_CONFIG_PATH, load_config  # noqa: E402
from exacerbalert_ml.models import MODEL_NAMES  # noqa: E402
from exacerbalert_ml.runner import ALL_ANALYSES, RunError, run_training  # noqa: E402
from exacerbalert_ml.utils import set_seeds  # noqa: E402


def safe_outputs(path: Path, cfg) -> Path:
    """Outputs must be inside the git-ignored ml/outputs folder or outside the project."""
    out, root = path.expanduser().resolve(), cfg.project_root.resolve()
    ignored = (root / "ml" / "outputs").resolve()
    if (out == root or root in out.parents) and not (out == ignored or ignored in out.parents):
        raise RunError("--outputs inside the project must be ml/outputs (git-ignored)")
    return out


def run(args) -> int:
    cfg = load_config(args.config, project_root=args.project_dir)
    set_seeds(int(cfg["training"]["random_seed"]))
    analyses = list(ALL_ANALYSES) if args.analyses == ["all"] else args.analyses
    outputs = safe_outputs(Path(args.outputs), cfg) if args.outputs else None
    run_dir = run_training(cfg, analyses=analyses, models=args.models, n_repeats=args.repeats,
                           label=args.label, audit_dir=args.audit_dir, temporal_csv=args.temporal_csv,
                           outputs_dir=outputs, progress=None if args.quiet else (lambda m: print(m, flush=True)))
    try:
        shown = run_dir.resolve().relative_to(cfg.project_root.resolve())
    except ValueError:
        shown = run_dir.name
    print(f"Run complete. Aggregate outputs: {shown}")
    print((run_dir / "report.md").read_text(encoding="utf-8"))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    ap.add_argument("--project-dir", default=None)
    ap.add_argument("--analyses", nargs="+", default=["primary"], choices=list(ALL_ANALYSES) + ["all"])
    ap.add_argument("--models", nargs="+", default=None, choices=list(MODEL_NAMES))
    ap.add_argument("--repeats", type=int, default=None,
                    help="use only the first N configured repeats (flagged REDUCED; development only)")
    ap.add_argument("--audit-dir", default=None, help="overrides feature_exclusions.feature_audit_dir")
    ap.add_argument("--temporal-csv", default=None, help="overrides feature_exclusions.temporal_verification_csv")
    ap.add_argument("--outputs", default=None, help="default: paths.outputs (ml/outputs, git-ignored)")
    ap.add_argument("--label", default="cv")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    if args.repeats is not None and args.repeats < 1:
        ap.error("--repeats must be >= 1")
    return run_safely(run, args, run)


if __name__ == "__main__":
    sys.exit(main())
