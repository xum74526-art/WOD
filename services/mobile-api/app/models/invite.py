from datetime import datetime

from sqlalchemy import String, DateTime, Integer, Numeric, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


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

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    inviter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)  # 邀请人
    invitee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)  # 被邀请人
    invitee_phone: Mapped[str] = mapped_column(String(16))  # 脱敏手机号
    status: Mapped[str] = mapped_column(String(16), default="registered")  # registered/ordered/rewarded
    reward_amount: Mapped[float] = mapped_column(default=0)  # 邀请人获得的卡时奖励
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 首单完成时间
    rewarded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 奖励发放时间
