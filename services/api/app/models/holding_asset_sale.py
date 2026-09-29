from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HoldingAssetSale(Base):
    """Immutable audit fact for a platform CNY wallet buyback.

    A held asset can be sold exactly once.  The split fields preserve the
    original cash/promotional classification so a resale can never turn
    promotional reward balance into cash-backed consumption.
    """

    __tablename__ = "holding_asset_sales"
    __table_args__ = (
        UniqueConstraint("asset_id", name="uq_holding_asset_sale_asset"),
        UniqueConstraint("user_id", "client_request_id", name="uq_holding_asset_sale_request"),
        CheckConstraint(
            "sell_value_card_hours = cash_value_card_hours + promotional_value_card_hours",
            name="ck_holding_asset_sale_conservation",
        ),
        CheckConstraint(
            "buy_value_card_hours >= 0 AND sell_value_card_hours >= 0 "
            "AND cash_value_card_hours >= 0 AND promotional_value_card_hours >= 0",
            name="ck_holding_asset_sale_nonnegative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_key: Mapped[str] = mapped_column(String(128), unique=True)
    client_request_id: Mapped[str] = mapped_column(String(64))
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    purchase_hours: Mapped[int] = mapped_column(Integer)
    market_source: Mapped[str] = mapped_column(String(24))
    unit_price_cny_per_gpu_hour: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    unit_price_card_hours_per_gpu_hour: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    buy_value_card_hours: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    sell_value_card_hours: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    pnl_card_hours: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    cash_value_card_hours: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    promotional_value_card_hours: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    price_observed_at: Mapped[datetime] = mapped_column(DateTime)
    policy_version: Mapped[str] = mapped_column(String(32))
    policy_snapshot: Mapped[dict] = mapped_column(JSON)
    settled_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
