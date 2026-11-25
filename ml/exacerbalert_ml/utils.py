"""Reproducibility helpers: seeds, file hashes, environment metadata, run folders."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def set_seeds(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    os.environ.setdefault("PYTHONHASHSEED", str(seed))


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def environment_info() -> dict:
    info = {"python": platform.python_version(), "platform": f"{platform.system()} {platform.machine()}"}
    for mod in ("numpy", "pandas", "sklearn", "scipy", "pyarrow", "joblib", "yaml"):
        try:
            info[mod] = __import__(mod).__version__
        except Exception:  # pragma: no cover - optional package
            info[mod] = "not installed"
    return info


def new_run_dir(outputs: Path, subdir: str, label: str) -> Path:
    """Create a fresh, never-overwritten run folder (UTC timestamp of the run, not of any data)."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = Path(outputs) / subdir
    run = base / f"{stamp}_{label}"
    n = 1
    while run.exists():
        n += 1
        run = base / f"{stamp}_{label}_{n}"
    run.mkdir(parents=True, exist_ok=False)
    return run


def write_json(path: Path, obj) -> None:
    def default(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return None if not np.isfinite(o) else float(o)
        if isinstance(o, Path):
            return o.name
        return str(o)
    path.write_text(json.dumps(obj, indent=2, default=default, sort_keys=True) + "\n", encoding="utf-8")


def command_line() -> str:
    """The command used, with absolute paths reduced to their final component."""
    return " ".join(Path(a).name if os.path.isabs(a) else a for a in sys.argv)
