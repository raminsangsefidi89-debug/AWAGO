# AWAGO Data Sources

> **Honesty note.** The build environment has no outbound access to market-data
> hosts (only github/npm/pypi). Every remote provider below is implemented from
> its documented API but labeled **"unverified live"** — it was never called
> successfully from the build machine. Before relying on one, set
> `DATA_MODE=live`, run `GET /api/v1/providers` (the `health` block), and
> confirm `reachable: true` on your own network. The default `DATA_MODE=demo`
> uses deterministic synthetic data and is clearly labeled everywhere in the
> UI and API.

## Implemented providers

| Provider | Type | Key | Interval | License / terms | Verified live in build env | Notes |
|---|---|---|---|---|---|---|
| `demo` | synthetic (seeded) | none | 1d | generated locally | **yes** (local) | Deterministic geometric random walk per pair. Clearly labeled "demo". Default mode. |
| `frankfurter` | ECB reference rates via frankfurter.dev | none | 1d (business days) | free service, ECB data (ECB reference rates are free for reuse with attribution) | **no** | Close-only ECB daily reference rates; business-day cadence. Provider of choice for real EUR-cross data. |
| `stooq` | stooq.com daily CSV endpoint | none | 1d | stooq.com publishes free data for personal/educational use — respect rate limits and re-check their terms | **no** | Daily OHLC, business days. Rate limit declared 30 req/min in capabilities. |
| `csv_import` | local files (`data/imports/*.csv`) | none | 1d | user-supplied — user is responsible for rights/provenance | **yes** (local) | **The sanctioned path for IRR / any rate without a legitimate API.** Columns: `date,open,high,low,close[,volume]`; file named `EURUSD.csv` etc. |

### Why no scraping for IRR

Iran-market (IRR) rates have no free, legitimate machine API that we could
verify. Rather than scrape sites whose terms forbid it, AWAGO supports
**user-supplied CSV import** with full provenance (`data_source='csv_import'`,
`fetched_at`, `dataset_version`). You provide the file; the app stores,
validates (OHLC sanity, outliers via Hampel, gap/staleness checks) and charts
it exactly like provider data — while always labeling its source.

## Evaluated but NOT implemented

| Source | Why not |
|---|---|
| **FRED (Federal Reserve)** | Requires an API key; keys cannot be provisioned or verified from the build environment. Excellent candidate once you add `FRED_API_KEY` — we would implement it as a keyed provider (macro/US-rate series, with publication-lag metadata). |
| **Alpha Vantage** | Requires API key + rate limits (25 req/day free tier) too tight for 10 pairs × 3 years. |
| **Twelve Data** | Requires API key; free tier 800 req/day. Same keyed-provider path as FRED. |
| **Yahoo Finance (unofficial)** | No official API; terms murky. Rejected on legitimacy grounds. |
| **Any web scraping of broker/exchange sites** | Almost always violates ToS. Rejected outright. |

## Demo vs real — schema-level separation

`price_bars` carries `is_demo` and `data_source`, with a **CHECK constraint**
`is_demo = (data_source = 'demo')` enforced in the database (migration 0002).
Demo and real rows can never masquerade as each other; the UI badges and API
responses read these columns directly.

## Per-bar provenance

Every stored bar records:

* `data_source` — which provider produced it (`demo`, `frankfurter`, `stooq`, `csv_import`)
* `fetched_at` — when it was ingested
* `dataset_version` — provider + ingest date (used for reproducibility snapshots)
* `quality_flag` — `ok` / `suspect` / `bad` from the quality engine

Series are mirrored to Parquet under `data/series/PAR__SOURCE.parquet` for fast
bulk queries (DuckDB when installed, else pandas).

## Data quality engine

`GET /api/v1/quality/{PAIR}?refresh=true` runs and stores a report:

* **Gaps** — missing expected trading days (cadence inferred: business vs calendar)
* **Staleness** — newest bar older than 3 days
* **Outliers** — Hampel robust z-score on log returns
* **OHLC sanity** — positive prices, high ≥ max(open, close), low ≤ min(open, close)
* **Triangular cross-rate consistency** — EUR/USD ≈ GBP/USD × EUR/GBP, **only for real, same-source legs** (independent synthetic walks make the check meaningless on demo data; the report says "not applicable")

## API keys

Only via `.env` (never in code or git): `FRED_API_KEY`, `ALPHA_VANTAGE_KEY`,
`TWELVE_DATA_API_KEY` are reserved names for future keyed providers.
