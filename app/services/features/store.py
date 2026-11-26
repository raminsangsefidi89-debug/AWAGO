"""Feature store: versioned Parquet artifacts under data/features/."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from app.config import DATA_DIR
from app.logging_config import get_logger
from app.services.features.set import FEATURE_SET_VERSION, get_feature_set

logger = get_logger(__name__)


def features_dir(base: Path | None = None) -> Path:
    d = (base or DATA_DIR) / "features"
    d.mkdir(parents=True, exist_ok=True)
    return d


def features_path(
    pair_symbol: str, version: str = FEATURE_SET_VERSION, base: Path | None = None
) -> Path:
    slug = pair_symbol.replace("/", "_").upper()
    return features_dir(base) / f"{slug}__v{version}.parquet"


def save_features(
    frame: pd.DataFrame,
    pair_symbol: str,
    version: str = FEATURE_SET_VERSION,
    base: Path | None = None,
    meta: dict | None = None,
) -> Path:
    """Persist a feature frame plus its feature-set metadata."""
    path = features_path(pair_symbol, version, base)
    frame.to_parquet(path, engine="pyarrow", compression="zstd", index=False)
    meta_path = path.with_suffix(".meta.json")
    meta_doc = {
        "pair_symbol": pair_symbol,
        "feature_set_version": version,
        "row_count": len(frame),
        "feature_set": get_feature_set().as_dict(),
        **(meta or {}),
    }
    meta_path.write_text(json.dumps(meta_doc), encoding="utf-8")
    logger.info("Saved features %s (%d rows)", path.name, len(frame))
    return path


def load_features(
    pair_symbol: str,
    version: str = FEATURE_SET_VERSION,
    base: Path | None = None,
) -> pd.DataFrame | None:
    path = features_path(pair_symbol, version, base)
    if not path.exists():
        return None
    return pd.read_parquet(path, engine="pyarrow")
