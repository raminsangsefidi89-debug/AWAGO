"""Demo provider: determinism, realism constraints, source flags."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from app.services.data_providers.demo import DemoProvider


def test_deterministic_same_seed_same_data():
    a = DemoProvider(seed=42)
    b = DemoProvider(seed=42)
    end = date.today()
    start = end - timedelta(days=60)
    bars_a = a.fetch_history("EUR/USD", start, end)
    bars_b = b.fetch_history("EUR/USD", start, end)
    assert len(bars_a) == len(bars_b) > 30
    for x, y in zip(bars_a, bars_b, strict=False):
        assert x.timestamp == y.timestamp
        assert x.close == y.close
        assert x.high == y.high
        assert x.low == y.low


def test_different_seed_different_data():
    end = date.today()
    start = end - timedelta(days=60)
    a = DemoProvider(seed=1).fetch_history("EUR/USD", start, end)
    b = DemoProvider(seed=2).fetch_history("EUR/USD", start, end)
    assert any(x.close != y.close for x, y in zip(a, b, strict=False))


def test_past_values_stable_when_time_advances():
    """Values for a past date must not change when the window end moves."""
    p = DemoProvider(seed=7)
    d1 = date(2024, 6, 1)
    d2 = date(2024, 6, 30)
    early = p.fetch_history("USD/JPY", date(2024, 1, 1), d1)
    later = p.fetch_history("USD/JPY", date(2024, 1, 1), d2)
    by_date = {b.day: b.close for b in later}
    for bar in early:
        assert by_date[bar.day] == bar.close


def test_ohlc_sanity():
    p = DemoProvider(seed=42)
    bars = p.fetch_history("EUR/USD", date.today() - timedelta(days=90), date.today())
    for b in bars:
        assert b.low > 0
        assert b.high >= max(b.open, b.close) - 1e-9
        assert b.low <= min(b.open, b.close) + 1e-9
        assert b.close > 0


def test_volatility_clustering_present():
    """Squared returns should be more autocorrelated than raw returns (clustering)."""
    p = DemoProvider(seed=42)
    bars = p.fetch_history("EUR/USD", date.today() - timedelta(days=800), date.today())
    closes = np.array([b.close for b in bars])
    rets = np.diff(np.log(closes))
    sq = rets**2
    autocorr_ret = abs(np.corrcoef(rets[:-1], rets[1:])[0, 1])
    autocorr_sq = abs(np.corrcoef(sq[:-1], sq[1:])[0, 1])
    assert autocorr_sq > autocorr_ret


def test_pairs_have_distinct_series():
    p = DemoProvider(seed=42)
    end = date.today()
    start = end - timedelta(days=40)
    a = [b.close for b in p.fetch_history("EUR/USD", start, end)]
    b = [b.close for b in p.fetch_history("GBP/USD", start, end)]
    assert a != b
