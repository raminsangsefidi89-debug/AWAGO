# AWAGO v1 Baseline (recorded 2026-11-26)

This is the v1 benchmark that AWAGO v2 is compared against. All numbers below
were produced by an actual training run in this repository on **demo data**
(DEMO_SEED=42, 1095 days, `quick=True` training), captured mechanically into
`/tmp/baseline_v1.json` and transcribed here without alteration.

- **v1 test suite:** 62 tests, all passing (`python -m pytest tests/ -q`).
- **Data:** deterministic demo series (synthetic — never real market data).
- **Evaluation:** v1 walk-forward (expanding window, 3 splits in quick mode),
  metrics in price space, naive baseline = "price unchanged".
- **Interpretation:** on a synthetic random walk, most models correctly do
  **not** beat the naive baseline. Beats on USD/TRY (strong deterministic
  trend in the generator) and USD/CHF h=30 are properties of the synthetic
  data, not evidence of real-market predictability.

## Forecast metrics per pair and horizon (v1 quick training)

| Pair | h | winner | model MAE | naive MAE | beats baseline |
|---|---|---|---|---|---|
| EUR/USD | 1 | hist_gb | 0.000841 | 0.000799 | False |
| EUR/USD | 7 | hist_gb | 0.002322 | 0.001963 | False |
| EUR/USD | 30 | hist_gb | 0.007213 | 0.004477 | False |
| GBP/USD | 1 | hist_gb | 0.001161 | 0.001109 | False |
| GBP/USD | 7 | hist_gb | 0.003259 | 0.002879 | False |
| GBP/USD | 30 | hist_gb | 0.008565 | 0.006641 | False |
| USD/JPY | 1 | hist_gb | 0.217808 | 0.19433 | False |
| USD/JPY | 7 | hist_gb | 0.612566 | 0.511809 | False |
| USD/JPY | 30 | lightgbm | 1.132184 | 1.028579 | False |
| USD/CHF | 1 | hist_gb | 0.000725 | 0.000706 | False |
| USD/CHF | 7 | hist_gb | 0.001787 | 0.001718 | False |
| USD/CHF | 30 | lightgbm | 0.002414 | 0.002745 | True |
| AUD/USD | 1 | hist_gb | 0.000907 | 0.000826 | False |
| AUD/USD | 7 | hist_gb | 0.002775 | 0.002108 | False |
| AUD/USD | 30 | hist_gb | 0.006623 | 0.005522 | False |
| USD/CAD | 1 | hist_gb | 0.001368 | 0.001242 | False |
| USD/CAD | 7 | hist_gb | 0.004415 | 0.003248 | False |
| USD/CAD | 30 | hist_gb | 0.01154 | 0.006644 | False |
| NZD/USD | 1 | hist_gb | 0.000578 | 0.000535 | False |
| NZD/USD | 7 | hist_gb | 0.00162 | 0.001371 | False |
| NZD/USD | 30 | hist_gb | 0.003111 | 0.002789 | False |
| EUR/GBP | 1 | hist_gb | 0.000621 | 0.000598 | False |
| EUR/GBP | 7 | hist_gb | 0.001928 | 0.00154 | False |
| EUR/GBP | 30 | hist_gb | 0.004572 | 0.003442 | False |
| EUR/JPY | 1 | hist_gb | 0.176695 | 0.164137 | False |
| EUR/JPY | 7 | hist_gb | 0.531345 | 0.462169 | False |
| EUR/JPY | 30 | hist_gb | 1.145989 | 0.99215 | False |
| USD/TRY | 1 | hist_gb | 4.454237 | 4.474219 | True |
| USD/TRY | 7 | hist_gb | 11.09065 | 15.294799 | True |
| USD/TRY | 30 | hist_gb | 28.88791 | 57.628683 | True |

## v1 first-run timing (this machine, Python 3.11)

- Seed 10 pairs x 1095 days: ~3 s.
- Quick training 10 pairs x 3 horizons (ridge + hist_gb + lightgbm, 3 splits):
  ~21 s total (measured from the run that produced the table above).
- Server start: < 1 s.

## v1 feature set (FEATURES_VERSION=2)

log returns (1d + lags 2/3/5/10), SMA 5/10/20/50 + distances, EMA 12/26,
RSI-14, MACD (12/26/9), Bollinger (20, 2σ) incl. width and %B, ATR-14,
rolling vol 5/20/60d + ratio, calendar (dow/month/dom + sin/cos).
