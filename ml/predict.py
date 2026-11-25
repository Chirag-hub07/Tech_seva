#!/usr/bin/env python3
"""Score a feature table with a final model saved by fit_final.py.

Research prototype only - not a clinically validated prediction system.
Never use these outputs for clinical decisions.

Usage:
    python ml/predict.py --model-dir <run>/final_model_<model> --input features.parquet \
        --output ~/exacerbalert_predictions/predictions.csv

The output holds one row per input row (participant/date keys if present,
probability, alert) and is patient-level, so it must be written OUTSIDE the
project folder. Nothing patient-level is printed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _cli import run_safely  # noqa: E402
from exacerbalert_ml.config import DEFAULT_CONFIG_PATH, load_config  # noqa: E402
from exacerbalert_ml.data import DataValidationError, read_table  # noqa: E402
from exacerbalert_ml.features import is_banned  # noqa: E402
from exacerbalert_ml.runner import RunError  # noqa: E402


def load_artifact(model_dir: Path):
    import joblib

    schema_path, model_path = model_dir / "input_schema.json", model_dir / "model.joblib"
    if not schema_path.is_file() or not model_path.is_file():
        raise FileNotFoundError("model.joblib / input_schema.json not found")
    return joblib.load(model_path), json.loads(schema_path.read_text(encoding="utf-8"))


def predict_frame(pipe, schema: dict, frame, cfg):
    import pandas as pd

    predictors = schema["predictors"]
    missing = [c for c in predictors if c not in frame.columns]
    if missing:
        raise DataValidationError(f"input lacks {len(missing)} of {len(predictors)} required predictors")
    if any(is_banned(c, cfg) for c in predictors):
        raise RunError("the model schema lists a banned column")
    p = pipe.predict_proba(frame[predictors])[:, 1]
    out = pd.DataFrame({c: frame[c] for c in (cfg.pid, cfg.date) if c in frame.columns})
    out["probability_7d"] = p
    out["alert"] = (p >= float(schema["alert_threshold"])).astype(int)
    return out


def run(args) -> int:
    cfg = load_config(args.config, project_root=args.project_dir)
    out_path = Path(args.output).expanduser().resolve()
    root = cfg.project_root.resolve()
    if out_path == root or root in out_path.parents:
        raise RunError("--output must be outside the project folder (predictions are patient-level)")
    pipe, schema = load_artifact(Path(args.model_dir).expanduser())
    frame = read_table(Path(args.input).expanduser())
    if cfg.pid in frame.columns:
        run.ids = frame[cfg.pid].dropna().unique()
    out = predict_frame(pipe, schema, frame, cfg)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and not args.overwrite:
        raise RunError("--output exists; choose a new file or pass --overwrite")
    out.to_csv(out_path, index=False)
    print(f"Scored {len(out)} rows; {int(out['alert'].sum())} alerts at threshold "
          f"{schema['alert_threshold']:.4f}. Written to {out_path.name}. Research use only.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    ap.add_argument("--project-dir", default=None)
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args(argv)
    run.ids = ()
    return run_safely(run, args, run)


if __name__ == "__main__":
    sys.exit(main())
