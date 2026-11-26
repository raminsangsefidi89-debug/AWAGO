# ADR-0002: Data platform — providers, columnar store, quality engine

Date: 2026-11-26
Status: Accepted

## Context

v1 has one abstraction (Demo + Frankfurter + fallback). v2 requires
capability-declared providers, resilience (retries, circuit breaker, cache),
columnar bulk storage, a data-quality engine, and provenance — while keeping
every v1 test green and the offline demo experience intact. Outbound network
in the build sandbox is restricted to github/npm/pypi, so **no live market
data source can be verified here**.

## Decisions

1. **Provider set.** Ship: `demo` (deterministic), `frankfurter` (ECB,
   key-less, **unverified live**), `stooq` (key-less daily CSV endpoint,
   **unverified live**, free for personal/educational use per its public
   terms — see docs/DATA_SOURCES.md), and `csv_import` (user-supplied local
   files — always verifiable, and the sanctioned path for IRR/other rates
   with no legitimate API). FRED / Alpha Vantage / Twelve Data require API
   keys and cannot be verified here → **documented as evaluated, not
   implemented** (honesty over feature count). No scraping of sources that
   forbid it.
2. **Resilience** is a wrapper (`ResilientProvider`) with exponential backoff
   + jitter, a circuit breaker (open after N failures, half-open probe after
   the reset window) and a TTL cache keyed by (pair, start, end). Pure
   stdlib/`httpx` — no new heavy deps (APScheduler/tenacity rejected as
   unnecessary).
3. **Columnar store.** SQLite stays the source of truth for bars (v1
   compatibility). Every ingest also writes a Parquet mirror per
   (pair, source) under `data/series/` via **pyarrow** (required, wheels on
   all platforms). **DuckDB** is used for queries when installed
   (optional extra), else pandas. `requirements.txt` gains `pyarrow`;
   `duckdb` goes to `requirements-ml.txt` as an optional extra... decision
   revised: duckdb is small and pure-wheel; we keep it optional anyway and
   test both paths (installed → duckdb query path; absent → pandas path).
4. **Quality engine** is pure pandas/numpy: gap detection with
   cadence inference (business-day vs calendar-day), stale detection,
   Hampel outlier flags on log returns, OHLC schema validation, and
   triangular cross-rate consistency **only for real, same-source legs**
   (demo series are independent walks — the check is reported as
   "not applicable" for demo data). Reports are stored in a
   `quality_reports` table and exposed via API/dashboard.
5. **Provenance.** `price_bars` gains `fetched_at`, `dataset_version`,
   `quality_flag` (migration 0002). Demo/real separation is enforced at
   schema level with a CHECK constraint
   (`is_demo = (data_source = 'demo')`) applied via Alembic batch rebuild.
6. **Scheduler.** A minimal thread-based scheduler (no APScheduler),
   disabled by default, never blocking startup; job cancellation is
   cooperative via a `cancel_requested` flag on `job_records`.
7. **Jobs** gain resource guards: training refuses to start when free disk
   < 200 MB or free RAM < 256 MB, with a clear message.

## Consequences

- Every real provider ships labeled "unverified in build environment"; the
  app defaults to demo and falls back safely.
- pyarrow becomes a required dependency (~40 MB wheel) — accepted for the
  Parquet store.
- Triangular-consistency checks silently mislead on synthetic data unless
  restricted to real sources; restricting them is mandatory (implemented).

## Revision note (Phase 3)

See ADR-0004 for the model-platform decisions layered on top of this one.
