# ADR-0004: Model platform — one harness, two training paths

Date: 2026-11-26
Status: Accepted

## Context

The spec calls for a plugin registry and ONE harness for every model family,
with probabilistic outputs, ensembles, and statistically grounded verdicts.
AWAGO v1 already ships a tested `Forecaster` + `train_pair` demo path (62
green tests, one-command launcher flow). Reworking it in place would risk the
"never delete/rewrite passing v1 work" constraint.

## Decisions

1. **One evaluation harness, two training paths.** The v2 experiment runner
   (`app/services/evaluation/runner.py`) is the single harness: every model
   is a `ForecastModel` plugin and is evaluated through the same purged
   walk-forward machinery, metrics, DM tests, and leaderboard. The v1
   `Forecaster`/`train_pair` remains as the *demo quick-train* path only
   (launcher auto-train, `/api/v1/jobs/train`), unchanged and regression-tested.
2. **Plugin contract**: fit/predict/predict_quantiles/save/load/metadata;
   point forecasts are h-step future log returns; quantile support is
   optional and reported honestly when missing.
3. **CPU honesty**: ARIMA refits on a cadence (every 15 origins, 500-bar
   window); deep learning is a sklearn MLP (no torch requirement); GARCH is
   behind the optional `arch` extra and the registry says exactly why when
   unavailable.
4. **Leakage discipline in ensembles**: combiners use an explicit fit/predict
   split — weights and meta-models are fit only on earlier OOF rows; fold 0
   falls back to plain average; failures fall back to the baseline.
5. **Verdicts are statistical**: Diebold-Mariano (Harvey correction) per
   model vs naive, Holm-Bonferroni across the model family; champion
   promotion requires paired-bootstrap significance; every leaderboard row
   carries the verdict string and the p-values.
6. **Skipped with reasons** (documented, not faked): torch LSTM/GRU/N-BEATS
   (heavy optional dep — N-BEATS-class MLP covered by `deep_mlp`), TFT/PatchTST
   (P2), foundation models (P2), Optuna nested-WF (time budget; feature
   selection is already walk-forward-based), SHAP (extra dep; permutation
   importance implemented instead), VAR (P1, needs multi-endpoint statsmodels
   plumbing).

## Consequences

- The final leaderboard can mix rows from both paths; rows carry `run_id` +
  `feature_set_version` in `details_json` so they are attributable.
- Lite profile: quick experiments fit in a few minutes; `full` expands pairs,
  horizons, and folds.
