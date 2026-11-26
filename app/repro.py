"""Deterministic experiments: global seeding, config hashing, snapshot hashing.

Any result produced by AWAGO can be reproduced from a **run id** together
with the data snapshot it consumed. Run ids are derived from:

* the config hash (all non-secret settings),
* the data-snapshot hash (sha256 over the exact bars used),
* an optional human label.

``seed_everything`` seeds Python, NumPy and (if present) the ML libraries.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Iterable

from app.config import Settings, get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)


def seed_everything(seed: int) -> int:
    """Seed all RNGs we touch. Returns the seed for logging."""
    import contextlib

    random.seed(seed)
    with contextlib.suppress(Exception):  # numpy required in practice; never fail hard
        import numpy as np

        np.random.seed(seed % (2**32))
    with contextlib.suppress(Exception):  # torch is optional
        import torch

        torch.manual_seed(seed)
    return seed


def config_hash(settings: Settings | None = None) -> str:
    return (settings or get_settings()).config_hash()


def snapshot_hash(rows: Iterable[tuple]) -> str:
    """Hash an iterable of sortable row tuples (deterministic order-insensitive).

    Typical use: ``snapshot_hash((b.pair_symbol, b.timestamp.isoformat(), b.close)
    for b in bars)`` — values are sorted before hashing so row order does not
    matter, while content changes always change the hash.
    """
    h = hashlib.sha256()
    for row in sorted(rows):
        h.update(json.dumps(row, default=str).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()[:16]


def make_run_id(
    label: str,
    *,
    settings: Settings | None = None,
    snapshot: str | None = None,
) -> str:
    """Build a reproducible run id: ``label-cfgX-snapY`` style short hash."""
    ch = config_hash(settings)
    sh = snapshot or "nosnap"
    digest = hashlib.sha256(f"{label}|{ch}|{sh}".encode()).hexdigest()[:12]
    return f"{label}-{digest}"


def verify_reproducible(
    run_id: str, label: str, settings: Settings | None, snapshot: str | None
) -> bool:
    """Recompute a run id and compare — used by the reproducibility tests."""
    expected = make_run_id(label, settings=settings, snapshot=snapshot)
    ok = expected == run_id
    if not ok:
        logger.warning("Reproducibility check FAILED: %s != %s", expected, run_id)
    return ok
