from datetime import datetime
from decimal import Decimal

from pydantic import Field

from app.buy_request_schemas import InputModel


class QuoteCreateIn(InputModel):
    resource_id: int | None = Field(default=None, ge=1)
    price_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=6)
    price_currency: str = Field(min_length=3, max_length=8, pattern=r"^[A-Z0-9_]+$")
    price_unit: str = Field(min_length=2, max_length=32, pattern=r"^[a-z0-9_]+$")
    available_quantity: int = Field(ge=1, le=10_000)
    delivery_time_hours: int | None = Field(default=None, ge=0, le=10_000_000)
    valid_until: datetime
    service_description: str = Field(default="", max_length=5000)


class QuoteUpdateIn(InputModel):
    version: int = Field(ge=1)
    resource_id: int | None = Field(default=None, ge=1)
    price_amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=6)
    price_currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=8,
        pattern=r"^[A-Z0-9_]+$",
    )
    price_unit: str | None = Field(
        default=None,
        min_length=2,
        max_length=32,
        pattern=r"^[a-z0-9_]+$",
    )
    available_quantity: int | None = Field(default=None, ge=1, le=10_000)
    delivery_time_hours: int | None = Field(default=None, ge=0, le=10_000_000)
    valid_until: datetime | None = None
    service_description: str | None = Field(default=None, max_length=5000)


class QuoteVersionedActionIn(InputModel):
    version: int = Field(ge=1)


class QuoteWithdrawIn(QuoteVersionedActionIn):
    reason: str | None = Field(default=None, max_length=500)


class QuoteDecisionIn(InputModel):
    quote_version: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=1000)


class QuoteAcceptIn(QuoteDecisionIn):
    request_version: int = Field(ge=1)
