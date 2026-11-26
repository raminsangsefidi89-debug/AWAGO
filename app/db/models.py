"""SQLAlchemy 2.x ORM models (typed, 2.0 style)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Timezone-aware UTC now."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Declarative base for all AWAGO models."""


class CurrencyPair(Base):
    """A currency pair managed by the application."""

    __tablename__ = "currency_pairs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    base: Mapped[str] = mapped_column(String(8), nullable=False)
    quote: Mapped[str] = mapped_column(String(8), nullable=False)
    display_name_fa: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    bars: Mapped[list["PriceBar"]] = relationship(back_populates="pair", cascade="all, delete-orphan")


class PriceBar(Base):
    """One daily OHLC bar for a pair from one data source.

    De-duplication: unique on (pair, timestamp, interval, data_source).
    ``data_source`` / ``is_demo`` keep demo and real data strictly separate.
    """

    __tablename__ = "price_bars"
    __table_args__ = (
        UniqueConstraint("pair_symbol", "timestamp", "interval", "data_source", name="uq_bar_identity"),
        Index("ix_price_bars_pair_ts", "pair_symbol", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pair_symbol: Mapped[str] = mapped_column(String(16), ForeignKey("currency_pairs.symbol"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    interval: Mapped[str] = mapped_column(String(8), nullable=False, default="1d")
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_source: Mapped[str] = mapped_column(String(32), nullable=False, default="demo")
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    pair: Mapped[CurrencyPair] = relationship(back_populates="bars")


class ModelArtifact(Base):
    """Metadata for one persisted trained model (joblib file on disk)."""

    __tablename__ = "model_artifacts"
    __table_args__ = (
        UniqueConstraint("pair_symbol", "horizon", "model_name", "data_source", name="uq_model_identity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pair_symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    horizon: Mapped[int] = mapped_column(Integer, nullable=False)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    train_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    train_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    n_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    features_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")
    data_source: Mapped[str] = mapped_column(String(32), nullable=False, default="demo")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    params_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class MetricRecord(Base):
    """Walk-forward evaluation metrics for one (pair, horizon, model)."""

    __tablename__ = "metric_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pair_symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    horizon: Mapped[int] = mapped_column(Integer, nullable=False)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    mae: Mapped[float] = mapped_column(Float, nullable=False)
    rmse: Mapped[float] = mapped_column(Float, nullable=False)
    smape: Mapped[float] = mapped_column(Float, nullable=False)
    directional_accuracy: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_mae: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_rmse: Mapped[float] = mapped_column(Float, nullable=False)
    beats_baseline: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    n_test: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    data_source: Mapped[str] = mapped_column(String(32), nullable=False, default="demo")
    details_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class JobRecord(Base):
    """An asynchronous job (data collection / model training)."""

    __tablename__ = "job_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    params_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    message: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    result_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
