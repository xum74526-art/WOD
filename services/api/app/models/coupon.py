from datetime import datetime
from decimal import Decimal

from sqlalchemy import String, DateTime, Numeric, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Coupon(Base):
    __tablename__ = "coupons"
    __table_args__ = (
        UniqueConstraint("user_id", "campaign_id", name="uq_coupons_user_campaign"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("coupon_campaigns.id"), nullable=True, index=True,
    )
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id"), nullable=True, index=True,
    )
    name: Mapped[str] = mapped_column(String(64))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))  # 抵扣金额（CNY）
    min_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))  # 满减门槛
    status: Mapped[str] = mapped_column(String(16), default="available", index=True)  # available/used/expired
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    used_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id"), nullable=True, index=True,
    )
    created_platform: Mapped[str] = mapped_column(
        String(16), default="legacy", server_default="legacy",
    )
    last_modified_platform: Mapped[str] = mapped_column(
        String(16), default="legacy", server_default="legacy",
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CouponCampaign(Base):
    """A bounded redemption campaign; the plaintext code is never persisted."""

    __tablename__ = "coupon_campaigns"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    code_hint: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(64))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    min_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id"), nullable=True, index=True,
    )
    max_redemptions: Mapped[int] = mapped_column(Integer)
    redeemed_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    coupon_ttl_days: Mapped[int] = mapped_column(Integer, default=30, server_default="30")
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    last_modified_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_platform: Mapped[str] = mapped_column(
        String(16), default="admin", server_default="admin",
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )
