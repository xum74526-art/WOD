from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.buy_request_schemas import InputModel, VersionedActionIn


class ResourceCreateIn(InputModel):
    name: str = Field(min_length=3, max_length=128)
    gpu_model: str = Field(min_length=2, max_length=64)
    gpu_memory_gb: int = Field(ge=1, le=1_048_576)
    region: str = Field(min_length=2, max_length=64)
    cpu_cores: int | None = Field(default=None, ge=1, le=4096)
    ram_gb: int | None = Field(default=None, ge=1, le=1_048_576)
    disk_gb: int | None = Field(default=None, ge=1, le=10_000_000)
    bandwidth_mbps: int | None = Field(default=None, ge=1, le=10_000_000)
    image_url: str | None = Field(default=None, max_length=2048)
    description: str = Field(default="", max_length=5000)
    price_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=6)
    price_currency: Literal["CNY"] = "CNY"
    price_unit: Literal["server_hour"] = "server_hour"
    total_quantity: Literal[1] = 1
    public_host: str = Field(default="127.0.0.1", min_length=1, max_length=255)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    ssh_username: str = Field(default="kai", min_length=1, max_length=32, pattern=r"^[a-z_][a-z0-9_-]*$")
    agent_mode: str = Field(default="mtls", pattern=r"^(local_simulator|mtls)$")


class ResourceUpdateIn(InputModel):
    version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=3, max_length=128)
    gpu_model: str | None = Field(default=None, min_length=2, max_length=64)
    gpu_memory_gb: int | None = Field(default=None, ge=1, le=1_048_576)
    region: str | None = Field(default=None, min_length=2, max_length=64)
    cpu_cores: int | None = Field(default=None, ge=1, le=4096)
    ram_gb: int | None = Field(default=None, ge=1, le=1_048_576)
    disk_gb: int | None = Field(default=None, ge=1, le=10_000_000)
    bandwidth_mbps: int | None = Field(default=None, ge=1, le=10_000_000)
    image_url: str | None = Field(default=None, max_length=2048)
    description: str | None = Field(default=None, max_length=5000)
    price_amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=6)
    price_currency: Literal["CNY"] | None = None
    price_unit: Literal["server_hour"] | None = None
    total_quantity: Literal[1] | None = None
    public_host: str | None = Field(default=None, min_length=1, max_length=255)
    ssh_port: int | None = Field(default=None, ge=1, le=65535)
    ssh_username: str | None = Field(default=None, min_length=1, max_length=32, pattern=r"^[a-z_][a-z0-9_-]*$")
    agent_mode: str | None = Field(default=None, pattern=r"^(local_simulator|mtls)$")
    change_note: str | None = Field(default=None, max_length=500)


class ResourceReviewIn(VersionedActionIn):
    note: str | None = Field(default=None, max_length=1000)


class ResourceRejectIn(VersionedActionIn):
    note: str = Field(min_length=2, max_length=1000)


class ReservationReleaseIn(VersionedActionIn):
    reason: str = Field(min_length=2, max_length=500)
