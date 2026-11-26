"""Stooq data provider (stooq.com — free daily CSV endpoint, no API key).

HONESTY NOTE
------------
Implemented from the documented Stooq CSV endpoint
(``https://stooq.com/q/d/l/?s=eurusd&i=d``). The build environment has NO
outbound access to stooq.com, so this provider is **unverified live** and
labeled as such in its capabilities. It is never selected automatically:
users must set ``DATA_PROVIDER=stooq`` explicitly. Stooq publishes free data
for personal/educational use; be respectful of rate limits
(``rate_limit_per_minute`` below). See docs/DATA_SOURCES.md.

Stooq provides daily OHLC (close-based adjustments vary); weekend/holiday
rows are absent (business-day cadence).
"""

from __future__ import annotations

import csv
import io
from datetime import date

from app.logging_config import get_logger
from app.services.data_providers.base import (
    DataProvider,
    PriceBarData,
    ProviderError,
    http_get_with_retries,
    to_utc_midnight,
)
from app.services.data_providers.capabilities import ProviderCapabilities

logger = get_logger(__name__)

STOOQ_URL = "https://stooq.com/q/d/l/"


class StooqProvider(DataProvider):
    """Daily FX bars from Stooq's public CSV endpoint."""

    name = "stooq"
    is_demo = False

    capabilities = ProviderCapabilities(
        name="stooq",
        pairs=("*",),
        intervals=("1d",),
        history_depth_days=None,
        rate_limit_per_minute=30,
        latency_typical_ms=400,
        license_notes=(
            "Stooq publishes free market data for personal/educational use; "
            "do not abuse rate limits. Verify current terms at stooq.com."
        ),
        requires_key=False,
        verified_live=False,
        is_demo=False,
    )

    def __init__(self, timeout: float = 15.0, retries: int = 3) -> None:
        self.timeout = timeout
        self.retries = retries

    # ------------------------------------------------------------------
    @staticmethod
    def _symbol(pair: str) -> str:
        parts = pair.upper().split("/")
        if len(parts) != 2 or len(parts[0]) != 3 or len(parts[1]) != 3:
            raise ProviderError(f"Invalid pair symbol: {pair!r}")
        return (parts[0] + parts[1]).lower()

    def fetch_history(self, pair: str, start: date, end: date) -> list[PriceBarData]:
        response = http_get_with_retries(
            STOOQ_URL,
            params={
                "s": self._symbol(pair),
                "d1": start.strftime("%Y%m%d"),
                "d2": end.strftime("%Y%m%d"),
                "i": "d",
            },
            timeout=self.timeout,
            retries=self.retries,
        )
        if response.status_code != 200:
            raise ProviderError(f"Stooq returned HTTP {response.status_code} for {pair}")
        text = response.text.strip()
        if not text or text.lower().startswith("no data"):
            raise ProviderError(f"Stooq returned no data for {pair}")
        try:
            reader = csv.DictReader(io.StringIO(text))
            bars: list[PriceBarData] = []
            for row in reader:
                day = date.fromisoformat(row["Date"])
                if day < start or day > end:
                    continue
                close = float(row["Close"])
                bars.append(
                    PriceBarData(
                        timestamp=to_utc_midnight(day),
                        open=float(row.get("Open") or close),
                        high=float(row.get("High") or close),
                        low=float(row.get("Low") or close),
                        close=close,
                        volume=float(row["Volume"]) if row.get("Volume") else None,
                    )
                )
        except (KeyError, ValueError) as exc:
            raise ProviderError(f"Stooq CSV parse error for {pair}: {exc}") from exc
        logger.info("Stooq: fetched %d bars for %s (%s..%s)", len(bars), pair, start, end)
        return bars
