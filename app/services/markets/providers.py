"""Market data sources for gold/dollar/Iran layer (addendum B).

SOURCING POLICY (non-negotiable):
* Every source is PROBED via ``scripts/verify_sources.py`` on a machine with
  internet; results (URL, auth, rate limits, history depth, update frequency,
  terms, status) land in docs/DATA_SOURCES.md. In the build sandbox these
  hosts are unreachable, so every source ships with ``verified_live=False``.
* NO scraping of sources that forbid it. Sources are API-first; where no
  legitimate public API exists (several Iran-market trackers), we provide a
  CSV/Excel import + manual-entry path and SAY SO honestly instead of
  scraping behind a ToS wall.
* Fail-soft: provider errors degrade to stale/"unavailable" badges — never
  silent fabrication. Rate limits: polite intervals + backoff (resilience
  helpers from the v2 data platform are reused where possible).
* Cache/demo is never shown as live: every quote carries
  (as_of, fetched_at, is_demo, verified_live).
"""

from __future__ import annotations

import csv
import io
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import ClassVar

import httpx

from app.services.markets.consensus import SourceQuote

USER_AGENT = "AWAGO/2.0 (research; polite; contact in README)"
MIN_POLL_SECONDS = 60.0  # never hammer a source


@dataclass
class SourceCapabilities:
    id: str
    url: str
    auth: str = "none"
    rate_limit: str = "unspecified — verify before production polling"
    history: str = "unspecified"
    update_frequency: str = "unspecified"
    terms: str = "check ToS before use"
    verified_live: bool = False
    status: str = "unverified in build environment"
    last_checked: str | None = None
    supports_csv_import: bool = False
    notes: str = ""


@dataclass
class FetchResult:
    ok: bool
    quotes: list[SourceQuote] = field(default_factory=list)
    error: str = ""
    fetched_at: str = ""
    detail: dict[str, object] = field(default_factory=dict)


class MarketSource:
    """Base class: probe() verifies reachability; fetch_last() pulls quotes."""

    capabilities: SourceCapabilities

    def __init__(self) -> None:
        self._last_call = 0.0

    def _throttle(self) -> None:
        dt = time.monotonic() - self._last_call
        if dt < MIN_POLL_SECONDS:
            time.sleep(min(2.0, MIN_POLL_SECONDS - dt))  # in-process courtesy only
        self._last_call = time.monotonic()

    def probe(self, client: httpx.Client) -> dict[str, object]:
        """Live-verification probe. Returns a record for DATA_SOURCES.md."""
        raise NotImplementedError

    def fetch_last(self, client: httpx.Client) -> FetchResult:
        raise NotImplementedError

    def import_csv(self, text: str) -> list[SourceQuote]:
        """CSV import path (columns: instrument,value,as_of)."""
        rows: list[SourceQuote] = []
        for rec in csv.DictReader(io.StringIO(text)):
            rows.append(
                SourceQuote(
                    source=self.capabilities.id,
                    value=float(rec["value"]),
                    as_of=str(rec["as_of"]),
                    verified_live=False,
                )
            )
        return rows


# ---------------------------------------------------------------- global ----
class MetalsDevSource(MarketSource):
    """metals.dev-style free gold/silver API (USD per ounce)."""

    capabilities = SourceCapabilities(
        id="metals_dev",
        url="https://api.metals.dev/v1/latest",
        auth="API key (free tier)",
        rate_limit="free tier — verify exact quota",
        history="limited on free tier — verify",
        update_frequency="minutes-level",
        terms="metals.dev terms — verify",
        supports_csv_import=True,
        notes="XAU/USD + XAG/USD spot in USD/oz.",
    )

    def probe(self, client: httpx.Client) -> dict[str, object]:
        try:
            r = client.get(self.capabilities.url, params={"api_key": "probe"}, timeout=15)
            self.capabilities.verified_live = r.status_code in (200, 401, 403)
            self.capabilities.status = (
                f"reachable (HTTP {r.status_code})"
                if r.status_code < 500
                else f"HTTP {r.status_code}"
            )
        except Exception as exc:
            self.capabilities.status = f"unreachable: {exc}"[:120]
            self.capabilities.verified_live = False
        self.capabilities.last_checked = datetime.now(timezone.utc).isoformat()
        return self.capabilities.__dict__.copy()

    def fetch_last(self, client: httpx.Client, api_key: str = "") -> FetchResult:
        self._throttle()
        now = datetime.now(timezone.utc).isoformat()
        try:
            r = client.get(self.capabilities.url, params={"api_key": api_key}, timeout=20)
            r.raise_for_status()
            js = r.json()
            metals = js.get("metals") or js.get("data") or {}
            quotes = [
                SourceQuote("metals_dev", float(metals["gold"]), now, True),
                SourceQuote("metals_dev", float(metals["silver"]), now, True),
            ]
            return FetchResult(True, quotes, fetched_at=now)
        except Exception as exc:
            return FetchResult(False, error=str(exc)[:200], fetched_at=now)


class FredSource(MarketSource):
    """FRED-style CSV endpoints for yields/oil/equity/vol drivers (public)."""

    capabilities = SourceCapabilities(
        id="fred",
        url="https://fred.stlouisfed.org/graph/fredgraph.csv",
        auth="API key for API; CSV endpoint public",
        rate_limit="be polite — daily cadence sufficient",
        history="decades (series-dependent)",
        update_frequency="daily",
        terms="FRED terms of use — verify",
        notes="Series: DGS10/DFII10 (yields), DCOILBRENTEU/DCOILWTICO (oil), SP500, VIXCLS.",
    )

    SERIES: ClassVar[dict[str, str]] = {
        "US10Y_NOMINAL": "DGS10",
        "US10Y_REAL": "DFII10",
        "BRENT": "DCOILBRENTEU",
        "WTI": "DCOILWTICO",
        "SP500": "SP500",
        "VIX": "VIXCLS",
    }

    def probe(self, client: httpx.Client) -> dict[str, object]:
        try:
            r = client.get(self.capabilities.url, params={"id": "DGS10"}, timeout=15)
            self.capabilities.verified_live = r.status_code == 200
            self.capabilities.status = f"reachable (HTTP {r.status_code})"
        except Exception as exc:
            self.capabilities.status = f"unreachable: {exc}"[:120]
        self.capabilities.last_checked = datetime.now(timezone.utc).isoformat()
        return self.capabilities.__dict__.copy()

    def fetch_last(self, client: httpx.Client) -> FetchResult:
        self._throttle()
        now = datetime.now(timezone.utc).isoformat()
        quotes: list[SourceQuote] = []
        try:
            for instrument, sid in self.SERIES.items():
                r = client.get(self.capabilities.url, params={"id": sid}, timeout=20)
                r.raise_for_status()
                rows = list(csv.DictReader(io.StringIO(r.text)))
                last = next(
                    (row for row in reversed(rows) if row.get(sid) not in (None, "", ".")), None
                )
                if last:
                    val = float(last[sid])
                    d = last.get("DATE") or last.get("observation_date") or now
                    quotes.append(SourceQuote(f"fred:{instrument}", val, str(d), True))
            return FetchResult(
                bool(quotes), quotes, fetched_at=now, error="" if quotes else "no rows"
            )
        except Exception as exc:
            return FetchResult(False, quotes, error=str(exc)[:200], fetched_at=now)


class FrankfurterSource(MarketSource):
    """Existing v2 FX provider reused for USD basket rates."""

    capabilities = SourceCapabilities(
        id="frankfurter",
        url="https://api.frankfurter.dev/v1/latest",
        auth="none",
        rate_limit="undocumented — daily polling safe",
        history="ECB reference rates since 1999 (close only)",
        update_frequency="daily (ECB working days)",
        terms="free, no key; ECB data — attribution",
        status="implemented; unreachable from build sandbox",
    )

    def probe(self, client: httpx.Client) -> dict[str, object]:
        try:
            r = client.get(self.capabilities.url, timeout=15)
            self.capabilities.verified_live = r.status_code == 200
            self.capabilities.status = f"reachable (HTTP {r.status_code})"
        except Exception as exc:
            self.capabilities.status = f"unreachable: {exc}"[:120]
        self.capabilities.last_checked = datetime.now(timezone.utc).isoformat()
        return self.capabilities.__dict__.copy()

    def fetch_last(self, client: httpx.Client) -> FetchResult:
        self._throttle()
        now = datetime.now(timezone.utc).isoformat()
        try:
            r = client.get(self.capabilities.url, params={"base": "USD"}, timeout=20)
            r.raise_for_status()
            rates = r.json().get("rates", {})
            quotes = [
                SourceQuote(f"frankfurter:{k}", float(v), now, True) for k, v in rates.items()
            ]
            return FetchResult(True, quotes, fetched_at=now)
        except Exception as exc:
            return FetchResult(False, error=str(exc)[:200], fetched_at=now)


# ------------------------------------------------------------------ Iran ----
class IranApiSource(MarketSource):
    """Generic Iran market price API (tgju/bonbast-style JSON APIs).

    The concrete hosts change often and many forbid scraping; this source
    targets *API-style JSON endpoints* only (configurable base URL). If a
    given tracker has no legitimate API, use the CSV/manual path — we do NOT
    scrape HTML behind a ToS wall.
    """

    capabilities = SourceCapabilities(
        id="iran_market_api",
        url="(configurable) e.g. a public JSON endpoint of a market tracker",
        auth="varies",
        rate_limit="verify per host; poll >= 5 min",
        history="varies — verify",
        update_frequency="minutes-level during market hours",
        terms="CHECK ToS of the concrete host — many forbid automated access",
        supports_csv_import=True,
        notes="Unofficial market quotes (always labelled). CSV/Excel/manual import "
        "is the fallback when no legitimate API exists.",
    )

    def probe(self, client: httpx.Client) -> dict[str, object]:
        self.capabilities.status = "no default host — configure + verify before use"
        self.capabilities.last_checked = datetime.now(timezone.utc).isoformat()
        return self.capabilities.__dict__.copy()

    def fetch_last(self, client: httpx.Client, base_url: str = "", token: str = "") -> FetchResult:
        if not base_url:
            return FetchResult(False, error="no host configured — use CSV/manual import")
        self._throttle()
        now = datetime.now(timezone.utc).isoformat()
        try:
            headers = {"User-Agent": USER_AGENT}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            r = client.get(base_url, headers=headers, timeout=20)
            r.raise_for_status()
            js = r.json()
            items = js if isinstance(js, list) else js.get("data", [])
            quotes = [
                SourceQuote("iran_market_api", float(it["value"]), str(it.get("as_of", now)), True)
                for it in items
                if "value" in it
            ]
            return FetchResult(bool(quotes), quotes, fetched_at=now)
        except Exception as exc:
            return FetchResult(False, error=str(exc)[:200], fetched_at=now)


class CryptoExchangeIRTSource(MarketSource):
    """USDT/IRT from a legitimate crypto exchange public ticker API.

    Configure ``base_url`` to the chosen exchange's public ticker. Many
    Iranian exchanges block non-IR IPs — the probe records reachability
    honestly instead of fabricating quotes.
    """

    capabilities = SourceCapabilities(
        id="crypto_exchange_irt",
        url="(configurable) exchange public ticker API",
        auth="none for public ticker",
        rate_limit="per-exchange — verify; poll >= 1 min",
        history="ticker only — snapshot history via forward snapshots",
        update_frequency="seconds-level",
        terms="per-exchange",
        supports_csv_import=True,
        notes="USDT/IRT (toman). Unofficial market quote label applies.",
    )

    def probe(self, client: httpx.Client) -> dict[str, object]:
        self.capabilities.status = "no default exchange — configure + verify before use"
        self.capabilities.last_checked = datetime.now(timezone.utc).isoformat()
        return self.capabilities.__dict__.copy()

    def fetch_last(self, client: httpx.Client, base_url: str = "") -> FetchResult:
        if not base_url:
            return FetchResult(False, error="no exchange configured — use CSV/manual import")
        self._throttle()
        now = datetime.now(timezone.utc).isoformat()
        try:
            r = client.get(base_url, headers={"User-Agent": USER_AGENT}, timeout=20)
            r.raise_for_status()
            js = r.json()
            val = float(js.get("price") or js.get("last") or js["data"]["price"])
            return FetchResult(
                True, [SourceQuote("crypto_exchange_irt", val, now, True)], fetched_at=now
            )
        except Exception as exc:
            return FetchResult(False, error=str(exc)[:200], fetched_at=now)


ALL_SOURCES: list[MarketSource] = [
    MetalsDevSource(),
    FredSource(),
    FrankfurterSource(),
    IranApiSource(),
    CryptoExchangeIRTSource(),
]
