from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DisplayExchangeRate(Base):
    """Durable daily reference rate used only for localized presentation.

    The account ledger and payment provider continue to settle in CNY.  These
    rows preserve the dated CNY -> quote-currency reference values so every
    client receives one server-owned conversion instead of inventing rates.
    """

    __tablename__ = "display_exchange_rates"
    __table_args__ = (
        UniqueConstraint(
            "base_currency",
            "quote_currency",
            "reference_date",
            name="uq_display_exchange_rate_daily_pair",
        ),
        Index(
            "ix_display_exchange_rate_latest",
            "base_currency",
            "quote_currency",
            "reference_date",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    base_currency: Mapped[str] = mapped_column(String(3), default="CNY")
    quote_currency: Mapped[str] = mapped_column(String(3))
    rate_per_base: Mapped[Decimal] = mapped_column(Numeric(24, 12))
    source: Mapped[str] = mapped_column(String(32))
    reference_date: Mapped[date] = mapped_column(Date)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
