"""Walk-forward splitters with purging and embargo (no lookahead, ever).

Two schemes:
* ``expanding``: train grows monotonically.
* ``rolling``: train window slides (``train_size`` rows).

**Purging**: train rows whose h-step target window would overlap the test
block's targets are dropped (``horizon - 1`` rows before the test start).
**Embargo**: optionally drop an extra ``embargo`` rows at the boundary to
reduce serial-correlation bleed.
"""

from __future__ import annotations

import numpy as np


def purged_splits(
    n: int,
    n_splits: int,
    horizon: int = 1,
    scheme: str = "expanding",
    train_size: int = 0,
    embargo: int = 0,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Return [(train_idx, test_idx)] with purge + embargo applied."""
    if n_splits < 1:
        raise ValueError("n_splits must be >= 1")
    if n < n_splits * 15:
        raise ValueError(f"series too short for {n_splits} splits (n={n})")

    # split the post-initial region into n_splits test blocks
    initial = max(horizon + 10, n // (n_splits + 1))
    if scheme == "rolling" and train_size <= 0:
        train_size = initial
    test_region = n - initial
    block = test_region // n_splits
    if block < 5:
        raise ValueError(f"test blocks too small (block={block}); reduce n_splits")

    splits: list[tuple[np.ndarray, np.ndarray]] = []
    for k in range(n_splits):
        test_start = initial + k * block
        test_end = test_start + block if k < n_splits - 1 else n
        purge = horizon - 1 + embargo
        train_end = max(1, test_start - purge)
        if scheme == "rolling":
            train_start = max(0, train_end - train_size)
        else:
            train_start = 0
        train_idx = np.arange(train_start, train_end)
        test_idx = np.arange(test_start, test_end)
        if len(train_idx) < 20 or len(test_idx) == 0:
            continue
        splits.append((train_idx, test_idx))
    if not splits:
        raise ValueError("no usable walk-forward splits")
    return splits
