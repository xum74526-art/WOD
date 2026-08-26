from datetime import datetime
from decimal import Decimal

from sqlalchemy import String, DateTime, Numeric, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Wallet(Base):
    __tablename__ = "wallets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    # Card-hours are quoted to six decimal places (for example
    # CNY 0.01 / 1.002 = 0.009980 CH).  Four decimal places silently rounded
    # that value to 0.0100 and broke conservation between a payment order and
    # the wallet/ledger credit.
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    frozen: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    # Promotional card-hours are a strict subset of ``balance``/``frozen``.
    # They may be spent inside WOD, but never withdrawn and never counted as
    # cash-backed consumption for invitation commission.
    promotional_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0"), server_default="0"
    )
    promotional_frozen: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0"), server_default="0"
    )
    # Only funds backed by an auditable, settled earnings source may be moved
    # into this bucket.  Historical wallets, recharge card-hours, test rebates,
    # and synthetic revenue migrate as zero-withdrawable by design.
    withdrawable_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0")
    )
    withdraw_frozen: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
