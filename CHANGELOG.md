# Changelog

## 2.1.0 (2026-11-26) — Gold/USD market + news intelligence (addendum)

### Added — market layer
- `app/services/units.py`: single tested unit utility (rial/toman ×10,
  troy-oz/gram ×31.1035, 18k purity 0.750, Emami coin 8.136 g @900 = 7.3224 g
  fine); explicit unit pair on every series.
- `app/services/calendar_iran.py`: Tehran UTC+3:30, Thu/Fri weekend,
  fixed Jalali holidays + curated lunar-holiday file, expected trading days.
- Instruments registry (XAU/USD, USD basket ×6 + computed dollar-index-style
  basket, drivers: real/nominal yields, Brent/WTI, S&P500, VIX, silver, BTC;
  Iran: USD/IRR free+official, 18k gram, Emami/half/quarter coin, USDT/IRT);
  `MARKET_GLOBAL_ENABLED`/`MARKET_IRAN_ENABLED`; Iran quotes always labelled
  unofficial market quotes.
- Derived series (formula-documented + unit-tested): implied global gram IRR,
  18k value, coin intrinsic + bubble (abs/%), USD free/official gap (abs/%),
  cross-market consistency → quality warnings (never auto-corrected).
- Multi-source consensus (median + MAD outlier rejection) with per-source
  values and disagreement % always exposed.
- Source verification script `scripts/verify_sources.py` → appends honest
  probed rows to docs/DATA_SOURCES.md (market sources + news feeds). All
  remote sources `verified_live=False` in the build sandbox (recorded).
- CSV/Excel import + manual-entry fallback where no legitimate API exists.

### Added — news intelligence
- RSS/Atom fetcher: ETag/If-Modified-Since, ≥15-min polite polling,
  exponential backoff, fail-soft; title/source/url/published+fetch/lang/
  snippet + link-back only.
- Persian normalization (variants, ZWNJ, digits), shingle-Jaccard dedup +
  thread clustering, rules-first FA/EN topic tags, inspectable lexicon
  sentiment (`lexicon-fa-en/1`, name+version persisted).
- Reliability tiers + rumor/unattributed flags; no complete-coverage claims
  (active sources + last fetch shown).
- Point-in-time news features (available_at = max(published, fetched)):
  1h/6h/24h/7d counts, net sentiment, surprise index — leakage-tested.
- Rule-based event extraction (confidence) + event studies (windows, CIs,
  sample sizes, no causal claims).
- News-value test: with-vs-without-news walk-forward + Diebold-Mariano →
  honest verdict panel (including "no significant difference").

### Added — drivers & dashboard
- Rolling correlations, lead-lag (spurious-correlation caution), regime
  dependence, permutation importance.
- New RTL pages: «طلا و دلار» (global|Iran side-by-side, derived table with
  formulas, toman/rial toggle, freshness + disagreement + stale badges),
  «اخبار» (feed + value verdict), «محرک‌ها».
- Migration 0003: market_quotes, market_snapshots, news_items, news_events,
  source_registry.

## 2.0.0 (2026-11-26)

Research-grade evolution of AWAGO: probabilistic forecasting platform with
statistical honesty guarantees.

### Added — data layer
- Provider capabilities registry + health checks; retries with exponential
  backoff + full jitter; circuit breaker; TTL cache.
- New providers: `stooq` (unverified live), `csv_import` (user files — the
  sanctioned IRR path). FRED/AlphaVantage/TwelveData documented as
  evaluated-not-implemented.
- Data-quality engine (gaps + cadence inference, staleness, Hampel outliers,
  OHLC validation, triangular cross-rate for real legs) + stored reports
  (`quality_reports`) + API/UI.
- Per-bar provenance (`fetched_at`, `dataset_version`, `quality_flag`);
  schema-level demo/real CHECK constraint (migration 0002).
- Parquet series mirrors (`data/series/`) with DuckDB-or-pandas querying.
- Job cancellation + resource guards; thread scheduler (disabled by default);
  CSV/Parquet export.

### Added — modeling
- Versioned feature store (`FEATURE_SET_VERSION = "3"`), point-in-time by
  construction: returns, realized volatility (close-close/Parkinson/
  Garman-Klass), momentum, mean-reversion z-scores, RSI/MACD/Bollinger/ATR,
  slopes, skew/kurtosis, drawdown, calendar, cross-pair (USD factor,
  relative strength, rolling correlation).
- Leakage-audit harness (perturb-future + suspicious-correlation), negative-
  tested.
- Model plugin registry + one walk-forward harness: baselines, ARIMA, GARCH
  (optional), classical ML (direct + recursive), MLP, ensembles, quantile
  regression + split/CQR/adaptive conformal with empirical-vs-nominal
  coverage.
- Purged walk-forward evaluation (expanding/rolling + embargo), DM-Harvey +
  Holm significance testing, holdout-once-per-family, stability breakdowns,
  simulated backtests with costs/slippage + random-signal control.
- Model lifecycle: artifacts with run/config/snapshot hashes,
  champion/challenger with paired-bootstrap significance, audit trail.

### Added — presentation
- Persian RTL dashboard v2: 9-page vanilla-ES-module SPA (no build step),
  honesty badges, fan charts with measured coverage, Jalali dates (tested
  converter) + Persian digits, dark/light, keyboard+ARIA, reduced motion,
  skeletons, deep links, local preferences.
- New typed API: experiments, leaderboards, registry, regimes, volatility,
  probabilistic forecasts, backtests, explainability, drift, reports; SSE
  job stream; per-IP rate limiting; ETag/304 caching; closed CORS.
- Persian RTL print report generated strictly from stored artifacts.
- 10/10 images generated (retry campaign); manifest + prompts recorded.

### Changed
- Alembic migrations replace ad-hoc `create_all` (v1 databases are stamped
  and upgraded losslessly — tested).
- Structured logging with correlation IDs; domain-typed configuration with
  `config show` (redacted); reproducibility utilities (seed/config/snapshot
  hashes → run ids).

### Kept from v1 (no regression)
- One-command launchers, `/api/v1` contract, demo data pipeline, 62 original
  tests (all green throughout), Chart.js + Vazirmatn vendored offline.

### Known limitations
- Remote data providers are **unverified live** (build sandbox cannot reach
  market-data hosts); defaults remain demo data.
- GitHub Actions workflow is authored but unexecuted here; Windows launcher
  untested in this environment.
- Skipped with reasons: deep learning beyond MLP (torch), foundation models,
  news features, VAR, Optuna nested HPO, SHAP, LLM report assistant (all
  documented in docs/MODELS.md and ADRs).

## 1.0.0 (2026-11-26)

Initial release: Persian RTL FX dashboard with demo/real data modes,
30-model training pipeline, walk-forward backtests with intervals, background
jobs, offline-first single-command launcher. See git history.
