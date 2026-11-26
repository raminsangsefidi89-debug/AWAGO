"""Application configuration via pydantic-settings (all values from env / .env)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root (…/awago) — app/ is one level below it.
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

VALID_DATA_MODES = ("demo", "auto", "live")
VALID_PROVIDERS = ("frankfurter", "demo")


class Settings(BaseSettings):
    """All runtime configuration. Environment variables override the defaults."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Server ---
    app_name: str = "AWAGO"
    app_version: str = "1.0.0"
    host: str = "127.0.0.1"
    port: int = 8000
    open_browser: bool = True

    # --- Database ---
    database_url: str = ""

    # --- Data sources ---
    data_mode: str = "demo"
    data_provider: str = "frankfurter"
    fallback_to_demo: bool = True
    frankfurter_base_url: str = "https://api.frankfurter.dev/v1"
    http_timeout_seconds: float = 15.0
    http_retries: int = 3

    # --- Market data ---
    default_pairs: str = (
        "EUR/USD,GBP/USD,USD/JPY,USD/CHF,AUD/USD,USD/CAD,"
        "NZD/USD,EUR/GBP,EUR/JPY,USD/TRY"
    )
    history_days: int = 1095
    demo_seed: int = 42

    # --- Forecasting ---
    forecast_horizons: str = "1,7,30"
    prediction_interval_level: float = 0.90
    auto_train_on_seed: bool = True

    # --- Security ---
    api_token: str = ""

    # --- Logging ---
    log_level: str = "INFO"
    log_dir: str = str(DATA_DIR / "logs")

    # Derived / validated helpers ---------------------------------

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
            raise ValueError(
                f"DATA_PROVIDER must be one of {VALID_PROVIDERS}, got {v!r}"
            )
        return v

    @field_validator("prediction_interval_level")
    @classmethod
    def _validate_interval_level(cls, v: float) -> float:
        if not 0.5 <= v < 1.0:
            raise ValueError("PREDICTION_INTERVAL_LEVEL must be in [0.5, 1.0)")
        return v

    @property
    def pairs_list(self) -> List[str]:
        pairs = [p.strip().upper() for p in self.default_pairs.split(",") if p.strip()]
        return pairs

    @property
    def horizons_list(self) -> List[int]:
        hs = sorted({int(h.strip()) for h in self.forecast_horizons.split(",") if h.strip()})
        if not hs or any(h <= 0 or h > 365 for h in hs):
            raise ValueError("FORECAST_HORIZONS must be integers in 1..365")
        return hs

    @property
    def effective_database_url(self) -> str:
        """Return a concrete SQLAlchemy URL, defaulting to SQLite under data/."""
        if self.database_url:
            url = self.database_url
            # Make relative sqlite paths absolute so the DB location is stable.
            if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
                rel = url[len("sqlite:///"):]
                if rel != ":memory:":
                    return "sqlite:///" + str((BASE_DIR / rel).resolve())
            return url
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        return "sqlite:///" + str((DATA_DIR / "awago.db").resolve())

    @property
    def models_dir(self) -> Path:
        d = DATA_DIR / "models"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def logs_dir(self) -> Path:
        d = Path(self.log_dir)
        d.mkdir(parents=True, exist_ok=True)
        return d


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance (env + .env file)."""
    return Settings()
