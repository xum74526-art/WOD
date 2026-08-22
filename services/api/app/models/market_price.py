from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MarketPriceSnapshot(Base):
    """A real, source-attributed aggregate of currently rentable GPU offers."""

    __tablename__ = "market_price_snapshots"
    __table_args__ = (
        Index(
            "ix_market_snapshot_latest",
            "source", "gpu_model", "gpu_variant", "billing_mode", "observed_at",
        ),
        Index(
            "ix_market_snapshot_history",
            "source", "observed_at", "gpu_model", "gpu_variant", "billing_mode",
        ),
        Index(
            "ix_market_snapshot_candles",
            "gpu_model", "gpu_variant", "billing_mode", "source", "observed_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(24), index=True)
    gpu_model: Mapped[str] = mapped_column(String(64), index=True)
    gpu_variant: Mapped[str] = mapped_column(String(64), default="", index=True)
    billing_mode: Mapped[str] = mapped_column(String(24), default="ondemand", index=True)
    currency: Mapped[str] = mapped_column(String(8))
    min_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    p25_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    median_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    p75_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    max_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    min_price_cny: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    median_price_cny: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    max_price_cny: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    available_gpu_count: Mapped[int] = mapped_column(Integer, default=0)
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    fx_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fx_date: Mapped[str | None] = mapped_column(String(16), nullable=True)
    data_quality: Mapped[str] = mapped_column(String(24), default="verified")
    signature: Mapped[str] = mapped_column(String(64), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MarketSourceStatus(Base):
    __tablename__ = "market_source_status"

    source: Mapped[str] = mapped_column(String(24), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    refresh_seconds: Mapped[int] = mapped_column(Integer, default=60)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class MarketHistoryPoint(Base):
    """An attributed historical market-index observation.

    Historical imports intentionally live outside ``market_price_snapshots``:
    a licensed third-party archive must never masquerade as a quote collected
    directly by WOD. Prices are normalized to one GPU-hour before storage.
    """

    __tablename__ = "market_history_points"
    __table_args__ = (
        UniqueConstraint(
            "dataset_source", "upstream_provider", "gpu_model", "gpu_variant",
            "billing_mode", "observed_at", "index_method",
            name="uq_market_history_observation",
        ),
        Index(
            "ix_market_history_selection",
            "upstream_provider", "gpu_model", "gpu_variant", "billing_mode",
            "dataset_source", "observed_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dataset_source: Mapped[str] = mapped_column(String(48), index=True)
    upstream_provider: Mapped[str] = mapped_column(String(24), index=True)
    gpu_model: Mapped[str] = mapped_column(String(64), index=True)
    gpu_variant: Mapped[str] = mapped_column(String(64), default="", index=True)
    billing_mode: Mapped[str] = mapped_column(String(24), default="ondemand", index=True)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    low_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    representative_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    high_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    low_price_cny: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    representative_price_cny: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    high_price_cny: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    available_gpu_count: Mapped[int] = mapped_column(Integer, default=0)
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    fx_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fx_date: Mapped[str | None] = mapped_column(String(16), nullable=True)
    data_quality: Mapped[str] = mapped_column(String(32))
    index_method: Mapped[str] = mapped_column(String(64))
    source_url: Mapped[str] = mapped_column(Text)
    license_name: Mapped[str] = mapped_column(String(64))
    dataset_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signature: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MarketHistorySourceStatus(Base):
    __tablename__ = "market_history_source_status"

    source: Mapped[str] = mapped_column(String(48), primary_key=True)
    upstream_provider: Mapped[str] = mapped_column(String(24), default="vast")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    refresh_seconds: Mapped[int] = mapped_column(Integer, default=21600)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dataset_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    license_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
