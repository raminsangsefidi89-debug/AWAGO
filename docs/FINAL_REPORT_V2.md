# AWAGO v2 + Addendum — Final Report (2026-11-26)

Everything below was measured in this build environment unless explicitly
marked unverified. Nothing is claimed that was not observed.

## Phase table (P0/P1/P2)

| Phase | P0 (must) | P1 (should) | P2 (nice) |
|---|---|---|---|
| 0 Foundation | tooling, Alembic (v1 data lossless), typed config, repro, logging | `config show` CLI | — |
| 1 Data platform | provider v2 + health, resilience, stooq + csv_import, Parquet/DuckDB store, quality engine, provenance + demo/real CHECK | job cancel, resource guards, scheduler | extra live providers (FRED etc. — evaluated, not implemented; documented) |
| 2 Features | versioned store v3 (point-in-time), leakage harness (negative-tested), 30 features | cross-pair features, selection (clustering + stability) | LLM feature assistant — **skipped** (heavyweight; reasons in ADR-0003) |
| 3 Models/eval | plugin registry, walk-forward harness, baselines/ARIMA/ML/ensembles, conformal (split/CQR/adaptive), verdicts vs baseline | probabilistic fan charts, lifecycle + champion/challenger | GARCH/extra ML — lightgbm auto-detected |
| 4 Eval hardening | purged WF, holdout-once-per-family, stability | simulated backtests + controls + deflated-Sharpe caution | regime overlays |
| 5 API | typed experiment API, leaderboards, registry, export (csv/parquet) | SSE, rate limit, ETag, write guard | — |
| 6 Dashboard | Persian RTL SPA (9 pages), Jalali + Persian digits, honesty badges | dark/light, a11y, fan charts, deep links | — |
| 6B Images | 10/10 generated (<300KB), manifest | prompts doc | logo-mark lacks true alpha (recorded) |
| 7 Report | Persian print HTML from computed outputs only | CLI `report` | LLM assistant — skipped (documented) |
| 8 Hardening | property tests, failure injection, security, repro (18 tests) | docs set + CHANGELOG | — |
| A0 Market P0 | units utility, Iran calendar, instruments, derived series, consensus, verify_sources | CSV/manual import path | — |
| A1 News P1 | fetcher (conditional GET/backoff), Persian normalization, dedup, topics, sentiment lexicon, point-in-time features (leakage-tested), events + event studies, DM news-value test, drivers layer, 3 dashboard pages | reliability tiers, surprise index | transformer sentiment — out of scope (full profile later) |

## Tests & quality

- **258/258 tests pass** (62 v1 regression + 196 v2/addendum). v1 tests never
  deleted; all kept passing.
- ruff clean, ruff-format clean, mypy clean (80 → 97 source files).
- Coverage **86%** (`pytest --cov=app`, measured at Phase 8 wrap-up) —
  ≥85% target met. Weak spots recorded: statistical.py ~30%, scheduler ~39%.
- Property tests (Hypothesis), failure injection (provider down, corrupt
  parquet, disk guard, malformed news XML, rate-limit/backoff, feed 304),
  security (path traversal, secrets scan, .env gitignored), reproducibility
  (seeded demo provider, deterministic features).

## Measured results (honest verdicts)

- Fresh E2E (2026-11-26, demo data, 10 pairs / 10,960 bars): quick experiment
  (2 pairs × 2 horizons × 17 models, 3 splits) finished in **~30 s**;
  launcher fresh-start (migrate + seed + serve) **~7 s**.
- Leaderboard verdicts (quick E2E): **54 rows "worse than baseline
  (significant)", 10 "not better than baseline", 4 "baseline (yardstick)"** —
  on demo data the naive baseline wins, as expected. This is a valid result
  and is reported verbatim; no model is claimed to beat the baseline.
- Calibration/coverage: conformal models are covered by the test suite
  (interval coverage assertions, CQR/adaptive). Quick profile runs point
  models only; run `--profile full` for probabilistic rows with empirical
  coverage per model (never nominal-only claims).
- News value (addendum): the DM test infrastructure is implemented and
  tested; the demo verdict panel is labelled demo. On real data the panel
  reports per-instrument "improves / WORSE / no significant difference"
  honestly; news is kept contextual-only unless the test says otherwise.

## Images (outcome per file)

10/10 generated (Phase 6B), all under `app/static/img/` with `manifest.json`
and prompts in `docs/IMAGE_PROMPTS.md`: hero-bg.webp (37KB), empty-state,
error-state, training, demo-banner, card-forecast, card-trend,
card-evaluation (15–108KB), og-image.webp (70KB), logo-mark.png (297KB,
1024², **no true alpha channel — recorded honestly**). SVG placeholders kept
as fallback.

## Sources: verified / failed / unverified

Recorded by actually probing (`scripts/verify_sources.py` →
`docs/DATA_SOURCES.md`):

- **Verified (local):** demo provider, CSV import, manual entry.
- **Unreachable from build sandbox (recorded, honest):** frankfurter,
  stooq, metals.dev, FRED, Iran market API (no default host — configure),
  crypto-exchange USDT/IRT (no default exchange), all 5 news feeds (Fed, ECB,
  BLS, IMF, GDELT). Status "unverified in build environment" — they may work
  on the user's networked machine; re-run the script there before relying on
  any of them.
- **Never scraped:** sources that forbid it are not scraped; the sanctioned
  path is CSV/Excel import + manual entry with provenance labels.
- **Real history depth per series (build env):** FX demo series 1,096 bars/pair
  (seed); all market/news series have **no real history in this environment**
  (forward snapshots + imports are the honest path to history). Nothing was
  backfilled.

## Addendum honesty/safety checklist

- [x] Iran quotes always labelled unofficial market quotes.
- [x] Units explicit on every series; conversions only via tested utility.
- [x] Data timestamp + age + "stale" on every price; demo never shown as live.
- [x] No "all news" claims; active sources + last fetch shown.
- [x] No buy/sell/hold advice anywhere; disclaimer on every page + report.
- [x] Low-credibility/unattributed items flagged; "unconfirmed" labels.
- [x] Multi-source disagreement exposed (per-source values + %).
- [x] Point-in-time news (max(published, fetched)); leakage negative-tested.
- [x] Polite polling (ETag/If-Modified-Since, ≥15 min, backoff, fail-soft).
- [x] Privacy: public bylines/source names only.

## Skipped / limitations (with reasons)

- Live-source verification: impossible in build sandbox (network allowlist).
- P2 LLM feature assistant + LLM report assistant: skipped (heavyweight,
  optional dependency, low value at P0/P1 — ADR-0003/0006).
- Transformer sentiment: out of scope; lexicon baseline shipped with
  model name/version.
- GH Actions CI + Windows launcher untestable from sandbox (labelled).
- Lunar Iranian holidays: curated file, honest coverage reporting.
- Demo derived values are internally consistent but are DEMO — real values
  require verified sources.

## Run commands

```bash
# Linux/macOS
./run.sh                       # lite profile (default) — first run few minutes
./run.sh --profile full        # heavy models (requirements-ml.txt)
# Windows
run.bat
# any OS
python run.py --no-browser     # headless
python -m app.cli report --run latest --out report.html
PYTHONPATH=. python scripts/verify_sources.py   # verify sources (networked)
```

## Next steps

1. On a networked machine: run `scripts/verify_sources.py`, configure Iran
   market + crypto-exchange hosts that permit API access, import legitimate
   history archives → real depth per series.
2. Run `--profile full` experiments to populate probabilistic coverage and
   the with-vs-without-news DM verdicts on real instruments.
3. Add transformer sentiment in `full` profile with model card persistence.
4. Configure curated lunar holidays annually.
