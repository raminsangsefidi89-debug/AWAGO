# ADR-0003: Feature engineering and leakage defense

Date: 2026-11-26
Status: Accepted

## Context

Features must be point-in-time correct by construction (no lookahead), versioned,
and auditable. FX is close to efficient, so any backtest that benefits from
leakage is guaranteed to be fiction. The feature layer must make leakage a
*mechanical* impossibility where it can, and *detectable* otherwise.

## Decisions

1. **Point-in-time by construction.** Every builder uses trailing rolling
   windows only (no `center=True`, no backfill, no full-sample statistics).
   A feature row labeled `T` uses bars `<= T`. The modeling layer appends
   targets; the feature frame itself never carries them.
2. **Versioned feature store.** `FEATURE_SET_VERSION = "3"` (v1 used raw
   returns "1", v1.5 drifted "2"; we continue the lineage). The version is
   embedded in every model artifact, run-id config hash, and leaderboard row.
   Feature frames are persisted as Parquet under `data/features/` with
   `.meta.json` (feature-set spec + row count).
3. **Registry parity.** `features/set.py` declares every column with its
   required lookback; tests assert the builder output matches the registry
   exactly (both directions).
4. **Leakage-audit harness** (`features/leakage.py`):
   - *Perturb-future*: randomize every bar after a cutoff, recompute features,
     assert rows before the cutoff are bit-identical. A negative test
     (deliberately leaky builder) proves the harness detects leaks.
   - *Suspicious correlation*: |corr(feature, target)| at leads -5..+5; flags
     near-1.0 correlations (copy-leak smell). The report carries an explicit
     caveat: passing does NOT prove absence of leakage.
5. **Feature selection (P1)**: unsupervised correlation clustering (no target
   use in choosing representatives) + stability selection via fold-local
   permutation importance on expanding time-ordered folds. Full per-fold
   importances are reported, not just the winner list.
6. **Skipped with reasons**: exogenous macro series (P1) — no macro source
   verifiable from the build environment; publication-lag handling designed
   but unexercised. News features (P2) — no legitimate news feed available
   offline. Both are documented rather than faked.

## Consequences

- Feature correctness is enforced by tests that fail when someone introduces
  a centered window or a full-sample normalization.
- Calendar features are safe because day-of-week/month for day T is known at T.
- Cross-pair features align on timestamps and only ever see `<= T` values of
  the other pairs; missing legs produce NaN, never silent fills.
