"""User-provided CSV import provider.

The sanctioned path for market data with no legitimate API (for example
Iran-market / IRR rates): the user drops CSV files into the import directory
(``data/imports`` by default) and AWAGO ingests them with full provenance
(``data_source='csv_import'``). We never scrape sources that forbid it.

Expected file naming: ``EURUSD.csv`` / ``EUR_USD.csv`` / ``EUR-USD.csv``.
Expected columns (header row required, case-insensitive):
    date, open, high, low, close   (open/high/low optional -> set to close)
    optional: volume

Dates are ISO ``YYYY-MM-DD``. Rows are validated (positive prices,
high >= max(open, close) etc.); invalid rows are skipped and reported in
the quality flag of the ingestion summary.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from app.logging_config import get_logger
from app.services.data_providers.base import (
    DataProvider,
    PriceBarData,
    ProviderError,
    to_utc_midnight,
)
from app.services.data_providers.capabilities import ProviderCapabilities

logger = get_logger(__name__)


class CSVImportProvider(DataProvider):
    """Reads locally imported CSV files; always available offline."""

    name = "csv_import"
    is_demo = False

    capabilities = ProviderCapabilities(
        name="csv_import",
        pairs=("*",),
        intervals=("1d",),
        history_depth_days=None,
        rate_limit_per_minute=None,
        latency_typical_ms=1,
        license_notes="User-supplied data; the user is responsible for its provenance and rights.",
        requires_key=False,
        verified_live=True,  # local file reads are verifiable by definition
        is_demo=False,
    )

    def __init__(self, import_dir: str | Path, timeout: float = 15.0, retries: int = 3) -> None:
        self.import_dir = Path(import_dir)
        self.timeout = timeout  # unused (local reads) — kept for interface parity
        self.retries = retries

    # ------------------------------------------------------------------
    def _find_file(self, pair: str) -> Path | None:
        slug_variants = [
            pair.replace("/", "").upper(),
            pair.replace("/", "_").upper(),
            pair.replace("/", "-").upper(),
            pair.upper(),
        ]
        if not self.import_dir.exists():
            return None
        for path in sorted(self.import_dir.glob("*.csv")):
            if path.stem.upper() in slug_variants:
                return path
        return None

    def fetch_history(self, pair: str, start: date, end: date) -> list[PriceBarData]:
        path = self._find_file(pair)
        if path is None:
            raise ProviderError(
                f"No CSV file for {pair} in {self.import_dir}. "
                f"Expected one of: {pair.replace('/', '').upper()}.csv, ..."
            )
        bars: list[PriceBarData] = []
        skipped = 0
        with path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                raise ProviderError(f"CSV file has no header: {path}")
            cols = {c.strip().lower(): c for c in reader.fieldnames}
            if "date" not in cols or "close" not in cols:
                raise ProviderError(f"CSV must contain at least 'date' and 'close' columns: {path}")
            for row in reader:
                try:
                    day = date.fromisoformat(row[cols["date"]].strip())
                    close = float(row[cols["close"]])
                    open_ = (
                        float(row[cols["open"]])
                        if "open" in cols and row.get(cols["open"])
                        else close
                    )
                    high = (
                        float(row[cols["high"]])
                        if "high" in cols and row.get(cols["high"])
                        else max(open_, close)
                    )
                    low = (
                        float(row[cols["low"]])
                        if "low" in cols and row.get(cols["low"])
                        else min(open_, close)
                    )
                    volume = (
                        float(row[cols["volume"]])
                        if "volume" in cols and row.get(cols["volume"])
                        else None
                    )
                    if (
                        close <= 0
                        or low <= 0
                        or high < max(open_, close) - 1e-9
                        or low > min(open_, close) + 1e-9
                    ):
                        skipped += 1
                        continue
                except (ValueError, KeyError):
                    skipped += 1
                    continue
                if day < start or day > end:
                    continue
                bars.append(
                    PriceBarData(
                        timestamp=to_utc_midnight(day),
                        open=open_,
                        high=high,
                        low=low,
                        close=close,
                        volume=volume,
                    )
                )
        if skipped:
            logger.warning("CSV import %s: skipped %d invalid rows", path.name, skipped)
        logger.info("CSV import: %d bars for %s from %s", len(bars), pair, path.name)
        return bars
