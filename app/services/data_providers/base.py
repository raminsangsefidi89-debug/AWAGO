"""Abstract data-provider layer and shared HTTP retry helpers."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, timezone

import httpx

from app.logging_config import get_logger

logger = get_logger(__name__)


class ProviderError(RuntimeError):
    """Raised when a data provider cannot deliver data."""


@dataclass
class PriceBarData:
    """One daily OHLC bar returned by a provider."""

    timestamp: datetime  # UTC midnight of the trading day
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None

    @property
    def day(self) -> date:
        return self.timestamp.date()


def to_utc_midnight(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


class DataProvider(ABC):
    """Interface every market-data provider must implement."""

    name: str = "abstract"
    is_demo: bool = False

    @abstractmethod
    def fetch_history(self, pair: str, start: date, end: date) -> list[PriceBarData]:
        """Return daily bars for ``pair`` in [start, end] (inclusive)."""

    def fetch_latest(self, pair: str) -> PriceBarData | None:
        """Return the most recent bar, or None. Default: use fetch_history."""
        bars = self.fetch_history(
            pair, end=date.today(), start=date.fromordinal(date.today().toordinal() - 10)
        )
        return bars[-1] if bars else None


def http_get_with_retries(
    url: str,
    *,
    params: dict | None = None,
    timeout: float = 15.0,
    retries: int = 3,
) -> httpx.Response:
    """GET with exponential backoff on network errors / 429 / 5xx.

    Raises ProviderError when all attempts fail.
    """
    last_error: str = ""
    for attempt in range(max(1, retries)):
        try:
            response = httpx.get(url, params=params, timeout=timeout, follow_redirects=True)
            if response.status_code == 429 or response.status_code >= 500:
                last_error = f"HTTP {response.status_code}"
            else:
                return response
        except httpx.HTTPError as exc:
            last_error = str(exc)
        if attempt < retries - 1:
            wait = 2**attempt
            logger.warning("HTTP GET %s failed (%s), retrying in %ss", url, last_error, wait)
            time.sleep(wait)
    raise ProviderError(f"Request to {url} failed after {retries} attempts: {last_error}")
