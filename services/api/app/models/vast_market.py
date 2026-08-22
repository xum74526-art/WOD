from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class VastOffer(Base):
    """Latest Vast.ai offer state used as reference data, never sellable stock."""

    __tablename__ = "vast_offers"
    __table_args__ = (
        UniqueConstraint("billing_mode", "external_offer_id", name="uq_vast_offer_mode_id"),
        Index("ix_vast_offer_selection", "active", "billing_mode", "gpu_model", "gpu_variant"),
        Index("ix_vast_offer_freshness", "billing_mode", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    external_offer_id: Mapped[int] = mapped_column(Integer)
    billing_mode: Mapped[str] = mapped_column(String(24), index=True)
    gpu_name: Mapped[str] = mapped_column(String(96))
    gpu_model: Mapped[str] = mapped_column(String(64), index=True)
    gpu_variant: Mapped[str] = mapped_column(String(64), default="", index=True)
    num_gpus: Mapped[int] = mapped_column(Integer, default=1)
    gpu_ram_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gpu_total_ram_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    compute_capability: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cuda_version: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    gpu_memory_bandwidth: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    nvlink_bandwidth: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    total_flops: Mapped[Decimal | None] = mapped_column(Numeric(24, 6), nullable=True)
    cpu_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    cpu_arch: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cpu_cores: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cpu_ram_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    disk_space_gb: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    disk_bandwidth_mbps: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    internet_down_mbps: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    internet_up_mbps: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    geolocation: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    hosting_type: Mapped[str | None] = mapped_column(String(48), nullable=True)
    verification: Mapped[str | None] = mapped_column(String(48), nullable=True)
    reliability: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    duration_days: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    compute_price_hourly: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    total_price_hourly: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    per_gpu_compute_price_hourly: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    per_gpu_total_price_hourly: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    minimum_bid_hourly: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    storage_price_gb_month: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    internet_down_price_tb: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    internet_up_price_tb: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    discount_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    rentable: Mapped[bool] = mapped_column(Boolean, default=True)
    rented: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    raw_hash: Mapped[str] = mapped_column(String(64), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class VastPriceSnapshot(Base):
    """Per-GPU USD price distribution derived from one complete search result."""

    __tablename__ = "vast_price_snapshots"
    __table_args__ = (
        UniqueConstraint("signature", name="uq_vast_price_snapshot_signature"),
        Index(
            "ix_vast_price_snapshot_series",
            "gpu_model", "gpu_variant", "billing_mode", "observed_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    gpu_model: Mapped[str] = mapped_column(String(64), index=True)
    gpu_variant: Mapped[str] = mapped_column(String(64), default="", index=True)
    billing_mode: Mapped[str] = mapped_column(String(24), index=True)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    min_compute_price: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    median_compute_price: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    max_compute_price: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    min_total_price: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    median_total_price: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    max_total_price: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    sample_count: Mapped[int] = mapped_column(Integer)
    available_gpu_count: Mapped[int] = mapped_column(Integer)
    signature: Mapped[str] = mapped_column(String(64), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class VastSyncStatus(Base):
    __tablename__ = "vast_sync_status"

    billing_mode: Mapped[str] = mapped_column(String(24), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    refresh_seconds: Mapped[int] = mapped_column(Integer, default=600)
    offer_count: Mapped[int] = mapped_column(Integer, default=0)
    active_offer_count: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rate_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rate_limit_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rate_limit_reset_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_url: Mapped[str] = mapped_column(String(255), default="https://console.vast.ai/api/v0/bundles/")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class MarketIngestionBatch(Base):
    """Idempotency and audit record for one internal collector submission."""

    __tablename__ = "market_ingestion_batches"
    __table_args__ = (
        UniqueConstraint("source", "dataset", "batch_id", name="uq_market_ingestion_batch"),
        Index("ix_market_ingestion_recent", "source", "dataset", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32))
    dataset: Mapped[str] = mapped_column(String(48))
    batch_id: Mapped[str] = mapped_column(String(128))
    schema_version: Mapped[str] = mapped_column(String(16))
    billing_mode: Mapped[str] = mapped_column(String(24))
    sync_mode: Mapped[str] = mapped_column(String(24))
    payload_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="running")
    received_count: Mapped[int] = mapped_column(Integer, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    stale_count: Mapped[int] = mapped_column(Integer, default=0)
    deleted_count: Mapped[int] = mapped_column(Integer, default=0)
    snapshot_count: Mapped[int] = mapped_column(Integer, default=0)
    observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
