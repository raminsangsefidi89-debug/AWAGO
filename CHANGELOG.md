# Changelog

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
