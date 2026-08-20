from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


RegionCode = Annotated[str, Field(min_length=2, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")]
RequestType = Literal["cloud_compute", "offline_device"]
Visibility = Literal["public", "invited", "private"]
DeliveryMode = Literal["remote", "dedicated", "negotiable"]
ContactVisibility = Literal["quote_submitted", "shortlisted", "accepted", "manual_grant"]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CloudComputeRequestDetailIn(InputModel):
    min_cpu_cores: int | None = Field(default=None, ge=1, le=4096)
    min_ram_gb: int | None = Field(default=None, ge=1, le=1_048_576)
    min_disk_gb: int | None = Field(default=None, ge=1, le=10_000_000)
    min_download_mbps: int | None = Field(default=None, ge=1, le=10_000_000)
    public_ip_required: bool = False
    container_image: str | None = Field(default=None, max_length=255)
    software_stack: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(
        default_factory=list,
        max_length=20,
    )
    special_requirements: str | None = Field(default=None, max_length=3000)


class BuyRequestContactIn(InputModel):
    contact_name: str = Field(min_length=2, max_length=64)
    contact_phone: str | None = Field(default=None, min_length=6, max_length=32)
    contact_email: EmailStr | None = None
    contact_wechat: str | None = Field(default=None, min_length=2, max_length=64)
    address: str | None = Field(default=None, min_length=2, max_length=500)
    visible_after: ContactVisibility = "accepted"


class BuyRequestCreateIn(InputModel):
    request_type: RequestType = "cloud_compute"
    title: str = Field(min_length=3, max_length=160)
    visibility: Visibility = "public"
    gpu_model: str = Field(min_length=2, max_length=64)
    min_gpu_memory_gb: int | None = Field(default=None, ge=1, le=1_048_576)
    gpu_quantity: int = Field(ge=1, le=10_000)
    region_codes: list[RegionCode] = Field(default_factory=list, max_length=20)
    delivery_mode: DeliveryMode = "remote"
    budget_amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=6)
    budget_currency: str = Field(default="USD", min_length=3, max_length=8, pattern=r"^[A-Z0-9_]+$")
    budget_unit: str = Field(default="gpu_hour", min_length=2, max_length=32, pattern=r"^[a-z0-9_]+$")
    quote_deadline_at: datetime
    expected_start_at: datetime | None = None
    expected_duration_hours: int | None = Field(default=None, ge=1, le=10_000_000)
    requirements: str = Field(default="", max_length=5000)
    cloud_details: CloudComputeRequestDetailIn | None = None
    contact: BuyRequestContactIn | None = None


class BuyRequestUpdateIn(InputModel):
    version: int = Field(ge=1)
    request_type: RequestType | None = None
    title: str | None = Field(default=None, min_length=3, max_length=160)
    visibility: Visibility | None = None
    gpu_model: str | None = Field(default=None, min_length=2, max_length=64)
    min_gpu_memory_gb: int | None = Field(default=None, ge=1, le=1_048_576)
    gpu_quantity: int | None = Field(default=None, ge=1, le=10_000)
    region_codes: list[RegionCode] | None = Field(default=None, max_length=20)
    delivery_mode: DeliveryMode | None = None
    budget_amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=6)
    budget_currency: str | None = Field(default=None, min_length=3, max_length=8, pattern=r"^[A-Z0-9_]+$")
    budget_unit: str | None = Field(default=None, min_length=2, max_length=32, pattern=r"^[a-z0-9_]+$")
    quote_deadline_at: datetime | None = None
    expected_start_at: datetime | None = None
    expected_duration_hours: int | None = Field(default=None, ge=1, le=10_000_000)
    requirements: str | None = Field(default=None, max_length=5000)
    cloud_details: CloudComputeRequestDetailIn | None = None
    contact: BuyRequestContactIn | None = None


class VersionedActionIn(InputModel):
    version: int = Field(ge=1)


class CloseBuyRequestIn(VersionedActionIn):
    reason: str = Field(min_length=2, max_length=500)


class ExtendBuyRequestIn(VersionedActionIn):
    quote_deadline_at: datetime
