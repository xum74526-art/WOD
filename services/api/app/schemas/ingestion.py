from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class MarketOfferRecord(BaseModel):
    external_id: int = Field(gt=0)
    gpu_name: str = Field(min_length=1, max_length=96)
    gpu_model: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z0-9]+$")
    gpu_variant: str = Field(default="", max_length=64)
    gpu_count: int = Field(ge=1, le=1024)
    gpu_ram_mb: int | None = Field(default=None, ge=0)
    gpu_total_ram_mb: int | None = Field(default=None, ge=0)
    compute_capability: int | None = Field(default=None, ge=0)
    cuda_version: Decimal | None = Field(default=None, ge=0)
    gpu_memory_bandwidth: Decimal | None = Field(default=None, ge=0)
    nvlink_bandwidth: Decimal | None = Field(default=None, ge=0)
    total_flops: Decimal | None = Field(default=None, ge=0)
    cpu_name: str | None = Field(default=None, max_length=160)
    cpu_arch: str | None = Field(default=None, max_length=32)
    cpu_cores: int | None = Field(default=None, ge=0)
    cpu_ram_mb: int | None = Field(default=None, ge=0)
    disk_space_gb: Decimal | None = Field(default=None, ge=0)
    disk_bandwidth_mbps: Decimal | None = Field(default=None, ge=0)
    internet_down_mbps: Decimal | None = Field(default=None, ge=0)
    internet_up_mbps: Decimal | None = Field(default=None, ge=0)
    region: str | None = Field(default=None, max_length=160)
    hosting_type: str | None = Field(default=None, max_length=48)
    verification: str | None = Field(default=None, max_length=48)
    reliability: Decimal | None = Field(default=None, ge=0, le=1)
    duration_days: Decimal | None = Field(default=None, ge=0)
    currency: Literal["USD"] = "USD"
    compute_price_hourly: Decimal = Field(ge=0)
    total_price_hourly: Decimal = Field(ge=0)
    per_gpu_compute_price_hourly: Decimal = Field(ge=0)
    per_gpu_total_price_hourly: Decimal = Field(ge=0)
    minimum_bid_hourly: Decimal | None = Field(default=None, ge=0)
    storage_price_gb_month: Decimal | None = Field(default=None, ge=0)
    internet_down_price_tb: Decimal | None = Field(default=None, ge=0)
    internet_up_price_tb: Decimal | None = Field(default=None, ge=0)
    discount_rate: Decimal | None = Field(default=None, ge=0, le=1)
    rentable: bool = True
    rented: bool = False

    @field_validator("gpu_name", "gpu_model", "gpu_variant", mode="before")
    @classmethod
    def strip_required_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class MarketOfferBatchIn(BaseModel):
    schema_version: Literal["1.0"]
    source: Literal["vast"]
    dataset: Literal["gpu_offers"]
    billing_mode: Literal["on-demand", "bid", "reserved"]
    batch_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    sync_mode: Literal["incremental", "snapshot"] = "incremental"
    observed_at: datetime
    refresh_seconds: int = Field(ge=60, le=86400)
    upstream_rate_limit: int | None = Field(default=None, ge=0)
    upstream_rate_limit_remaining: int | None = Field(default=None, ge=0)
    upstream_rate_limit_reset_at: datetime | None = None
    records: list[MarketOfferRecord] = Field(min_length=1, max_length=5000)


class MarketOfferBatchResult(BaseModel):
    batch_id: str
    duplicate: bool = False
    received: int
    accepted: int
    inserted: int
    updated: int
    rejected: int
    stale: int
    deleted: int
    snapshots: int


class MarketOfferBatchResponse(BaseModel):
    code: Literal[0] = 0
    msg: str = "ok"
    data: MarketOfferBatchResult
