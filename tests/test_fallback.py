"""Demo fallback behaviour when a real provider fails."""

from __future__ import annotations

from datetime import date, timedelta

from app.services.data_providers.base import (
    DataProvider,
    PriceBarData,
    ProviderError,
    to_utc_midnight,
)
from app.services.data_providers.demo import DemoProvider
from app.services.data_providers.factory import FallbackProvider, get_provider


class BrokenProvider(DataProvider):
    name = "broken"
    is_demo = False

    def fetch_history(self, pair, start, end):
        raise ProviderError("simulated network failure")


class WorkingProvider(DataProvider):
    name = "working"
    is_demo = False

    def fetch_history(self, pair, start, end):
        return [
            PriceBarData(
                timestamp=to_utc_midnight(date(2024, 1, 2)),
                open=1.0,
                high=1.1,
                low=0.9,
                close=1.05,
            )
        ]


def test_fallback_to_demo_on_failure():
    fb = FallbackProvider(BrokenProvider(), DemoProvider(seed=42))
    end = date.today()
    start = end - timedelta(days=10)
    bars = fb.fetch_history("EUR/USD", start, end)
    assert len(bars) > 0
    assert fb.fallback_used is True
    assert fb.last_source == "demo"
    assert fb.is_demo is True


def test_no_fallback_when_primary_works():
    fb = FallbackProvider(WorkingProvider(), DemoProvider(seed=42))
    bars = fb.fetch_history("EUR/USD", date(2024, 1, 1), date(2024, 1, 3))
    assert fb.fallback_used is False
    assert fb.last_source == "working"
    assert fb.is_demo is False
    assert bars[0].close == 1.05


def test_get_provider_demo_mode_returns_demo():
    class S:
        data_mode = "demo"
        data_provider = "frankfurter"
        fallback_to_demo = True
        frankfurter_base_url = "https://api.frankfurter.dev/v1"
        http_timeout_seconds = 5.0
        http_retries = 1
        demo_seed = 42

    p = get_provider(S())
    assert p.name == "demo"
    assert p.is_demo is True


def test_get_provider_live_mode_wraps_fallback_when_allowed():
    class S:
        data_mode = "live"
        data_provider = "frankfurter"
        fallback_to_demo = True
        frankfurter_base_url = "https://api.frankfurter.dev/v1"
        http_timeout_seconds = 5.0
        http_retries = 1
        demo_seed = 42

    p = get_provider(S())
    assert isinstance(p, FallbackProvider)


def test_get_provider_live_mode_strict():
    class S:
        data_mode = "live"
        data_provider = "frankfurter"
        fallback_to_demo = False
        frankfurter_base_url = "https://api.frankfurter.dev/v1"
        http_timeout_seconds = 5.0
        http_retries = 1
        demo_seed = 42

    p = get_provider(S())
    assert not isinstance(p, FallbackProvider)
    assert p.name == "frankfurter"
