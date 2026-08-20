from pydantic import BaseModel, Field

from app.buy_request_schemas import InputModel, VersionedActionIn


class SshKeyCreateIn(InputModel):
    name: str = Field(min_length=2, max_length=64)
    public_key: str = Field(min_length=32, max_length=16384)


class SshKeyUpdateIn(VersionedActionIn):
    name: str = Field(min_length=2, max_length=64)


class DirectServerRentalIn(BaseModel):
    product_id: int = Field(gt=0)
    ssh_key_id: int = Field(gt=0)
    duration_hours: int = Field(ge=1, le=8760)
    payment_channel: str | None = Field(default=None, pattern=r"^[a-z0-9_]{2,32}$")


class LeaseRenewIn(VersionedActionIn):
    duration_hours: int = Field(ge=1, le=8760)
    payment_channel: str | None = Field(default=None, pattern=r"^[a-z0-9_]{2,32}$")


class LeaseSweepIn(BaseModel):
    confirmation: str = Field(pattern=r"^PROCESS_DUE_LEASES$")


class RefundInitiateIn(VersionedActionIn):
    note: str | None = Field(default=None, max_length=500)


class LocalRefundCompleteIn(VersionedActionIn):
    provider_reference: str = Field(min_length=4, max_length=128)
    note: str | None = Field(default=None, max_length=500)
