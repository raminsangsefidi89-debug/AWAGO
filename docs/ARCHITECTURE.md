# AWAGO v2 Architecture

(See the Mermaid diagram in README.md for the visual overview.)

## Layers

1. **Data layer** (`app/services/data_providers/`, `app/services/storage/`)
   - Providers declare capabilities (`ProviderCapabilities`): pairs,
     intervals, rate limits, license notes, `verified_live`, `is_demo`.
   - `ResilientProvider` wraps any provider with a TTL cache + circuit
     breaker; `with_backoff` adds exponential backoff with full jitter.
   - SQLite is the source of truth for bars (v1 compatibility); every ingest
     also writes a Parquet mirror per (pair, source) under `data/series/`
     (queried with DuckDB when installed, else pandas).
   - Provenance per bar: `data_source`, `fetched_at`, `dataset_version`,
     `quality_flag`. Demo/real split enforced by a SQL CHECK constraint.

2. **Quality layer** (`app/services/quality/`)
   - Gaps with cadence inference (business vs calendar), staleness, Hampel
     outliers on log returns, OHLC sanity, triangular cross-rate consistency
     (real same-source legs only — "not applicable" on demo by design).
   - Reports persist to `quality_reports` and surface via API/UI.

3. **Feature layer** (`app/services/features/`)
   - Versioned registry (`FEATURE_SET_VERSION = "3"`) with per-feature
     lookbacks; builders use trailing windows only.
   - Leakage audits: perturb-future (bit-identical prefix requirement) and
     suspicious-correlation, both negative-tested.
   - Selection: correlation clustering + stability selection (fold-local
     permutation importance).

4. **Model layer** (`app/services/models/`)
   - `ForecastModel` plugin contract; registry with honest availability.
   - Ensembles combine walk-forward predictions with fit/predict separation.
   - Lifecycle: artifacts with run/config/snapshot hashes, champion/
     challenger with paired-bootstrap significance, JSONL audit trail.

5. **Evaluation layer** (`app/services/evaluation/`)
   - Purged walk-forward (expanding/rolling + embargo), holdout-once-per-
     family, stability breakdowns, DM+Harvey with Holm, simulated backtests
     with controls.

6. **Presentation** (`app/api/`, `app/static/`, `app/services/report/`)
   - FastAPI with one error envelope, correlation IDs, rate limiting,
     ETag/304, SSE job stream, localhost-or-token write guard.
   - Vanilla ES-module SPA (no build step): hash router, 9 pages, Jalali
     dates, honesty badges, fan charts, dark/light, reduced motion.

## Reproducibility

`app/repro.py`: `seed_everything`, `config_hash`, `snapshot_hash`,
`make_run_id` — every artifact and leaderboard row carries its triple.

## Storage layout

```
data/
  awago.db            # SQLite: bars + metadata + jobs + quality + metrics
  series/*.parquet    # columnar mirrors per (pair, source)
  features/*.parquet  # versioned feature frames + .meta.json
  leaderboards/       # {run_id}.json, latest.json, {run_id}_preds/*.npz
  registry/           # artifacts, champions.json, events.jsonl
  logs/               # rotating logs with correlation ids
```
