"""Provider factory with documented Demo fallback behaviour."""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from app.config import Settings
from app.logging_config import get_logger
from app.services.data_providers.base import DataProvider, PriceBarData, ProviderError
from app.services.data_providers.demo import DemoProvider
from app.services.data_providers.frankfurter import FrankfurterProvider

logger = get_logger(__name__)


class FallbackProvider(DataProvider):
    """Wraps a real provider and transparently falls back to Demo data.

    ``fallback_used`` reports whether the most recent call fell back, and
    ``last_source`` names the provider that actually supplied the data, so
    callers can label stored bars truthfully.
    """

    name = "fallback"

    def __init__(self, primary: DataProvider, fallback: DataProvider) -> None:
        self.primary = primary
        self.fallback = fallback
        self.fallback_used = False
        self.last_source: str = primary.name

    @property
    def is_demo(self) -> bool:  # type: ignore[override]
        return self.last_source == self.fallback.name

    def _do(self, fn_name: str, *args, **kwargs):
        try:
            result = getattr(self.primary, fn_name)(*args, **kwargs)
            self.fallback_used = False
            self.last_source = self.primary.name
            return result
        except Exception as exc:  # noqa: BLE001 — deliberate: any provider failure triggers fallback
            logger.warning("%s failed (%s); falling back to demo data", self.primary.name, exc)
            self.fallback_used = True
            self.last_source = self.fallback.name
            return getattr(self.fallback, fn_name)(*args, **kwargs)

    def fetch_history(self, pair: str, start: date, end: date) -> List[PriceBarData]:
        return self._do("fetch_history", pair, start, end)

    def fetch_latest(self, pair: str) -> Optional[PriceBarData]:
        return self._do("fetch_latest", pair)


def build_real_provider(settings: Settings) -> DataProvider:
    """Build the configured real provider (currently: Frankfurter)."""
    if settings.data_provider == "frankfurter":
        return FrankfurterProvider(
            base_url=settings.frankfurter_base_url,
            timeout=settings.http_timeout_seconds,
            retries=settings.http_retries,
        )
    raise ProviderError(f"Unknown real provider: {settings.data_provider!r}")


def get_provider(settings: Settings) -> DataProvider:
    """Return the provider for the configured DATA_MODE.

    - ``demo``: always the deterministic Demo provider.
    - ``live``: real provider only (raises ProviderError if unreachable,
      unless FALLBACK_TO_DEMO=true, which wraps it in FallbackProvider).
    - ``auto``: real provider with transparent Demo fallback.
    """
    demo = DemoProvider(seed=settings.demo_seed)

    if settings.data_mode == "demo":
        return demo

    real = build_real_provider(settings)

    if settings.data_mode == "auto" or settings.fallback_to_demo:
        return FallbackProvider(real, demo)

    return real
