from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(128))
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    title_en: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    type: Mapped[str] = mapped_column(String(32), default="system")  # major_announcement/system/order/device/revenue/wallet
    action_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Business event key used by the periodic synchronizer. It is scoped by
    # user_id, so the same order state remains isolated for every recipient.
    dedupe_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (UniqueConstraint("user_id", name="uq_notification_preferences_user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    order_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    device_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    revenue_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    wallet_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    system_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class NotificationBroadcast(Base):
    """Durable audit/idempotency boundary for an administrator announcement.

    The broadcast row is kept separately from the recipient inbox rows so an
    administrator can safely retry a timed-out request without creating a
    second copy for every account.  ``client_request_id`` is supplied by the
    control plane and is intentionally unique across administrators.
    """

    __tablename__ = "notification_broadcasts"
    __table_args__ = (
        UniqueConstraint(
            "client_request_id",
            name="uq_notification_broadcast_client_request",
        ),
        Index("ix_notification_broadcast_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_request_id: Mapped[str] = mapped_column(String(64), index=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(128))
    content: Mapped[str] = mapped_column(Text)
    title_en: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    notification_type: Mapped[str] = mapped_column(String(32), default="system")
    action_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    audience: Mapped[str] = mapped_column(String(32), default="all_active")
    status: Mapped[str] = mapped_column(String(24), default="completed", index=True)
    recipient_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
