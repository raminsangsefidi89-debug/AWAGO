# Contributing to AWAGO

## Ground rules (non-negotiable)

1. **Honesty over aesthetics.** Never claim unverified success. If a source
   or metric was not actually observed, label it "unverified" or omit it.
2. **No lookahead, ever.** Features must be point-in-time; run the leakage
   audits (`tests/test_features.py`) before and after your change.
3. **Never delete a passing test to make things pass.** Fix the code.
4. **One-command launch must keep working**: `run.bat` / `./run.sh` /
   `python run.py`.
5. Demo data must stay unmistakably labeled; demo and real data never mix
   (schema CHECK enforces it — keep it that way).
6. Secrets live only in `.env` (git-ignored). Never commit keys.

## Quality gates (run before committing)

```bash
make lint        # ruff check + format --check
make typecheck   # mypy
make test        # pytest — includes the 62 v1 regression tests
```

Coverage target: ≥85% overall (currently measured in CI/local runs).

## Conventional commits

`feat(scope): …`, `fix(scope): …`, `docs: …`, `test: …`, `chore: …`.
One milestone per commit where practical; never leave the branch broken.

## Adding a model

1. Subclass `ForecastModel` in `app/services/models/`.
2. Register it in `app/services/models/registry.py` with an honest
   availability flag (`optional_requires` if it needs an extra package).
3. Add it to `core_model_names()` only if it is lite-safe.
4. Add tests (fit/predict shape, save/load, no-lookahead where applicable).

## Adding a data source

1. Declare `ProviderCapabilities` with `verified_live=False` unless you have
   actually called the endpoint successfully.
2. Document terms/licensing in `docs/DATA_SOURCES.md`.
3. Never scrape sources that forbid it — use the `csv_import` provider.
