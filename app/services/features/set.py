"""Feature-set registry: versioned metadata with lookback + availability.

POINT-IN-TIME RULE (enforced by the builders and tested by the leakage
harness): a feature row labeled timestamp T is computed exclusively from
bars with timestamp <= T. Nothing else is allowed — no centered windows, no
backfill from the future, no target-derived columns in the feature frame.

``FEATURE_SET_VERSION`` must be bumped whenever the feature list or its
computation changes; it is embedded in every model artifact and leaderboard
row so results stay attributable to an exact feature definition.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Bump when features change in any way that affects values.
FEATURE_SET_VERSION = "3"

FEATURE_SET_NAME = "awago_core"


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    lookback: int  # minimum bars required before the first non-NaN value
    group: str
    description: str


@dataclass
class FeatureSet:
    name: str
    version: str
    specs: list[FeatureSpec] = field(default_factory=list)

    @property
    def feature_names(self) -> list[str]:
        return [s.name for s in self.specs]

    @property
    def required_lookback(self) -> int:
        return max((s.lookback for s in self.specs), default=1)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "required_lookback": self.required_lookback,
            "features": [vars(s) for s in self.specs],
        }


# Metadata for every feature the core set emits. Builders must stay in sync
# (tests assert the builder output columns match this registry).
CORE_SPECS: list[FeatureSpec] = [
    # multi-horizon log returns (of the primary pair)
    FeatureSpec("ret_1d", 2, "returns", "1-day log return"),
    FeatureSpec("ret_5d", 6, "returns", "5-day log return"),
    FeatureSpec("ret_10d", 11, "returns", "10-day log return"),
    FeatureSpec("ret_20d", 21, "returns", "20-day log return"),
    # realized volatility estimators
    FeatureSpec("vol_cc_20", 21, "volatility", "close-close realized vol, 20d"),
    FeatureSpec("vol_parkinson_20", 21, "volatility", "Parkinson high-low vol, 20d"),
    FeatureSpec("vol_gk_20", 21, "volatility", "Garman-Klass vol, 20d"),
    # momentum
    FeatureSpec("mom_10", 11, "momentum", "10-day momentum (log return)"),
    FeatureSpec("mom_20", 21, "momentum", "20-day momentum (log return)"),
    FeatureSpec("mom_60", 61, "momentum", "60-day momentum (log return)"),
    # mean reversion
    FeatureSpec("zscore_20", 21, "mean_reversion", "z-score of price vs 20d mean"),
    FeatureSpec("zscore_60", 61, "mean_reversion", "z-score of price vs 60d mean"),
    # technical indicators
    FeatureSpec("rsi_14", 15, "technical", "Relative Strength Index, 14d"),
    FeatureSpec("macd_hist", 35, "technical", "MACD histogram (12,26,9)"),
    FeatureSpec("bb_pct_b_20", 21, "technical", "Bollinger %B, 20d"),
    FeatureSpec("bb_width_20", 21, "technical", "Bollinger bandwidth, 20d"),
    FeatureSpec("atr_14", 15, "technical", "Average True Range, 14d"),
    # shape of the distribution
    FeatureSpec("skew_20", 21, "distribution", "rolling return skewness, 20d"),
    FeatureSpec("kurt_20", 21, "distribution", "rolling return kurtosis, 20d"),
    # trend shape
    FeatureSpec("slope_10", 11, "trend", "OLS slope of log price, 10d"),
    FeatureSpec("slope_20", 21, "trend", "OLS slope of log price, 20d"),
    # drawdown
    FeatureSpec("drawdown_60", 61, "risk", "drawdown from 60d rolling max"),
    # calendar (known in advance for day T -> still only uses T's own label)
    FeatureSpec("dow_sin", 1, "calendar", "sine of day-of-week"),
    FeatureSpec("dow_cos", 1, "calendar", "cosine of day-of-week"),
    FeatureSpec("month_sin", 1, "calendar", "sine of month"),
    FeatureSpec("month_cos", 1, "calendar", "cosine of month"),
    # cross-pair (USD factor etc. — added by the cross-pair builder)
    FeatureSpec("usd_factor_20", 21, "cross_pair", "20d return of the USD basket factor"),
    FeatureSpec("rel_strength_20", 21, "cross_pair", "20d relative strength vs USD basket"),
    FeatureSpec("corr_usd_20", 21, "cross_pair", "20d rolling correlation with the USD factor"),
]

CORE_FEATURE_SET = FeatureSet(name=FEATURE_SET_NAME, version=FEATURE_SET_VERSION, specs=CORE_SPECS)


def get_feature_set(name: str = FEATURE_SET_NAME) -> FeatureSet:
    if name != FEATURE_SET_NAME:
        raise ValueError(f"Unknown feature set: {name!r}")
    return CORE_FEATURE_SET
