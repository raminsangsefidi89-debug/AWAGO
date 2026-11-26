# ADR-0001: v2 foundation — tooling, migrations, config, determinism

Date: 2026-11-26
Status: Accepted

## Context

AWAGO v1 is a working local-first platform (FastAPI + SQLAlchemy 2 + vanilla
JS) with 62 green tests. v2 requires professional tooling (lint, types, CI),
schema migrations that preserve v1 data, and reproducible experiments,
without breaking the one-command launcher or the offline-first behaviour.

## Options considered

1. **Tooling:** adopt `pyproject.toml`-based ruff+mypy+pytest (vs. adding
   separate setup.cfg/tox). Chosen: single pyproject; ruff also formats.
2. **Migrations:** Alembic (vs. hand-rolled schema_version table vs.
   recreate-on-change). Chosen: Alembic — standard, safe autogenerate flow,
   and we can stamp legacy v1 databases instead of recreating them.
3. **Config:** keep single flat `Settings` but organise into nested domain
   objects (`ServerCfg`, `DataCfg`, `ModelCfg`, ...) while keeping **all
   existing env var names working** (field aliases) so v1 `.env` files keep
   working unchanged. `config show` CLI redacts secret-looking values.
4. **CI:** GitHub Actions matrix (ubuntu/windows/macos x py3.10-3.12) is
   requested; we ship the workflow file but can only *verify* it syntactically
   here (Actions cannot run in this sandbox) — recorded as unverified.
5. **Determinism:** one `app/repro.py` with `seed_everything`, config hashing
   (sha256 of canonical JSON of non-secret settings) and data-snapshot hashing
   (sha256 of the sorted bar rows). Run IDs = first 12 hex of
   `config_hash + snapshot_hash + name`.
6. **Pre-commit:** `.pre-commit-config.yaml` with ruff; documented as optional
   (hooks cannot be installed offline in some environments).

## Consequences

- v1 `.env` and v1 SQLite files keep working (migrations stamp legacy DBs).
- Lint/type gates may surface v1 code smells; we fix them in Phase 0/8 rather
  than suppressing wholesale.
- CI workflow ships but is **unverified** until pushed to GitHub.
