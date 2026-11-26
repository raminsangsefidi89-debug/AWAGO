# AWAGO v2 — Progress (persistent memory)

> Re-read this file at the start of every phase. Update after every milestone.

## Current state

- **Branch:** `arena/1f20119b-awago` (from `main` @ `8966cdb`, the v1 merge).
- **v1 baseline recorded:** `docs/BASELINE_V1.md` (62 tests green, metric table captured from a real run).
- **Environment:** Python 3.11.2, `.venv` rebuilt, requirements + dev + lightgbm installed.
- **Image generation:** was unavailable in the v1 session (SVG placeholders ship in `app/static/img/`). Phase 6B will retry once.

## Phase status

| Phase | P0 | P1 | P2 | Status |
|---|---|---|---|---|
| 0 Foundation & tooling | todo | — | — | in progress |
| 1 Data platform | todo | todo | — | not started |
| 2 Features & exogenous | todo | todo | todo | not started |
| 3 Modeling engine | todo | todo | todo | not started |
| 4 Evaluation & backtesting | todo | todo | — | not started |
| 5 Platform & API | todo | todo | — | not started |
| 6 Dashboard | todo | todo | todo | not started |
| 6B Images | retry | — | — | not started |
| 7 Reports & assistant | — | todo | todo | not started |
| 8 Hardening & verification | todo | — | — | not started |

## Done

- (2026-11-26) Repo inspection; venv rebuild; v1 tests green (62/62);
  `docs/BASELINE_V1.md` written from a real training run.

## In progress

- Phase 0: tooling (pyproject, lint/type config, Makefile, CI), Alembic
  migrations preserving v1 data, domain-organized settings + `config show`
  CLI, correlation IDs, determinism helpers.

## Next

- Phase 0 quality gate (tests + ruff + mypy + launcher smoke).
- Phase 1 data platform (provider v2 registry, parquet series store, quality engine).

## Open problems / risks

- Image generation service likely still unavailable (retry in Phase 6B, keep fallback).
- Real-data providers (FRED/ECB/Stooq/etc.) cannot be verified from this sandbox
  (outbound network restricted to github/npm/pypi) → they must ship marked
  "unverified" with graceful fallback; only Demo data can be verified here.
- mypy strictness must not block progress: adopt pragmatic config (check
  app/, allow untyped third-party stubs), fix reported issues rather than
  silencing everything.

## Resume commands

```bash
cd /home/user/AWAGO
.venv/bin/python -m pytest tests/ -q      # full suite
make lint                                  # ruff (after Phase 0)
make typecheck                             # mypy (after Phase 0)
python run.py --no-browser --skip-train    # launcher smoke
```

## Decision log index

- ADR-0001: v2 scope tooling & stack decisions (Phase 0)
- ADR-0002: (pending) data platform choices
