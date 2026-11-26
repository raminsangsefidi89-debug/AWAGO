# AWAGO v2 Model Catalog

Every model implements `ForecastModel` (`app/services/models/base.py`):
`fit(FitData)` / `predict(PredictData)` / optional `predict_quantiles` /
`save` / `load` / `metadata`. Point forecasts are always **h-step future log
returns** computed point-in-time.

## Baselines (the yardstick)

| Model | id | Method |
|---|---|---|
| Naive | `baseline_naive` | Random walk: expected log return 0 |
| Drift | `baseline_drift` | Mean of past h-step returns |
| Seasonal naive | `baseline_seasonal_naive` | Same as 7 days ago (weekly) |
| Moving average | `baseline_ma` | Forecast price = rolling mean (20) |
| Holt ETS | `baseline_ets` | ETS(A,A,N) on log prices, sequential state updates |

## Statistical

| Model | id | Method | Notes |
|---|---|---|---|
| ARIMA | `stat_arima` | ARIMA(1,1,1), statsmodels | Refits every 15 origins on a 500-bar window (CPU honesty) |
| GARCH vol | `stat_garch_vol` | GARCH(1,1) via `arch` | σ-forecast only; direction forecast is 0 **by design**; unavailable without the optional `arch` package (registry says exactly why) |

## Classical ML (direct multi-horizon)

| Model | id | Notes |
|---|---|---|
| Ridge | `ml_ridge` | α=1.0 |
| ElasticNet | `ml_elasticnet` | α=0.01, l1_ratio=0.5 |
| Random forest | `ml_rf` | 100 trees, min_samples_leaf=5 |
| Extra trees | `ml_extratrees` | 100 trees |
| HistGB | `ml_histgb` | 150 iters |
| Ridge recursive | `ml_ridge_recursive` | Chained 1-step models |

## Deep (lite)

| Model | id | Notes |
|---|---|---|
| MLP | `deep_mlp` | sklearn MLPRegressor (32,16), early stopping — **no torch required** |

## Ensembles

`ensemble_avg`, `ensemble_inv_error`, `ensemble_stacking` (Ridge meta),
`ensemble_online` (decayed weights). Weights/meta fit on **earlier OOF folds
only**; fold 0 falls back to plain average; any failure falls back to the
baseline — "fall back to baseline" is first-class behavior.

## Probabilistic

| Method | id | Notes |
|---|---|---|
| Quantile regression | `prob_quantile_gbm` | GBM quantile loss per quantile, interpolated grid |
| Split conformal | (post-processor) | Time-aware calibration split; symmetric intervals |
| CQR | (post-processor) | Romano-style conformalized quantile regression |
| Adaptive conformal | (post-processor) | Rolling residual window, no lookahead |

Every interval reports **empirical vs nominal coverage**, mean width and
Winkler score. Nominal coverage is never presented as a guarantee.

## Documented skips (with reasons)

* LSTM/GRU/N-BEATS/N-HiTS (torch) — heavy optional dependency; `deep_mlp`
  covers the small-CPU niche honestly.
* TFT/PatchTST (P2), foundation models Chronos/TimesFM (P2) — heavy
  downloads + frameworks; out of scope for a laptop-first tool.
* VAR (P1) — multi-endpoint statsmodels plumbing not worth the maintenance.
* Optuna nested walk-forward (P1) — feature selection is already
  walk-forward-based; nested HPO recorded as future work.
* SHAP (P1) — extra dependency; permutation importance implemented instead.

## Champion / challenger

`app/services/models/lifecycle.py`: artifacts under `data/registry/` carry
`run_id`, `config_hash`, `snapshot_hash`, and metrics. Promotion requires a
significant paired-bootstrap win over the incumbent (1000 resamples, 95%
CI); every compare/promote/rollback is appended to `events.jsonl`.
