"""Provider registry and factory with documented Demo fallback behaviour.

Backward compatible with v1: ``get_provider(settings)`` keeps its exact
semantics (demo / live / auto + fallback flag). v2 adds a registry with
capability declarations and a resilience wrapper.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timezone
from typing import Any

from app.config import Settings
from app.logging_config import get_logger
from app.services.data_providers.base import DataProvider, PriceBarData, ProviderError
from app.services.data_providers.capabilities import ProviderCapabilities, ProviderHealth
from app.services.data_providers.csv_import import CSVImportProvider
from app.services.data_providers.demo import DemoProvider
from app.services.data_providers.frankfurter import FrankfurterProvider
from app.services.data_providers.resilience import CircuitBreaker, CircuitOpenError, TTLCache
from app.services.data_providers.stooq import StooqProvider

logger = get_logger(__name__)


# ----------------------------------------------------------------------
# Resilience wrapper
# ----------------------------------------------------------------------


class ResilientProvider(DataProvider):
    """Wraps a provider with a circuit breaker and a TTL cache.

    Failures open the circuit (admitting no calls until the reset window
    passes); successful calls serve from cache within ``cache_ttl_seconds``.
    """

    def __init__(
        self,
        inner: DataProvider,
        *,
        cache_ttl_seconds: float = 900.0,
        failure_threshold: int = 3,
        reset_seconds: float = 60.0,
    ) -> None:
        self.inner = inner
        self.name = inner.name
        self.is_demo = inner.is_demo
        self.capabilities = getattr(inner, "capabilities", None)
        self._cache = TTLCache(ttl_seconds=cache_ttl_seconds)
        self._breaker = CircuitBreaker(
            failure_threshold=failure_threshold, reset_seconds=reset_seconds
        )

    @property
    def circuit_state(self) -> str:
        return self._breaker.state

    def fetch_history(self, pair: str, start: date, end: date) -> list[PriceBarData]:
        key = (pair, start.isoformat(), end.isoformat())
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        if not self._breaker.allow():
            raise CircuitOpenError(
                f"Provider '{self.name}' circuit is open (recent failures); try again later."
            )
        try:
            bars = self.inner.fetch_history(pair, start, end)
        except Exception:
            self._breaker.record_failure()
            raise
        self._breaker.record_success()
        self._cache.set(key, bars)
        return bars

    def fetch_latest(self, pair: str) -> PriceBarData | None:
        return self.inner.fetch_latest(pair)

    def health(self) -> ProviderHealth:
        started = time.monotonic()
        now = datetime.now(timezone.utc)
        try:
            end = date.today()
            start = date.fromordinal(end.toordinal() - 10)
            self.inner.fetch_history("EUR/USD", start, end)
            return ProviderHealth(
                name=self.name,
                reachable=True,
                checked_at=now,
                latency_ms=(time.monotonic() - started) * 1000.0,
                circuit_state=self._breaker.state,
            )
        except Exception as exc:
            return ProviderHealth(
                name=self.name,
                reachable=False,
                checked_at=now,
                latency_ms=(time.monotonic() - started) * 1000.0,
                detail=str(exc)[:200],
                circuit_state=self._breaker.state,
            )


# ----------------------------------------------------------------------
# Fallback wrapper (v1 behaviour preserved)
# ----------------------------------------------------------------------


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
        except Exception as exc:
            logger.warning("%s failed (%s); falling back to demo data", self.primary.name, exc)
            self.fallback_used = True
            self.last_source = self.fallback.name
            return getattr(self.fallback, fn_name)(*args, **kwargs)

    def fetch_history(self, pair: str, start: date, end: date) -> list[PriceBarData]:
        return self._do("fetch_history", pair, start, end)

    def fetch_latest(self, pair: str) -> PriceBarData | None:
        return self._do("fetch_latest", pair)


# ----------------------------------------------------------------------
# Registry
# ----------------------------------------------------------------------


def _demo_capabilities() -> ProviderCapabilities:
    return ProviderCapabilities(
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


PROVIDER_REGISTRY: dict[str, Any] = {
    "demo": DemoProvider,
    "frankfurter": FrankfurterProvider,
    "stooq": StooqProvider,
    "csv_import": CSVImportProvider,
}


def all_capabilities() -> list[dict]:
    """Capability declarations for every registered provider."""
    caps = [
        _demo_capabilities(),
        FrankfurterProvider.capabilities,
        StooqProvider.capabilities,
        CSVImportProvider.capabilities,
    ]
    return [c.as_dict() for c in caps]


def build_real_provider(settings: Any) -> DataProvider:
    """Build the configured real provider by name from the registry."""
    name = getattr(settings, "data_provider", "frankfurter")
    timeout = getattr(settings, "http_timeout_seconds", 15.0)
    retries = getattr(settings, "http_retries", 3)
    if name == "frankfurter":
        return FrankfurterProvider(
            base_url=getattr(settings, "frankfurter_base_url", "https://api.frankfurter.dev/v1"),
            timeout=timeout,
            retries=retries,
        )
    if name == "stooq":
        return StooqProvider(timeout=timeout, retries=retries)
    if name == "csv_import":
        import os
        from pathlib import Path

        from app.config import DATA_DIR

        import_dir = getattr(settings, "csv_import_dir", None) or str(DATA_DIR / "imports")
        return CSVImportProvider(
            Path(os.path.expanduser(import_dir)), timeout=timeout, retries=retries
        )
    if name == "demo":
        return DemoProvider(seed=getattr(settings, "demo_seed", 42))
    raise ProviderError(f"Unknown data provider: {name!r}")


def get_provider(settings: Settings) -> DataProvider:
    """Return the provider for the configured DATA_MODE (v1 semantics kept).

    - ``demo``: always the deterministic Demo provider.
    - ``live``: real provider only (raises ProviderError if unreachable,
      unless FALLBACK_TO_DEMO=true, which wraps it in FallbackProvider).
    - ``auto``: real provider with transparent Demo fallback.

    Real providers are additionally wrapped in :class:`ResilientProvider`
    (circuit breaker + TTL cache).
    """
    demo = DemoProvider(seed=getattr(settings, "demo_seed", 42))

    if getattr(settings, "data_mode", "demo") == "demo":
        return demo

    real: DataProvider = build_real_provider(settings)
    real = ResilientProvider(
        real,
        cache_ttl_seconds=getattr(settings, "provider_cache_ttl_seconds", 900.0),
        failure_threshold=getattr(settings, "circuit_breaker_failures", 3),
        reset_seconds=getattr(settings, "circuit_breaker_reset_seconds", 60.0),
    )

    if getattr(settings, "data_mode", "auto") == "auto" or getattr(
        settings, "fallback_to_demo", True
    ):
        return FallbackProvider(real, demo)

    return real


def provider_health(settings: Settings) -> list[dict]:
    """Health-check every registered provider (never raises)."""
    results = []
    for name in PROVIDER_REGISTRY:
        try:
            provider = ResilientProvider(build_real_provider_for(name, settings))
            results.append(provider.health().as_dict())
        except Exception as exc:
            results.append({"name": name, "reachable": False, "detail": str(exc)[:200]})
    return results


def build_real_provider_for(name: str, settings: Any) -> DataProvider:
    shim: Any = {"data_provider": name}
    for attr in (
        "http_timeout_seconds",
        "http_retries",
        "frankfurter_base_url",
        "demo_seed",
        "csv_import_dir",
    ):
        shim[attr] = getattr(settings, attr, None)

    class _Namespace:
        def __init__(self, values: Any) -> None:
            self.__dict__.update(values)

    return build_real_provider(_Namespace(shim))
