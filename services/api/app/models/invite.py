from datetime import date, datetime

from sqlalchemy import Date, String, DateTime, Integer, Numeric, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


INVITE_CODE_PREFIX = "ZTW"


class InviteCode(Base):
    __tablename__ = "invite_codes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    invited_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class InviteRecord(Base):
    """邀请记录：邀请人与被邀请人的一对一关系"""
    __tablename__ = "invite_records"
    __table_args__ = (
        UniqueConstraint("invitee_id", name="uq_invite_record_invitee"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    inviter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)  # 邀请人
    invitee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)  # 被邀请人
    invitee_phone: Mapped[str] = mapped_column(String(16))  # 脱敏手机号
    status: Mapped[str] = mapped_column(String(16), default="registered")  # registered/ordered/rewarded
    reward_amount: Mapped[float] = mapped_column(default=0)  # 邀请人获得的卡时奖励
    created_platform: Mapped[str] = mapped_column(
        String(16), default="legacy", server_default="legacy", index=True
    )
    last_modified_platform: Mapped[str] = mapped_column(
        String(16), default="legacy", server_default="legacy"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 首单完成时间
    rewarded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 奖励发放时间
    # V1 columns above remain immutable historical facts. V2 relationships are
    # opt-in through a non-NULL policy version so an upgrade never grants a new
    # reward to an old V1 row.
    qualification_status: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )
    qualification_policy_version: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    identity_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    qualified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    qualification_day: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    daily_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qualification_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id"), nullable=True, index=True
    )
    qualification_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fixed_reward_accrual_id: Mapped[int | None] = mapped_column(
        ForeignKey("reward_accruals.id"), nullable=True
    )


class InviteDailyQuota(Base):
    """Serialized UTC+8 qualification slots for one inviter and business day."""

    __tablename__ = "invite_daily_quotas"
    __table_args__ = (
        UniqueConstraint("inviter_id", "business_day", name="uq_invite_daily_quota"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    inviter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    business_day: Mapped[date] = mapped_column(Date, index=True)
    used_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    policy_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
