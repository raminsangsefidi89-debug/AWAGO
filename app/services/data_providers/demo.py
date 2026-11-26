"""Deterministic synthetic market-data provider (Demo mode).

Data is generated from a fixed seed per pair as a geometric random walk with
GARCH(1,1)-style volatility clustering. The value for any given date never
changes between runs (the series is always generated sequentially from a
fixed epoch), so demo data is fully reproducible.

Demo data is unmistakable: it is stored with ``data_source="demo"`` and
``is_demo=True``, and the dashboard shows a prominent banner.
"""

from __future__ import annotations

import zlib
from datetime import date, timedelta

import numpy as np

from app.services.data_providers.base import (
    DataProvider,
    PriceBarData,
    to_utc_midnight,
)
from app.services.data_providers.capabilities import ProviderCapabilities

EPOCH = date(2015, 1, 1)  # fixed generation start -> stable history over time

# Realistic starting levels and per-pair volatility/drift for the synthetic walk.
PAIR_PROFILES: dict[str, tuple[float, float, float]] = {
    # symbol: (start_price, daily_vol, annual_drift)
    "EUR/USD": (1.1000, 0.0052, 0.00),
    "GBP/USD": (1.2700, 0.0056, -0.01),
    "USD/JPY": (148.00, 0.0062, 0.02),
    "USD/CHF": (0.8800, 0.0050, -0.01),
    "AUD/USD": (0.6600, 0.0068, -0.01),
    "USD/CAD": (1.3500, 0.0048, 0.00),
    "NZD/USD": (0.6100, 0.0070, -0.01),
    "EUR/GBP": (0.8600, 0.0042, 0.00),
    "EUR/JPY": (163.00, 0.0064, 0.01),
    "USD/TRY": (29.500, 0.0110, 0.25),
}
DEFAULT_PROFILE = (1.0000, 0.0055, 0.0)

# GARCH(1,1) parameters (persistent volatility clustering).
GARCH_ALPHA = 0.09
GARCH_BETA = 0.87
GARCH_LONG_RUN_FRAC = 0.04  # omega = frac * (1 - alpha - beta) * long_run_var


def _pair_seed(base_seed: int, pair: str) -> int:
    """Stable per-pair seed derived from the base seed and the symbol.

    Uses CRC32 (not Python's salted ``hash``) so results are identical
    across processes and platforms.
    """
    return (base_seed * 1_000_003 + zlib.crc32(pair.encode("utf-8"))) % (2**31 - 1)


class DemoProvider(DataProvider):
    """Reproducible synthetic OHLC provider."""

    name = "demo"
    is_demo = True

    capabilities = ProviderCapabilities(
        name="demo",
        pairs=("*",),
        intervals=("1d",),
        history_depth_days=None,
        rate_limit_per_minute=None,
        latency_typical_ms=1,
        license_notes="Synthetic data generated locally (fixed seed); not real market data.",
        requires_key=False,
        verified_live=True,
        is_demo=True,
    )

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed

    # ------------------------------------------------------------------
    def _generate_closes(self, pair: str, n_days: int) -> np.ndarray:
        """Generate ``n_days`` daily closes from EPOCH, deterministic per pair."""
        start_price, daily_vol, annual_drift = PAIR_PROFILES.get(pair, DEFAULT_PROFILE)
        rng = np.random.default_rng(_pair_seed(self.seed, pair))

        daily_drift = annual_drift / 252.0
        long_run_var = daily_vol**2
        omega = GARCH_LONG_RUN_FRAC * (1 - GARCH_ALPHA - GARCH_BETA) * long_run_var

        z = rng.standard_normal(n_days)
        log_returns = np.empty(n_days)
        sigma2 = long_run_var
        for t in range(n_days):
            sigma2 = (
                omega
                + GARCH_ALPHA * (log_returns[t - 1] ** 2 if t > 0 else long_run_var)
                + GARCH_BETA * sigma2
            )
            sigma2 = max(sigma2, 1e-12)
            log_returns[t] = daily_drift + np.sqrt(sigma2) * z[t]

        closes = start_price * np.exp(np.cumsum(log_returns))
        return closes

    def _generate_series(self, pair: str, start: date, end: date) -> list[PriceBarData]:
        if end < start:
            return []
        n_days = (end - EPOCH).days + 1
        if n_days <= 0:
            return []
        closes = self._generate_closes(pair, n_days)
        rng = np.random.default_rng(_pair_seed(self.seed + 7, pair))

        bars: list[PriceBarData] = []
        prev_close = float(closes[0])
        for i in range(n_days):
            current_day = EPOCH + timedelta(days=i)
            if current_day < start:
                prev_close = float(closes[i])
                continue
            if current_day > end:
                break
            close = float(closes[i])
            # Synthetic intraday range around the close-to-close move.
            daily_range = abs(close - prev_close) + abs(rng.normal(0, 0.0025)) * close
            gap = rng.normal(0, 0.0012) * prev_close
            open_ = prev_close + gap
            high = max(open_, close) + abs(rng.normal(0, 0.4)) * daily_range
            low = min(open_, close) - abs(rng.normal(0, 0.4)) * daily_range
            low = max(low, 1e-6)
            bars.append(
                PriceBarData(
                    timestamp=to_utc_midnight(current_day),
                    open=round(open_, 6),
                    high=round(high, 6),
                    low=round(low, 6),
                    close=round(close, 6),
                    volume=None,
                )
            )
            prev_close = close
        return bars

    # ------------------------------------------------------------------
    def fetch_history(self, pair: str, start: date, end: date) -> list[PriceBarData]:
        pair = pair.upper()
        return self._generate_series(pair, start, end)

    def fetch_latest(self, pair: str) -> PriceBarData | None:
        today = date.today()
        bars = self._generate_series(pair.upper(), today - timedelta(days=7), today)
        return bars[-1] if bars else None
