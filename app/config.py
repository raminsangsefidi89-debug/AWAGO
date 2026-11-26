"""Application configuration via pydantic-settings, organized by domain.

All existing v1 environment variable names keep working unchanged; the
domain classes below group related settings for readability and hashing.
Secrets are redacted by :meth:`Settings.redacted_dict`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root (…/awago) — app/ is one level below it.
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

VALID_DATA_MODES = ("demo", "auto", "live")
VALID_PROVIDERS = ("frankfurter", "demo", "csv_import")
VALID_PROFILES = ("lite", "full")

SECRET_MARKERS = ("TOKEN", "KEY", "SECRET", "PASSWORD")


class _BaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


class ServerSettings(_BaseSettings):
    """HTTP server, browser and security settings."""

    app_name: str = "AWAGO"
    app_version: str = "2.0.0"
    host: str = "127.0.0.1"
    port: int = 8000
    open_browser: bool = True
    api_token: str = ""
    jobs_max_workers: int = 2
    request_max_body_kb: int = 512


class StorageSettings(_BaseSettings):
    """Database and local storage paths."""

    database_url: str = ""

    @property
    def effective_database_url(self) -> str:
        """Return a concrete SQLAlchemy URL, defaulting to SQLite under data/."""
        if self.database_url:
            url = self.database_url
            if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
                rel = url[len("sqlite:///") :]
                if rel != ":memory:":
                    return "sqlite:///" + str((BASE_DIR / rel).resolve())
            return url
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        return "sqlite:///" + str((DATA_DIR / "awago.db").resolve())

    @property
    def series_dir(self) -> Path:
        """Columnar (Parquet) series store."""
        d = DATA_DIR / "series"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def models_dir(self) -> Path:
        d = DATA_DIR / "models"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def logs_dir(self) -> Path:
        d = DATA_DIR / "logs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def experiments_dir(self) -> Path:
        d = DATA_DIR / "experiments"
        d.mkdir(parents=True, exist_ok=True)
        return d


class DataSettings(_BaseSettings):
    """Market-data providers, demo generation and quality controls."""

    data_mode: str = "demo"
    data_provider: str = "frankfurter"
    fallback_to_demo: bool = True
    frankfurter_base_url: str = "https://api.frankfurter.dev/v1"
    http_timeout_seconds: float = 15.0
    http_retries: int = 3
    provider_cache_ttl_seconds: int = 900
    circuit_breaker_failures: int = 3
    circuit_breaker_reset_seconds: float = 60.0
    default_pairs: str = (
        "EUR/USD,GBP/USD,USD/JPY,USD/CHF,AUD/USD,USD/CAD,NZD/USD,EUR/GBP,EUR/JPY,USD/TRY"
    )
    history_days: int = 1095
    demo_seed: int = 42
    csv_import_dir: str = str(DATA_DIR / "imports")

    @field_validator("data_mode")
    @classmethod
    def _validate_data_mode(cls, v: str) -> str:
        v = (v or "demo").strip().lower()
        if v not in VALID_DATA_MODES:
            raise ValueError(f"DATA_MODE must be one of {VALID_DATA_MODES}, got {v!r}")
        return v

    @field_validator("data_provider")
    @classmethod
    def _validate_provider(cls, v: str) -> str:
        v = (v or "demo").strip().lower()
        if v not in VALID_PROVIDERS:
            raise ValueError(f"DATA_PROVIDER must be one of {VALID_PROVIDERS}, got {v!r}")
        return v

    @property
    def pairs_list(self) -> list[str]:
        return [p.strip().upper() for p in self.default_pairs.split(",") if p.strip()]


class ModelSettings(_BaseSettings):
    """Forecasting, evaluation and experiment settings."""

    forecast_horizons: str = "1,7,30"
    prediction_interval_level: float = 0.90
    auto_train_on_seed: bool = True
    profile: str = "lite"
    feature_set_version: str = "v2"
    walkforward_splits: int = 5
    walkforward_splits_quick: int = 3
    embargo_bars: int = 5
    holdout_days: int = 120
    hpo_trials: int = 20
    model_time_budget_seconds: int = 300

    @field_validator("prediction_interval_level")
    @classmethod
    def _validate_interval_level(cls, v: float) -> float:
        if not 0.5 <= v < 1.0:
            raise ValueError("PREDICTION_INTERVAL_LEVEL must be in [0.5, 1.0)")
        return v

    @field_validator("profile")
    @classmethod
    def _validate_profile(cls, v: str) -> str:
        v = (v or "lite").strip().lower()
        if v not in VALID_PROFILES:
            raise ValueError(f"PROFILE must be one of {VALID_PROFILES}, got {v!r}")
        return v

    @property
    def horizons_list(self) -> list[int]:
        hs = sorted({int(h.strip()) for h in self.forecast_horizons.split(",") if h.strip()})
        if not hs or any(h <= 0 or h > 365 for h in hs):
            raise ValueError("FORECAST_HORIZONS must be integers in 1..365")
        return hs


class SchedulerSettings(_BaseSettings):
    """Local background scheduler (disabled by default; never blocks startup)."""

    scheduler_enabled: bool = False
    scheduler_interval_minutes: int = 60
    scheduler_retrain: bool = False


class LLMSettings(_BaseSettings):
    """Optional OpenAI-compatible explainer (hidden when unconfigured)."""

    llm_base_url: str = ""
    llm_model: str = ""
    llm_api_key: str = ""


class Settings(
    ServerSettings, StorageSettings, DataSettings, ModelSettings, SchedulerSettings, LLMSettings
):
    """All runtime configuration. Environment variables override the defaults.

    Domain classes are composed in; attribute access stays flat so v1 code
    (``settings.data_mode``, ``settings.models_dir``, ...) keeps working.
    """

    log_level: str = "INFO"

    # ------------------------------------------------------------------
    def redacted_dict(self) -> dict[str, Any]:
        """Flat dict of all settings with secret-looking values redacted."""
        out: dict[str, Any] = {}
        for key, value in self.model_dump().items():
            if any(marker in key.upper() for marker in SECRET_MARKERS) and value:
                out[key] = "***REDACTED***"
            else:
                out[key] = value
        # derived / non-field values useful for debugging
        out["effective_database_url"] = self.effective_database_url
        return out

    def config_hash(self) -> str:
        """Stable hash of all non-secret settings (for reproducible run ids)."""
        import hashlib
        import json

        payload = {
            k: v
            for k, v in sorted(self.model_dump().items())
            if not any(marker in k.upper() for marker in SECRET_MARKERS)
        }
        blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()[:16]


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance (env + .env file)."""
    return Settings()
