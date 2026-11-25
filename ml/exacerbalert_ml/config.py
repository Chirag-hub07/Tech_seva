"""Configuration loading."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ML_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ML_DIR / "config.yaml"


@dataclass
class Config:
    raw: dict[str, Any]
    project_root: Path
    source: Path | None = None
    _cache: dict[str, Any] = field(default_factory=dict, repr=False)

    # ---- convenience accessors -------------------------------------------
    def path(self, key: str) -> Path:
        value = self.raw["paths"][key]
        p = Path(value)
        return p if p.is_absolute() else self.project_root / p

    def col(self, key: str) -> str:
        return self.raw["columns"][key]

    @property
    def pid(self) -> str:
        return self.col("participant_id")

    @property
    def date(self) -> str:
        return self.col("date")

    @property
    def horizon_days(self) -> int:
        return int(self.raw["target"]["horizon_days"])

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]


def load_config(path: str | Path | None = None, project_root: str | Path | None = None) -> Config:
    """Load a YAML configuration file.

    project_root defaults to the parent of the ml/ directory.
    """
    cfg_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    with open(cfg_path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    root = Path(project_root) if project_root is not None else ML_DIR.parent
    return Config(raw=raw, project_root=root.resolve(), source=cfg_path)


def config_from_dict(raw: dict[str, Any], project_root: str | Path = ".") -> Config:
    """Build a Config from an in-memory dictionary (used by tests)."""
    return Config(raw=raw, project_root=Path(project_root).resolve())
