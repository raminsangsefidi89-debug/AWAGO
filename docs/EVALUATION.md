# AWAGO v2 Evaluation Methodology

## Targets and splits

* Target for horizon h at origin t: `log(close[t+h] / close[t])`.
* Walk-forward only (`expanding` or `rolling`), split into k test blocks.
* **Purging**: train rows whose h-step target overlaps the test block are
  dropped (h−1 rows + optional embargo).
* The tail holdout (20%, min 60 rows) is evaluated **once per model family**
  — representative chosen on pre-holdout walk-forward MAE only.

## Metrics

MAE · RMSE · MASE (naive in-sample scale) · sMAPE · directional accuracy ·
pinball (per quantile) · CRPS (quantile-grid approximation) · empirical
coverage · interval width · Winkler score.

## Significance testing

* Diebold-Mariano test on absolute-error differential losses with the
  Harvey-Leybourne-Newbold small-sample correction.
* Holm-Bonferroni adjustment across the model family (multiple comparisons
  are corrected, never ignored).
* Leaderboard verdicts (verbatim strings used in UI + reports):
  `beats baseline significantly` · `beats baseline, not significantly` ·
  `worse than baseline (significant)` · `not better than baseline` ·
  `baseline (yardstick)`.
* Champion promotion uses a paired bootstrap on |error| differences (1000
  resamples).

## Leakage defense

1. Features are point-in-time by construction (trailing windows only).
2. Perturb-future audit: post-cutoff randomization must not move pre-cutoff
   feature rows (negative-tested with a deliberately leaky builder).
3. Suspicious-correlation audit: |corr(feature, target)| ≥ 0.99 is flagged
   (negative-tested with a copied target).
4. Ensemble weights and stacking meta-features use only earlier OOF folds.
5. The honest caveat stands: **passing these audits does not prove the
   absence of leakage** — purged splits and provenance cover the rest.

## Stability

Breakdowns by calendar year and point-in-time volatility regime (and by
pair). These tables are descriptive failure-surfacing — selecting a model
because of its best subgroup would be cherry-picking and is called out in
every report.

## Simulated backtests

* Sign positions from the point forecast, 1x notional, **no leverage**.
* Costs + slippage always charged (bps per side).
* Benchmarks: buy-and-hold AND a seeded random-signal control with identical
  cost structure. "Did not beat the random control" is a displayed outcome.
* Every result carries the disclaimer and the deflated-Sharpe caution.

## Calibration

Coverage tables always show nominal AND empirical values side by side, with
the method labeled (`split_conformal`, `adaptive_conformal`, `cqr`,
`wf-residual-quantiles`). Intervals under exchangeability assumptions —
which time series only approximate — are labeled as such.
