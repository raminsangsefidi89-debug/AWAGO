"""Model persistence (joblib) under data/models/ with metadata."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import joblib

from app.logging_config import get_logger

logger = get_logger(__name__)


def pair_slug(pair_symbol: str) -> str:
    return pair_symbol.replace("/", "").upper()


def model_path(models_dir: Path, pair_symbol: str, horizon: int, model_name: str) -> Path:
    d = models_dir / pair_slug(pair_symbol)
    d.mkdir(parents=True, exist_ok=True)
    return d / f"h{horizon}_{model_name}.joblib"


def save_bundle(path: Path, bundle: Dict[str, Any]) -> str:
    """Persist a model bundle; returns the absolute path as a string."""
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, path)
    logger.info("Saved model bundle to %s", path)
    return str(path.resolve())


def load_bundle(path: str | Path) -> Dict[str, Any]:
    """Load a model bundle previously saved with :func:`save_bundle`."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Model bundle not found: {p}")
    return joblib.load(p)
