"""Frankfurter data provider (frankfurter.dev — free ECB reference rates).

IMPORTANT / HONESTY NOTE
------------------------
This provider is implemented from the publicly documented Frankfurter API
(ECB daily reference rates, no API key required). The build environment for
this project has NO outbound internet access to frankfurter.dev, so the live
endpoint could NOT be verified here. The application therefore defaults to
``DATA_MODE=demo``; switching to live data is documented in the README and
falls back to Demo data if the request fails (when FALLBACK_TO_DEMO=true).

Frankfurter provides daily *close-only* rates on TARGET business days.
Bars are stored with open=high=low=close; the ATR formula then naturally
degrades to a smoothed close-to-close range. Weekends/holidays are absent.
"""

from __future__ import annotations

from datetime import date
from typing import List

from app.logging_config import get_logger
from app.services.data_providers.base import (
    DataProvider,
    PriceBarData,
    ProviderError,
    http_get_with_retries,
    to_utc_midnight,
)

logger = get_logger(__name__)


class FrankfurterProvider(DataProvider):
    """Real data provider backed by the Frankfurter API (ECB rates)."""

    name = "frankfurter"
    is_demo = False

    def __init__(
        self,
        base_url: str = "https://api.frankfurter.dev/v1",
        timeout: float = 15.0,
        retries: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries

    # ------------------------------------------------------------------
    def _split_pair(self, pair: str) -> tuple[str, str]:
        parts = pair.upper().split("/")
        if len(parts) != 2 or len(parts[0]) != 3 or len(parts[1]) != 3:
            raise ProviderError(f"Invalid pair symbol: {pair!r} (expected BASE/QUOTE)")
        return parts[0], parts[1]

    def fetch_history(self, pair: str, start: date, end: date) -> List[PriceBarData]:
        base, quote = self._split_pair(pair)
        if end < start:
            return []
        url = f"{self.base_url}/{start.isoformat()}..{end.isoformat()}"
        response = http_get_with_retries(
            url,
            params={"base": base, "symbols": quote},
            timeout=self.timeout,
            retries=self.retries,
        )
        if response.status_code != 200:
            raise ProviderError(
                f"Frankfurter returned HTTP {response.status_code} for {pair}: {response.text[:200]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError(f"Frankfurter returned invalid JSON for {pair}") from exc

        rates = payload.get("rates") or {}
        bars: List[PriceBarData] = []
        for day_str, quote_map in sorted(rates.items()):
            if quote not in quote_map:
                continue
            close = float(quote_map[quote])
            if close <= 0:
                continue
            day = date.fromisoformat(day_str)
            bars.append(
                PriceBarData(
                    timestamp=to_utc_midnight(day),
                    open=close,
                    high=close,
                    low=close,
                    close=close,
                    volume=None,
                )
            )
        logger.info("Frankfurter: fetched %d bars for %s (%s..%s)", len(bars), pair, start, end)
        return bars
