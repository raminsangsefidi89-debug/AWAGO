"""Chronological / walk-forward splitting guarantees."""

from __future__ import annotations

import numpy as np

from app.services.forecasting.evaluation import walk_forward_indices


def test_walk_forward_is_strictly_chronological():
    n = 200
    folds = walk_forward_indices(n, n_splits=4)
    assert len(folds) >= 1
    for train_idx, test_idx in folds:
        assert train_idx.max() < test_idx.min(), "test rows must come strictly after train rows"
        # expanding window: train always starts at 0
        assert train_idx.min() == 0


def test_walk_forward_test_folds_are_disjoint_and_ordered():
    n = 200
    folds = walk_forward_indices(n, n_splits=4)
    all_test = np.concatenate([te for _, te in folds])
    assert len(all_test) == len(np.unique(all_test)), "test folds must not overlap"
    assert np.all(np.diff(all_test) > 0), "test indices must be increasing"


def test_walk_forward_handles_small_samples():
    folds = walk_forward_indices(10, n_splits=5)
    assert len(folds) >= 1
    for train_idx, test_idx in folds:
        assert len(train_idx) > 0 and len(test_idx) > 0
        assert train_idx.max() < test_idx.min()
