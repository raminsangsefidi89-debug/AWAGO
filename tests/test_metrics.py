"""Metric calculations vs known values."""

from __future__ import annotations

import numpy as np
import pytest

from app.services.forecasting.evaluation import (
    directional_accuracy,
    mae,
    mape,
    residual_quantiles,
    rmse,
    smape,
)


def test_mae_rmse_known_values():
    y_true = np.array([1.0, 2.0, 3.0])
    y_pred = np.array([1.5, 1.5, 3.5])
    assert mae(y_true, y_pred) == pytest.approx((0.5 + 0.5 + 0.5) / 3)
    assert rmse(y_true, y_pred) == pytest.approx(np.sqrt((0.25 + 0.25 + 0.25) / 3))


def test_smape_known_value_and_symmetry():
    y_true = np.array([100.0])
    y_pred = np.array([110.0])
    expected = abs(100 - 110) / ((100 + 110) / 2) * 100
    assert smape(y_true, y_pred) == pytest.approx(expected)
    assert smape(y_pred, y_true) == pytest.approx(expected)


def test_mape():
    y_true = np.array([100.0, 200.0])
    y_pred = np.array([110.0, 180.0])
    assert mape(y_true, y_pred) == pytest.approx((0.10 + 0.10) / 2 * 100)


def test_directional_accuracy():
    last = np.array([100.0, 100.0, 100.0, 100.0])
    y_true = np.array([101.0, 99.0, 102.0, 98.0])  # up, down, up, down
    y_pred = np.array([102.0, 98.0, 99.0, 101.0])  # up, down, down, up -> 2 of 4 correct
    da = directional_accuracy(y_true, y_pred, last)
    assert da == pytest.approx(50.0)


def test_directional_accuracy_undefined_for_naive():
    last = np.array([100.0, 100.0])
    y_true = np.array([101.0, 99.0])
    y_pred = np.array([100.0, 100.0])  # no predicted move
    assert directional_accuracy(y_true, y_pred, last) is None


def test_residual_quantiles():
    residuals = np.linspace(-0.02, 0.02, 1001)
    q_lo, q_hi = residual_quantiles(residuals, level=0.90)
    assert q_lo == pytest.approx(-0.018, abs=5e-4)
    assert q_hi == pytest.approx(0.018, abs=5e-4)
    assert q_lo < 0 < q_hi
