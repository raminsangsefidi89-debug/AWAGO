# ADR-0005: Evaluation protocol — holdout, stability, simulated backtests

Date: 2026-11-26
Status: Accepted

## Decisions

1. **Holdout evaluated once per family.** The tail (default 20%, min 60
   rows) is never used for fitting/selection/calibration. Each family's
   representative is chosen on pre-holdout walk-forward MAE only; the
   holdout number is labeled "held out, evaluated once".
2. **Stability breakdowns are descriptive** (by year / vol regime / pair).
   They surface failures; they are never selection criteria — selecting on
   the best subgroup is cherry-picking and the caveat says so in every
   report.
3. **Backtests are simulations, always.** Sign-based positions, 1x
   notional, no leverage, mandatory costs+slippage, buy-and-hold AND a
   seeded random-signal control. Outputs carry the full disclaimer and the
   deflated-Sharpe caution. "Did not beat the random control" is a valid,
   displayed outcome.
4. **Regimes (P1)**: point-in-time vol-regime labels (trailing-vol terciles
   computed from past data only) + CUSUM change points. Overlays/features
   only — never retroactive storytelling.
