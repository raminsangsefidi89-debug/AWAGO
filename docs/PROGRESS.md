# AWAGO v2 — Progress (persistent memory)

_Last updated: 2026-11-26 (addendum complete, pre-PR)._

## Current state

v2 + addendum complete on branch `arena/1f20119b-awago`. **258/258 tests green**
(62 v1 + 196 v2/addendum), ruff + mypy clean, coverage ≥85% (86% measured at
Phase 8). One-command launcher works (`run.py` / `run.sh` / `run.bat`),
lite profile default, Persian RTL dashboard with 12 pages.

> Sandbox note: a session reset on 2026-11-26 dropped git history and the
> venv; all work survived in the working tree and was re-verified green and
> recommitted (`cfa7041` = recovered v2 baseline). Never trust background
> processes or `data/` to survive a reset; always re-check `git log` first.

## Phase status

| Phase | Scope | Status | Evidence |
|---|---|---|---|
| P0 | Foundation, Alembic, config, repro | done | tests, migrations 0001 |
| P1 | Data platform (providers, quality, provenance) | done | tests/test_data_platform.py (26) |
| P2 | Features + leakage audit | done | tests/test_features.py (16); LLM feature assistant skipped (documented) |
| P3 | Models + walk-forward + probabilistic | done | tests/test_models.py (30) |
| P4 | Evaluation hardening (holdout, stability, backtest) | done | tests/test_evaluation.py (14) |
| P5 | Experiment API, jobs, export | done | tests/test_api_v2.py (14) |
| P6 | Persian RTL dashboard (9 pages) | done | tests/test_jalali.py (19), JS modules |
| P6B | Images (10/10 generated) | done | app/static/img/manifest.json |
| P7 | Persian print report | done | tests/test_report.py (7) |
| P8 | Hardening + docs | done | tests/test_hardening.py (18), docs/ set |
| A0 | Addendum P0: units, calendar, instruments, derived, consensus, verify_sources | done | tests/test_market_units.py (23) |
| A1 | Addendum P1: news pipeline, drivers, markets API, dashboard pages | done | tests/test_news.py (26) + tests/test_markets_api.py (8) |

## Done (addendum specifics)

- Units: one tested utility (rial/toman, oz/gram, coin fine gold 7.3224 g).
- Derived series with documented formulas + tests: implied gram IRR (global),
  18k, coin intrinsic, coin bubble abs/%, USD gap abs/%, cross-market check →
  quality warnings (never auto-corrected).
- Consensus: median + MAD rejection, disagreement always exposed.
- Iran calendar: UTC+3:30, Thu/Fri weekend, fixed Jalali holidays + curated
  lunar file with honest coverage.
- Instruments registry with `MARKET_GLOBAL_ENABLED`/`MARKET_IRAN_ENABLED`;
  Iran quotes always unofficial-labelled.
- News: RSS fetcher (conditional GET, backoff, fail-soft), Persian
  normalization, dedup clustering, topics, lexicon sentiment
  (`lexicon-fa-en/1`), rule events + event studies, point-in-time features
  (leakage-tested), DM news-value test with honest verdict strings.
- Drivers: rolling corr, lead-lag + spurious-caution, regime dependence,
  permutation importance.
- Dashboard: «طلا و دلار» (global|iran, derived table, toman/rial toggle),
  «اخبار» (feed + value verdict), «محرک‌ها». Every number: source + timestamp
  + unit + Demo/real + stale badges.
- `scripts/verify_sources.py` probes market + news sources and appends honest
  rows to docs/DATA_SOURCES.md (all unreachable from build sandbox — recorded).

## Skipped / unverified (with reasons)

- Live verification of every remote source (market + news): impossible in the
  build sandbox (network allowlist); all `verified_live=False`, status
  recorded in docs/DATA_SOURCES.md.
- P2 LLM feature assistant: skipped — heavyweight, `llama-cpp` optional, low
  P0/P1 value (reasons in ADR-0003).
- Transformer sentiment (full profile): out of scope; lexicon baseline
  shipped with model name/version persisted.
- GH Actions CI, Windows launcher: untestable from sandbox (labelled).

## Resume commands

```bash
cd /home/user/AWAGO
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -q            # full suite (258)
.venv/bin/python -m ruff check app scripts tests
.venv/bin/python -m mypy
PYTHONPATH=. .venv/bin/python scripts/verify_sources.py   # on networked machine
python3 run.py --no-browser                     # launcher (lite)
python3 run.py --profile full                   # heavy models
```

## Decision log index

- ADR-0001: v2 scope, tooling & stack
- ADR-0002: data platform choices (providers, provenance, quality)
- ADR-0003: feature engineering & leakage policy (LLM assistant skipped)
- ADR-0004: model/evaluation design (walk-forward, conformal, verdicts)
- ADR-0005: evaluation hardening (holdout-once, stability, backtests)
- ADR-0006: market/news layer (units, sourcing, point-in-time, news value)
