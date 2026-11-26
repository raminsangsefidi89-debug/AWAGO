"""Backtest SIMULATION — educational, not a trading system.

Hard rules (enforced here and repeated in every output):
* Direction-only positions (long/short/flat), NO leverage, NO compounding
  tricks — exposure is 1x notional at most.
* Costs and slippage are ALWAYS charged (basis points per side).
* Benchmarks: buy-and-hold of the same pair AND a seeded random-signal
  control with identical cost structure. A strategy that cannot beat the
  random control has no demonstrated skill.
* Every result carries: "Educational and analytical use only. Not financial
  advice. Past performance does not indicate future results." and a
  deflated-Sharpe caution (with many trials, some Sharpe looks good by luck).
"""

from __future__ import annotations

from typing import Any

import numpy as np

DISCLAIMER = (
    "Educational and analytical use only. Not financial advice. "
    "This is a simulation with modeled costs — past performance does not "
    "indicate future results. FX is close to efficient; treat any edge with "
    "deep skepticism."
)
DEFLATED_SHARPE_CAUTION = (
    "With many models/horizons tried, the best observed Sharpe is biased "
    "upward (selection on noise). Treat single backtest Sharpes as upper "
    "bounds, not expectations — this is the deflated-Sharpe problem."
)


def simulate(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    cost_bps_per_side: float = 1.0,
    slippage_bps_per_side: float = 0.5,
    seed: int = 42,
    level: float = 0.90,
) -> dict[str, Any]:
    """Simulate sign-based positions over realized log returns.

    ``y_true[t]`` is the realized log return over (t, t+h]; positions are set
    at t from ``y_pred[t]`` and earn ``y_true[t]`` minus turnover costs.
    """
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_pred, dtype=float)
    n = min(len(y), len(p))
    y, p = y[:n], p[:n]

    pos = np.sign(np.nan_to_num(p, nan=0.0))
    turnover = np.abs(np.diff(pos, prepend=0.0))
    cost_rate = (cost_bps_per_side + slippage_bps_per_side) / 10_000.0
    costs = turnover * cost_rate
    strategy_returns = pos * y - costs

    # buy & hold (same asset, no signal, cost once at entry)
    bh_returns = y.copy()
    bh_returns[0] -= cost_rate

    # random-signal control: same position distribution, seeded
    rng = np.random.default_rng(seed)
    rand_pos = rng.choice([-1.0, 0.0, 1.0], size=n, p=[1 / 3, 1 / 3, 1 / 3])
    rand_turnover = np.abs(np.diff(rand_pos, prepend=0.0))
    rand_returns = rand_pos * y - rand_turnover * cost_rate

    def _stats(rets: np.ndarray) -> dict[str, float]:
        eq = np.cumprod(1.0 + rets)
        mean = float(np.mean(rets))
        std = float(np.std(rets, ddof=1)) if len(rets) > 1 else float("nan")
        sharpe = (
            float(mean / std * np.sqrt(252.0))
            if std and np.isfinite(std) and std > 0
            else float("nan")
        )
        running_max = np.maximum.accumulate(eq)
        max_dd = float(np.min(eq / running_max - 1.0))
        return {
            "total_return": round(float(eq[-1] - 1.0), 6),
            "annualized_sharpe": round(sharpe, 4),
            "max_drawdown": round(max_dd, 6),
            "hit_rate": round(float(np.mean(np.sign(rets) == np.sign(y))), 4),
        }

    n_trades = int(np.sum(turnover > 0))
    return {
        "strategy": _stats(strategy_returns),
        "buy_and_hold": _stats(bh_returns),
        "random_control": _stats(rand_returns),
        "n_trades": n_trades,
        "cost_bps_per_side": cost_bps_per_side,
        "slippage_bps_per_side": slippage_bps_per_side,
        "position": "sign of forecast, 1x notional, no leverage",
        "disclaimer": DISCLAIMER,
        "deflated_sharpe_caution": DEFLATED_SHARPE_CAUTION,
        "verdict_vs_random": (
            "strategy beat the random control on total return (simulation only)"
            if float(np.cumprod(1.0 + strategy_returns)[-1])
            > float(np.cumprod(1.0 + rand_returns)[-1])
            else "strategy did NOT beat the random control (no demonstrated skill)"
        ),
    }
