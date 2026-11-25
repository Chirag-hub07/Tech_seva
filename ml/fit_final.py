#!/usr/bin/env python3
"""Fit ONE final model on all development participants, after cross-validation.

Research prototype only - not a clinically validated prediction system.

Usage (from the project root):
    python ml/fit_final.py --run-dir ml/outputs/runs/<run folder> --model <model name>

Refuses unless the given run completed the primary AND all sensitivity analyses
with the full configured design, the model was cross-validated there, and the
inputs and feature register are unchanged. The saved artifact has NO performance
estimate of its own: the run's cross-validation figures describe the procedure.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _cli import run_safely  # noqa: E402
from exacerbalert_ml.config import DEFAULT_CONFIG_PATH, load_config  # noqa: E402
from exacerbalert_ml.models import MODEL_NAMES  # noqa: E402
from exacerbalert_ml.runner import run_final_fit  # noqa: E402
from exacerbalert_ml.utils import set_seeds  # noqa: E402


def run(args) -> int:
    cfg = load_config(args.config, project_root=args.project_dir)
    set_seeds(int(cfg["training"]["random_seed"]))
    out = run_final_fit(cfg, Path(args.run_dir).expanduser(), args.model, args.audit_dir, args.temporal_csv)
    print(f"Final model saved in the run folder: {out.name}/ (model.joblib, input_schema.json)")
    print("Its performance is NOT measured by this step; see the run's cross-validation report.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    ap.add_argument("--project-dir", default=None)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--model", required=True, choices=list(MODEL_NAMES))
    ap.add_argument("--audit-dir", default=None)
    ap.add_argument("--temporal-csv", default=None)
    return run_safely(run, ap.parse_args(argv), run)


if __name__ == "__main__":
    sys.exit(main())
